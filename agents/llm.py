"""Provider-neutral JSON LLM wrapper and deterministic narration helpers.

Configure XC_LLM_MODEL and optionally XC_LLM_PROVIDER. Credentials are read
only from OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY. Credentials
are never logged or included in results/errors. The stdlib HTTP transport
requires no provider SDK. Calls are non-streaming and return validated JSON.
"""
from __future__ import annotations
import http.client
import json
import os
import time
from collections.abc import Mapping
from typing import Any, Callable
from urllib.parse import quote

_KEYS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}

class LLMError(RuntimeError):
    """Safe base error for provider-neutral failures."""
class LLMUnavailableError(LLMError):
    """Model/provider credentials or transport are unavailable."""
class InvalidLLMOutput(LLMError, ValueError):
    """Response is not a JSON object matching the requested schema."""
class LLMRequestError(LLMError):
    """Request failed; message intentionally omits provider details."""

def _provider(model: str, configured: str | None = None) -> tuple[str | None, str]:
    provider, actual = (configured or "").strip().lower(), model.strip()
    if ":" in actual:
        prefix, rest = actual.split(":", 1)
        if prefix.lower() in _KEYS:
            provider, actual = provider or prefix.lower(), rest.strip()
    if not provider:
        lowered = actual.lower()
        if lowered.startswith(("gpt-", "o1", "o3", "o4")): provider = "openai"
        elif lowered.startswith("claude-"): provider = "anthropic"
        elif lowered.startswith("gemini-"): provider = "gemini"
    return provider or None, actual

def _http_transport(*, provider: str, model: str, api_key: str, prompt: str,
                    schema: Mapping[str, Any], connect_timeout: float,
                    read_timeout: float) -> Any:
    """Make one non-streaming HTTPS request using only Python's stdlib."""
    instruction = ("Return one JSON object conforming to this JSON Schema, with no markdown: "
                   + json.dumps(schema, ensure_ascii=False, separators=(",", ":")))
    if provider == "openai":
        host, path = "api.openai.com", "/v1/chat/completions"
        headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "system", "content": instruction},
                   {"role": "user", "content": prompt}], "response_format": {"type": "json_object"}, "stream": False}
        result_path = ("choices", 0, "message", "content")
    elif provider == "anthropic":
        host, path = "api.anthropic.com", "/v1/messages"
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        payload = {"model": model, "max_tokens": 4096, "system": instruction,
                   "messages": [{"role": "user", "content": prompt}]}
        result_path = ("content", 0, "text")
    elif provider == "gemini":
        host, path = "generativelanguage.googleapis.com", "/v1beta/models/" + quote(model, safe="") + ":generateContent"
        headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        payload = {"contents": [{"parts": [{"text": instruction + "\n\n" + prompt}]}],
                   "generationConfig": {"responseMimeType": "application/json"}}
        result_path = ("candidates", 0, "content", "parts", 0, "text")
    else:
        raise LLMUnavailableError("Unsupported or unrecognized LLM provider")
    connection = http.client.HTTPSConnection(host, timeout=connect_timeout)
    try:
        connection.connect()
        if connection.sock is not None: connection.sock.settimeout(read_timeout)
        connection.request("POST", path, body=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers)
        response = connection.getresponse()
        raw = response.read()
        if not 200 <= response.status < 300:
            raise LLMRequestError("Provider returned an unsuccessful HTTP status")
        value: Any = json.loads(raw.decode("utf-8"))
        for part in result_path: value = value[part]
        return value
    finally:
        connection.close()

def _matches(value: Any, kind: str) -> bool:
    if kind == "object": return isinstance(value, dict)
    if kind == "array": return isinstance(value, list)
    if kind == "string": return isinstance(value, str)
    if kind == "boolean": return isinstance(value, bool)
    if kind == "integer": return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number": return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "null": return value is None
    return True

