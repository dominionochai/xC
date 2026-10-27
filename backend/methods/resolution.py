"""Entity resolution with an injected search function and deterministic scoring."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

BRAND_SCOPE = "urn:entity:brand"


def _candidate_list(payload: Any) -> list[Any]:
    """Extract candidates from common search response shapes without raising."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, tuple):
        return list(payload)
    if isinstance(payload, Mapping):
        for key in ("candidates", "results", "items", "data"):
            value = payload.get(key)
            if isinstance(value, (list, tuple)):
                return list(value)
            if isinstance(value, Mapping):
                nested = _candidate_list(value)
                if nested:
                    return nested
        if any(k in payload for k in ("name", "id", "entity_id", "urn")):
            return [payload]
    return []


def _normalize(candidate: Any) -> dict[str, Any] | None:
    """Normalize a candidate; malformed entries are ignored safely."""
    if not isinstance(candidate, Mapping):
        return None
    name = candidate.get("name") or candidate.get("label") or candidate.get("title")
    if not isinstance(name, str) or not name.strip():
        return None
    raw_popularity = candidate.get("popularity", candidate.get("score", 0))
    missing_popularity = raw_popularity is None
    try:
        popularity = float(raw_popularity) if raw_popularity is not None else 0.0
    except (TypeError, ValueError, OverflowError):
        popularity = 0.0
        missing_popularity = True
    if popularity < 0:
        popularity = 0.0
    identifier = next((candidate[k] for k in ("id", "entity_id", "urn", "uri") if candidate.get(k) is not None), None)
    result = dict(candidate)
    result.update({"name": name.strip(), "popularity": popularity, "id": identifier})
    if missing_popularity:
        result["note"] = "popularity missing or invalid; treated as 0"
    return result


def resolve_entity(
    query: str,
    search_fn: Callable[[str, str | None], Any],
    max_candidates: int = 20,
    popularity_ratio_threshold: float = 2.0,
    brand_first: bool = True,
    exact_match_required: bool = False,
    confidence_alpha: float = 0.6,
) -> dict[str, Any]:
    """Resolve a name via injected search; report uncertainty instead of guessing.

    Search is first constrained to the brand entity type. If that pass is empty,
    ``brand_first`` enables one broader search (type ``None``). Candidate parsing
    is intentionally tolerant of malformed API response shapes.
    """
    notes: list[str] = []
    passes_used: list[str | None] = []
    try:
        scoped_raw = search_fn(query, BRAND_SCOPE)
    except Exception as exc:  # injected clients may fail or return malformed data
        scoped_raw = None
        notes.append(f"brand search failed: {type(exc).__name__}")
    passes_used.append(BRAND_SCOPE)
    scoped = [item for raw in _candidate_list(scoped_raw) if (item := _normalize(raw)) is not None]
    raw_candidates = scoped
    silent_ignore = False
    if not scoped and brand_first:
        try:
            broad_raw = search_fn(query, None)
        except Exception as exc:
            broad_raw = None
            notes.append(f"broader search failed: {type(exc).__name__}")
        passes_used.append(None)
        broad = [item for raw in _candidate_list(broad_raw) if (item := _normalize(raw)) is not None]
        scoped_ids = {str(c.get("id")) for c in scoped if c.get("id") is not None}
        broad_ids = {str(c.get("id")) for c in broad if c.get("id") is not None}
        silent_ignore = scoped_ids == broad_ids
        raw_candidates = broad

    try:
        limit = max(0, int(max_candidates))
    except (TypeError, ValueError):
        limit = 20
        notes.append("invalid max_candidates; used 20")
    candidates = raw_candidates[:limit]
    query_key = query.strip().casefold() if isinstance(query, str) else ""
    for item in candidates:
        item["exact_match"] = item["name"].casefold() == query_key
    candidates.sort(key=lambda item: (not item["exact_match"], -item["popularity"], item["name"].casefold()))
    if not candidates:
        return {
            "status": "not_found", "candidate": None, "candidates": [], "confidence": 0.0,
            "passes_used": passes_used, "detected_silent_ignore": silent_ignore,
            "notes": notes,
        }

    exacts = [item for item in candidates if item["exact_match"]]
    ordered = sorted(candidates, key=lambda item: (-item["popularity"], item["name"].casefold()))
    top = ordered[0]
    second = ordered[1]["popularity"] if len(ordered) > 1 else 0.0
    try:
        ratio = max(0.0, float(popularity_ratio_threshold))
    except (TypeError, ValueError):
        ratio = 2.0
        notes.append("invalid popularity_ratio_threshold; used 2.0")
    selected: dict[str, Any] | None = None
    if len(exacts) == 1:
        selected = exacts[0]
    elif top["popularity"] >= ratio * second:
        selected = top
    if exact_match_required and selected is not None and not selected["exact_match"]:
        selected = None
        notes.append("exact match required but the leading candidate was not exact")

    if selected is None:
        return {
            "status": "ambiguous", "candidate": None, "candidates": candidates,
            "confidence": 0.0, "passes_used": passes_used,
            "detected_silent_ignore": silent_ignore, "notes": notes,
        }
    alpha = min(1.0, max(0.0, float(confidence_alpha)))
    if len(candidates) == 1 and not selected["exact_match"]:
        confidence = 0.0
    else:
        gap = min(1.0, max(0.0, (top["popularity"] - second) / max(1e-9, top["popularity"])))
        confidence = alpha * float(selected["exact_match"]) + (1.0 - alpha) * gap
    return {
        "status": "resolved", "candidate": selected, "candidates": candidates,
        "confidence": round(confidence, 6), "passes_used": passes_used,
        "detected_silent_ignore": silent_ignore, "notes": notes,
    }
