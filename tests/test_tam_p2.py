"""P2 acceptance tests for the TAM engine adapter and regional provenance."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.methods.tam import tam_expansion
from backend.src.contract import ReportResult
from backend.src.engine import tam as tam_engine


TAM_FIELDS = (
    "pop",
    "penetration",
    "spend",
    "affinity",
    "ip_loss_base",
    "ip_loss_low",
    "ip_loss_high",
)
REGION_NAME = "synthetic_acceptance_market"


def _sourced_region() -> dict[str, object]:
    """Return a valid, synthetic, cited M8 worked-example input."""
    values: dict[str, object] = {
        "pop": 1_000_000,
        "penetration": 0.10,
        "spend": 200,
        "affinity": 60,
        "ip_loss_base": 0.20,
        "ip_loss_low": 0.10,
        "ip_loss_high": 0.30,
    }
    sources = {
        field: {
            "url": f"https://example.org/acceptance/{field}",
            "year": 2024,
            "note": "Synthetic acceptance-test citation.",
        }
        for field in TAM_FIELDS
    }
    return {"region": REGION_NAME, **values, "sources": sources}


def _unsourced_region() -> dict[str, object]:
    return {
        "region": REGION_NAME,
        **{field: None for field in TAM_FIELDS},
        "sources": {},
    }


def _run_adapter(region: dict[str, object], affinity: object) -> ReportResult:
    locality = {"locality": [{"region": REGION_NAME, "affinity": affinity}]}
    with patch.object(tam_engine, "run_locality", return_value=locality):
        return tam_engine.run(
            qloo=None,
            budget=None,
            regions_data={"regions": [region]},
        )


def _metric_value(report: ReportResult, name: str) -> object:
    return next(metric.value for metric in report.metrics if metric.name == name)


def _numeric_assumption_fields(value: object, field: str | None = None):
    """Yield leaf field names for numeric values, excluding provenance metadata."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"region", "sources"}:
                continue
            yield from _numeric_assumption_fields(child, str(key))
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _numeric_assumption_fields(child, field)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if field is not None:
            yield field


class TamP2AcceptanceTests(unittest.TestCase):
    def test_m8_engine_path_returns_documented_9600000_example(self) -> None:
        report = _run_adapter(_sourced_region(), affinity=60)

        self.assertIsInstance(report, ReportResult)
        value = _metric_value(report, "tam_expansion")
        self.assertEqual(value, 9_600_000.0)
        self.assertNotEqual(value, 11_976_000.0)

    def test_every_numeric_region_value_has_url_and_year_citation(self) -> None:
        regions_path = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "data"
            / "regions.json"
        )
        regions = json.loads(regions_path.read_text(encoding="utf-8"))
        self.assertIsInstance(regions, list)

        for region in regions:
            self.assertIsInstance(region, dict)
            region_name = region.get("region", "<unnamed>")
            sources = region.get("sources", {})
            self.assertIsInstance(sources, dict)
            for field in _numeric_assumption_fields(region):
                with self.subTest(region=region_name, field=field):
                    citation = sources.get(field)
                    self.assertIsInstance(citation, dict)
                    url = citation.get("url")
                    self.assertIsInstance(url, str)
                    self.assertTrue(url.strip())
                    self.assertIn("year", citation)
                    self.assertIsNotNone(citation["year"])
                    self.assertTrue(str(citation["year"]).strip())

    def test_engine_adapter_matches_direct_tam_method_for_same_inputs(self) -> None:
        region = _sourced_region()
        direct = tam_expansion([region])
        report = _run_adapter(region, affinity=60)

        self.assertEqual(
            _metric_value(report, "tam_expansion"),
            direct["total_expansion"],
        )

    def test_no_sources_or_overrides_returns_partial_null_tam_metrics(self) -> None:
        report = _run_adapter(_unsourced_region(), affinity=None)

        self.assertTrue(report.partial)
        self.assertEqual(report.status, "partial")
        self.assertTrue(report.warnings)
        self.assertTrue(all(metric.value is None for metric in report.metrics))
        tam_result = report.results["tam"]
        self.assertIsNone(tam_result["tam"])
        self.assertIsNone(tam_result["total_expansion"])
        self.assertIsNone(tam_result["baseline_total"])


if __name__ == "__main__":
    unittest.main()
