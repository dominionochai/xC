"""Offline tests for audience community construction."""
import unittest

from backend.methods import build_communities


class BuildCommunitiesTests(unittest.TestCase):
    def test_groups_tags_by_three_categories_and_reports_core_share(self):
        contrasts = [
            {"tag": "c1", "strength": 1.0, "weight": 0.5},
            {"tag": "c2", "strength": 1.0, "weight": 0.3},
            {"tag": "c3", "strength": 1.0, "weight": 0.3},
            {"tag": "c4", "strength": 1.0, "weight": 0.2},
            {"tag": "c5", "strength": 1.0, "weight": 0.4},
            {"tag": "c6", "strength": 1.0, "weight": 0.3},
        ]
        categories = {
            "c1": "X",
            "c2": "X",
            "c3": "Y",
            "c4": "Y",
            "c5": "Z",
            "c6": "Z",
        }

        result = build_communities(contrasts, tag_category_fn=categories.get)

        self.assertEqual(result["method"], "category")
        self.assertFalse(result["degraded"])
        communities = {
            frozenset(community["basis_tags"]): community
            for community in result["communities"]
        }
        self.assertEqual(
            set(communities),
            {
                frozenset({"c1", "c2"}),
                frozenset({"c3", "c4"}),
                frozenset({"c5", "c6"}),
            },
        )
        self.assertAlmostEqual(
            communities[frozenset({"c1", "c2"})]["core_audience_share"], 0.40
        )
        self.assertAlmostEqual(
            communities[frozenset({"c3", "c4"})]["core_audience_share"], 0.25
        )
        self.assertAlmostEqual(
            communities[frozenset({"c5", "c6"})]["core_audience_share"], 0.35
        )

    def test_single_category_falls_back_to_co_weighting(self):
        contrasts = [
            {"tag": "a", "strength": 4.0, "weight": 1.0},
            {"tag": "b", "strength": 3.0, "weight": 1.0},
            {"tag": "c", "strength": 2.0, "weight": 1.0},
            {"tag": "d", "strength": 1.0, "weight": 1.0},
        ]
        co_occurring_pairs = {frozenset({"a", "c"}), frozenset({"b", "d"})}

        def co_occurrence(tag_a, tag_b):
            return 1.0 if frozenset({tag_a, tag_b}) in co_occurring_pairs else 0.0

        result = build_communities(
            contrasts,
            tag_category_fn=lambda _tag: "one-category",
            max_communities=2,
            co_occurrence_fn=co_occurrence,
        )

        self.assertEqual(result["method"], "co_weighting")
        self.assertTrue(result["degraded"])
        self.assertEqual(len(result["communities"]), 2)
        communities = {
            frozenset(community["basis_tags"]): community
            for community in result["communities"]
        }
        self.assertEqual(set(communities), {frozenset({"a", "c"}), frozenset({"b", "d"})})
        self.assertAlmostEqual(
            communities[frozenset({"a", "c"})]["core_audience_share"], 0.5
        )
        self.assertAlmostEqual(
            communities[frozenset({"b", "d"})]["core_audience_share"], 0.5
        )


if __name__ == "__main__":
    unittest.main()
