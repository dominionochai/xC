"""Group Qloo entities into communities and derive co-weights."""
from __future__ import annotations

import inspect
import math
from typing import Any, Mapping


def _budget_check(budget: Any) -> None:
    """Check the operation budget immediately before a Qloo method call."""
    if budget is None:
        return
    check = getattr(budget, "check", None)
    result = check() if callable(check) else budget() if callable(budget) else budget
    if result is False:
        raise RuntimeError("Qloo call budget exhausted")


def _entities(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        value = value.get("entities", value.get("results", value.get("items", [])))
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _score(entity: Mapping[str, Any]) -> float | None:
    raw = entity.get("weight", entity.get("score", entity.get("affinity")))
    try:
        value = float(raw) if raw is not None else None
    except (TypeError, ValueError, OverflowError):
        return None
    return value if value is not None and math.isfinite(value) and value >= 0 else None


def _key(entity: Mapping[str, Any]) -> str:
    for field in ("community", "category", "type", "genre"):
        value = entity.get(field)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value:
            return str(value)
    tags = entity.get("tags")
    if isinstance(tags, (list, tuple)) and tags:
        first = tags[0]
        return str(first.get("name", first.get("id", "ungrouped"))
                   if isinstance(first, Mapping) else first)
    return "ungrouped"


def _co_weight(group: list[dict[str, Any]]) -> tuple[dict[str, float], bool]:
    raw: list[float | None] = [_score(entity) for entity in group]
    total = sum(value for value in raw if value is not None)
    fallback = total <= 0
    if fallback:
        value = 1.0 / len(group) if group else 0.0
        return {str(item.get("id", item.get("entity_id", item.get("name", index)))): value
                for index, item in enumerate(group)}, True
    return {str(item.get("id", item.get("entity_id", item.get("name", index)))):
            (raw[index] / total if raw[index] is not None else 0.0)
            for index, item in enumerate(group)}, False


def communities(qloo: Any, entities: Any = None, *, budget: Any = None) -> dict[str, Any]:
    """Group input entities and compute per-community normalized co-weights.

    Qloo grouping data is preferred when available; if unavailable or empty,
    entities are grouped locally by community/category/type/genre/tag. If no
    usable weights exist in a group, members receive equal co-weights.
    """
    warnings: list[str] = []
    provenance: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    payload = None
    method = next((getattr(qloo, name, None) for name in ("get_communities", "group_entities")
                   if callable(getattr(qloo, name, None))), None)
    if method is not None:
        try:
            _budget_check(budget)
            try:
                params = inspect.signature(method).parameters
            except (TypeError, ValueError):
                params = {"entities": None}
            payload = method(entities) if params else method()
            provenance.append({"source": "qloo", "method": getattr(method, "__name__", "get_communities")})
        except Exception as exc:
            warnings.append("qloo_communities_failed: " + type(exc).__name__)
    elif entities is None:
        warnings.append("qloo_communities_method_unavailable")
    grouped: dict[str, list[dict[str, Any]]] = {}
    if isinstance(payload, Mapping):
        raw_groups = payload.get("communities", payload.get("groups"))
        if isinstance(raw_groups, Mapping):
            for key, members in raw_groups.items():
                grouped[str(key)] = _entities(members)
        elif isinstance(raw_groups, (list, tuple)):
            for index, item in enumerate(raw_groups):
                if isinstance(item, Mapping):
                    key = str(item.get("id", item.get("name", f"community_{index + 1}")))
                    grouped[key] = _entities(item.get("entities", item.get("members", [])))
    if not grouped:
        for entity in _entities(entities if entities is not None else payload):
            grouped.setdefault(_key(entity), []).append(entity)
        if grouped:
            provenance.append({"source": "local", "method": "attribute_grouping"})
    output: list[dict[str, Any]] = []
    for key in sorted(grouped):
        members = grouped[key]
        co_weights, used_fallback = _co_weight(members)
        if used_fallback:
            warnings.append(f"equal_weight_fallback:{key}")
        row = {"id": key, "entities": members, "co_weights": co_weights,
               "weight_sum": sum(co_weights.values()), "weight_fallback": used_fallback}
        output.append(row)
        evidence.append({"kind": "community", "id": key,
                         "entity_count": len(members), "co_weights": co_weights,
                         "weight_fallback": used_fallback})
    if not output:
        warnings.append("no_communities")
    return {"communities": output, "provenance": provenance,
            "evidence": evidence, "warnings": warnings}
