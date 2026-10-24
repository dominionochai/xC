"""Offline tests for entity resolution."""
import unittest

from backend.src.engine.resolve import resolve


class FakeQloo:
    def __init__(self, rows=None, fallback=None):
        self.rows = rows or []
        self.fallback = fallback
        self.calls = []

    def search_entities(self, query, limit=10):
        self.calls.append(("search_entities", query, limit))
        return self.rows

    def get_entity(self, query):
        self.calls.append(("get_entity", query))
        return self.fallback


class ResolveTests(unittest.TestCase):
    def test_exact_name_dominates_popularity(self):
        qloo = FakeQloo([
            {"id": "popular", "name": "Other Artist", "popularity": 99},
            {"id": "exact", "name": "Blue Note", "popularity": 2},
        ])
        result = resolve(qloo, "Blue Note")
        self.assertEqual(result["entity"]["id"], "exact")
        self.assertTrue(result["evidence"][0]["exact"])
        self.assertEqual(result["provenance"][0]["source"], "qloo")

    def test_popularity_breaks_ties_between_exact_matches(self):
        qloo = FakeQloo([
            {"id": "low", "name": "Blue Note", "popularity": 1},
            {"id": "high", "name": "Blue Note", "popularity": 8},
        ])
        self.assertEqual(resolve(qloo, "blue note")["entity"]["id"], "high")

    def test_direct_fallback_when_search_is_empty(self):
        qloo = FakeQloo([], {"id": "direct", "name": "Unknown"})
        result = resolve(qloo, "Unknown")
        self.assertEqual(result["entity"]["id"], "direct")
        self.assertEqual([call[0] for call in qloo.calls], ["search_entities", "get_entity"])
        self.assertIn("fallback_resolution", [item["kind"] for item in result["evidence"]])

    def test_budget_is_checked_before_qloo_search(self):
        qloo = FakeQloo([{"id": "x", "name": "X"}])
        def exhausted():
            return False
        result = resolve(qloo, "X", budget=exhausted)
        self.assertEqual(qloo.calls, [])
        self.assertIn("search_failed: RuntimeError", result["warnings"])

    def test_empty_query_does_not_call_qloo(self):
        qloo = FakeQloo()
        result = resolve(qloo, "   ")
        self.assertIsNone(result["entity"])
        self.assertEqual(qloo.calls, [])
        self.assertIn("empty_query", result["warnings"])


if __name__ == "__main__":
    unittest.main()
