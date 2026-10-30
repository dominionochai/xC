import unittest

from backend.methods.bridge_adapter import run_bridge_adapter


class BridgeAdapterTests(unittest.TestCase):
    def _pool(self):
        return [
            {"id": "bridge-a", "category": "category-a", "with_a": 0.75, "with_t": 0.72},
            {"id": "bridge-b", "category": "category-b", "with_a": 0.70, "with_t": 0.68},
            {"id": "bridge-c", "category": "category-c", "with_a": 0.65, "with_t": 0.62},
        ]

    def _category(self, entity_id):
        return {
            "bridge-a": "category-a",
            "bridge-b": "category-b",
            "bridge-c": "category-c",
        }[entity_id]

    def _affinity(self, score):
        return lambda _left, _right: score

    def test_strong_fit_not_needed(self):
        result = run_bridge_adapter(
            fit_affinity=80,
            pool=self._pool(),
            affinity_fn=self._affinity(0.64),
            category_fn=self._category,
        )
        self.assertEqual(result.status, 'not_needed')
        self.assertEqual(result.steps, [])
        self.assertEqual(result.friction_reduction_pct, 0.0)

    def test_weak_fit_found_three_steps(self):
        result = run_bridge_adapter(
            fit_affinity=38,
            pool=self._pool(),
            affinity_fn=self._affinity(0.64),
            category_fn=self._category,
        )
        self.assertEqual(result.status, 'found')
        self.assertEqual([step.name for step in result.steps], ['Familiarization', 'Bridge adoption', 'Conversion'])
        self.assertEqual(len(result.steps), 3)
        self.assertTrue(all(0 <= step.affinity_lift <= 1 for step in result.steps))
        self.assertEqual(result.friction_before, 62)
        self.assertEqual(result.friction_after, 36)
        self.assertLess(abs(result.friction_reduction_pct - 41.9), 0.1)

    def test_no_bridge_found(self):
        result = run_bridge_adapter(
            fit_affinity=38,
            pool=self._pool(),
            affinity_fn=self._affinity(0.31),
            category_fn=self._category,
        )
        self.assertEqual(result.status, 'not_found')
        self.assertEqual(result.steps, [])
        self.assertTrue(result.warnings)


if __name__ == '__main__':
    unittest.main()
