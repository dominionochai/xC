"""Tests for canonical hashing and tamper detection in the evidence ledger."""

import unittest

from backend.src.services.evidence_ledger import (
    XcEvidenceLedger,
    canonical_json,
    verify_evidence_chain,
)


class EvidenceLedgerTests(unittest.TestCase):
    def test_canonical_json_is_deterministic_and_chain_verifies(self):
        self.assertEqual(canonical_json({"z": 1, "a": {"y": 2, "x": 3}}),
                         canonical_json({"a": {"x": 3, "y": 2}, "z": 1}))

        ledger = XcEvidenceLedger()
        first = ledger.append(
            "market-report",
            "https://example.test/report/1",
            "Revenue increased in the observed period.",
            {"revenue": 125.5, "currency": "USD"},
            timestamp="2026-01-01T00:00:00Z",
        )
        second = ledger.append(
            "market-report",
            "https://example.test/report/2",
            "Customer count is stable.",
            {"customers": 42},
            timestamp="2026-01-02T00:00:00Z",
        )

        self.assertEqual(first["index"], 0)
        self.assertIsNone(first["previous_hash"])
        self.assertEqual(second["index"], 1)
        self.assertEqual(second["previous_hash"], first["current_hash"])
        self.assertEqual(ledger.verify()["valid"], True)
        self.assertEqual(verify_evidence_chain(ledger.records)["records_checked"], 2)

    def test_payload_tampering_is_detected(self):
        ledger = XcEvidenceLedger()
        ledger.append("source-a", "ref-a", "Claim A", {"value": 1}, timestamp="t0")
        ledger.append("source-b", "ref-b", "Claim B", {"value": 2}, timestamp="t1")
        changed = ledger.records
        changed[1]["payload"]["value"] = 999

        report = verify_evidence_chain(changed)
        self.assertFalse(report["valid"])
        self.assertEqual(report["index"], 1)
        self.assertEqual(report["error"], "current_hash does not match record contents")
        # The public record view is defensive; tampering with it did not mutate the ledger.
        self.assertTrue(ledger.verify()["valid"])


if __name__ == "__main__":
    unittest.main()
