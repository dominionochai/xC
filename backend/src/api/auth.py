"""Strict bearer-token dependency for protected API routes."""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_api_token(authorization: str | None = Header(default=None, alias="Authorization")) -> None:
    """Require XC_API_TOKEN; missing server configuration is distinct from bad auth."""
    expected = os.getenv("XC_API_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "missing_configuration",
                "message": "XC_API_TOKEN is not configured.",
            },
        )
    supplied = ""
    if isinstance(authorization, str) and authorization.startswith("Bearer "):
        supplied = authorization[7:]
    if not supplied or not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")
