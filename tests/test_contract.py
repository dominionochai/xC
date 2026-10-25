import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from backend.src.contract import Metric, ReportResult, Signal


class ContractTests(unittest.TestCase):
    def test_report_result_round_trips_json(self):
        report = ReportResult(metrics=[Metric(value=1.0, provenance="test source")])

        restored = ReportResult.model_validate_json(report.model_dump_json())

        self.assertEqual(restored, report)

    def test_report_result_rejects_unexpected_field(self):
        with self.assertRaises(ValidationError):
            ReportResult.model_validate(
                {
                    "metrics": [{"value": 1.0, "provenance": "test source"}],
                    "unexpected": True,
                }
            )

    def test_signal_rejects_percent_over_100(self):
        with self.assertRaises(ValidationError):
            Signal(percent=101)

    def test_metric_requires_provenance(self):
        with self.assertRaises(ValidationError):
            Metric(value=1)

    def test_checked_in_schema_is_fresh(self):
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "docs/contract/xc-report.schema.json"
        )
        with schema_path.open(encoding="utf-8") as schema_file:
            checked_in_schema = json.load(schema_file)

        self.assertEqual(checked_in_schema, ReportResult.model_json_schema())


if __name__ == "__main__":
    unittest.main()
