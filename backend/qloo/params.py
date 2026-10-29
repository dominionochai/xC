"""Strict validation and deterministic builders for Qloo query parameters."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlencode, urlsplit

DEFAULT_BASE_URL = "https://hackathon.api.qloo.com"
_MAX_PARAMS = 100
_MAX_PAIRS = 500

# V1: Valid type URNs for search/insights
VALID_ENTITY_TYPES = {"urn:entity:brand", "urn:entity:place", "urn:entity:artist", "urn:entity:movie", "urn:entity:tv_show", "urn:entity:podcast", "urn:entity:book", "urn:entity:destination", "urn:entity:person"}
VALID_FILTER_TYPES = {"urn:entity:brand", "urn:entity:place", "urn:entity:artist", "urn:entity:movie", "urn:entity:tv_show", "urn:entity:podcast", "urn:entity:book", "urn:entity:destination", "urn:entity:person", "urn:tag", "urn:heatmap", "urn:demographics"}
VALID_SIGNAL_TYPES = {"signal.interests.entities", "signal.entities", "signal.location.query"}

# V13: Valid location signal forms
VALID_LOCATION_SIGNALS = {"signal.location.query", "filter.location.query"}

# V5: take limits
_MIN_TAKE = 1
_MAX_TAKE = 50

# V4: Known valid parameter names for build-time rejection
VALID_SEARCH_PARAMS = {"query", "types", "take"}
VALID_INSIGHTS_PARAMS = {
    "filter.type", "filter.entities", "filter.entity_ids", "filter.location", "filter.location.query",
    "signal.interests.entities", "signal.entities", "signal.location.query",
    "take", "feature.explainability"
}
VALID_TRENDING_PARAMS = {"take", "filter.start_date", "filter.end_date", "signal.interests.entities"}
VALID_TAGS_PARAMS = {"filter.query", "take"}


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


def _validate_search_params(params: Mapping[str, Any] | Iterable[tuple[str, Any]] | None) -> list[tuple[str, Any]]:
    """Validate search parameters, rejecting unknown names and validating types."""
    if params is None:
        return []
    entries = _entries(params)
    if len(entries) > 100:
        raise ParamError("at most 100 parameters are allowed")

    seen: set[str] = set()
    validated: list[tuple[str, Any]] = []
    for raw_name, value in entries:
        name = _parameter_name(raw_name)
        if name not in VALID_SEARCH_PARAMS:
            raise ParamError(f"unknown search parameter {name!r}; allowed: {sorted(VALID_SEARCH_PARAMS)}")
        if name in seen:
            raise ParamError(f"duplicate parameter name {name!r}")
        seen.add(name)
        if name == "types" and isinstance(value, str):
            # V1: validate entity type format
            types = [t.strip() for t in value.split(",")]
            for t in types:
                if t not in VALID_ENTITY_TYPES:
                    raise ParamError(f"invalid entity type {t!r}; allowed: {sorted(VALID_ENTITY_TYPES)}")
        if name == "take" and isinstance(value, (int, float, str)):
            try:
                take_val = int(value)
                if not (_MIN_TAKE <= take_val <= _MAX_TAKE):
                    raise ParamError(f"take must be between {_MIN_TAKE} and {_MAX_TAKE}")
            except (TypeError, ValueError):
                raise ParamError("take must be an integer between 1 and 50")
        validated.append((name, value))
    return validated


def _validate_insights_params(
    entity_types: Any,
    take: Any,
    filters: Mapping[str, Any] | None,
    signals: Mapping[str, Any] | None,
    array_style: str
) -> list[tuple[str, Any]]:
    """Validate insights parameters with strict name checking."""
    if array_style not in {"repeat", "comma"}:
        raise ParamError("array_style must be 'repeat' or 'comma'")
    
    entries: list[tuple[str, Any]] = []
    seen_take = 0
    
    # V1-V6: entity_types -> filter.type with URN validation
    if entity_types is not None:
        if isinstance(entity_types, str):
            types = [t.strip() for t in entity_types.split(",")]
            for t in types:
                if t not in VALID_FILTER_TYPES:
                    raise ParamError(f"invalid filter.type {t!r}; allowed: {sorted(VALID_FILTER_TYPES)}")
        entries.append(("filter.type", entity_types))
    
    if take is not None:
        try:
            take_val = int(take)
            if not (_MIN_TAKE <= take_val <= _MAX_TAKE):
                raise ParamError(f"take must be between {_MIN_TAKE} and {_MAX_TAKE}")
        except (TypeError, ValueError):
            raise ParamError("take must be an integer between 1 and 50")
        entries.append(("take", take))
        seen_take += 1
    
    # V4: Reject unknown filter/signal names at build time
    if filters:
        for name, value in filters.items():
            if name not in VALID_INSIGHTS_PARAMS:
                raise ParamError(f"unknown filter parameter {name!r}; allowed: {sorted(VALID_INSIGHTS_PARAMS)}")
            # V13: validate location signal forms
            if name in VALID_LOCATION_SIGNALS:
                if not isinstance(value, str) or not value.strip():
                    raise ParamError(f"location parameter {name!r} must be a non-empty string")
        for name, value in filters.items():
            entries.append((name, value))
    
    if signals:
        for name, value in signals.items():
            if name not in VALID_INSIGHTS_PARAMS:
                raise ParamError(f"unknown signal parameter {name!r}; allowed: {sorted(VALID_INSIGHTS_PARAMS)}")
        for name, value in signals.items():
            entries.append((name, value))
    
    # V3: V3 - signal.interests.entities accepts single id, comma list, or repeated params
    # V6: filter.entities for pairwise affinity
    # V14: signal.location.query for heatmap
    
    # Check duplicate 'take'
    take_count = sum(1 for name, _ in entries if name == "take")
    if take_count > 1:
        raise ParamError("take must be supplied at most once per insights request")
    
    return entries


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


def _validate_search_params_legacy(
    params: Mapping[str, Any] | Iterable[tuple[str, Any]] | None,
    array_style: str = "repeat",
) -> list[tuple[str, str]]:
    """Legacy normalize_params for backward compatibility."""
    if array_style not in {"repeat", "comma"}:
        raise ParamError("array_style must be 'repeat' or 'comma'")
    if params is None:
        return []
    entries = _entries(params)
    if len(entries) > 100:
        raise ParamError("at most 100 parameters are allowed")

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
        if len(pairs) > 500:
            raise ParamError("at most 500 parameter pairs are allowed")
    return pairs


def _builder_entries(extra: Mapping[str, Any] | None, name: str) -> list[tuple[str, Any]]:
    if extra is None:
        return []
    if not isinstance(extra, Mapping):
        raise ParamError(f"{name} must be a mapping")
    return list(extra.items())


def _flatten_pairs(entries: list[tuple[str, Any]], array_style: str) -> list[tuple[str, str]]:
    """Flatten builder entries into query pairs, allowing repeated names."""
    if len(entries) > 100:
        raise ParamError("at most 100 parameters are allowed")
    pairs: list[tuple[str, str]] = []
    for raw_name, value in entries:
        name = _parameter_name(raw_name)
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
        if len(pairs) > 500:
            raise ParamError("at most 500 parameter pairs are allowed")
    return pairs


def build_search_params(
    query: str,
    entity_types: Any = None,
    take: Any = None,
    extra: Mapping[str, Any] | None = None,
    array_style: str = "repeat",
) -> list[tuple[str, str]]:
    """Build search pairs: ``query``, optional ``types``/``take``, then extras.
    
    V1: entity_types must be URN format (e.g., urn:entity:brand), not plain 'brand'.
    """
    if not isinstance(query, str) or not query.strip():
        raise ParamError("query must be a non-empty string")
    entries = [("query", query)]
    if entity_types is not None:
        entries.append(("types", entity_types))
    if take is not None:
        entries.append(("take", take))
    if extra:
        if not isinstance(extra, Mapping):
            raise ParamError("extra must be a mapping")
        entries.extend(list(extra.items()))
    return _validate_search_params_legacy(entries, array_style=array_style)


def build_insights_params(
    entity_types: Any = None,
    take: Any = None,
    filters: Mapping[str, Any] | None = None,
    signals: Mapping[str, Any] | None = None,
    array_style: str = "repeat",
) -> list[tuple[str, str]]:
    """Build insight pairs using Qloo field names in ``filters``/``signals``.
    
    V1-V6: entity_types -> filter.type (URN only)
    V3: signal.interests.entities accepts single id, comma list, or repeated params
    V6: filter.entities for pairwise affinity (single or comma-separated)
    V13: signal.location.query for heatmap locality
    V14: filter.type=urn:heatmap requires signal.location.query
    V15: filter.type=urn:demographics for demographics
    V16: filter.type=urn:tag for tags
    
    V4: Unknown parameters are rejected at build time.
    """
    if array_style not in {"repeat", "comma"}:
        raise ParamError("array_style must be 'repeat' or 'comma'")
    entries = _validate_insights_params(entity_types, take, filters, signals, array_style)
    return _flatten_pairs(entries, array_style)


# ... (keep rest of file unchanged)
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


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)


def _parameter_name(name: Any) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ParamError("parameter names must be non-empty strings")
    if name != name.strip() or _has_control(name):
        raise ParamError("parameter names must not contain surrounding whitespace or controls")
    return name


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


def _builder_entries(extra: Mapping[str, Any] | None, name: str) -> list[tuple[str, Any]]:
    if extra is None:
        return []
    if not isinstance(extra, Mapping):
        raise ParamError(f"{name} must be a mapping")
    return list(extra.items())


def _flatten_pairs(entries: list[tuple[str, Any]], array_style: str) -> list[tuple[str, str]]:
    """Flatten builder entries into query pairs, allowing repeated names."""
    if len(entries) > 100:
        raise ParamError("at most 100 parameters are allowed")
    pairs: list[tuple[str, str]] = []
    for raw_name, value in entries:
        name = _parameter_name(raw_name)
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
        if len(pairs) > 500:
            raise ParamError("at most 500 parameter pairs are allowed")
    return pairs


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
            if len(cleaned) > 500:
                raise ParamError(f"at most 500 parameter pairs are allowed")
    except (TypeError, ValueError) as error:
        if isinstance(error, ParamError):
            raise
        raise ParamError("each parameter must be a name/value pair") from None
    return urlencode(cleaned)


def diagnose_params(params: Mapping[str, Any] | None) -> list[str]:
    """Return supplied parameter names as possible empty-result filter suspects."""
    if params is None:
        return []
    if not isinstance(params, Mapping):
        raise ParamError("params must be a mapping")
    return [name for name, _ in _validate_search_params_legacy(params)]


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
    _validate_search_params_legacy(params)
    cleaned: dict[str, str | int | float | bool] = {}
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            raise ParamError(f"parameter {key!r} must be scalar for this client API")
        cleaned[key] = value
    return cleaned