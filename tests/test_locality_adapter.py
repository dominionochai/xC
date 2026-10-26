"""Offline tests for the P6 locality contract adapter."""

import os
import sys
import unittest


_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
for _path in (_BACKEND, os.path.join(_BACKEND, 'src')):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from methods.locality_adapter import DEFAULT_REGIONS, run_locality_adapter


_NEIGHBORHOOD_CAVEAT = 'neighborhood granularity not supported by the data provider'
_IDENTICAL_CAVEAT = (
    'identical affinity across all regions: location filter may be ignored for this entity type'
)


class LocalityAdapterTests(unittest.TestCase):
    def test_region_query_success_and_backend_metrics(self):
        result = run_locality_adapter(
            lambda region: 61,
            lambda region: None,
            lambda region: None,
            regions=['soho_nyc'],
            global_affinity=52,
        )
        row = result.regions[0]
        self.assertEqual(result.status, 'resolved')
        self.assertEqual(row.ladder_level, 1)
        self.assertEqual(row.affinity, 61)
        self.assertEqual(row.friction, 39)
        self.assertEqual(row.delta_vs_global, 9)
        self.assertIsNone(row.caveat)

    def test_heatmap_cosine_success(self):
        result = run_locality_adapter(
            lambda region: None,
            lambda region: ([1, 1], [1, 0]),
            lambda region: None,
            regions=['soho_nyc'],
        )
        row = result.regions[0]
        self.assertEqual(result.status, 'resolved')
        self.assertEqual(row.ladder_level, 2)
        self.assertAlmostEqual(row.affinity, 70.7, places=1)
        self.assertIsNone(row.caveat)

    def test_city_fallback_caveat_and_warning(self):
        result = run_locality_adapter(
            lambda region: None,
            lambda region: None,
            lambda region: 47,
            regions=['soho_nyc'],
        )
        row = result.regions[0]
        self.assertEqual(result.status, 'resolved')
        self.assertEqual(row.ladder_level, 3)
        self.assertEqual(row.caveat, _NEIGHBORHOOD_CAVEAT)
        self.assertEqual(row.sample_note, _NEIGHBORHOOD_CAVEAT)
        self.assertTrue(any(_NEIGHBORHOOD_CAVEAT in warning for warning in result.warnings))

    def test_all_levels_failed(self):
        result = run_locality_adapter(
            lambda region: None,
            lambda region: None,
            lambda region: None,
            regions=['soho_nyc'],
        )
        self.assertEqual(result.status, 'failed')
        self.assertIsNone(result.regions[0].affinity)
        self.assertEqual(result.regions[0].reason, 'all_levels_failed')
        self.assertIn('soho_nyc:all_levels_failed', result.warnings)

    def test_partial_result_and_delta_sum_check(self):
        result = run_locality_adapter(
            lambda region: 61 if region == 'soho_nyc' else None,
            lambda region: None,
            lambda region: None,
            regions=['soho_nyc', 'shibuya_tokyo'],
            global_affinity=52,
        )
        self.assertEqual(result.status, 'partial')
        self.assertIn('shibuya_tokyo:all_levels_failed', result.warnings)
        for row in result.regions:
            if row.affinity is not None:
                self.assertIsNotNone(row.delta_vs_global)
                self.assertEqual(row.delta_vs_global, row.affinity - result.global_affinity)

    def test_identical_default_regions_trigger_suspect_empty_caveat(self):
        result = run_locality_adapter(
            lambda region: 55,
            lambda region: None,
            lambda region: None,
        )
        self.assertEqual([row.region for row in result.regions], list(DEFAULT_REGIONS))
        self.assertTrue(all(row.caveat == _IDENTICAL_CAVEAT for row in result.regions))
        self.assertTrue(all(row.sample_note == _IDENTICAL_CAVEAT for row in result.regions))
        self.assertIn(_IDENTICAL_CAVEAT, result.warnings)
        suspect = next(
            item for item in result.provenance
            if item.get('source') == 'locality_adapter.suspect_empty'
        )
        self.assertIs(suspect['triggered'], True)


if __name__ == '__main__':
    unittest.main()
