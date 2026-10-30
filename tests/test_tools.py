"""Offline tests for the guarded Qloo tool registry."""
import json
import unittest

from agents.events import EventBus
from agents.tools import (
    REGISTRY,
    qloo_affinity,
    qloo_demographics,
    qloo_heatmap,
    qloo_search,
    qloo_tags,
    qloo_trending,
    verify_channel,
)
from backend.src.engine.budget import Budget


class FakeQloo:
    def __init__(self):
        self.call_count = 0
        self.event_bus = EventBus()

    def search(self, **kwargs):
        return {"results": [{"id": "entity-1", **kwargs}]}

    def affinity(self, **kwargs):
        return {"results": [kwargs]}

    def tags(self, **kwargs):
        return ["tag-a"]

    def demographics(self, **kwargs):
        return {"data": [{"age": "adult"}]}

    def heatmap(self, **kwargs):
        return [{"region": kwargs["region"], "score": 1}]

    def trending(self, **kwargs):
        return {"items": [{"category": kwargs.get("category")}]}

    def verify_channel(self, **kwargs):
        return {"verified": True, **kwargs}


class ExhaustedBudget:
    def is_exhausted(self, _tool_name):
        return True


class ToolTests(unittest.TestCase):
    def test_registry_names_and_schema_properties(self):
        expected = {
            "qloo_search": {"query", "entity_type"},
            "qloo_affinity": {"entity_a", "entity_b"},
            "qloo_tags": {"entity_id"},
            "qloo_demographics": {"entity_id"},
            "qloo_heatmap": {"region"},
            "qloo_trending": {"category"},
            "verify_channel": {"channel_name", "contact"},
        }
        self.assertEqual(len(expected), 7)
        self.assertEqual(set(REGISTRY), set(expected))
        self.assertEqual({spec.name for spec in REGISTRY.values()}, set(expected))
        for name, properties in expected.items():
            with self.subTest(tool=name):
                self.assertEqual(REGISTRY[name].name, name)
                self.assertEqual(
                    set(REGISTRY[name].json_schema["properties"]), properties
                )

    def test_wrappers_emit_call_then_result_and_forward_fields(self):
        qloo, budget = FakeQloo(), Budget(40)
        calls = [
            ("qloo_search", qloo_search, {"query": "music", "entity_type": "artist"}),
            ("qloo_affinity", qloo_affinity, {"entity_a": "a", "entity_b": "b"}),
            ("qloo_tags", qloo_tags, {"entity_id": "e1"}),
            ("qloo_demographics", qloo_demographics, {"entity_id": "e1"}),
            ("qloo_heatmap", qloo_heatmap, {"region": "US"}),
            ("qloo_trending", qloo_trending, {"category": "music"}),
            (
                "verify_channel",
                verify_channel,
                {"channel_name": "example", "contact": "site"},
            ),
        ]
        results = {}
        for name, wrapper, kwargs in calls:
            results[name] = wrapper(qloo, budget, **kwargs)
            self.assertTrue(results[name]["ok"])

        events = qloo.event_bus.get_run_events()
        expected_types = [
            event_type
            for _ in calls
            for event_type in ("tool.call", "tool.result")
        ]
        self.assertEqual([event["type"] for event in events], expected_types)

        for index, (name, _wrapper, kwargs) in enumerate(calls):
            with self.subTest(tool=name):
                call_event = events[index * 2]
                result_event = events[index * 2 + 1]
                call_payload = json.loads(call_event["payload_preview"])
                result_payload = json.loads(result_event["payload_preview"])
                self.assertEqual(call_payload["tool"], name)
                self.assertEqual(call_payload["parameters"], sorted(kwargs))
                self.assertEqual(result_payload["tool"], name)
                self.assertEqual(result_payload["status"], "ok")

        self.assertEqual(
            results["verify_channel"],
            {"verified": True, "channel_name": "example", "contact": "site"},
        )
        self.assertEqual(qloo.call_count, len(calls))

    def test_exhausted_budget_has_no_tool_result_event(self):
        qloo = FakeQloo()
        result = qloo_search(qloo, ExhaustedBudget(), query="ignored")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "budget_exhausted:qloo_search")
        events = qloo.event_bus.get_run_events()
        self.assertEqual(events, [])
        self.assertNotIn("tool.result", [event["type"] for event in events])
        self.assertEqual(qloo.call_count, 0)


if __name__ == "__main__":
    unittest.main()
