"""Tests for deterministic investment memo Markdown and PDF exports."""
import unittest

from backend.src.services.memo_export import (
    render_investment_memo_markdown,
    render_investment_memo_pdf,
)


class MemoExportTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "acquirer": "Northstar Capital",
            "target": "Juniper Labs",
            "tam": {"tam_usd": 1234567890, "currency": "USD"},
            "risk": {"score": 27.5, "level": "medium"},
            "regional_scores": {"EMEA": 81.25, "North America": 74.0},
            "bridge_steps": ["Creator tools", "Community platform", "Juniper Labs"],
            "evidence_references": [
                {"id": "ev-104", "url": "https://example.test/source/104", "claim": "Market growth"}
            ],
        }

    def test_markdown_contains_report_values_and_is_deterministic(self):
        markdown = render_investment_memo_markdown(self.report)
        self.assertEqual(markdown, render_investment_memo_markdown(self.report))
        for expected in (
            "Northstar Capital", "Juniper Labs", "1234567890", "medium", "27.5",
            "EMEA", "81.25", "North America", "Creator tools", "Community platform",
            "ev-104", "https://example.test/source/104", "Market growth",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, markdown)

    def test_pdf_has_header_xref_and_report_text(self):
        pdf = render_investment_memo_pdf(self.report)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf.endswith(b"%%EOF\n"))
        xref_offset = int(pdf.rsplit(b"startxref\n", 1)[1].splitlines()[0])
        self.assertEqual(pdf[xref_offset:xref_offset + 4], b"xref")
        for expected in (b"Northstar Capital", b"Juniper Labs", b"1234567890", b"medium", b"EMEA", b"81.25", b"Creator tools", b"ev-104"):
            with self.subTest(expected=expected):
                self.assertIn(expected, pdf)


if __name__ == "__main__":
    unittest.main()
