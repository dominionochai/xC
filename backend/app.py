"""Single offline-safe FastAPI application for the xC API."""
from __future__ import annotations

import hmac
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.src.api.events import encode_comment, encode_sse, event_envelope
from backend.src.api.resume import (
    REPLAY_BUFFER_SIZE as _DEFAULT_REPLAY_BUFFER_SIZE,
    EventReplayBuffer,
    ReplayCursorExpired,
)
from backend.src.services.presets import get_preset, list_presets, resolve_preset

REPLAY_BUFFER_SIZE = 5000


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ResolveRequest(ApiModel):
    preset_id: str
    acquirer_brand: str | None = None
    target_brand: str | None = None


class CreateReportRequest(ApiModel):
    preset_id: str | None = None
    source_entity_id: str | None = None
    comparison_entity_id: str | None = None
    entity_type: str | None = None
    title: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] | None = None


class GenerateRequest(ApiModel):
    preset_id: str | None = None
    source_entity_id: str | None = None
    comparison_entity_id: str | None = None
    entity_type: str | None = None
    title: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] | None = None


class CancelRequest(ApiModel):
    run_id: str


def _strip_client_credentials(value: Any) -> Any:
    """Remove client-supplied API credentials recursively before storage/output."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
            credentialish = (
                "qloo" in normalized
                or normalized in {"apikey", "apitoken", "clientkey", "clientsecret", "authorization"}
                or ("secret" in normalized)
                or ("token" in normalized and normalized not in {"token_count"})
                or ("key" in normalized and ("api" in normalized or "client" in normalized))
            )
            if not credentialish:
                result[key] = _strip_client_credentials(child)
        return result
    if isinstance(value, list):
        return [_strip_client_credentials(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_client_credentials(item) for item in value]
    return value


def _api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": code, "message": message})


async def _authenticate(request: Request) -> None:
    configured = os.getenv("XC_API_TOKEN")
    if not configured:
        raise _api_error(503, "missing_configuration", "XC_API_TOKEN is not configured")
    authorization = request.headers.get("authorization", "")
    scheme, _, supplied = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not supplied or not hmac.compare_digest(supplied, configured):
        raise _api_error(401, "unauthorized", "A valid bearer token is required")


app = FastAPI(title="xC API", version="1.0.0")
router = APIRouter(prefix="/api/v1", dependencies=[Depends(_authenticate)])
_reports: dict[str, dict[str, Any]] = {}
_runs: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_payload(model: BaseModel) -> dict[str, Any]:
    return _strip_client_credentials(model.model_dump(mode="json", exclude_none=True))


def _run_finished(run: dict[str, Any]) -> None:
    if run["terminal"]:
        return
    run_id = run["run_id"]
    report_id = str(uuid.uuid4())
    request_data = run["request"]
    report = {
        "id": report_id,
        "run_id": run_id,
        "preset_id": request_data.get("preset_id"),
        "source_entity_id": request_data.get("source_entity_id"),
        "comparison_entity_id": request_data.get("comparison_entity_id"),
        "entity_type": request_data.get("entity_type"),
        "title": request_data.get("title") or "xC report",
        "status": "completed",
        "content": _strip_client_credentials(request_data.get("report") or request_data.get("input") or {}),
        "created_at": _now(),
    }
    _reports[report_id] = report
    run["report_id"] = report_id
    run["terminal"] = True
    run["status"] = "completed"
    run["buffer"].append("report.completed", {"run_id": run_id, "report_id": report_id})
    run["buffer"].append("run.finished", {"run_id": run_id, "status": "completed"})


@app.get("/health")
async def health() -> dict[str, str]:
    """Unauthenticated liveness endpoint; performs no network or key checks."""
    return {"status": "ok"}


@router.get("/presets")
async def presets() -> list[dict[str, Any]]:
    try:
        return _strip_client_credentials(list_presets())
    except Exception:
        raise _api_error(503, "missing_configuration", "Preset catalog is unavailable") from None


@router.post("/resolve")
async def resolve(request: ResolveRequest) -> dict[str, Any]:
    try:
        result = resolve_preset(
            request.preset_id,
            acquirer_brand=request.acquirer_brand,
            target_brand=request.target_brand,
        )
        return _strip_client_credentials(result)
    except (ValueError, KeyError):
        raise _api_error(422, "validation_error", "The requested preset or brand combination is invalid") from None


@router.post("/reports", status_code=201)
async def create_report(request: CreateReportRequest) -> dict[str, Any]:
    payload = _model_payload(request)
    preset_id = payload.get("preset_id")
    if preset_id:
        try:
            get_preset(preset_id)
        except (ValueError, KeyError):
            raise _api_error(422, "validation_error", "Unknown preset_id") from None
    report_id = str(uuid.uuid4())
    report = {
        "id": report_id,
        "preset_id": preset_id,
        "source_entity_id": payload.get("source_entity_id"),
        "comparison_entity_id": payload.get("comparison_entity_id"),
        "entity_type": payload.get("entity_type"),
        "title": payload.get("title"),
        "status": "created",
        "content": _strip_client_credentials(payload.get("report") or payload.get("content") or {}),
        "created_at": _now(),
    }
    _reports[report_id] = report
    return report


@router.get("/reports")
async def reports() -> list[dict[str, Any]]:
    return [_strip_client_credentials(report) for report in reversed(list(_reports.values()))]


@router.get("/reports/{report_id}")
async def get_report(report_id: str) -> dict[str, Any]:
    report = _reports.get(report_id)
    if report is None:
        raise _api_error(404, "not_found", "Report not found")
    return _strip_client_credentials(report)


@router.post("/generate", status_code=202)
async def generate(request: GenerateRequest) -> dict[str, Any]:
    payload = _model_payload(request)
    if payload.get("preset_id"):
        try:
            get_preset(payload["preset_id"])
        except (ValueError, KeyError):
            raise _api_error(422, "validation_error", "Unknown preset_id") from None
    run_id = str(uuid.uuid4())
    buffer = EventReplayBuffer(capacity=REPLAY_BUFFER_SIZE)
    run: dict[str, Any] = {
        "run_id": run_id,
        "request": payload,
        "buffer": buffer,
        "terminal": False,
        "status": "running",
        "report_id": None,
    }
    buffer.append("run.started", {"run_id": run_id})
    _runs[run_id] = run
    return {"run_id": run_id, "status": "running", "stream_url": f"/api/v1/generate/stream?run_id={run_id}"}


@router.get("/generate/stream")
async def generate_stream(
    run_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    run = _runs.get(run_id)
    if run is None:
        raise _api_error(404, "not_found", "Run not found")
    if last_event_id is None or last_event_id == "":
        cursor = 0
    else:
        try:
            cursor = int(last_event_id)
            if cursor < 0:
                raise ValueError
        except ValueError:
            raise _api_error(422, "validation_error", "Last-Event-ID must be a non-negative integer") from None

    async def stream():
        # An immediate comment keeps intermediaries alive without consuming a sequence ID.
        yield encode_comment("keepalive")
        _run_finished(run)
        try:
            pending = run["buffer"].replay_after(cursor)
        except ReplayCursorExpired:
            marker = run["buffer"].append("RUN_NOT_RESUMABLE", {"run_id": run_id, "reason": "cursor_expired"})
            yield encode_sse("RUN_NOT_RESUMABLE", marker)
            return
        for envelope in pending:
            yield encode_sse(envelope["type"], envelope)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/cancel", status_code=202)
async def cancel(request: CancelRequest) -> dict[str, Any]:
    run = _runs.get(request.run_id)
    if run is None:
        raise _api_error(404, "not_found", "Run not found")
    if not run["terminal"]:
        run["terminal"] = True
        run["status"] = "cancelled"
        run["buffer"].append("run.cancelled", {"run_id": request.run_id})
        run["buffer"].append("run.finished", {"run_id": request.run_id, "status": "cancelled"})
    return {"run_id": request.run_id, "status": run["status"], "accepted": True}


@router.get("/memo.md")
async def memo_markdown() -> JSONResponse:
    raise _api_error(503, "missing_configuration", "Memo export is not configured")


@router.get("/memo.pdf")
async def memo_pdf() -> JSONResponse:
    raise _api_error(503, "missing_configuration", "Memo export is not configured")


app.include_router(router)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if not isinstance(detail, dict) or "error" not in detail:
        detail = {"error": "http_error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content={"detail": _strip_client_credentials(detail)}, headers=exc.headers)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Do not return exception text, request data, credentials, or upstream payloads.
    return JSONResponse(status_code=502, content={"detail": {"error": "upstream_error", "message": "The request could not be completed"}})


try:
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(item.get("loc", ())), "type": item.get("type", "value_error")} for item in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": {"error": "validation_error", "message": "Request validation failed", "errors": errors}})
except ImportError:  # pragma: no cover - FastAPI always includes this in supported deployments.
    pass
