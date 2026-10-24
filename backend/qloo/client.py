"""Paced, bounded, retrying Qloo JSON client with an in-memory response cache."""
from __future__ import annotations
import copy
import json
import math
import time
from collections.abc import Mapping
from typing import Any, Callable, Protocol
from .params import DEFAULT_BASE_URL, validate_base_url, validate_endpoint, validate_params
from .transport_urllib import TransportResponse, UrllibTransport

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class QlooError(RuntimeError):
    """Base error; messages exclude credentials and response bodies."""


class CallBudgetExceeded(QlooError):
    """Another network attempt would exceed the configured budget."""


class QlooHTTPError(QlooError):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"Qloo returned HTTP status {status}")


class QlooResponseError(QlooError):
    """Malformed JSON response, reported without echoing its body."""


class Transport(Protocol):
    def get(self, url: str, *, params: Mapping[str, str | int | float | bool],
            headers: Mapping[str, str], timeout: float) -> TransportResponse: ...


class QlooClient:
    """Synchronous client. Inject transport and timing hooks for deterministic tests.

    The call budget counts each network attempt, including retries. Cache hits
    consume no budget. Call-log entries omit query values and request headers.
    """
    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL,
                 transport: Transport | None = None, timeout: float = 8.0,
                 retries: int = 2, pacing_seconds: float = 0.25,
                 cache_ttl: float = 30.0, call_budget: int = 20,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a non-empty string")
        if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 5:
            raise ValueError("retries must be an integer from 0 through 5")
        if isinstance(call_budget, bool) or not isinstance(call_budget, int) or call_budget < 1:
            raise ValueError("call_budget must be a positive integer")
        for name, value, allow_zero in (("timeout", timeout, False),
                ("pacing_seconds", pacing_seconds, True), ("cache_ttl", cache_ttl, True)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
                qualifier = "non-negative" if allow_zero else "positive"
                raise ValueError(f"{name} must be finite and {qualifier}")
        self._api_key = api_key.strip()
        self._base_url = validate_base_url(base_url)
        self._transport = transport or UrllibTransport()
        self._timeout = float(timeout)
        self._retries = retries
        self._pacing = float(pacing_seconds)
        self._cache_ttl = float(cache_ttl)
        self._budget = call_budget
        self._sleep = sleep
        self._clock = clock
        self._used = 0
        self._last_started: float | None = None
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, dict[str, Any]]] = {}
        self._call_log: list[dict[str, Any]] = []

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._call_log)

    @property
    def calls_used(self) -> int:
        return self._used

    def get(self, endpoint: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        route = validate_endpoint(endpoint)
        query = validate_params(params)
        cache_key = (route, tuple(sorted((key, str(value)) for key, value in query.items())))
        now = self._clock()
        cached = self._cache.get(cache_key)
        if cached is not None and cached[0] > now:
            self._call_log.append({"path": route, "cached": True, "status": 200, "attempt": 0})
            return copy.deepcopy(cached[1])
        if cached is not None:
            del self._cache[cache_key]

        url = self._base_url + route
        for attempt in range(self._retries + 1):
            if self._used >= self._budget:
                self._call_log.append({"path": route, "cached": False, "status": None,
                    "attempt": attempt + 1, "error": "call_budget_exhausted"})
                raise CallBudgetExceeded("Qloo network call budget exhausted")
            started = self._clock()
            if self._last_started is not None:
                wait = self._pacing - (started - self._last_started)
                if wait > 0:
                    self._sleep(wait)
                    started = self._clock()
            self._last_started = started
            self._used += 1
            try:
                response = self._transport.get(url, params=query,
                    headers={"X-Api-Key": self._api_key, "Accept": "application/json"},
                    timeout=self._timeout)
            except (OSError, TimeoutError):
                elapsed = max(0.0, self._clock() - started)
                self._call_log.append({"path": route, "cached": False, "status": None,
                    "attempt": attempt + 1, "elapsed_seconds": round(elapsed, 6),
                    "error": "transport_error"})
                if attempt < self._retries:
                    self._sleep(min(0.25 * (2 ** attempt), 3.0))
                    continue
                raise QlooError("Qloo transport failed after bounded retries") from None

            elapsed = max(0.0, self._clock() - started)
            retry_after = _retry_after(response.headers)
            row: dict[str, Any] = {"path": route, "cached": False,
                "status": response.status, "attempt": attempt + 1,
                "elapsed_seconds": round(elapsed, 6)}
            if retry_after is not None:
                row["retry_after_seconds"] = retry_after
            self._call_log.append(row)
            if response.status in _RETRYABLE_STATUS and attempt < self._retries:
                self._sleep(retry_after if retry_after is not None else min(0.25 * (2 ** attempt), 3.0))
                continue
            if not 200 <= response.status < 300:
                raise QlooHTTPError(response.status)
            try:
                body = response.body.decode("utf-8") if isinstance(response.body, bytes) else response.body
                payload = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                raise QlooResponseError("Qloo response was not valid JSON") from None
            if not isinstance(payload, Mapping):
                raise QlooResponseError("Qloo JSON response must be an object")
            result = dict(payload)
            if self._cache_ttl > 0:
                self._cache[cache_key] = (self._clock() + self._cache_ttl, copy.deepcopy(result))
            return result
        raise QlooError("Qloo request exhausted its bounded retry budget")


def _retry_after(headers: Mapping[str, str]) -> float | None:
    for key, value in headers.items():
        if key.lower() == "retry-after":
            try:
                delay = float(value)
            except (TypeError, ValueError):
                return None
            return min(max(delay, 0.0), 3.0) if math.isfinite(delay) else None
    return None
