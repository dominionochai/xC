"""Strict validation for Qloo request paths and query parameters."""
from __future__ import annotations
import math
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

DEFAULT_BASE_URL = "https://hackathon.api.qloo.com"


def validate_endpoint(endpoint: str) -> str:
    """Return a safe absolute-path API route; reject full URLs and traversal."""
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("endpoint must be a non-empty string")
    if not endpoint.startswith("/") or endpoint.startswith("//"):
        raise ValueError("endpoint must be a single-slash absolute API path")
    if any(char in endpoint for char in "?#\\"):
        raise ValueError("endpoint must not contain query, fragment, or backslash")
    parts = urlsplit(endpoint)
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise ValueError("endpoint must be a path only")
    if any(segment in {".", ".."} for segment in endpoint.split("/")):
        raise ValueError("endpoint path traversal is not allowed")
    return endpoint


def validate_base_url(base_url: str) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("base_url must be a non-empty URL")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("base_url must not contain credentials, query, or fragment")
    return base_url.rstrip("/")


def validate_params(params: Mapping[str, Any] | None) -> dict[str, str | int | float | bool]:
    """Validate and copy scalar query parameters; do not silently coerce."""
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ValueError("params must be a mapping of names to scalar values")
    cleaned: dict[str, str | int | float | bool] = {}
    for key, value in params.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("parameter names must be non-empty strings")
        if key != key.strip() or any(ord(char) < 32 for char in key):
            raise ValueError("parameter names must not contain whitespace or controls")
        if isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, int):
            cleaned[key] = value
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError(f"parameter {key!r} must be finite")
            cleaned[key] = value
        elif isinstance(value, str):
            if any(ord(char) < 32 for char in value):
                raise ValueError(f"parameter {key!r} must not contain control characters")
            cleaned[key] = value
        else:
            raise ValueError(f"parameter {key!r} must be a string, integer, finite float, or boolean")
    return cleaned
