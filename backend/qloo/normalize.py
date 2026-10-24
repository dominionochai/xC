"""Defensive, tolerant helpers for inconsistent Qloo JSON envelopes."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any


def result_items(payload: Any) -> list[Any]:
    """Return result-like items, accepting common envelopes and odd entries."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        return []
    results = payload.get("results")
    if isinstance(results, list):
        return results
    if isinstance(results, Mapping):
        for key in ("items", "entities", "tags"):
            value = results.get(key)
            if isinstance(value, list):
                return value
    return []


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _entity(item: Any) -> Mapping[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    nested = item.get("entity")
    return nested if isinstance(nested, Mapping) else item


def normalize_results(payload: Any) -> list[dict[str, str]]:
    """Normalize result objects without requiring one particular response schema."""
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in result_items(payload):
        entity = _entity(item)
        if entity is None:
            continue
        identity = next((_text(entity.get(k)) for k in ("id", "entity_id", "uri")
                         if _text(entity.get(k))), None)
        name = next((_text(entity.get(k)) for k in ("name", "label", "title")
                     if _text(entity.get(k))), None)
        kind = next((_text(entity.get(k)) for k in ("type", "entity_type", "category")
                     if _text(entity.get(k))), None)
        if identity is None and name is None:
            continue
        identity = identity or name
        name = name or identity
        dedupe_key = identity.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        row = {"id": identity, "name": name}
        if kind is not None:
            row["type"] = kind
        output.append(row)
    return output


def normalize_entities(payload: Any) -> list[dict[str, str]]:
    """Alias emphasizing entity search/result normalization."""
    return normalize_results(payload)


def is_suspect_empty(payload: Any) -> bool:
    """Flag missing or empty ``results`` as suspicious, not as an API failure.

    Empty results can be legitimate; this is deliberately a diagnostic signal.
    """
    if isinstance(payload, list):
        return not payload
    if not isinstance(payload, Mapping) or "results" not in payload:
        return True
    results = payload.get("results")
    if isinstance(results, list):
        return not results
    if isinstance(results, Mapping):
        for key in ("items", "entities", "tags"):
            value = results.get(key)
            if isinstance(value, list):
                return not value
        return not results
    return results is None
