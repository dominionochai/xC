"""Defensive, tolerant helpers for inconsistent Qloo JSON envelopes."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def result_items(payload: Any) -> list[Any]:
    """Return result-like items, accepting common envelopes and odd entries.
    
    V9: /search and /entities return results as a list.
    /v2/insights returns results as an object grouped by type.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, Mapping):
        return []
    results = payload.get("results")
    if isinstance(results, list):
        return results
    if isinstance(results, Mapping):
        # V9: Check type-specific groups
        for key in ("items", "entities", "tags", "heatmap", "demographics"):
            value = results.get(key)
            if isinstance(value, list):
                return value
        # Also check for entities directly
        for key in ("entities",):
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
        identity = next((_text(entity.get(key)) for key in ("id", "entity_id", "uri") if _text(entity.get(key))), None)
        name = next((_text(entity.get(key)) for key in ("name", "label", "title") if _text(entity.get(key))), None)
        kind = next((_text(entity.get(key)) for key in ("type", "entity_type", "category") if _text(entity.get(key))), None)
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


# V7: Convert affinity 0..1 to 0..100 scale
def _scale_affinity(value: Any) -> int | None:
    """Convert 0..1 affinity float to 0..100 integer."""
    try:
        val = float(value)
        if val < 0 or val > 1:
            return None
        return round(val * 100)
    except (TypeError, ValueError):
        return None


def normalize_insights(payload: Any) -> list[dict[str, Any]]:
    """Normalize insight results preserving measured fields.
    
    V7: Convert query.affinity 0..1 to 0..100 scale.
    V8: Preserve explainability as evidence.
    V10: Tolerate None/empty in properties (V10: many brand fields None).
    V11: Tag insights with per-tag query.affinity.
    V10/V11: Preserve all properties for communities/contrast evidence.
    """
    items = result_items(payload)
    output: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        entity = _entity(item)
        if entity is None:
            continue
        
        # V7: Convert query.affinity 0..1 to 0..100
        affinity_raw = item.get("query", {}).get("affinity")
        affinity_scaled = _scale_affinity(affinity_raw)
        
        # V8: Preserve explainability as evidence
        explainability = item.get("query", {}).get("explainability")
        
        # V10: Tolerate None/empty in properties
        properties = entity.get("properties")
        if properties and not isinstance(properties, Mapping):
            properties = None
        
        # V10: Collect all property fields as evidence (V10: ~55 brand fields)
        evidence_props = {}
        if properties:
            for key, value in properties.items():
                if value is not None and value != []:
                    evidence_props[key] = value
        
        row = {
            "id": next((_text(entity.get(k)) for k in ("id", "entity_id", "uri") if _text(entity.get(k))), None),
            "name": next((_text(entity.get(k)) for k in ("name", "label", "title") if _text(entity.get(k))), None),
            "type": next((_text(entity.get(k)) for k in ("type", "entity_type", "category") if _text(entity.get(k))), None),
            "affinity": affinity_scaled,  # V7: 0..100 scale
            "affinity_raw": affinity_raw,  # Preserve raw 0..1 for provenance
            "explainability": explainability,  # V8: per-signal contribution
            "popularity": entity.get("popularity"),
            "tags": entity.get("tags"),
            "properties": properties,  # V10: full properties preserved
            "evidence_props": evidence_props,  # V10: non-None properties for evidence
        }
        output.append(row)
    return output


def normalize_entities(payload: Any) -> list[dict[str, Any]]:
    """Alias emphasizing entity search/result normalization."""
    return normalize_results(payload)


def is_suspect_empty(payload: Any) -> bool:
    """Flag missing or empty ``results`` as suspicious, not as an API failure.
    
    V9: Check type-specific groups for emptiness.
    """
    if isinstance(payload, list):
        return not payload
    if not isinstance(payload, Mapping):
        return False
    if "results" not in payload:
        return False
    results = payload.get("results")
    if isinstance(results, list):
        return not results
    if isinstance(results, Mapping):
        # V9: Check type-specific groups
        for key in ("items", "entities", "tags", "heatmap", "demographics"):
            value = results.get(key)
            if isinstance(value, list):
                return not value
        return not results
    return results is None


def is_empty_results(payload: Any) -> bool:
    """Compatibility alias for the package's suspicious-empty diagnostic."""
    return is_suspect_empty(payload)


