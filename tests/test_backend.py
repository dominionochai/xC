"""Tests for the deterministic analysis helpers, Qloo client, and API slice."""

import os
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.analytics import (affinity_clash, affinity_graph, dollarized_tam,
                               find_transition_bridge, geographic_market_split)
from backend.app import app, get_qloo_client
from backend.qloo_client import QlooClient


class AnalyticsTests(unittest.TestCase):
    def test_affinity_clash_and_unknown_data(self) -> None:
        result = affinity_clash(["a", "b"], ["b", "c"])
        self.assertEqual(result["shared_entities"], ["b"])
        # Production rounds Jaccard similarity to 4 places.
        self.assertAlmostEqual(result["jaccard_similarity"], 0.3333, places=4)
        self.assertEqual(result["risk"], "high")
        self.assertEqual(affinity_clash([], ["a"])["risk"], "unknown")

    def test_transition_bridge_is_deterministic_and_limited_to_three_hops(self) -> None:
        graph = {"s": {"z", "a"}, "a": {"t"}, "z": {"t"}}
        self.assertEqual(find_transition_bridge("s", "t", graph), ["s", "a", "t"])
        too_long = {"s": {"a"}, "a": {"b"}, "b": {"c"}, "c": {"t"}}
        self.assertIsNone(find_transition_bridge("s", "t", too_long))
        shared = affinity_graph("s", "t", ["shared"], ["shared"])
        self.assertEqual(find_transition_bridge("s", "t", shared), ["s", "shared", "t"])

    def test_geographic_split_and_dollarized_tam(self) -> None:
        self.assertEqual(geographic_market_split({"US": 75, "CA": 25}), [
            {"region": "CA", "population": 25, "share_fraction": 0.25},
            {"region": "US", "population": 75, "share_fraction": 0.75},
        ])
        self.assertEqual(dollarized_tam(100, 12.345)["tam_usd"], 1234.5)


class QlooClientTests(unittest.TestCase):
    def test_insights_request_uses_qloo_path_and_query_form(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, json={"results": []})

        with QlooClient("", retries=0, transport=httpx.MockTransport(handler)) as client:
            client.get_insights("urn:entity:brand:example", entity_type="urn:entity:brand", take=7)
        request = requests[0]
        self.assertEqual(request.url.host, "hackathon.api.qloo.com")
        self.assertEqual(request.url.path, "/v2/insights")
        self.assertEqual(request.url.params["signal.interests.entities"], "urn:entity:brand:example")
        self.assertEqual(request.url.params["filter.type"], "urn:entity:brand")
        self.assertEqual(request.url.params["take"], "7")

    def test_transient_retries_are_bounded(self) -> None:
        attempts = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, json={"error": "temporarily unavailable"})

        with patch("backend.qloo_client.time.sleep"):
            with QlooClient("", retries=2, transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(httpx.HTTPStatusError):
                    client.get_insights("urn:entity:brand:example")
        self.assertEqual(attempts, 3)


class ApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_qloo_client, None)

    def test_health_does_not_require_qloo_configuration(self) -> None:
        response = TestClient(app).get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_analyze_endpoint_returns_computed_report(self) -> None:
        class FakeQlooClient:
            def get_insights(self, entity_id: str, *, entity_type: str) -> dict[str, object]:
                del entity_type
                affinity = "urn:entity:brand:shared"
                return {"results": [{"id": affinity}]} if entity_id == "source" else {"results": [{"id": affinity}]}

        app.dependency_overrides[get_qloo_client] = lambda: FakeQlooClient()
        response = TestClient(app).post("/api/v1/reports/analyze", json={
            "source_entity_id": "source",
            "comparison_entity_id": "target",
            "regions": {"US": 800, "CA": 200},
            "annual_spend_per_person": 15.5,
        })
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["transition_bridge"], ["source", "urn:entity:brand:shared", "target"])
        self.assertEqual(body["tam"]["tam_usd"], 15500.0)
        self.assertEqual(body["affinity"]["risk"], "low")

    def test_analyze_requires_an_environment_key_when_not_overridden(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            response = TestClient(app).post("/api/v1/reports/analyze", json={
                "source_entity_id": "source",
                "comparison_entity_id": "target",
                "regions": {"US": 10},
                "annual_spend_per_person": 1,
            })
        self.assertEqual(response.status_code, 503)
        self.assertIn("QLOO_API_KEY", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
