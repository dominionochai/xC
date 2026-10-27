"""Optional bearer-token auth for sensitive report API routes.

Set ``XC_API_TOKEN`` to enable authentication; when it is unset, requests
remain permitted for backward compatibility. Protect a FastAPI route with
``dependencies=[Depends(require_report_auth)]``.
"""
from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def require_report_auth(authorization: str | None = Header(default=None)) -> None:
    """Require an exact ``Bearer <XC_API_TOKEN>`` header when configured."""
    expected_token = os.getenv("XC_API_TOKEN")
    if expected_token is None:
        return

    is_authenticated = (
        bool(expected_token)
        and authorization is not None
        and authorization.startswith("Bearer ")
        and hmac.compare_digest(
            authorization[len("Bearer ") :].encode("utf-8"),
            expected_token.encode("utf-8"),
        )
    )
    if not is_authenticated:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
