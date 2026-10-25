"""Small, dependency-free resilience helpers for entity resolution."""

from __future__ import annotations

import importlib
import inspect
import json
import threading
import time
from typing import Any, Callable, Optional


def sanitize_name(name: str) -> str:
    """Remove ASCII control characters and validate a trimmed name."""
    cleaned = "".join(char for char in str(name) if ord(char) >= 32 and ord(char) != 127).strip()
    if not 1 <= len(cleaned) <= 120:
        raise ValueError("name must contain between 1 and 120 characters")
    return cleaned


def _search(qloo: Any, query: Any) -> Any:
    search = getattr(qloo, "search")
    try:
        signature = inspect.signature(search)
        params = signature.parameters
        if "query" in params or any(p.kind == p.VAR_KEYWORD for p in params.values()):
            return search(query=query)
    except (TypeError, ValueError):
        pass
    return search(query)


def _search_wrapper(qloo: Any) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        query = kwargs.get("query")
        if query is None:
            query = args[0] if args else kwargs.get("name", "")
        return _search(qloo, query)

    return wrapper


def _invoke(func: Callable[..., Any], qloo: Any, budget: Any, query: Any) -> Any:
    """Pass known arguments by name when possible, tolerating engine API variants."""
    context = {
        "qloo": qloo,
        "client": qloo,
        "budget": budget,
        "query": query,
        "name": query,
        "brand": query,
        "entity": query,
    }
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func(qloo, budget, query)

    parameters = signature.parameters
    if any(param.kind == param.VAR_KEYWORD for param in parameters.values()):
        return func(qloo=qloo, budget=budget, query=query)

    kwargs = {
        name: context[name]
        for name, param in parameters.items()
        if name in context and param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
    }
    required = [
        param for param in parameters.values()
        if param.default is param.empty
        and param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
    ]
    if all(param.name in kwargs for param in required):
        return func(**kwargs)
    return func(qloo, budget, query)


def _invoke_legacy(func: Callable[..., Any], query: Any, search_wrapper: Callable[..., Any]) -> Any:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func(query, search_wrapper)

    parameters = signature.parameters
    context = {
        "query": query,
        "name": query,
        "brand": query,
        "entity": query,
        "search": search_wrapper,
        "search_fn": search_wrapper,
        "searcher": search_wrapper,
        "search_func": search_wrapper,
        "qloo_search": search_wrapper,
    }
    if any(param.kind == param.VAR_KEYWORD for param in parameters.values()):
        return func(query=query, search=search_wrapper)
    kwargs = {
        name: context[name]
        for name, param in parameters.items()
        if name in context and param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
    }
    required = [
        param for param in parameters.values()
        if param.default is param.empty
        and param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
    ]
    if all(param.name in kwargs for param in required):
        return func(**kwargs)
    return func(query, search_wrapper)


def _candidate_names(results: Any) -> list[str]:
    if isinstance(results, dict):
        results = results.get("candidates", results.get("results", results.get("items", [])))
    if results is None or isinstance(results, (str, bytes)):
        return []
    try:
        items = list(results)
    except TypeError:
        items = [results]
    names: list[str] = []
    for item in items:
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = item.get("name") or item.get("brand") or item.get("display_name")
        else:
            name = getattr(item, "name", None) or getattr(item, "brand", None)
        if name is not None:
            names.append(str(name))
    return names


def _as_result(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, dict):
            return dict(converted)
    if value is None:
        return {}
    return {"result": value}


def resolve_with_robustness(
    qloo: Any,
    budget: Any,
    query: Any,
    sleep_fn: Callable[[float], Any] = time.sleep,
) -> dict[str, Any]:
    """Resolve an entity, retry transient failures, and return safe status data."""
    try:
        try:
            resolver_module = importlib.import_module("backend.src.engine.resolve")
            resolver = getattr(resolver_module, "run")
            invoke = lambda: _invoke(resolver, qloo, budget, query)
        except (ImportError, AttributeError):
            resolver_module = importlib.import_module("backend.methods.resolution")
            resolver = getattr(resolver_module, "resolve_entity")
            search_wrapper = _search_wrapper(qloo)
            invoke = lambda: _invoke_legacy(resolver, query, search_wrapper)
    except Exception:
        return {"status": "partial", "warnings": ["resolution_engine_unavailable"]}

    result: Any = None
    for attempt in range(3):
        try:
            result = invoke()
            break
        except Exception:
            if attempt < 2:
                try:
                    sleep_fn((0.1, 0.2)[attempt])
                except Exception:
                    pass
            else:
                return {
                    "status": "partial",
                    "warnings": ["qloo_transient_failure:2 retries"],
                }

    response = _as_result(result)
    candidates = response.get("candidates")
    status = str(response.get("status", "")).lower()
    if candidates is not None and len(candidates) > 1:
        response["status"] = "ambiguous"
        return response
    if (candidates is not None and len(candidates) == 0) or status in {
        "not_found", "not-found", "unknown", "unknown_brand"
    }:
        try:
            suggestions = _candidate_names(_search(qloo, query))
        except Exception:
            suggestions = []
        return {
            "status": "not_found",
            "error": "unknown brand",
            "suggestions": suggestions,
        }
    return response


class Cache:
    """Thread-safe in-memory TTL cache; disabled unless explicitly enabled."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self._entries: dict[Any, tuple[Any, float]] = {}

    def get(self, key: Any) -> Any:
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= now:
                del self._entries[key]
                return None
            return value

    def set(self, key: Any, value: Any, ttl_seconds: float = 86400) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._entries[key] = (value, time.monotonic() + max(0.0, ttl_seconds))


class RunLimiter:
    """Thread-safe counter limiting the number of concurrent active runs."""

    def __init__(self, max_runs: int = 3) -> None:
        self.max_runs = max_runs
        self._active = 0
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            if self._active >= self.max_runs:
                return False
            self._active += 1
            return True

    def release(self) -> None:
        with self._lock:
            if self._active > 0:
                self._active -= 1


class SafeLogger:
    """JSON-lines logger that redacts common credential fields and values."""

    def __init__(self, sink: Any = print) -> None:
        self.sink = sink

    @staticmethod
    def _redact(value: Any) -> Any:
        if isinstance(value, str):
            if "sk-" in value or "AKIA" in value:
                return "[REDACTED]"
            return value
        if isinstance(value, dict):
            return {
                key: ("[REDACTED]" if any(token in str(key).lower() for token in ("key", "token", "secret"))
                      else SafeLogger._redact(item))
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [SafeLogger._redact(item) for item in value]
        return value

    def _write(self, level: str, message: Any, fields: dict[str, Any]) -> None:
        payload: dict[str, Any] = {"level": level, "message": self._redact(message)}
        for key, value in fields.items():
            payload[key] = (
                "[REDACTED]"
                if any(token in str(key).lower() for token in ("key", "token", "secret"))
                else self._redact(value)
            )
        line = json.dumps(payload, ensure_ascii=False, default=str)
        if callable(self.sink):
            self.sink(line)
        else:
            self.sink.write(line + "\n")

    def info(self, message: Any, **fields: Any) -> None:
        self._write("info", message, fields)

    def warn(self, message: Any, **fields: Any) -> None:
        self._write("warn", message, fields)

    def error(self, message: Any, **fields: Any) -> None:
        self._write("error", message, fields)
