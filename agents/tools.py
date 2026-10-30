"""Agent tool specifications and guarded Qloo operation wrappers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    """Describe a callable agent tool and the JSON schema for its arguments."""

    name: str
    description: str
    json_schema: dict[str, Any]
    fn: Callable[..., dict[str, Any]]


def _cancelled(budget: Any, qloo: Any) -> bool:
    """Return whether either supplied context has requested cancellation."""
    for obj in (budget, qloo):
        if obj is None:
            continue
        for attr in ("is_cancelled", "cancelled", "is_canceled", "canceled"):
            value = getattr(obj, attr, False)
            try:
                value = value() if callable(value) else value
            except Exception:
                continue
            if value:
                return True
        for attr in ("cancel_event", "cancellation_event", "cancel_token"):
            token = getattr(obj, attr, None)
            is_set = getattr(token, "is_set", None)
            if callable(is_set):
                try:
                    if is_set():
                        return True
                except Exception:
                    pass
    return False


def _budget_exhausted(budget: Any, tool_name: str) -> bool:
    """Check common budget interfaces without requiring a particular bus type."""
    if budget is None:
        return False
    for attr in ("is_exhausted", "exhausted"):
        value = getattr(budget, attr, False)
        try:
            value = value(tool_name) if callable(value) else value
        except TypeError:
            try:
                value = value() if callable(value) else value
            except Exception:
                continue
        except Exception:
            continue
        if value:
            return True
    remaining = getattr(budget, "remaining", None)
    if isinstance(remaining, (int, float)) and remaining <= 0:
        return True
    if isinstance(remaining, dict) and remaining.get(tool_name, 1) <= 0:
        return True
    for attr in ("can_call", "has_budget", "allow_call", "check"):
        check = getattr(budget, attr, None)
        if callable(check):
            try:
                allowed = check(tool_name)
            except TypeError:
                try:
                    allowed = check()
                except Exception:
                    continue
            except Exception:
                continue
            if allowed is False:
                return True
    return False


def _emit(qloo: Any, event_name: str, payload: dict[str, Any]) -> None:
    """Emit an event when a compatible event bus is available; otherwise do nothing."""
    if qloo is None:
        return
    for attr in ("event_bus", "events", "bus"):
        bus = getattr(qloo, attr, None)
        if bus is None:
            continue
        for method_name in ("emit", "publish", "dispatch"):
            method = getattr(bus, method_name, None)
            if callable(method):
                try:
                    method(event_name, payload)
                    return
                except TypeError:
                    try:
                        method({"type": event_name, **payload})
                        return
                    except Exception:
                        pass
                except Exception:
                    pass


def _increment_call_count(qloo: Any) -> None:
    """Increment the Qloo client's successful-call counter when it is writable."""
    try:
        qloo.call_count = getattr(qloo, "call_count", 0) + 1
    except Exception:
        pass


def _result_count(result: Any) -> int:
    """Derive a non-sensitive result count for event telemetry."""
    if isinstance(result, (list, tuple, set)):
        return len(result)
    if isinstance(result, dict):
        count = result.get("count")
        if isinstance(count, int):
            return count
        for key in ("results", "items", "data"):
            value = result.get(key)
            if isinstance(value, (list, tuple, set)):
                return len(value)
    return 0


