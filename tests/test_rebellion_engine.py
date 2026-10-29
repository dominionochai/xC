"""Offline tests for the rebellion-engine adapter and real method modules."""

import json
import unittest

from backend.methods import rebellion as rebellion_methods
from backend.methods.communities import build_communities
from backend.src.engine.rebellion_engine import (
    map_rebellion_communities,
    run_rebellion_pipeline,
)


class RebellionEngineTests(unittest.TestCase):
    def setUp(self):
        # Exercise the repository's real builder and its actual input contract.
        self.contrast_tags = [
            {"tag": "film", "strength": 2.0, "weight": 0.6},
            {"tag": "jazz", "strength": 1.0, "weight": 0.4},
            {"tag": "hiking", "strength": 2.0, "weight": 0.5},
            {"tag": "cooking", "strength": 1.0, "weight": 0.5},
        ]
        categories = {
            "film": "culture",
            "jazz": "culture",
            "hiking": "outdoors",
            "cooking": "outdoors",
        }
        self.build_result = build_communities(
            self.contrast_tags,
            tag_category_fn=categories.get,
        )
        self.communities = self.build_result["communities"]

    def test_maps_real_builder_output_to_share_name_and_tag_sets(self):
        mapped = map_rebellion_communities(self.build_result)
        self.assertFalse(mapped["guarded"])
        self.assertEqual(len(mapped["communities"]), len(self.communities))
        for original, item in zip(self.communities, mapped["communities"]):
            self.assertEqual(
                set(item), {"share", "name", "community_tag_sets"}
            )
            self.assertAlmostEqual(item["share"], original["core_audience_share"])
            self.assertEqual(item["name"], original["label"])
            self.assertEqual(item["community_tag_sets"], original["basis_tags"])

    def test_non_positive_share_is_clamped_and_reported_as_guarded(self):
        built = [dict(community) for community in self.communities]
        built[0]["core_audience_share"] = 0.0
        mapped = map_rebellion_communities(built)
        self.assertTrue(mapped["guarded"])
        self.assertEqual(mapped["communities"][0]["share"], 0.0)
        self.assertEqual(
            set(mapped["communities"][0]),
            {"share", "name", "community_tag_sets"},
        )

    def test_empty_or_none_input_returns_none(self):
        self.assertIsNone(run_rebellion_pipeline(None))
        self.assertIsNone(run_rebellion_pipeline([]))
        self.assertIsNone(run_rebellion_pipeline({"communities": []}))

    def test_same_seed_produces_byte_identical_distribution(self):
        self.assertTrue(callable(rebellion_methods.simulate_rebellion))
        first = run_rebellion_pipeline(
            self.build_result, alignment_gap=0.5, seed=27, runs=500
        )
        second = run_rebellion_pipeline(
            self.build_result, alignment_gap=0.5, seed=27, runs=500
        )
        first_bytes = json.dumps(
            first["simulation"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        second_bytes = json.dumps(
            second["simulation"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.assertEqual(first_bytes, second_bytes)

    def test_changed_seed_changes_distribution(self):
        first = run_rebellion_pipeline(
            self.build_result, alignment_gap=0.5, seed=27, runs=500
        )
        second = run_rebellion_pipeline(
            self.build_result, alignment_gap=0.5, seed=28, runs=500
        )
        first_bytes = json.dumps(
            first["simulation"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        second_bytes = json.dumps(
            second["simulation"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.assertNotEqual(first_bytes, second_bytes)


if __name__ == "__main__":
    unittest.main()
