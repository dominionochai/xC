import unittest

from backend.methods.verdict import verdict_and_confidence


class VerdictAndConfidenceTests(unittest.TestCase):
    def test_proceed(self):
        result = verdict_and_confidence(58, 4, 12, 0.2, "found", 10, 9)
        self.assertEqual(result["verdict"], "proceed")
        self.assertAlmostEqual(result["confidence"], 0.90)

    def test_remediation_with_penalty(self):
        result = verdict_and_confidence(42, -1, 25, 0.2, "found", 10, 8,
                                        suspect_empty_count=1)
        self.assertEqual(result["verdict"], "proceed_with_remediation")
        self.assertAlmostEqual(result["confidence"], 0.65)

    def test_high_risk(self):
        result = verdict_and_confidence(58, 4, 35, 0.2, "found", 10, 9)
        self.assertEqual(result["verdict"], "high_risk")


if __name__ == "__main__":
    unittest.main()
