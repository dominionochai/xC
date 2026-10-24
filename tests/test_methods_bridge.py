"""Deterministic offline tests for the M6 bridge builder."""

import unittest

from backend.methods.bridge import build_bridge


class BuildBridgeTests(unittest.TestCase):
    @staticmethod
    def _pool():
        # Three distinct categories allow a valid triple under the category rule.
        return [
            {
                "id": "bridge-a",
                "category": "category-a",
                "with_a": "A connects to bridge-a",
                "with_t": "bridge-a connects to T",
            },
            {
                "id": "bridge-b",
                "category": "category-b",
                "with_a": "A connects to bridge-b",
                "with_t": "bridge-b connects to T",
            },
            {
                "id": "bridge-c",
                "category": "category-c",
                "with_a": "A connects to bridge-c",
                "with_t": "bridge-c connects to T",
            },
        ]

    @classmethod
    def _build(cls, edge_affinity, fit_affinity=38):
        def affinity_fn(*_args):
            # Fixed edge score keeps the test deterministic and exercises the
            # builder's triple-scoring logic rather than an external model.
            return edge_affinity

        return build_bridge(
            fit_affinity=fit_affinity,
            pool=cls._pool(),
            affinity_fn=affinity_fn,
            category_fn=lambda item: item["category"],
        )

    @staticmethod
    def _field(result, name):
        # Accept either a mapping result or a result object/dataclass.
        if isinstance(result, dict):
            return result[name]
        return getattr(result, name)

    def test_finds_bridge_and_reports_friction_reduction(self):
        result = self._build(edge_affinity=0.64)

        self.assertEqual(self._field(result, "status"), "found")
        self.assertAlmostEqual(self._field(result, "weakest_edge"), 0.64)
        self.assertEqual(self._field(result, "friction_before"), 62)
        self.assertEqual(self._field(result, "friction_after"), 36)
        self.assertAlmostEqual(self._field(result, "friction_reduction_pct"), 41.9, places=1)

    def test_does_not_find_bridge_when_best_weakest_edge_is_too_low(self):
        # Direct fit is still 38; the best available triple has a weakest edge
        # of only 0.31, so it must not be reported as found.
        result = self._build(edge_affinity=0.31, fit_affinity=38)

        self.assertEqual(self._field(result, "status"), "not_found")

    def test_high_direct_fit_means_bridge_is_not_needed(self):
        result = self._build(edge_affinity=0.64, fit_affinity=70)

        self.assertEqual(self._field(result, "status"), "not_needed")


if __name__ == "__main__":
    unittest.main()
