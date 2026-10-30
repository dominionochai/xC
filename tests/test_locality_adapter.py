"""P6 offline tests for the locality adapter (backend-computed metrics)."""
import unittest
from backend.methods.locality_adapter import _IDENTICAL_CAVEAT, run_locality_adapter
from backend.src.contract_locality import LocalityResult
NEIGHBORHOOD_CAVEAT = "neighborhood granularity not supported by the data provider"
def _fns(region=61, heatmap=None, city=None):
    return (
        (lambda _r: region) if region is not None else (lambda _r: None),
        (lambda _r: heatmap),
        (lambda _r: city) if city is not None else (lambda _r: None),
    )
class LocalityAdapterTests(unittest.TestCase):
    def test_region_query_success_and_backend_metrics(self):
        result = run_locality_adapter(*_fns(region=61), regions=["soho_nyc"], global_affinity=52)
        self.assertIsInstance(result, LocalityResult)
        self.assertEqual(result.status, "resolved")
        row = result.regions[0]
        self.assertEqual(row.affinity, 61)
        self.assertEqual(row.ladder_level, 1)
        self.assertEqual(row.friction, 39)
        self.assertEqual(row.delta_vs_global, 9)
        self.assertIsNone(row.caveat)
    def test_heatmap_cosine_success(self):
        result = run_locality_adapter(*_fns(region=None, heatmap=([1.0, 1.0], [1.0, 0.0])), regions=["soho_nyc"])
        self.assertEqual(result.status, "resolved")
        row = result.regions[0]
        self.assertEqual(row.ladder_level, 2)
        self.assertAlmostEqual(row.affinity, 70.7, places=1)
        self.assertIsNone(row.caveat)
    def test_city_fallback_caveat_and_warning(self):
        result = run_locality_adapter(*_fns(region=None, city=47), regions=["soho_nyc"])
        self.assertEqual(result.status, "resolved")
        row = result.regions[0]
        self.assertEqual(row.ladder_level, 3)
        self.assertEqual(row.caveat, NEIGHBORHOOD_CAVEAT)
        self.assertEqual(row.sample_note, NEIGHBORHOOD_CAVEAT)
        self.assertTrue(any(NEIGHBORHOOD_CAVEAT in w for w in result.warnings))
    def test_all_levels_failed(self):
        result = run_locality_adapter(*_fns(region=None, heatmap=None, city=None), regions=["soho_nyc"])
        self.assertEqual(result.status, "failed")
        row = result.regions[0]
        self.assertIsNone(row.affinity)
        self.assertEqual(row.reason, "all_levels_failed")
        self.assertTrue(any("all_levels_failed" in w for w in result.warnings))
    def test_partial_result_and_delta_sum_check(self):
        result = run_locality_adapter(
            lambda r: 61 if r == "soho_nyc" else None,
            lambda _r: None,
            lambda _r: None,
            regions=["soho_nyc", "shibuya_tokyo"],
            global_affinity=52,
        )
        self.assertEqual(result.status, "partial")
        by_region = {row.region: row for row in result.regions}
        self.assertEqual(by_region["soho_nyc"].affinity, 61)
        self.assertEqual(by_region["soho_nyc"].delta_vs_global, 9)
        self.assertIsNone(by_region["shibuya_tokyo"].affinity)
        for row in result.regions:
            if row.affinity is not None:
                self.assertAlmostEqual(row.delta_vs_global, row.affinity - 52)
    def test_identical_default_regions_trigger_suspect_empty_caveat(self):
        result = run_locality_adapter(*_fns(region=55), regions=["soho_nyc", "shibuya_tokyo", "mayfair_london"], global_affinity=52)
        self.assertEqual(result.status, "resolved")
        self.assertTrue(all(row.caveat == _IDENTICAL_CAVEAT for row in result.regions))
        self.assertTrue(all(row.sample_note == _IDENTICAL_CAVEAT for row in result.regions))
        self.assertTrue(any(_IDENTICAL_CAVEAT in w for w in result.warnings))
        self.assertTrue(any(p.get("source") == "locality_adapter.suspect_empty" and p.get("triggered") for p in result.provenance))
if __name__ == "__main__":
    unittest.main()