def _run_tool(qloo: Any, budget: Any, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Run a Qloo method behind cancellation, budget, event, and accounting guards."""
    if _cancelled(budget, qloo):
        return {"ok": False, "error": f"cancelled:{tool_name}", "warnings": []}
    if _budget_exhausted(budget, tool_name):
        return {"ok": False, "error": f"budget_exhausted:{tool_name}", "warnings": []}
    operation = getattr(qloo, tool_name, None) if qloo is not None else None
    if not callable(operation):
        return {"ok": False, "error": f"unavailable_operation:{tool_name}", "warnings": []}
    _emit(qloo, "tool.call", {"tool": tool_name, "parameters": sorted(params.keys())})
    try:
        result = operation(**params)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "warnings": []}
    _increment_call_count(qloo)
    _emit(qloo, "tool.result", {"tool": tool_name, "status": "ok", "count": _result_count(result)})
    return result if isinstance(result, dict) else {"ok": True, "data": result}


def qloo_search(qloo: Any, budget: Any, **kwargs: Any) -> dict[str, Any]:
    """Search Qloo entities by text and optional entity type."""
    return _run_tool(qloo, budget, "qloo_search", {"query": kwargs["query"], "entity_type": kwargs.get("entity_type")})


def qloo_affinity(qloo: Any, budget: Any, **kwargs: Any) -> dict[str, Any]:
    """Retrieve the affinity relationship between two Qloo entities."""
    return _run_tool(qloo, budget, "qloo_affinity", {"entity_a": kwargs["entity_a"], "entity_b": kwargs["entity_b"]})


def qloo_tags(qloo: Any, budget: Any, **kwargs: Any) -> dict[str, Any]:
    """Retrieve tags associated with a Qloo entity."""
    return _run_tool(qloo, budget, "qloo_tags", {"entity_id": kwargs["entity_id"]})


def qloo_demographics(qloo: Any, budget: Any, **kwargs: Any) -> dict[str, Any]:
    """Retrieve demographic insights for a Qloo entity."""
    return _run_tool(qloo, budget, "qloo_demographics", {"entity_id": kwargs["entity_id"]})


def qloo_heatmap(qloo: Any, budget: Any, **kwargs: Any) -> dict[str, Any]:
    """Retrieve Qloo affinity heatmap information for a region."""
    return _run_tool(qloo, budget, "qloo_heatmap", {"region": kwargs["region"]})


def qloo_trending(qloo: Any, budget: Any, **kwargs: Any) -> dict[str, Any]:
    """Retrieve trending Qloo insights, optionally scoped to a category."""
    return _run_tool(qloo, budget, "qloo_trending", {"category": kwargs.get("category")})


def verify_channel(qloo: Any, budget: Any, **kwargs: Any) -> dict[str, Any]:
    """Verify a channel using its name and contact with the configured provider."""
    return _run_tool(qloo, budget, "verify_channel", {"channel_name": kwargs["channel_name"], "contact": kwargs["contact"]})


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Build a closed JSON object schema shared by the registry entries."""
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


REGISTRY: dict[str, ToolSpec] = {
    "qloo_search": ToolSpec("qloo_search", "Search Qloo entities by query, optionally filtering by entity type.", _schema({"query": {"type": "string"}, "entity_type": {"type": ["string", "null"]}}, ["query", "entity_type"]), qloo_search),
    "qloo_affinity": ToolSpec("qloo_affinity", "Find affinity between two Qloo entities.", _schema({"entity_a": {"type": "string"}, "entity_b": {"type": "string"}}, ["entity_a", "entity_b"]), qloo_affinity),
    "qloo_tags": ToolSpec("qloo_tags", "Get the tags associated with a Qloo entity.", _schema({"entity_id": {"type": "string"}}, ["entity_id"]), qloo_tags),
    "qloo_demographics": ToolSpec("qloo_demographics", "Get demographic insights associated with a Qloo entity.", _schema({"entity_id": {"type": "string"}}, ["entity_id"]), qloo_demographics),
    "qloo_heatmap": ToolSpec("qloo_heatmap", "Get the Qloo affinity heatmap for a region.", _schema({"region": {"type": "string"}}, ["region"]), qloo_heatmap),
    "qloo_trending": ToolSpec("qloo_trending", "Get trending Qloo insights, optionally for a category.", _schema({"category": {"type": ["string", "null"]}}, ["category"]), qloo_trending),
    "verify_channel": ToolSpec("verify_channel", "Verify a channel using its name and contact details.", _schema({"channel_name": {"type": "string"}, "contact": {"type": "string"}}, ["channel_name", "contact"]), verify_channel),
}
