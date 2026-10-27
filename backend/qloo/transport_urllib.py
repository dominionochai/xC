"""Minimal injectable HTTP GET transport built on Python's standard library."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class UrllibTransport:
    """Perform GET without logging URLs, headers, credentials, or response data."""
    def get(self, url: str, *, params: Mapping[str, str | int | float | bool],
            headers: Mapping[str, str], timeout: float) -> TransportResponse:
        query = urlencode(params)
        request_url = f"{url}?{query}" if query else url
        request = Request(request_url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                return TransportResponse(int(response.status),
                    {str(k): str(v) for k, v in response.headers.items()}, response.read())
        except HTTPError as error:
            return TransportResponse(int(error.code),
                {str(k): str(v) for k, v in error.headers.items()}, error.read())
        except URLError:
            # Discard the underlying reason; it may contain implementation details.
            raise OSError("Qloo transport failed") from None
