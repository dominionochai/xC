import re
import unittest

from backend.methods.evidence import (
    EvidenceLedgerAdapter,
    make_ledger_entry,
    record_call,
    validate_payload,
)


class EvidenceTests(unittest.TestCase):
    def test_entry_fields_and_auto_reference(self):
        entry = make_ledger_entry("computed:test", "derived metric", {"count": 2})
        self.assertEqual(set(entry), {"source", "reference", "claim", "payload"})
        self.assertRegex(entry["reference"], re.compile(r"^[0-9a-f]{16}$"))

    def test_call_does_not_leak_parameter_values(self):
        ledger = []
        entry = record_call(ledger, "GET", "/v1/test",
                            {"api_key": "SECRET-API-KEY", "limit": 3},
                            200, False, False, 1, 12.5)
        self.assertNotIn("SECRET-API-KEY", repr(entry))
        self.assertEqual(entry["payload"]["params_names"], ["api_key", "limit"])
        self.assertEqual(entry["row_id"], 1)

    def test_rejects_raw_looking_payload(self):
        self.assertFalse(validate_payload({"response_raw": {"items": []}}))

    def test_clean_ledger_verifies(self):
        ledger = [make_ledger_entry("computed:test", "derived metric", {"count": 2})]
        self.assertTrue(EvidenceLedgerAdapter(ledger).verify())


if __name__ == "__main__":
    unittest.main()
