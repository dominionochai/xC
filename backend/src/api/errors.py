"""Consistent exception-to-JSON mapping for API failures."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


def detail_for_exception(exc: Exception) -> tuple[int, Any]:
    """Return only the public detail and status; never serialize exception internals."""
    if isinstance(exc, ApiError):
        return exc.status_code, exc.detail
    if isinstance(exc, HTTPException):
        return exc.status_code, exc.detail
    if isinstance(exc, RequestValidationError):
        return 422, "Invalid request"
    if isinstance(exc, KeyError):
        return 404, "Resource not found"
    if isinstance(exc, ValueError):
        return 422, str(exc) or "Invalid request"
    return 503, {
        "error": "missing_configuration",
        "message": "A required API component is unavailable.",
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        del request
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        del request, exc
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        del request
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