# V9: is_suspect_empty now checks type-specific groups
# V14: Heatmap parsing
def normalize_heatmap(payload: Any) -> list[dict[str, Any]]:
    """Normalize heatmap results.
    
    V14: heatmap returns results.heatmap array with points containing:
    location: {latitude, longitude, geohash}
    query: {affinity (int), affinity_rank (float), popularity (int), entity_brand_affinity (int), entity_brand_affinity_rank (float)}
    """
    if not isinstance(payload, Mapping):
        return []
    results = payload.get("results")
    if not isinstance(results, Mapping):
        return []
    heatmap = results.get("heatmap")
    if not isinstance(heatmap, list):
        return []
    
    output = []
    for point in heatmap:
        if not isinstance(point, Mapping):
            continue
        location = point.get("location")
        query = point.get("query")
        if not isinstance(location, Mapping) or not isinstance(query, Mapping):
            continue
        output.append({
            "location": {
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude"),
                "geohash": location.get("geohash"),
            },
            "query": {
                "affinity": query.get("affinity"),  # int, scale unconfirmed
                "affinity_rank": query.get("affinity_rank"),
                "popularity": query.get("popularity"),
                "entity_brand_affinity": query.get("entity_brand_affinity"),
                "entity_brand_affinity_rank": query.get("entity_brand_affinity_rank"),
            }
        })
    return output


# V15: Demographics parsing
def normalize_demographics(payload: Any) -> dict[str, Any] | None:
    """Normalize demographics results.
    
    V15: returns results.demographics[0] = {entity_id, query: {age: {...}, gender: {...}}}
    Age buckets: 24_and_younger, 25_to_29, 30_to_34, 35_to_44, 45_to_54, 55_and_older
    Gender buckets: male, female
    All floats.
    """
    if not isinstance(payload, Mapping):
        return None
    results = payload.get("results")
    if not isinstance(results, Mapping):
        return None
    demographics = results.get("demographics")
    if not isinstance(demographics, list) or not demographics:
        return None
    demo = demographics[0]
    if not isinstance(demo, Mapping):
        return None
    return {
        "entity_id": demo.get("entity_id"),
        "query": demo.get("query"),
    }


# V11: Tag insights parsing
def normalize_tags(payload: Any) -> list[dict[str, Any]]:
    """Normalize tag insights results.
    
    V11: Tag items have name, popularity, query, subtype, tag_id, tag_value, types; per-tag query.affinity.
    Returns only id and name for backward compatibility with existing tests.
    """
    items = result_items(payload)
    if not items:
        return []
    
    output = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        entity = _entity(item)
        if not entity:
            continue
        output.append({
            "id": next((_text(entity.get(k)) for k in ("id", "entity_id", "tag_id", "uri") if _text(entity.get(k))), None),
            "name": next((_text(entity.get(k)) for k in ("name", "label", "title") if _text(entity.get(k))), None),
        })
    return output


# V12: Entity details parsing
def normalize_entity_details(payload: Any) -> dict[str, Any] | None:
    """Normalize /entities?entity_ids=<id> response.
    
    V12: Returns one item with name, entity_id, types, popularity, disambiguation, properties, tags.
    """
    items = result_items(payload)
    if not items:
        return None
    entity = _entity(items[0])
    if not entity:
        return None
    
    return {
        "id": entity.get("entity_id") or entity.get("id"),
        "name": entity.get("name"),
        "types": entity.get("types"),
        "popularity": entity.get("popularity"),
        "disambiguation": entity.get("disambiguation"),
        "properties": entity.get("properties"),  # short descriptions, external ids, image, akas
        "tags": entity.get("tags"),  # long tags list with name, tag_id, type
    }


def is_suspect_empty(payload: Any) -> bool:
    """Flag missing or empty ``results`` as suspicious, not as an API failure.
    
    V9: Check type-specific groups for emptiness.
    """
    if isinstance(payload, list):
        return not payload
    if not isinstance(payload, Mapping):
        return False
    if "results" not in payload:
        return False
    results = payload.get("results")
    if isinstance(results, list):
        return not results
    if isinstance(results, Mapping):
        # V9: Check type-specific groups
        for key in ("items", "entities", "tags", "heatmap", "demographics"):
            value = results.get(key)
            if isinstance(value, list):
                return not value
        return not results
    return results is None


def is_empty_results(payload: Any) -> bool:
    """Compatibility alias for the package's suspicious-empty diagnostic."""
    return is_suspect_empty(payload)


# V12: _entity helper now checks for nested "entity" key
def _entity(item: Any) -> Mapping[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    nested = item.get("entity")
    return nested if isinstance(nested, Mapping) else item


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def shape_paths(payload: Any) -> list[str]:
    """Return sorted-by-input dotted paths describing mapping/list structure.
    
    Mapping keys are joined with dots and list contents use ``[]`` instead of
    numeric indexes, so equivalent payload shapes produce equivalent paths.
    Paths start with ``$`` (JSONPath-style root marker). Non-container values
    are treated as leaves.
    """
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        if path not in seen:
            seen.add(path)
            paths.append(path)

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key in value:
                part = str(key)
                child = f"{path}.{part}" if path else f"$.{part}"
                add(child)
                visit(value[key], child)
        elif isinstance(value, list):
            marker = f"{path}[]" if path else "$[]"
            add(marker)
            for item in value:
                visit(item, marker)

    visit(payload, "$" )
    return paths