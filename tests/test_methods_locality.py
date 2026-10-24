"""Offline tests for backend.methods.locality
.locality_analysis."""

import unittest

from backend.methods.locality import locality_analysis


class LocalityAnalysisTests(unittest.TestCase):
    def test_region_query_sets_affinity_and_global_delta(self):
        result = locality_analysis(
            region_query_fn=lambda _region: 61,
            heatmap_fn=lambda _region: None,
            city_fallback_fn=lambda _region: None,
            regions=["soho_nyc"],
            global_affinity=52,
        )

        self.assertEqual(result["affinity"], 61)
        self.assertEqual(result["ladder_level"], 1)
        self.assertEqual(result["delta_vs_global"], 9)
        self.assertEqual(result["friction"], 39)

    def test_city_fallback_reports_neighborhood_granularity_caveat(self):
        result = locality_analysis(
            region_query_fn=lambda _region: None,
            heatmap_fn=lambda _region: None,
            city_fallback_fn=lambda _region: 47,
            regions=["soho_nyc"],
        )

        self.assertEqual(result["affinity"], 47)
        self.assertEqual(result["ladder_level"], 3)
        caveat = "neighborhood granularity not supported by the data provider"
        self.assertEqual(result["caveat"], caveat)
        self.assertEqual(result["sample_note"], caveat)

    def test_all_levels_failed_returns_none_affinity_and_reason(self):
        result = locality_analysis(
            region_query_fn=lambda _region: None,
            heatmap_fn=lambda _region: None,
            city_fallback_fn=lambda _region: None,
            regions=["soho_nyc"],
        )

        self.assertIsNone(result["affinity"])
        self.assertEqual(result["reason"], "all_levels_failed")


if __name__ == "__main__":
    unittest.main()
