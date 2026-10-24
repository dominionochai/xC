"""Resolve a user-supplied entity through the Qloo client."""
from __future__ import annotations

import inspect
import re
from typing import Any, Mapping


def _budget_check(budget: Any) -> None:
    """Raise before a Qloo call when the supplied call budget is exhausted."""
    if budget is None:
        return
    check = getattr(budget, "check", None)
    result = check() if callable(check) else budget() if callable(budget) else budget
    if result is False:
        raise RuntimeError("Qloo call budget exhausted")


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("entities", "results", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [dict(x) for x in value if isinstance(x, Mapping)]
        if payload:
            return [dict(payload)]
    if isinstance(payload, (list, tuple)):
        return [dict(x) for x in payload if isinstance(x, Mapping)]
    return []


def _call(method: Any, query: str, limit: int) -> Any:
    """Call common Qloo search signatures without retrying a network request."""
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return method(query, limit=limit)
    kwargs: dict[str, Any] = {}
    if "limit" in params:
        kwargs["limit"] = limit
    elif "take" in params:
        kwargs["take"] = limit
    if "query" in params and "q" not in params:
        return method(query=query, **kwargs)
    if "q" in params:
        return method(q=query, **kwargs)
    return method(query, **kwargs)


def resolve(qloo: Any, query: str, *, limit: int = 10, budget: Any = None) -> dict[str, Any]:
    """Resolve ``query`` to the best Qloo entity.

    Exact normalized-name matches dominate non-exact matches; popularity breaks
    ties within either class. If search has no usable result, a direct Qloo
    resolver is tried once. Results include provenance, evidence and warnings.
    """
    query = str(query or "").strip()
    warnings: list[str] = []
    provenance: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    if not query:
        return {"entity": None, "candidates": [], "provenance": provenance,
                "evidence": evidence, "warnings": ["empty_query"]}
    search = next((getattr(qloo, name, None) for name in
                   ("search_entities", "search", "search_entity")
                   if callable(getattr(qloo, name, None))), None)
    candidates: list[dict[str, Any]] = []
    if search is not None:
        try:
            _budget_check(budget)
            candidates = _items(_call(search, query, max(1, int(limit))))
            provenance.append({"source": "qloo", "method": getattr(search, "__name__", "search")})
        except Exception as exc:
            warnings.append("search_failed: " + type(exc).__name__)
    else:
        warnings.append("qloo_search_method_unavailable")
    qnorm = _normalized(query)
    def rank(entity: dict[str, Any]) -> tuple[int, float, str]:
        name = entity.get("name") or entity.get("entity_name") or ""
        exact = int(_normalized(name) == qnorm)
        raw = entity.get("popularity", entity.get("popularity_score", entity.get("score", 0)))
        try:
            popularity = float(raw or 0)
        except (TypeError, ValueError):
            popularity = 0.0
        return (exact, popularity, str(entity.get("id", entity.get("entity_id", ""))))
    candidates.sort(key=rank, reverse=True)
    if candidates:
        chosen = candidates[0]
        evidence.append({"kind": "name_match", "exact": bool(rank(chosen)[0]),
                         "query": query, "matched_name": chosen.get("name", chosen.get("entity_name"))})
        evidence.append({"kind": "popularity", "value": rank(chosen)[1]})
        return {"entity": chosen, "candidates": candidates, "provenance": provenance,
                "evidence": evidence, "warnings": warnings}
    fallback = next((getattr(qloo, name, None) for name in
                     ("resolve_entity", "get_entity")
                     if callable(getattr(qloo, name, None))), None)
    if fallback is not None:
        try:
            _budget_check(budget)
            try:
                result = fallback(query)
            except (TypeError, ValueError):
                result = fallback(name=query)
            normalized = _items(result)
            if normalized:
                chosen = normalized[0]
                provenance.append({"source": "qloo", "method": getattr(fallback, "__name__", "fallback")})
                evidence.append({"kind": "fallback_resolution", "query": query})
                return {"entity": chosen, "candidates": normalized, "provenance": provenance,
                        "evidence": evidence, "warnings": warnings}
        except Exception as exc:
            warnings.append("fallback_failed: " + type(exc).__name__)
    warnings.append("no_entity_match")
    return {"entity": None, "candidates": candidates, "provenance": provenance,
            "evidence": evidence, "warnings": warnings}
