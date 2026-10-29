"""Standard-library tests for the evidence ledger."""
from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

from backend.src.ledger import Ledger


class LedgerTests(unittest.TestCase):
    def test_append_builds_exact_hash_chain_and_returns_zero_based_indexes(self) -> None:
        ledger = Ledger()
        self.assertEqual(ledger.append("report", None, "The first claim is supported."), 0)
        self.assertEqual(ledger.append("interview", 0, "The second claim cites the first."), 1)

        entries = ledger.entries
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            set(entries[0]),
            {"index", "source", "reference", "claim", "previous_hash", "hash"},
        )
        self.assertEqual(entries[0]["previous_hash"], "0" * 64)
        self.assertEqual(entries[1]["previous_hash"], entries[0]["hash"])
        self.assertEqual([entry["index"] for entry in entries], [0, 1])
        self.assertTrue(ledger.verify())

    def test_verify_detects_tampering(self) -> None:
        ledger = Ledger()
        ledger.append("report", None, "The recorded claim is original.")
        ledger.append("note", 0, "A second claim points to the first.")
        ledger._entries[0]["claim"] = "The recorded claim was altered."
        self.assertFalse(ledger.verify())

    def test_verify_detects_tail_truncation_using_expected_length(self) -> None:
        ledger = Ledger()
        for number in range(3):
            ledger.append("report", None, f"Entry number {number} is present.")
        ledger._entries.pop()
        self.assertFalse(ledger.verify())

    def test_dicts_lists_and_all_json_values_are_rejected_as_claims(self) -> None:
        ledger = Ledger()
        for invalid in ({"claim": "A sentence."}, ["A sentence."]):
            with self.subTest(invalid=invalid):
                with self.assertRaises((TypeError, ValueError)):
                    ledger.append("report", None, invalid)  # type: ignore[arg-type]
        for json_blob in (
            '{"claim":"A sentence."}',
            '["A sentence."]',
            '"a JSON string"',
            "true",
            "42",
            "null",
        ):
            with self.subTest(json_blob=json_blob):
                with self.assertRaises(ValueError):
                    ledger.append("report", None, json_blob)

    def test_credential_bearing_claims_are_rejected(self) -> None:
        ledger = Ledger()
        credential_claims = (
            "The api_key=exampleCredential123 was exposed.",
            "The response contained Bearer abcdefghijklmnop.",
            "The configuration included sk-live-abcdefghijk123456.",
            "The payload included abcdefghijklmnopqrstuvwxyz0123456789.",
        )
        for claim in credential_claims:
            with self.subTest(claim=claim):
                with self.assertRaises(ValueError):
                    ledger.append("report", None, claim)

    def test_determinism_for_identical_append_sequences(self) -> None:
        first = Ledger()
        second = Ledger()
        rows = (
            ("source-a", None, "First deterministic claim."),
            ("source-b", 0, "Second deterministic claim."),
        )
        for source, reference, claim in rows:
            first.append(source, reference, claim)
            second.append(source, reference, claim)
        self.assertEqual(first.entries, second.entries)
        self.assertEqual([row["hash"] for row in first.entries], [row["hash"] for row in second.entries])

    def test_integer_references_resolve_to_prior_entries(self) -> None:
        ledger = Ledger()
        self.assertEqual(ledger.append("source-a", None, "The referenced claim is first."), 0)
        self.assertEqual(ledger.append("source-b", 0, "This claim references the first."), 1)
        second = ledger.entries[1]
        self.assertEqual(second["reference"], 0)
        self.assertEqual(ledger.resolve(second["reference"]), ledger.entries[0])
        with self.assertRaises(ValueError):
            ledger.append("source-c", 2, "A future reference is not allowed.")
        with self.assertRaises(TypeError):
            ledger.append("source-c", True, "Boolean references are not indexes.")
        self.assertTrue(ledger.verify())

    def test_claim_must_be_one_complete_sentence(self) -> None:
        ledger = Ledger()
        for invalid_claim in ("No ending punctuation", "First sentence. Second sentence."):
            with self.subTest(claim=invalid_claim):
                with self.assertRaises(ValueError):
                    ledger.append("report", None, invalid_claim)

    def test_concurrent_appends_are_serialized_and_verify(self) -> None:
        ledger = Ledger()
        total = 120

        def add(number: int) -> int:
            return ledger.append("concurrent-source", None, f"Concurrent claim {number} is recorded.")

        with ThreadPoolExecutor(max_workers=8) as executor:
            indexes = list(executor.map(add, range(total)))

        self.assertEqual(sorted(indexes), list(range(total)))
        self.assertEqual(len(ledger), total)
        self.assertTrue(ledger.verify())


if __name__ == "__main__":
    unittest.main()
