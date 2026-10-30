import unittest

from backend.methods.tam import tam_expansion


class TamExpansionTests(unittest.TestCase):
    def setUp(self):
        self.sources = {
            name: {"url": "https://example.test/" + name, "year": year}
            for name, year in (("pop", 2024), ("penetration", 2025), ("spend", 2024),
                               ("affinity", 2024), ("ip_loss_base", 2024),
                               ("ip_loss_low", 2024), ("ip_loss_high", 2024))
        }

    def test_sourced_synthetic_region(self):
        result = tam_expansion([{
            "region": "Example", "pop": 1_000_000, "penetration": 0.10,
            "spend": 200, "affinity": 60, "ip_loss_base": 0.20,
            "ip_loss_low": 0.20, "ip_loss_high": 0.20, "sources": self.sources,
        }])
        self.assertEqual(result["expansion"]["Example"]["reach"], 100_000)
        self.assertEqual(result["expansion"]["Example"]["expansion"], 9_600_000)
        self.assertFalse(result["tam_partial"])

    def test_missing_source_is_partial_and_warned(self):
        sources = dict(self.sources)
        del sources["spend"]
        result = tam_expansion([{
            "region": "Missing", "pop": 1_000_000, "penetration": 0.10,
            "spend": 200, "affinity": 60, "ip_loss_base": 0.20,
            "ip_loss_low": 0.20, "ip_loss_high": 0.20, "sources": sources,
        }])
        self.assertTrue(result["tam_partial"])
        self.assertTrue(result["expansion"]["Missing"]["partial"])
        self.assertIn("missing_source:spend:Missing", result["warnings"])

    def test_all_null(self):
        self.assertIsNone(tam_expansion([{"region": "Empty"}])["tam"])


if __name__ == "__main__":
    unittest.main()
