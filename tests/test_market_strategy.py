"""Standalone tests for the culture-economics strategy module."""
import unittest
from backend.src.services.market_strategy import (
    NEIGHBORHOOD_NAMES, build_investment_memo, build_transition_campaign,
    estimate_tam, pandering_authenticity_risk, score_neighborhood_affinities,
)

class CampaignTests(unittest.TestCase):
    def test_three_step_chain(self):
        c = build_transition_campaign("Gaming", "Travel", ["Music", "Fashion"])
        self.assertEqual(len(c.steps), 3)
        self.assertEqual([(s.from_category, s.to_category) for s in c.steps],
                         [("Gaming", "Music"), ("Music", "Fashion"), ("Fashion", "Travel")])
    def test_bad_chain(self):
        with self.assertRaises(ValueError): build_transition_campaign("A", "D", ["B"])
        with self.assertRaises(ValueError): build_transition_campaign("A", "a", ["B", "C"])

class AffinityTests(unittest.TestCase):
    def test_supplied_cosine_vectors(self):
        scores = score_neighborhood_affinities({"art": 1, "nightlife": 0}, {
            "SoHo NYC": {"art": 1, "nightlife": 0},
            "Shibuya Tokyo": {"art": 0, "nightlife": 1},
            "Mayfair London": {"art": 1, "nightlife": 1}})
        self.assertEqual(tuple(x.neighborhood for x in scores), NEIGHBORHOOD_NAMES)
        self.assertEqual([x.score for x in scores[:2]], [100.0, 0.0])
        self.assertAlmostEqual(scores[2].score, 70.710678, places=5)
    def test_invalid_vectors(self):
        refs = {name: {"a": 1, "b": 0} for name in NEIGHBORHOOD_NAMES}
        with self.assertRaises(ValueError): score_neighborhood_affinities({"a": 1}, refs)
        with self.assertRaises(ValueError): score_neighborhood_affinities({"a": 0, "b": 0}, refs)

class TAMRiskMemoTests(unittest.TestCase):
    def test_dollarized_tam_and_validation(self):
        self.assertEqual(estimate_tam(500, 120, .1).obtainable_market_usd, 6000)
        with self.assertRaises(ValueError): estimate_tam(-1, 5, .1)
        with self.assertRaises(ValueError): estimate_tam(1, 5, 1.1)
    def test_risk_formula_and_validation(self):
        risk = pandering_authenticity_risk([1, 1], [0, 0], [0, 0])
        self.assertEqual(risk.score, 50.0)
        with self.assertRaises(ValueError): pandering_authenticity_risk([1], [], [1])
        with self.assertRaises(ValueError): pandering_authenticity_risk([1.1], [0], [0])
    def test_memo_pdf_header_xref_and_content(self):
        tam = estimate_tam(1000, 80, .05)
        affinities = score_neighborhood_affinities({"culture": 1, "utility": 0}, {
            "SoHo NYC": {"culture": 1, "utility": 0},
            "Shibuya Tokyo": {"culture": 0, "utility": 1},
            "Mayfair London": {"culture": 1, "utility": 1}})
        risk = pandering_authenticity_risk([.8, .2], [.1, 0], [.6, .3])
        memo = build_investment_memo("Example Co", "Evaluate a supplied culture-led thesis.", tam, affinities, risk)
        self.assertIn("$80,000.00", memo.markdown)
        pdf = memo.pdf_bytes
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf.endswith(b"%%EOF\n"))
        offset = int(pdf.rsplit(b"startxref\n", 1)[1].splitlines()[0])
        self.assertEqual(pdf[offset:offset+4], b"xref")
        self.assertIn(b"/Type /Page", pdf)

if __name__ == "__main__":
    unittest.main()
