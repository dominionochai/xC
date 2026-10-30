"""Focused tests for async Qloo culture extractors."""
from __future__ import annotations

import unittest
from urllib.parse import parse_qs

import httpx

from backend.settings import QLOO_BASE_URL
from backend.src.services.qloo_extractors import (
    SEARCH_TYPES,
    compare_brand_cultures,
    fetch_entity_tastes,
    resolve_qloo_entity_id,
)


class QlooExtractorTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_query_and_all_search_types(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"results": [{"id": "brand:acme"}]})

        async with httpx.AsyncClient(
            base_url=QLOO_BASE_URL, transport=httpx.MockTransport(handler)
        ) as client:
            entity_id = await resolve_qloo_entity_id(client, "Acme")

        self.assertEqual(entity_id, "brand:acme")
        request = requests[0]
        self.assertEqual(request.url.path, "/search")
        params = parse_qs(request.url.query.decode())
        self.assertEqual(params["query"], ["Acme"])
        self.assertEqual(params["types"], [",".join(sorted(SEARCH_TYPES))])

    async def test_insights_uses_tag_filter_and_take_50(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={"results": [{"id": "tag:design", "name": "Design"}]},
            )

        async with httpx.AsyncClient(
            base_url=QLOO_BASE_URL, transport=httpx.MockTransport(handler)
        ) as client:
            tastes = await fetch_entity_tastes(client, "brand:acme")

        self.assertEqual(tastes, [{"id": "tag:design", "name": "Design"}])
        request = requests[0]
        self.assertEqual(request.url.path, "/v2/insights")
        params = parse_qs(request.url.query.decode())
        self.assertEqual(params["signal.interests.entities"], ["brand:acme"])
        self.assertEqual(params["filter.type"], ["urn:tag"])
        self.assertEqual(params["take"], ["50"])

    async def test_brand_comparison_returns_overlap_and_unique_tags(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            entity_id = parse_qs(request.url.query.decode())[
                "signal.interests.entities"
            ][0]
            if entity_id == "brand:first":
                results = [
                    {"id": "tag:shared", "name": "Shared"},
                    {"id": "tag:first", "name": "First only"},
                ]
            else:
                results = [
                    {"id": "tag:shared", "name": "Shared"},
                    {"id": "tag:second", "name": "Second only"},
                ]
            return httpx.Response(200, json={"results": results})

        async with httpx.AsyncClient(
            base_url=QLOO_BASE_URL, transport=httpx.MockTransport(handler)
        ) as client:
            comparison = await compare_brand_cultures(
                client, "brand:first", "brand:second"
            )

        self.assertEqual(
            comparison,
            {
                "shared": [{"id": "tag:shared", "name": "Shared"}],
                "first_only": [{"id": "tag:first", "name": "First only"}],
                "second_only": [{"id": "tag:second", "name": "Second only"}],
            },
        )


if __name__ == "__main__":
    unittest.main()
