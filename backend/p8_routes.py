"""P8 API routes for presets, reports, and one-shot run streams.

The route state is intentionally process-local. Streams expose the complete
snapshot for a run and then close; they do not simulate background progress.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict

from .src.api.events import encode_sse, event_envelope
from .src.auth import require_report_auth
from .src.services.memo_export import (
    render_investment_memo_markdown,
    render_investment_memo_pdf,
)
from .src.services.presets import get_preset, list_presets

router = APIRouter(prefix="/api/v1", tags=["p8"])

# The P8 slice deliberately uses small in-memory stores rather than introducing
# a second persistence or job framework.
_REPORTS: dict[str, dict[str, Any]] = {}
_RUNS: dict[str, dict[str, Any]] = {}


class _IgnoreExtraModel(BaseModel):
    """Accept known fields only; unknown values (including credentials) vanish."""

    model_config = ConfigDict(extra="ignore")


class ResolveRequest(_IgnoreExtraModel):
    preset_id: str | None = None
    acquirer_brand: str | None = None
    target_brand: str | None = None


class ReportRequest(_IgnoreExtraModel):
    preset_id: str | None = None
    acquirer_brand: Any = None
    target_brand: Any = None
    source_entity_id: Any = None
    comparison_entity_id: Any = None
    source_name: Any = None
    target_name: Any = None
    acquirer: Any = None
    target: Any = None
    regions: Any = None
    annual_spend_per_person: Any = None
    tam: Any = None
    risk: Any = None
    regional_scores: Any = None
    bridge_steps: Any = None
    evidence: Any = None
    content: Any = None
    report: Any = None
    data: Any = None


class CancelRequest(_IgnoreExtraModel):
    run_id: str


def _authenticated_report_request(
    authorization: str | None = Header(default=None),
) -> None:
    """Use the shared bearer validator and fail closed for an unconfigured P8 API."""
    if not os.getenv("XC_API_TOKEN"):
        raise HTTPException(
            status_code=503,
            detail={"missing_configuration": "XC_API_TOKEN"},
        )
    require_report_auth(authorization)


router.dependencies.append(Depends(_authenticated_report_request))

_SENSITIVE_KEY = re.compile(
    r"(?:^|_)(?:api_?key|access_?token|refresh_?token|token|secret|password|"
    r"credential|credentials|authorization)(?:$|_)|(?:api)?key$",
    re.IGNORECASE,
)


def _safe_value(value: Any) -> Any:
    """Copy JSON-like report data while dropping credential-bearing fields."""
    if isinstance(value, dict):
        return {
            str(key): _safe_value(item)
            for key, item in value.items()
            if not _SENSITIVE_KEY.search(str(key).replace("-", "_").replace(" ", "_"))
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # Do not stringify arbitrary request objects into a response or memo.
    return None


def _report_data(request: ReportRequest) -> tuple[str | None, dict[str, Any]]:
    fields = request.model_dump(exclude_none=True)
    preset_id = fields.pop("preset_id", None)
    nested = fields.pop("report", None)
    if nested is None:
        nested = fields.pop("data", None)
    else:
        fields.pop("data", None)
    if nested is None:
        nested = fields.pop("content", None)
    else:
        fields.pop("content", None)

    payload: dict[str, Any] = {}
    if isinstance(nested, dict):
        payload.update(_safe_value(nested))
    elif nested is not None:
        payload["content"] = _safe_value(nested)
    payload.update(_safe_value(fields))
    return preset_id, payload


def _new_report(request: ReportRequest) -> dict[str, Any]:
    preset_id, payload = _report_data(request)
    if preset_id is not None:
        try:
            get_preset(preset_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown preset_id") from None
    report_id = str(uuid.uuid4())
    record = {
        "id": report_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preset_id": preset_id,
        "data": payload,
    }
    _REPORTS[report_id] = record
    return record


def _make_run_event(run_id: str, report_id: str, seq: int, event_type: str) -> dict[str, Any]:
    return event_envelope(
        seq,
        event_type,
        {"run_id": run_id, "report_id": report_id},
    )


@router.get("/presets")
def presets() -> list[dict[str, Any]]:
    return list_presets()


@router.post("/resolve")
def resolve(request: ResolveRequest) -> dict[str, Any]:
    if request.preset_id:
        try:
            preset = get_preset(request.preset_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Unknown preset_id") from None
        acquirer = preset["acquirer_brand"]
        target = preset["target_brand"]
        if request.acquirer_brand and " ".join(request.acquirer_brand.casefold().split()) != " ".join(acquirer.casefold().split()):
            raise HTTPException(status_code=422, detail="acquirer_brand does not match preset")
        if request.target_brand and " ".join(request.target_brand.casefold().split()) != " ".join(target.casefold().split()):
            raise HTTPException(status_code=422, detail="target_brand does not match preset")
        return {
            "id": preset["id"],
            "label": preset["label"],
            "acquirer_brand": acquirer,
            "target_brand": target,
            "description": preset["description"],
        }

    if not request.acquirer_brand or not request.target_brand:
        raise HTTPException(status_code=422, detail="acquirer_brand and target_brand are required without preset_id")
    return {
        "id": None,
        "acquirer_brand": request.acquirer_brand.strip(),
        "target_brand": request.target_brand.strip(),
    }


@router.post("/reports", status_code=201)
def create_report(request: ReportRequest) -> dict[str, str]:
    record = _new_report(request)
    return {"id": record["id"]}


@router.get("/reports")
def reports() -> dict[str, list[dict[str, str]]]:
    # Expose metadata only, never the submitted report body.
    return {
        "reports": [
            {"id": record["id"], "created_at": record["created_at"]}
            for record in reversed(list(_REPORTS.values()))
        ]
    }


@router.post("/generate", status_code=202)
def generate(request: ReportRequest) -> dict[str, str]:
    report = _new_report(request)
    run_id = str(uuid.uuid4())
    events = [
        _make_run_event(run_id, report["id"], 1, "report.created"),
        _make_run_event(run_id, report["id"], 2, "report.completed"),
        _make_run_event(run_id, report["id"], 3, "run.finished"),
    ]
    _RUNS[run_id] = {
        "id": run_id,
        "report_id": report["id"],
        "status": "finished",
        "events": events,
    }
    return {"run_id": run_id}


def _error_stream() -> StreamingResponse:
    data = json.dumps({"code": "RUN_NOT_RESUMABLE"}, separators=(",", ":"))
    return StreamingResponse(
        iter((f"event: error\ndata: {data}\n\n",)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/generate/stream")
def generate_stream(
    run_id: str = Query(...),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    run = _RUNS.get(run_id)
    if run is None:
        return _error_stream()
    events = run["events"]
    latest_seq = events[-1]["seq"] if events else 0
    if last_event_id is None:
        cursor = 0
    else:
        try:
            cursor = int(last_event_id)
        except (TypeError, ValueError):
            return _error_stream()
        if cursor < 0 or cursor > latest_seq:
            return _error_stream()

    frames = [
        encode_sse(event["type"], event)
        for event in events
        if event["seq"] > cursor
    ]
    return StreamingResponse(
        iter(frames),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/cancel", status_code=202)
def cancel(request: CancelRequest) -> dict[str, str]:
    run = _RUNS.get(request.run_id)
    if run is not None and run["status"] != "finished":
        run["status"] = "cancelled"
    return {"status": "accepted"}


def _latest_report_data() -> dict[str, Any]:
    if not _REPORTS:
        return {}
    record = next(reversed(_REPORTS.values()))
    return record["data"]


@router.get("/memo.md")
def memo_markdown() -> Response:
    markdown = render_investment_memo_markdown(_latest_report_data())
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")


@router.get("/memo.pdf")
def memo_pdf() -> Response:
    pdf = render_investment_memo_pdf(_latest_report_data())
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="investment-memo.pdf"'},
    )
