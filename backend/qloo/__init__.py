"""Small, standard-library-only Qloo API foundation.

This package is additive: the existing ``backend.qloo_client`` and service
integrations remain untouched. The caller supplies credentials to QlooClient.
"""

from .client import CallBudgetExceeded, QlooClient, QlooError, QlooHTTPError, QlooResponseError
from .normalize import is_suspect_empty, normalize_entities, normalize_results
from .params import DEFAULT_BASE_URL, validate_endpoint, validate_params
from .transport_urllib import TransportResponse, UrllibTransport

__all__ = [
    "CallBudgetExceeded", "DEFAULT_BASE_URL", "QlooClient", "QlooError",
    "QlooHTTPError", "QlooResponseError", "TransportResponse", "UrllibTransport",
    "is_suspect_empty", "normalize_entities", "normalize_results",
    "validate_endpoint", "validate_params",
]
