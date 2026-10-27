"""Qloo service facade: validated params in, normalized data out, derived evidence only.

Every network request is built with backend/qloo/params.py builders and every
response is passed through backend/qloo/normalize.py. The underlying QlooClient
enforces the call budget; the service never retries and never returns raw
payloads. Routes for demographics, heatmap and trending are UNVERIFIED until
the P14 probe locks the real response shapes.
"""
from __future__ import annotations

from typing import Any

from backend.qloo.client import QlooClient
from backend.qloo.normalize import normalize_results
from backend.qloo.params import build_insights_params, build_search_params, normalize_params

_SEARCH = "/search"
_INSIGHTS = "/v2/insights"
_TRENDING = "/trending"
_TAG_TYPE = "urn:tag"
_LOCATION_SIGNAL = "signal.location.query"


def _empty_warning(client: QlooClient, path: str) -> list[str]:
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
        pairs = build_search_params(query, entity_types=entity_types, take=take, extra=extra, array_style="comma")
        payload = self.client.get(_SEARCH, dict(pairs))
        return {"ok": True, "data": normalize_results(payload), "warnings": _empty_warning(self.client, _SEARCH), "evidence_refs": []}

    def tags_for(self, entity_id: str, take: int = 50) -> dict[str, Any]:
        pairs = build_insights_params(entity_types=_TAG_TYPE, take=take, signals={"signal.interests.entities": entity_id}, array_style="comma")
        payload = self.client.get(_INSIGHTS, dict(pairs))
        return {"ok": True, "data": normalize_results(payload), "warnings": _empty_warning(self.client, _INSIGHTS), "evidence_refs": []}

    def affinity_pair(self, entity_a: str, entity_b: str) -> dict[str, Any]:
        left = {row["id"] for row in self.tags_for(entity_a)["data"]}
        right = {row["id"] for row in self.tags_for(entity_b)["data"]}
        union = left | right
        shared = left & right
        overlap = round(len(shared) / len(union), 4) if union else 0.0
        return {"ok": True, "data": {"overlap": overlap, "shared": sorted(shared), "union_size": len(union)}, "warnings": [], "evidence_refs": []}

    def affinity_batch(self, entity_ids: list[str]) -> dict[str, Any]:
        pairs = []
        for index in range(len(entity_ids)):
            for other in range(index + 1, len(entity_ids)):
                result = self.affinity_pair(entity_ids[index], entity_ids[other])
                pairs.append({"a": entity_ids[index], "b": entity_ids[other], "overlap": result["data"]["overlap"]})
        return {"ok": True, "data": {"pairs": pairs, "count": len(pairs)}, "warnings": [], "evidence_refs": []}

    def demographics_for(self, entity_id: str) -> dict[str, Any]:
        """UNVERIFIED until P14: demographic filter key may change after probing."""
        pairs = build_insights_params(take=100, signals={"signal.entities": entity_id}, filters={"filter.results.entities": entity_id}, array_style="comma")
        payload = self.client.get(_INSIGHTS, dict(pairs))
        return {"ok": True, "data": normalize_results(payload), "warnings": _empty_warning(self.client, _INSIGHTS), "evidence_refs": []}

    def heatmap(self, entity_id: str, location_query: str | None = None) -> dict[str, Any]:
        """UNVERIFIED until P14: heatmap responses are min-max normalized per area."""
        signals = {"signal.entities": entity_id}
        if location_query:
            signals[_LOCATION_SIGNAL] = location_query
        pairs = build_insights_params(take=100, signals=signals, array_style="comma")
        payload = self.client.get(_INSIGHTS, dict(pairs))
        return {"ok": True, "data": normalize_results(payload), "warnings": _empty_warning(self.client, _INSIGHTS), "evidence_refs": []}

    def trending(self, take: int = 10) -> dict[str, Any]:
        """UNVERIFIED until P14: trending route may differ from /trending."""
        pairs = normalize_params([("take", take)])
        payload = self.client.get(_TRENDING, dict(pairs))
        return {"ok": True, "data": normalize_results(payload), "warnings": _empty_warning(self.client, _TRENDING), "evidence_refs": []}
