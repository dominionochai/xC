"""Optional MCP stdio adapter for the shared agents.tools registry.

This module requires the optional [mcp] extra to create/run a server; importing
it without that extra remains safe. Qloo clients are supplied by injection and
wrapped with a per-tool-call request budget before reaching ToolSpec.fn.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import warnings
from collections.abc import Mapping
from typing import Any, Callable

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]


class QlooBudgetExceeded(RuntimeError):
    """Raised when a tool exceeds its per-invocation Qloo call budget."""


class _CallBudget:
    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.limit:
            raise QlooBudgetExceeded("Qloo call budget exceeded for this tool invocation")
        self.used += 1


class _BudgetedQlooClient:
    """Proxy that bounds calls made through an injected Qloo client."""
    def __init__(self, client: Any, budget: _CallBudget) -> None:
        self._client, self._budget = client, budget

    def __getattr__(self, name: str) -> Any:
        member = getattr(self._client, name)
        if not callable(member):
            return member
        def budgeted(*args: Any, **kwargs: Any) -> Any:
            self._budget.consume()
            return member(*args, **kwargs)
        return budgeted


def _budget_limit() -> int:
    try:
        return max(1, int(os.getenv("XC_QLOO_MAX_CALLS_PER_TOOL", "5")))
    except (TypeError, ValueError):
        return 5


def _load_registry() -> Any:
    """Load the project's single shared ToolSpec registry lazily."""
    try:
        from agents.tools import registry
    except ImportError as exc:
        raise RuntimeError("Unable to import the agents.tools registry") from exc
    return registry


def _entries(registry: Any) -> list[tuple[str, Any]]:
    if isinstance(registry, Mapping):
        return [(str(name), spec) for name, spec in registry.items()]
    tools = getattr(registry, "tools", None)
    if isinstance(tools, Mapping):
        return [(str(name), spec) for name, spec in tools.items()]
    if isinstance(tools, (list, tuple)):
        registry = tools
    if isinstance(registry, (list, tuple)):
        return [(str(spec.name), spec) for spec in registry if getattr(spec, "name", None) is not None]
    raise TypeError("agents.tools registry must be a mapping or a sequence of ToolSpecs")


def _input_schema(spec: Any) -> Mapping[str, Any]:
    for attr in ("input_schema", "parameters", "schema"):
        value = getattr(spec, attr, None)
        if isinstance(value, Mapping):
            if value.get("type") == "object" or "properties" in value:
                return value
            return {"type": "object", "properties": value}
    return {"type": "object", "properties": {}}


def _annotation(schema: Mapping[str, Any]) -> Any:
    return {"string": str, "integer": int, "number": float,
            "boolean": bool, "object": dict, "array": list}.get(schema.get("type"), Any)


def _mcp_signature(schema: Mapping[str, Any]) -> inspect.Signature:
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        properties = {}
    required = set(schema.get("required", []))
    ordered = [(key, value) for key, value in properties.items() if key in required]
    ordered += [(key, value) for key, value in properties.items() if key not in required]
    params = []
    for key, child in ordered:
        if not isinstance(key, str) or not key.isidentifier() or keyword_is_reserved(key):
            continue
        child_schema = child if isinstance(child, Mapping) else {}
        default = inspect.Parameter.empty if key in required else None
        params.append(inspect.Parameter(key, inspect.Parameter.KEYWORD_ONLY,
            default=default, annotation=_annotation(child_schema)))
    return inspect.Signature(params, return_annotation=Any)


def keyword_is_reserved(value: str) -> bool:
    import keyword
    return keyword.iskeyword(value)


def _call_parameters(fn: Callable[..., Any], supplied: dict[str, Any], qloo: Any) -> dict[str, Any]:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return supplied
    kwargs = dict(supplied)
    for name in ("qloo_client", "qloo"):
        if name in params:
            if qloo is None:
                raise RuntimeError("This tool requires an injected Qloo client")
            kwargs[name] = qloo
    ordinary = [p for p in params.values() if p.kind not in
                (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                and p.name not in ("qloo_client", "qloo")]
    if (len(ordinary) == 1 and ordinary[0].name not in kwargs
            and ordinary[0].name in ("args", "input", "inputs", "arguments", "params")):
        return {ordinary[0].name: supplied, **{k: v for k, v in kwargs.items()
                if k in ("qloo_client", "qloo")}}
    return kwargs


async def _invoke(fn: Callable[..., Any], arguments: dict[str, Any], qloo_client: Any) -> Any:
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    budgeted = None
    if qloo_client is not None and any(n in params for n in ("qloo_client", "qloo")):
        budgeted = _BudgetedQlooClient(qloo_client, _CallBudget(_budget_limit()))
    kwargs = _call_parameters(fn, arguments, budgeted)
    result = await asyncio.to_thread(fn, **kwargs)
    if inspect.isawaitable(result):
        result = await result
    return result


def create_server(name: str = "xC", *, registry: Any = None,
                  qloo_client: Any = None,
                  qloo_client_factory: Callable[[], Any] | None = None) -> Any:
    """Build FastMCP with every shared ToolSpec.fn registered.

    Returns None and emits a warning note when the optional SDK is absent.
    Inject a Qloo client (or factory) when required; calls are limited by
    XC_QLOO_MAX_CALLS_PER_TOOL, defaulting to 5 per tool invocation.
    """
    if FastMCP is None:
        warnings.warn("MCP server unavailable: install the optional [mcp] extra",
                      RuntimeWarning, stacklevel=2)
        return None
    if qloo_client is None and qloo_client_factory is not None:
        qloo_client = qloo_client_factory()
    specs = _entries(_load_registry() if registry is None else registry)
    server = FastMCP(name)
    for registry_name, spec in specs:
        fn = getattr(spec, "fn", None)
        if not callable(fn):
            raise TypeError(f"ToolSpec {registry_name!r} has no callable fn")
        tool_name = str(getattr(spec, "name", registry_name))
        description = str(getattr(spec, "description", ""))
        signature = _mcp_signature(_input_schema(spec))

        async def handler(_fn: Callable[..., Any] = fn, **arguments: Any) -> Any:
            return await _invoke(_fn, arguments, qloo_client)

        handler.__name__ = "tool_" + "".join(c if c.isalnum() or c == "_" else "_" for c in tool_name)
        handler.__doc__ = description
        handler.__signature__ = signature
        server.add_tool(handler, name=tool_name, description=description)
    return server


def main() -> None:
    """Run the MCP server over stdio when invoked as a script."""
    server = create_server()
    if server is not None:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
