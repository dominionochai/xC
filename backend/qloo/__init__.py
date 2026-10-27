"""Small, standard-library-only Qloo API foundation.

This package is additive: the existing ``backend.qloo_client`` and service
integrations remain untouched. The caller supplies credentials to QlooClient.
"""
from .client import CallBudgetExceeded, QlooClient, QlooError, QlooHTTPError, QlooResponseError
from .normalize import (
    is_empty_results,
    is_suspect_empty,
    normalize_entities,
    normalize_results,
    result_items,
    shape_paths,
)
from .params import (
    DEFAULT_BASE_URL,
    ParamError,
    build_insights_params,
    build_search_params,
    diagnose_params,
    encode_params,
    normalize_params,
    validate_endpoint,
    validate_params,
    validate_base_url,
)
from .transport_urllib import TransportResponse, UrllibTransport

__all__ = [
    "CallBudgetExceeded", "DEFAULT_BASE_URL", "ParamError", "QlooClient", "QlooError",
    "QlooHTTPError", "QlooResponseError", "TransportResponse", "UrllibTransport",
    "build_insights_params", "build_search_params", "diagnose_params", "encode_params",
    "is_empty_results", "is_suspect_empty", "normalize_entities", "normalize_params",
    "normalize_results", "result_items", "shape_paths", "validate_endpoint",
    "validate_params", "validate_base_url",
]
