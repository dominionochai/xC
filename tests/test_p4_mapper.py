"""Integration tests for mapping audience communities into rebellion simulation."""

import unittest

from backend.methods.communities import build_communities
from backend.methods.rebellion import (
    map_build_communities_to_rebellion,
    simulate_rebellion,
)


class RebellionMapperTests(unittest.TestCase):
    def test_real_weak_fit_pair_builder_output_maps_and_simulates(self):
        contrast_tags = [
            {"tag": "a", "strength": 4.0, "weight": 1.0},
            {"tag": "b", "strength": 3.0, "weight": 1.0},
            {"tag": "c", "strength": 2.0, "weight": 1.0},
            {"tag": "d", "strength": 1.0, "weight": 1.0},
        ]
        weak_fit_pairs = {frozenset({"a", "c"}), frozenset({"b", "d"})}

        def co_occurrence(tag_a, tag_b):
            return 1.0 if frozenset({tag_a, tag_b}) in weak_fit_pairs else 0.0

        built = build_communities(
            contrast_tags,
            tag_category_fn=lambda _tag: "one-category",
            max_communities=2,
            co_occurrence_fn=co_occurrence,
        )
        self.assertEqual(built["method"], "co_weighting")
        self.assertTrue(built["degraded"])
        self.assertEqual(len(built["communities"]), 2)

        mapped = map_build_communities_to_rebellion(built)
        self.assertEqual(len(mapped), 2)
        source_by_name = {row["label"]: row for row in built["communities"]}
        for item in mapped:
            source = source_by_name[item["name"]]
            self.assertEqual(item["share"], source["core_audience_share"])
            self.assertEqual(item["community_tag_sets"], source["basis_tags"])

        # The mapper intentionally returns the simulation share and tag set;
        # anti_strength is copied from the builder row for simulate_rebellion.
        simulation_communities = [
            {
                "name": item["name"],
                "share": item["share"],
                "anti_strength": source_by_name[item["name"]]["anti_strength"],
            }
            for item in mapped
        ]
        result = simulate_rebellion(
            simulation_communities,
            alignment_gap=0.5,
            runs=200,
            seed=42,
            fit_ratios=[0.9, 0.5],
            community_tag_sets=[item["community_tag_sets"] for item in mapped],
        )
        simulation = result["simulation"]
        self.assertIsNotNone(simulation)
        histogram = simulation["histogram"]
        self.assertEqual(histogram["bins"], 24)
        self.assertEqual(len(histogram["counts"]), 24)
        self.assertEqual(sum(histogram["counts"]), 200)

    def test_list_input_skips_zero_and_negative_shares(self):
        mapped = map_build_communities_to_rebellion(
            [
                {"label": "positive", "core_audience_share": 0.25, "basis_tags": ["a"]},
                {"label": "zero", "core_audience_share": 0.0, "basis_tags": ["b"]},
                {"label": "negative", "core_audience_share": -0.1, "basis_tags": ["c"]},
            ]
        )
        self.assertEqual(
            mapped,
            [{"name": "positive", "share": 0.25, "community_tag_sets": ["a"]}],
        )

    def test_empty_builder_output_returns_empty_list(self):
        self.assertEqual(map_build_communities_to_rebellion({"communities": []}), [])
        self.assertEqual(map_build_communities_to_rebellion([]), [])


if __name__ == "__main__":
    unittest.main()
