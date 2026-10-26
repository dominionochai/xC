"""Strict validation and deterministic builders for Qloo query parameters."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlencode, urlsplit

DEFAULT_BASE_URL = "https://hackathon.api.qloo.com"
_MAX_PARAMS = 100
_MAX_PAIRS = 500


class ParamError(ValueError):
    """Invalid endpoint or query-parameter input."""


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)


def _parameter_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ParamError("parameter names must be non-empty strings")
    if name != name.strip() or _has_control(name):
        raise ParamError("parameter names must not contain surrounding whitespace or controls")
    return name


def _scalar_text(value: Any, name: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ParamError(f"parameter {name!r} must be a finite number")
        return str(value)
    if isinstance(value, str):
        if _has_control(value):
            raise ParamError(f"parameter {name!r} must not contain control characters")
        return value
    raise ParamError(f"parameter {name!r} must contain only scalar values")


def _entries(params: Any) -> list[tuple[Any, Any]]:
    if isinstance(params, Mapping):
        return list(params.items())
    if isinstance(params, (str, bytes)) or not isinstance(params, Iterable):
        raise ParamError("params must be a mapping or an iterable of name/value pairs")
    entries: list[tuple[Any, Any]] = []
    try:
        for entry in params:
            if isinstance(entry, (str, bytes)):
                raise ParamError("each parameter must be a name/value pair")
            name, value = entry
            entries.append((name, value))
    except (TypeError, ValueError) as error:
        if isinstance(error, ParamError):
            raise
        raise ParamError("each parameter must be a name/value pair") from None
    return entries


def normalize_params(
    params: Mapping[str, Any] | Iterable[tuple[str, Any]] | None,
    array_style: str = "repeat",
) -> list[tuple[str, str]]:
    """Validate parameters and flatten arrays using repeated or comma values.

    Input names must be unique. Arrays are ordered lists or tuples of scalars;
    an empty array is rejected rather than silently omitted. ``repeat`` emits
    one pair per array item, while ``comma`` emits one comma-joined pair.
    """
    if array_style not in {"repeat", "comma"}:
        raise ParamError("array_style must be 'repeat' or 'comma'")
    if params is None:
        return []
    entries = _entries(params)
    if len(entries) > _MAX_PARAMS:
        raise ParamError(f"at most {_MAX_PARAMS} parameters are allowed")

    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for raw_name, value in entries:
        name = _parameter_name(raw_name)
        if name in seen:
            raise ParamError(f"duplicate parameter name {name!r}")
        seen.add(name)
        if isinstance(value, (list, tuple)):
            if not value:
                raise ParamError(f"parameter {name!r} must not be an empty array")
            values = [_scalar_text(item, name) for item in value]
            if array_style == "comma":
                pairs.append((name, ",".join(values)))
            else:
                pairs.extend((name, item) for item in values)
        else:
            pairs.append((name, _scalar_text(value, name)))
        if len(pairs) > _MAX_PAIRS:
            raise ParamError(f"at most {_MAX_PAIRS} parameter pairs are allowed")
    return pairs


def _builder_entries(extra: Mapping[str, Any] | None, name: str) -> list[tuple[str, Any]]:
    if extra is None:
        return []
    if not isinstance(extra, Mapping):
        raise ParamError(f"{name} must be a mapping")
    return list(extra.items())


def build_search_params(
    query: str,
    entity_types: Any = None,
    take: Any = None,
    extra: Mapping[str, Any] | None = None,
    array_style: str = "repeat",
) -> list[tuple[str, str]]:
    """Build search pairs: ``query``, optional ``types``/``take``, then extras."""
    if not isinstance(query, str) or not query.strip():
        raise ParamError("query must be a non-empty string")
    entries: list[tuple[str, Any]] = [("query", query)]
    if entity_types is not None:
        entries.append(("types", entity_types))
    if take is not None:
        entries.append(("take", take))
    entries.extend(_builder_entries(extra, "extra"))
    return normalize_params(entries, array_style=array_style)


def build_insights_params(
    entity_types: Any = None,
    take: Any = None,
    filters: Mapping[str, Any] | None = None,
    signals: Mapping[str, Any] | None = None,
    array_style: str = "repeat",
) -> list[tuple[str, str]]:
    """Build insight pairs using Qloo field names in ``filters``/``signals``.

    ``entity_types`` maps to ``filter.type`` unless ``filters`` already carries
    a ``filter.type`` key, which then wins verbatim. Filter and signal mapping
    keys are passed through verbatim (for example, ``signal.interests.entities``).
    """
    entries: list[tuple[str, Any]] = []
    filter_names = set(filters) if filters is not None else set()
    if entity_types is not None and "filter.type" not in filter_names:
        entries.append(("filter.type", entity_types))
    if take is not None:
        entries.append(("take", take))
    entries.extend(_builder_entries(filters, "filters"))
    entries.extend(_builder_entries(signals, "signals"))
    return normalize_params(entries, array_style=array_style)


def encode_params(pairs: Iterable[tuple[str, Any]]) -> str:
    """URL-encode validated name/value pairs, preserving repeated names."""
    if isinstance(pairs, (str, bytes)) or not isinstance(pairs, Iterable):
        raise ParamError("pairs must be an iterable of name/value pairs")
    cleaned: list[tuple[str, str]] = []
    try:
        for entry in pairs:
            if isinstance(entry, (str, bytes)):
                raise ParamError("each parameter must be a name/value pair")
            name, value = entry
            clean_name = _parameter_name(name)
            cleaned.append((clean_name, _scalar_text(value, clean_name)))
            if len(cleaned) > _MAX_PAIRS:
                raise ParamError(f"at most {_MAX_PAIRS} parameter pairs are allowed")
    except (TypeError, ValueError) as error:
        if isinstance(error, ParamError):
            raise
        raise ParamError("each parameter must be a name/value pair") from None
    return urlencode(cleaned)


def diagnose_params(params: Mapping[str, Any] | None) -> list[str]:
    """Return supplied parameter names as possible empty-result filter suspects.

    Only names are returned; values are deliberately excluded from diagnostics.
    This is a heuristic, not a claim that the service ignored any parameter.
    """
    if params is None:
        return []
    if not isinstance(params, Mapping):
        raise ParamError("params must be a mapping")
    return [name for name, _ in normalize_params(params)]


def validate_endpoint(endpoint: str) -> str:
    """Return a safe absolute-path API route; reject full URLs and traversal."""
    if not isinstance(endpoint, str) or not endpoint:
        raise ParamError("endpoint must be a non-empty string")
    if not endpoint.startswith("/") or endpoint.startswith("//"):
        raise ParamError("endpoint must be a single-slash absolute API path")
    if any(char in endpoint for char in "?#\\") or _has_control(endpoint):
        raise ParamError("endpoint must not contain query, fragment, controls, or backslash")
    parts = urlsplit(endpoint)
    if parts.scheme or parts.netloc or parts.query or parts.fragment:
        raise ParamError("endpoint must be a path only")
    if any(segment in {".", ".."} for segment in endpoint.split("/")):
        raise ParamError("endpoint path traversal is not allowed")
    return endpoint


def validate_base_url(base_url: str) -> str:
    if not isinstance(base_url, str) or not base_url.strip():
        raise ParamError("base_url must be a non-empty URL")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ParamError("base_url must be an absolute HTTP(S) URL")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ParamError("base_url must not contain credentials, query, or fragment")
    return base_url.rstrip("/")


def validate_params(params: Mapping[str, Any] | None) -> dict[str, str | int | float | bool]:
    """Validate and copy scalar-only mapping parameters for the HTTP client."""
    if params is None:
        return {}
    if not isinstance(params, Mapping):
        raise ParamError("params must be a mapping of names to scalar values")
    normalize_params(params)
    cleaned: dict[str, str | int | float | bool] = {}
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            raise ParamError(f"parameter {key!r} must be scalar for this client API")
        cleaned[key] = value
    return cleaned
