"""Offline tests for fit scoring."""
import unittest

from backend.src.engine.fit import fit, normalize_score


class FakeQloo:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def get_fit(self):
        self.calls += 1
        return self.payload


class FitTests(unittest.TestCase):
    def test_weighted_normalized_mean(self):
        qloo = FakeQloo({"components": [
            {"name": "music", "score": 80, "weight": 3},
            {"name": "travel", "score": 0.4, "weight": 1},
        ]})
        result = fit(qloo)
        self.assertAlmostEqual(result["score"], 0.7)
        self.assertEqual(result["coverage"], 1.0)
        self.assertEqual(qloo.calls, 1)
        self.assertEqual(result["formula"], "weighted_mean(normalized_scores)")

    def test_invalid_and_missing_values_are_excluded(self):
        qloo = FakeQloo({"signals": [
            {"name": "valid", "affinity": 1.2},
            {"name": "missing", "score": None},
            {"name": "invalid", "score": "nan"},
        ]})
        result = fit(qloo)
        self.assertEqual(result["score"], 1.0)
        self.assertAlmostEqual(result["coverage"], 1 / 3)
        self.assertEqual(result["components"][1]["score"], None)
        self.assertEqual(len(result["evidence"]), 3)

    def test_explicit_weights_override_component_weights(self):
        result = fit(FakeQloo({"components": [
            {"name": "a", "score": 0.2, "weight": 100},
            {"name": "b", "score": 0.8, "weight": 100},
        ]}), weights={"a": 3, "b": 1})
        self.assertAlmostEqual(result["score"], 0.35)

    def test_budget_checked_before_qloo_call(self):
        qloo = FakeQloo({"score": 0.5})
        result = fit(qloo, budget=lambda: False)
        self.assertEqual(qloo.calls, 0)
        self.assertIsNone(result["score"])
        self.assertIn("qloo_fit_failed: RuntimeError", result["warnings"])

    def test_normalize_score_handles_clamps_and_invalid_values(self):
        self.assertEqual(normalize_score(-2), 0.0)
        self.assertEqual(normalize_score(125), 1.0)
        self.assertEqual(normalize_score(0.25), 0.25)
        self.assertIsNone(normalize_score("not-a-number"))


if __name__ == "__main__":
    unittest.main()
