"""Offline deterministic tests for the memo exporters."""
import unittest

from backend.memo_export import render_markdown, render_pdf


class MemoExportTests(unittest.TestCase):
    def test_markdown_sections_and_disclaimer(self):
        markdown = render_markdown({})
        self.assertIn("# Memo", markdown)
        for heading in (
            "## Executive summary",
            "## Cultural fit",
            "## Rebellion risk",
            "## Bridge",
            "## Locality",
            "## TAM",
            "## Methods and limitations",
            "## Evidence appendix",
        ):
            self.assertIn(heading, markdown)
        self.assertIn("assumption-driven screening, not investment advice", markdown)

    def test_fixture_header_in_both_formats(self):
        marker = "FIXTURE DATA - NOT LIVE QLOO OUTPUT"
        self.assertTrue(render_markdown({}, fixture_mode=True).startswith("# Memo\n\n**" + marker))
        self.assertIn(marker.encode("ascii"), render_pdf({}, fixture_mode=True))

    def test_pdf_header_xref_trailer_and_page_number(self):
        pdf = render_pdf({"verdict": "clear"})
        self.assertTrue(pdf.startswith(b"%PDF-1.4\n"))
        self.assertIn(b"xref\n", pdf)
        self.assertIn(b"trailer\n", pdf)
        self.assertIn(b"startxref\n", pdf)
        self.assertIn(b"%%EOF", pdf)
        self.assertIn(b"Page 1 of 1", pdf)

    def test_repeated_pdf_bytes_are_deterministic(self):
        payload = {
            "verdict": "review",
            "fit": {"score": 0.72},
            "simulation": {"distribution": {"p50": 0.4, "p90": 0.8}},
            "warnings": ["offline fixture"],
        }
        self.assertEqual(render_pdf(payload), render_pdf(payload))

    def test_long_lines_and_tables_do_not_raise(self):
        long_text = "x" * 5000
        payload = {
            "communities": [{"name": long_text, "description": long_text}],
            "locality": {"locations": [{"location": long_text, "caveat": long_text}]},
            "tam": {"scenarios": [{"name": long_text, "assumptions": long_text}]},
        }
        markdown = render_markdown(payload)
        pdf = render_pdf(payload)
        self.assertIn("| Community |", markdown)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))

    def test_missing_fields_are_rendered_as_not_available(self):
        markdown = render_markdown(None)
        self.assertIn("not available", markdown)
        self.assertIn("| --- | --- | --- |", markdown)
        pdf = render_pdf(None)
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))


if __name__ == "__main__":
    unittest.main()
