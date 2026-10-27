"""Focused tests for optional report API bearer-token authentication."""
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from backend.src.auth import require_report_auth


class ReportAuthTests(unittest.TestCase):
    def test_unset_token_allows_request(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            require_report_auth(authorization=None)

    def test_valid_bearer_token_is_allowed(self) -> None:
        with patch.dict(os.environ, {"XC_API_TOKEN": "correct-secret"}):
            require_report_auth(authorization="Bearer correct-secret")

    def test_invalid_bearer_token_is_rejected(self) -> None:
        with patch.dict(os.environ, {"XC_API_TOKEN": "correct-secret"}):
            with self.assertRaises(HTTPException) as raised:
                require_report_auth(authorization="Bearer incorrect-secret")

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.headers["WWW-Authenticate"], "Bearer")

    def test_malformed_authorization_is_rejected(self) -> None:
        with patch.dict(os.environ, {"XC_API_TOKEN": "correct-secret"}):
            with self.assertRaises(HTTPException) as raised:
                require_report_auth(authorization="Bearer")

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.headers["WWW-Authenticate"], "Bearer")


if __name__ == "__main__":
    unittest.main()
