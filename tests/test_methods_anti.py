"""Offline unittest coverage for anti-co-occurrence scoring."""
import unittest

import backend.methods as methods
from backend.methods.anti import anti_cooccurrence


class AntiCooccurrenceTests(unittest.TestCase):
    def test_three_affinities_cutoff_and_anti_share(self):
        affinities = {("acquirer", "m1"): .12,
                      ("acquirer", "m2"): .18,
                      ("acquirer", "m3"): .09}
        result = anti_cooccurrence({"auto": {
            "target_entity_id": "target", "acquirer_entity_id": "acquirer",
            "target_items": ["m1", "m2", "m3"], "acquirer_items": []}},
            lambda source, item: affinities[(source, item)])
        self.assertAlmostEqual(result["cutoff"], .15)
        self.assertAlmostEqual(result["domains"]["auto"]["Anti"], 2 / 3)
        self.assertFalse(result["domains"]["auto"]["dropped"])
        self.assertEqual(result["normalization"], "minmax")
        self.assertEqual(result["recommendation"], "rank")

    def test_directional_means_and_item_cap(self):
        values = {("acquirer", "t1"): .4, ("acquirer", "t2"): .6,
                  ("target", "a1"): .2, ("target", "a2"): .8}
        result = anti_cooccurrence({"d": {
            "target_id": "target", "acquirer_id": "acquirer",
            "target_items": ["t1", "t2", "t3"],
            "acquirer_items": ["a1", "a2"]}},
            lambda source, item: values[(source, item)], signature_items_per_domain=2)
        self.assertAlmostEqual(result["domains"]["d"]["F"], .5)
        self.assertAlmostEqual(result["domains"]["d"]["C"], .5)

    def test_small_domain_drops_axis_and_short_sample_flags_fallback(self):
        result = anti_cooccurrence({"d": {
            "target_entity_id": "target", "acquirer_entity_id": "acquirer",
            "target_items": ["one", "two"], "acquirer_items": []}},
            lambda source, item: .3)
        row = result["domains"]["d"]
        self.assertTrue(row["dropped"])
        self.assertIn("warning", row["reason"])
        self.assertIsNone(row["Anti"])
        self.assertTrue(result["axis_uses_min_observed_fallback"])
        self.assertAlmostEqual(result["cutoff"], .3)

    def test_empty_input_is_safe(self):
        self.assertEqual(anti_cooccurrence({}, lambda *_: 1), {
            "domains": {}, "cutoff": None, "normalization": "raw",
            "cutoff_fallback": False, "axis_uses_min_observed_fallback": False,
            "cutoff_note": None})

    def test_function_is_reachable_from_backend_methods_package(self):
        self.assertTrue(callable(anti_cooccurrence))
        self.assertIsNotNone(methods)


if __name__ == "__main__":
    unittest.main()
