"""Offline deterministic tests for the QlooService adapter (synthetic transport)."""
import json
import unittest

from backend.qloo.client import CallBudgetExceeded, QlooClient
from backend.qloo.service import QlooService

BASE = "https://hackathon.api.qloo.com"


def _payload(status=200, **body):
    return {"status": status, "body": json.dumps(body).encode("utf-8")}


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body
        self.headers = {}


class FakeTransport:
    """Route values are either {status, body} dicts or callables(params)->dict."""
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        route = self.routes.get(url[len(BASE):])
        if callable(route):
            route = route(params)
        return FakeResponse(route["status"], route["body"])


def _client(transport, budget=200):
    return QlooClient(api_key="test-key", transport=transport, call_budget=budget, pacing_seconds=0.0, cache_ttl=0.0, sleep=lambda _s: None, clock=lambda: 0.0)


SEARCH_BODY = {"results": [{"entity": {"id": "urn:artist:1", "name": "Artist One", "type": "urn:entity:artist"}}, {"id": "urn:artist:2", "name": "Artist Two"}]}
TAGS_A = {"results": [{"entity": {"id": "urn:tag:x", "name": "X"}}, {"entity": {"id": "urn:tag:y", "name": "Y"}}]}
TAGS_B = {"results": [{"entity": {"id": "urn:tag:y", "name": "Y"}}]}
EMPTY = {"results": []}


class QlooServiceTests(unittest.TestCase):
    def test_search_normalizes_rows_and_builds_params(self):
        transport = FakeTransport({"/search": _payload(**SEARCH_BODY)})
        service = QlooService(_client(transport))
        result = service.search("chelsea", entity_types=["urn:entity:brand"], take=5)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"], [{"id": "urn:artist:1", "name": "Artist One", "type": "urn:entity:artist"}, {"id": "urn:artist:2", "name": "Artist Two"}])
        self.assertEqual(result["warnings"], [])
        sent = transport.calls[0]
        self.assertEqual(sent["params"]["query"], "chelsea")
        self.assertEqual(sent["params"]["types"], "urn:entity:brand")
        self.assertEqual(sent["params"]["take"], "5")
        self.assertEqual(sent["headers"]["X-Api-Key"], "test-key")

    def test_tags_for_uses_insights_route_and_tag_filter(self):
        transport = FakeTransport({"/v2/insights": _payload(**TAGS_A)})
        service = QlooService(_client(transport))
        result = service.tags_for("urn:brand:1", take=50)
        self.assertEqual(result["data"], [{"id": "urn:tag:x", "name": "X"}, {"id": "urn:tag:y", "name": "Y"}])
        sent = transport.calls[0]
        self.assertEqual(sent["params"]["signal.interests.entities"], "urn:brand:1")
        self.assertEqual(sent["params"]["filter.type"], "urn:tag")

    def test_affinity_pair_jaccard_overlap(self):
        state = {"n": 0}
        def handler(params):
            state["n"] += 1
            body = TAGS_A if state["n"] == 1 else TAGS_B
            return {"status": 200, "body": json.dumps(body).encode("utf-8")}
        transport = FakeTransport({"/v2/insights": handler})
        service = QlooService(_client(transport))
        result = service.affinity_pair("urn:brand:a", "urn:brand:b")
        self.assertEqual(result["data"]["overlap"], 0.5)
        self.assertEqual(result["data"]["shared"], ["urn:tag:y"])

    def test_affinity_batch_pair_count(self):
        transport = FakeTransport({"/v2/insights": _payload(**TAGS_B)})
        service = QlooService(_client(transport))
        result = service.affinity_batch(["e1", "e2", "e3"])
        self.assertEqual(result["data"]["count"], 3)
        self.assertEqual(len(result["data"]["pairs"]), 3)

    def test_empty_results_produce_warning(self):
        transport = FakeTransport({"/search": _payload(**EMPTY)})
        service = QlooService(_client(transport))
        result = service.search("nothing")
        self.assertEqual(result["data"], [])
        self.assertTrue(any("empty_results" in warning for warning in result["warnings"]))

    def test_call_budget_exhausted_raises(self):
        transport = FakeTransport({"/search": _payload(**SEARCH_BODY)})
        service = QlooService(_client(transport, budget=1))
        service.search("first")
        with self.assertRaises(CallBudgetExceeded):
            service.search("second")

    def test_data_rows_are_derived_only(self):
        transport = FakeTransport({"/search": _payload(**SEARCH_BODY)})
        service = QlooService(_client(transport))
        result = service.search("chelsea")
        for row in result["data"]:
            self.assertEqual(set(row.keys()), {"id", "name"} | ({"type"} if "type" in row else set()))
            self.assertNotIn("raw", row)
            self.assertNotIn("payload", row)


if __name__ == "__main__":
    unittest.main()
