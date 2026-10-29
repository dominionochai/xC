"""Qloo service facade: validated params in, normalized data out, derived evidence only.

Every network request is built with backend/qloo/params.py builders and every
response is passed through backend/qloo/normalize.py. The underlying QlooClient
enforces the call budget; the service never retries and never returns raw
payloads.
"""
from __future__ import annotations

from typing import Any

from backend.qloo.client import QlooClient
from backend.qloo.normalize import (
    normalize_results,
    normalize_insights,
    normalize_heatmap,
    normalize_demographics,
    normalize_tags,
    normalize_entity_details,
)
from backend.qloo.params import (
    build_insights_params,
    build_search_params,
)

_SEARCH = "/search"
_INSIGHTS = "/v2/insights"
_TRENDING = "/v2/trending"
_TAG_TYPE = "urn:tag"
_LOCATION_SIGNAL = "signal.location.query"
_HEATMAP_TYPE = "urn:heatmap"
_DEMOGRAPHICS_TYPE = "urn:demographics"
_ENTITY_TYPE = "urn:entity:brand"
_PLACE_TYPE = "urn:entity:place"


def _empty_warning(client: Any, path: str) -> list[str]:
    rows = [row for row in client.call_log if row.get("path") == path and not row.get("cached")]
    if not rows or not rows[-1].get("suspect_empty"):
        return []
    ignored = rows[-1].get("possibly_ignored", [])
    suffix = ":possibly_ignored " + ",".join(sorted(ignored)) if ignored else ""
    return ["empty_results" + suffix]


class QlooService:
    """Synchronous facade over QlooClient.get."""

    def __init__(self, client: QlooClient) -> None:
        self.client = client

    def search(self, query: str, entity_types=None, take: int | None = None, extra: dict | None = None) -> dict[str, Any]:
        """V1: entity_types must be URN format (e.g., urn:entity:brand)."""
        pairs = build_search_params(query, entity_types=entity_types, take=take, extra=extra, array_style="comma")
        payload = self.client.get(_SEARCH, dict(pairs))
        return {"ok": True, "data": normalize_results(payload), "warnings": _empty_warning(self.client, _SEARCH), "evidence_refs": []}

    def tags_for(self, entity_id: str, take: int = 50) -> dict[str, Any]:
        """V11: Tag insights via /v2/insights with filter.type=urn:tag."""
        pairs = build_insights_params(entity_types=_TAG_TYPE, take=take, signals={"signal.interests.entities": entity_id}, array_style="comma")
        payload = self.client.get(_INSIGHTS, dict(pairs))
        return {"ok": True, "data": normalize_tags(payload), "warnings": _empty_warning(self.client, _INSIGHTS), "evidence_refs": []}

    def affinity_pair(self, entity_a: str, entity_b: str) -> dict[str, Any]:
        """V6: Pairwise affinity using tags_for for Jaccard overlap (backward compat).
        
        Uses tags_for to get tags for both entities, computes Jaccard overlap.
        Returns overlap as Jaccard similarity (shared/union) for backward compat.
        """
        tags_a = self.tags_for(entity_a)
        tags_b = self.tags_for(entity_b)
        
        tags_a_set = {t["id"] for t in tags_a.get("data", [])}
        tags_b_set = {t["id"] for t in tags_b.get("data", [])}
        
        shared = tags_a_set & tags_b_set
        union = tags_a_set | tags_b_set
        overlap = round(len(shared) / len(union), 4) if union else 0.0
        
        return {
            "ok": True,
            "data": {
                "overlap": overlap,
                "shared": sorted(shared),
                "union_size": len(union),
            },
            "warnings": [],
            "evidence_refs": []
        }

    def affinity_batch(self, entity_ids: list[str]) -> dict[str, Any]:
        pairs = []
        for index in range(len(entity_ids)):
            for other in range(index + 1, len(entity_ids)):
                result = self.affinity_pair(entity_ids[index], entity_ids[other])
                pairs.append({"a": entity_ids[index], "b": entity_ids[other], "overlap": result["data"]["overlap"]})
        return {"ok": True, "data": {"pairs": pairs, "count": len(pairs)}, "warnings": [], "evidence_refs": []}

    def demographics_for(self, entity_id: str) -> dict[str, Any]:
        """V15: Demographics via filter.type=urn:demographics."""
        pairs = build_insights_params(
            entity_types="urn:demographics",
            take=100,
            signals={"signal.interests.entities": entity_id},
            array_style="comma"
        )
        payload = self.client.get(_INSIGHTS, dict(pairs))
        return {"ok": True, "data": normalize_demographics(payload), "warnings": _empty_warning(self.client, _INSIGHTS), "evidence_refs": []}

    def heatmap(self, entity_id: str, location_query: str | None = None) -> dict[str, Any]:
        """V14: Heatmap with signal.location.query for locality.
        
        filter.type=urn:heatmap + signal.interests.entities=<id> + signal.location.query=<location>
        Returns normalized heatmap points with location + query data.
        """
        signals = {"signal.interests.entities": entity_id}
        if location_query:
            signals[_LOCATION_SIGNAL] = location_query
        pairs = build_insights_params(
            entity_types="urn:heatmap",
            take=100,
            signals=signals,
            array_style="comma"
        )
        payload = self.client.get(_INSIGHTS, dict(pairs))
        return {"ok": True, "data": normalize_heatmap(payload), "warnings": _empty_warning(self.client, _INSIGHTS), "evidence_refs": []}

    def trending(self, take: int = 10) -> dict[str, Any]:
        """V16: Trending requires signal.interests.entities + filter.start_date/end_date."""
        pairs = build_insights_params(
            entity_types="urn:tag",
            take=take,
            filters={"filter.query": "trending"},
            array_style="comma"
        )
        payload = self.client.get("/v2/trending", dict(pairs))
        return {"ok": True, "data": normalize_results(payload), "warnings": _empty_warning(self.client, _INSIGHTS), "evidence_refs": []}

    def tags(self, entity_id: str, take: int = 50) -> dict[str, Any]:
        """V11: Tag insights with per-tag query.affinity."""
        pairs = build_insights_params(entity_types=_TAG_TYPE, take=take, signals={"signal.interests.entities": entity_id}, array_style="comma")
        payload = self.client.get(_INSIGHTS, dict(pairs))
        return {"ok": True, "data": normalize_tags(payload), "warnings": _empty_warning(self.client, _INSIGHTS), "evidence_refs": []}

    def entity_details(self, entity_id: str) -> dict[str, Any]:
        """V12: Cheap per-entity tag fetch via /entities?entity_ids=<id>."""
        from backend.qloo.params import build_insights_params
        pairs = build_insights_params(
            entity_types="urn:entity:place",
            take=100,
            signals={"signal.interests.entities": entity_id},
            array_style="comma"
        )
        payload = self.client.get("/entities", dict(pairs))
        return {"ok": True, "data": normalize_entity_details(payload), "warnings": [], "evidence_refs": []}