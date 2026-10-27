"""Qloo Insights client with bounded transient retries."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .settings import QLOO_BASE_URL

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class QlooClient:
    """Use Qloo's X-Api-Key header and Insights query-parameter request form."""

    def __init__(self, api_key: str, *, base_url: str = QLOO_BASE_URL,
                 timeout: float = 8.0, retries: int = 2,
                 transport: httpx.BaseTransport | None = None) -> None:
        if not 0 <= retries <= 3:
            raise ValueError("retries must be between 0 and 3")
        self._retries = retries
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> "QlooClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def get_insights(self, entity_id: str, *, entity_type: str = "urn:entity:brand",
                     take: int = 20) -> dict[str, Any]:
        """Fetch affinity recommendations for a Qloo entity identifier."""
        if not 1 <= take <= 100:
            raise ValueError("take must be between 1 and 100")
        params = {
            "signal.interests.entities": entity_id,
            "filter.type": entity_type,
            "take": take,
        }
        for attempt in range(self._retries + 1):
            try:
                response = self._http.get("/v2/insights", params=params)
            except httpx.TransportError:
                if attempt >= self._retries:
                    raise
                time.sleep(min(0.1 * (2 ** attempt), 0.8))
                continue
            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < self._retries:
                try:
                    delay = min(max(float(response.headers.get("Retry-After", "")), 0.0), 1.0)
                except ValueError:
                    delay = min(0.1 * (2 ** attempt), 0.8)
                time.sleep(delay)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Qloo Insights response must be a JSON object")
            return payload
        raise RuntimeError("Qloo request exhausted its bounded retry budget")