def _structural_validate(value: Any, schema: Mapping[str, Any], at: str = "$") -> None:
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches(value, kind) for kind in expected): raise InvalidLLMOutput(f"Wrong type at {at}")
    elif isinstance(expected, str) and not _matches(value, expected): raise InvalidLLMOutput(f"Wrong type at {at}")
    if "const" in schema and value != schema["const"]: raise InvalidLLMOutput(f"Constant mismatch at {at}")
    if "enum" in schema and value not in schema["enum"]: raise InvalidLLMOutput(f"Value not allowed at {at}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value: raise InvalidLLMOutput(f"Missing required field at {at}")
        props = schema.get("properties", {})
        if isinstance(props, Mapping):
            for key, child in props.items():
                if key in value and isinstance(child, Mapping): _structural_validate(value[key], child, at + "." + key)
            if schema.get("additionalProperties") is False and any(k not in props for k in value):
                raise InvalidLLMOutput(f"Unexpected field at {at}")
    if isinstance(value, list):
        child = schema.get("items")
        if isinstance(child, Mapping):
            for i, item in enumerate(value): _structural_validate(item, child, f"{at}[{i}]")
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]: raise InvalidLLMOutput(f"Array too short at {at}")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]: raise InvalidLLMOutput(f"Array too long at {at}")
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]: raise InvalidLLMOutput(f"String too short at {at}")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]: raise InvalidLLMOutput(f"String too long at {at}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]: raise InvalidLLMOutput(f"Below minimum at {at}")
        if "maximum" in schema and value > schema["maximum"]: raise InvalidLLMOutput(f"Above maximum at {at}")

def validate_output(value: Any, schema: Mapping[str, Any]) -> dict[str, Any]:
    """Validate against JSON Schema, with structural fallback if jsonschema is absent."""
    if not isinstance(value, dict): raise InvalidLLMOutput("LLM output must be a JSON object")
    if not isinstance(schema, Mapping): raise InvalidLLMOutput("A JSON Schema mapping is required")
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        _structural_validate(value, schema)
    else:
        try: jsonschema.validate(instance=value, schema=schema)
        except Exception: raise InvalidLLMOutput("LLM output does not match the requested JSON Schema") from None
    return value

class LLMWrapper:
    """JSON completion wrapper. Injected transport receives keyword args provider, model,
    api_key, prompt, schema, connect_timeout, read_timeout, and returns a dict or JSON string.
    The key is supplied only to transport and never copied into output or errors.
    """
    def __init__(self, model: str | None = None, *, provider: str | None = None,
                 transport: Callable[..., Any] | None = None, sleep: Callable[[float], Any] | None = None) -> None:
        self.model = (model if model is not None else os.getenv("XC_LLM_MODEL", "")).strip()
        self.provider, self.api_model = _provider(self.model, provider if provider is not None else os.getenv("XC_LLM_PROVIDER"))
        self._transport, self._sleep = transport or _http_transport, sleep or time.sleep
    def _api_key(self) -> str | None:
        if self.provider not in _KEYS: return None
        return os.getenv(_KEYS[self.provider], "").strip() or None
    def is_configured(self) -> bool:
        """Require model and its recognized provider key."""
        return bool(self.model and self.api_model and self._api_key())
    def complete(self, prompt: str, schema: Mapping[str, Any]) -> dict[str, Any]:
        """Return validated JSON; 10-second connect/60-second read, at most 2 retries (1s, 2s)."""
        if not isinstance(prompt, str): raise TypeError("prompt must be a string")
        if not isinstance(schema, Mapping): raise InvalidLLMOutput("A JSON Schema mapping is required")
        key = self._api_key()
        if not self.model or not self.api_model or not key or self.provider not in _KEYS:
            raise LLMUnavailableError("LLM is not configured; set XC_LLM_MODEL and its provider key")
        last: Exception | None = None
        for attempt in range(3):
            try:
                raw = self._transport(provider=self.provider, model=self.api_model, api_key=key, prompt=prompt,
                    schema=schema, connect_timeout=10.0, read_timeout=60.0)
                if isinstance(raw, str):
                    try: raw = json.loads(raw)
                    except (TypeError, ValueError): raise InvalidLLMOutput("Provider response was not valid JSON") from None
                return validate_output(raw, schema)
            except LLMUnavailableError: raise
            except Exception as exc:
                last = exc
                if attempt < 2: self._sleep(2 ** attempt)
        if isinstance(last, InvalidLLMOutput): raise last
        raise LLMRequestError("LLM request failed after the permitted retries") from None
    def fallback_plan(self, phase_name: str, inputs: Any) -> dict[str, Any]:
        return fallback_plan(phase_name, inputs)
    def template_narrate(self, phase_name: str, evidence_refs: Any, summary: Any) -> str:
        return template_narrate(phase_name, evidence_refs, summary)

_PLAN_SCHEMA = {"type": "object", "required": ["phase_name", "steps", "summary", "summary_source"],
    "properties": {"phase_name": {"type": "string"}, "steps": {"type": "array"},
    "summary": {"type": "string"}, "summary_source": {"const": "template"}}, "additionalProperties": False}

def fallback_plan(phase_name: str, inputs: Any) -> dict[str, Any]:
    """Return a validated deterministic plan; all steps come from inputs, never an LLM."""
    source = inputs if isinstance(inputs, Mapping) else {}
    raw_steps = source.get("steps", [])
    steps = list(raw_steps) if isinstance(raw_steps, list) else []
    summary = source.get("summary", source.get("objective", "No deterministic summary provided."))
    plan = {"phase_name": str(phase_name), "steps": steps,
            "summary": summary if isinstance(summary, str) else str(summary), "summary_source": "template"}
    return validate_output(plan, _PLAN_SCHEMA)

def template_narrate(phase_name: str, evidence_refs: Any, summary: Any) -> str:
    """Create user-facing text only via this fixed template; no model text is streamed."""
    text = summary if isinstance(summary, str) else str(summary)
    refs = evidence_refs if isinstance(evidence_refs, (list, tuple)) else []
    output = f"{phase_name}: {text}"
    if refs: output += "\nEvidence: " + ", ".join(str(ref) for ref in refs)
    return output

def complete(prompt: str, schema: Mapping[str, Any]) -> dict[str, Any]:
    """Convenience completion using environment configuration."""
    return LLMWrapper().complete(prompt, schema)
