"""Offline, deterministic contract tests for the exported Qloo helpers."""

import json
import unittest
from pathlib import Path

from backend.qloo import (
    is_empty_results,
    is_suspect_empty,
    normalize_results,
    normalize_entities,
    result_items,
    shape_paths,
)


SYNTHETIC_DIR = Path(__file__).parent / "synthetic"
INLINE_BASIC = {
    "results": [
        {
            "entity": {
                "entity_id": "urn:entity:brand:1",
                "name": "Alpha",
                "type": "brand",
            },
            "score": 0.9,
        }
    ]
}
INLINE_SURPRISE = {"unrelated": 1}


def load_fixture_or_inline(filename, inline_value):
    """Load an optional JSON fixture, falling back to an inline dict."""
    path = SYNTHETIC_DIR / filename
    if path.is_file():
        with path.open(encoding="utf-8") as fixture_file:
            return json.load(fixture_file)
    return inline_value


class QlooNormalizeTests(unittest.TestCase):
    def test_normalize_results_keeps_a_valid_entity_result(self):
        normalized = normalize_results(INLINE_BASIC)
        self.assertIsInstance(normalized, list)
        self.assertTrue(normalized)
        self.assertTrue(all(isinstance(item, dict) for item in normalized))

    def test_normalize_results_surprise_inputs_are_non_raising_and_stable(self):
        for value in ({"unrelated": 1}, [1, 2], "x", None):
            with self.subTest(value=value):
                first = normalize_results(value)
                second = normalize_results(value)
                self.assertEqual(first, second)

    def test_normalize_entities_is_non_raising_and_stable(self):
        for value in (INLINE_BASIC, {"entities": [{"name": "Alpha"}]}, [1, 2], None):
            with self.subTest(value=value):
                first = normalize_entities(value)
                second = normalize_entities(value)
                self.assertEqual(first, second)

    def test_is_empty_results_recognizes_empty_and_nonempty_results(self):
        self.assertTrue(is_empty_results({"results": []}))
        self.assertFalse(is_empty_results({"results": [{"entity": {}}]}))

    def test_is_empty_results_surprise_shapes_are_false_and_non_raising(self):
        for value in ({"unrelated": 1}, [1, 2], "x", None):
            with self.subTest(value=value):
                first = is_empty_results(value)
                second = is_empty_results(value)
                self.assertFalse(first)
                self.assertEqual(first, second)

    def test_is_suspect_empty_returns_bool_and_recognizes_empty_results(self):
        self.assertIs(is_suspect_empty({"results": []}), True)
        for value in ({"results": [{"entity": {}}]}, {"unrelated": 1}, [1, 2], "x", None):
            with self.subTest(value=value):
                self.assertIsInstance(is_suspect_empty(value), bool)

    def test_shape_paths_returns_sorted_paths_and_accepts_none(self):
        paths = shape_paths({"a": {"b": 1}})
        self.assertIsInstance(paths, list)
        self.assertEqual(paths, sorted(paths))
        self.assertIn("$.a.b", paths)
        self.assertIsInstance(shape_paths(None), list)

    def test_result_items_iterates_a_results_list(self):
        items = list(result_items({"results": [{"entity": {}}, {"entity": {}}]}))
        self.assertEqual(len(items), 2)

    def test_synthetic_fixtures_load_or_use_inline_fallbacks(self):
        fixtures = (
            ("qloo_search_basic.json", INLINE_BASIC),
            ("qloo_surprise_shape.json", INLINE_SURPRISE),
        )
        for filename, fallback in fixtures:
            with self.subTest(filename=filename):
                fixture_path = SYNTHETIC_DIR / filename
                value = load_fixture_or_inline(filename, fallback)
                if fixture_path.is_file():
                    self.assertIsNotNone(value)
                else:
                    self.assertEqual(value, fallback)
                # Exercise either the real fixture or its inline substitute without
                # making the suite depend on optional synthetic files being present.
                normalize_results(value)
                self.assertIsInstance(is_empty_results(value), bool)


if __name__ == "__main__":
    unittest.main()
