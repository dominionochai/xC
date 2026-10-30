"""FastAPI endpoints for health and Qloo-backed report analysis."""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, root_validator, validator

from .qloo_client import QlooClient
from .settings import Settings, get_settings
from .src.auth import require_report_auth
from .src.orchestration import AnalysisPlan, ResearchExecutionResults, XcOrchestrator
from .src.services.memo_export import (
    render_investment_memo_markdown,
    render_investment_memo_pdf,
)
from .src.services.presets import get_preset, list_presets

app = FastAPI(title="xC API", version="0.2.0")


class AnalyzeRequest(BaseModel):
    source_entity_id: str = Field(..., min_length=1, max_length=512)
    comparison_entity_id: str = Field(..., min_length=1, max_length=512)
    entity_type: str = Field("urn:entity:brand", min_length=1, max_length=200)
    regions: dict[str, int]
    annual_spend_per_person: float = Field(..., ge=0)
    preset_id: str = Field("market_entry", min_length=1, max_length=80)

    @validator("source_entity_id", "comparison_entity_id", "entity_type")
    def strip_required_strings(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @validator("regions", pre=True)
    def validate_regions(cls, value: Any) -> dict[str, int]:
        if not isinstance(value, dict) or not value:
            raise ValueError("regions must be a non-empty mapping")
        for region, population in value.items():
            if not isinstance(region, str) or not region.strip():
                raise ValueError("region names must be non-empty strings")
            if type(population) is not int or population < 0:
                raise ValueError("regional populations must be non-negative integers")
        return value

    @validator("annual_spend_per_person")
    def validate_spend(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("annual_spend_per_person must be finite and non-negative")
        return value

    @validator("preset_id")
    def validate_preset(cls, value: str) -> str:
        value = value.strip()
        try:
            get_preset(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return value


class ReportAnalysisInputs(BaseModel):
    """Optional analysis inputs accepted at creation and generation time."""

    source_entity_id: str | None = Field(None, min_length=1, max_length=512)
    comparison_entity_id: str | None = Field(None, min_length=1, max_length=512)
    entity_type: str | None = Field(None, min_length=1, max_length=200)
    regions: dict[str, int] | None = None
    annual_spend_per_person: float | None = Field(None, ge=0)

    @validator("source_entity_id", "comparison_entity_id", "entity_type")
    def strip_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank when provided")
        return value

    @validator("regions", pre=True)
    def validate_optional_regions(cls, value: Any) -> dict[str, int] | None:
        if value is None:
            return None
        if not isinstance(value, dict) or not value:
            raise ValueError("regions must be a non-empty mapping when provided")
        for region, population in value.items():
            if not isinstance(region, str) or not region.strip():
                raise ValueError("region names must be non-empty strings")
            if type(population) is not int or population < 0:
                raise ValueError("regional populations must be non-negative integers")
        return value

    @validator("annual_spend_per_person")
    def validate_optional_spend(cls, value: float | None) -> float | None:
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("annual_spend_per_person must be finite and non-negative")
        return value

    @root_validator
    def distinct_entity_ids(cls, values: dict[str, Any]) -> dict[str, Any]:
        source = values.get("source_entity_id")
        comparison = values.get("comparison_entity_id")
        if source and comparison and source == comparison:
            raise ValueError("source_entity_id and comparison_entity_id must differ")
        return values


class CreateReportRequest(ReportAnalysisInputs):
    acquirer_brand: str = Field(..., min_length=1, max_length=200)
    target_brand: str = Field(..., min_length=1, max_length=200)
    preset_id: str | None = Field(None, min_length=1, max_length=80)

    @validator("acquirer_brand", "target_brand")
    def strip_brand_names(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("brand names must not be blank")
        return value

    @validator("preset_id")
    def validate_optional_preset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        try:
            get_preset(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @root_validator
    def brands_must_be_consistent(cls, values: dict[str, Any]) -> dict[str, Any]:
        acquirer = values.get("acquirer_brand")
        target = values.get("target_brand")
        if acquirer and target and acquirer.casefold() == target.casefold():
            raise ValueError("acquirer_brand and target_brand must identify different brands")
        return values


class GenerateReportRequest(ReportAnalysisInputs):
    """Optional overrides for inputs supplied when the report was created."""


# Development-only: this process-local registry is intentionally not database-backed.
# Report records and generated output are lost whenever the application restarts.
_REPORTS: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _report_or_404(report_id: str) -> dict[str, Any]:
    report = _REPORTS.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def get_qloo_client(settings: Settings = Depends(get_settings)) -> Iterator[QlooClient]:
    if not settings.qloo_api_key:
        raise HTTPException(status_code=503, detail="QLOO_API_KEY is required for report analysis")
    with QlooClient(settings.qloo_api_key) as client:
        yield client


def _result_entity_ids(payload: dict[str, Any]) -> list[str]:
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    entity_ids: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        nested = result.get("entity")
        candidates = [result.get("entity_id"), result.get("id")]
        if isinstance(nested, dict):
            candidates.extend([nested.get("entity_id"), nested.get("id")])
        entity_id = next((item.strip() for item in candidates if isinstance(item, str) and item.strip()), None)
        if entity_id:
            entity_ids.append(entity_id)
    return sorted(set(entity_ids))


def _run_analysis(request: AnalyzeRequest, qloo: QlooClient) -> dict[str, Any]:
    try:
        source_payload = qloo.get_insights(request.source_entity_id, entity_type=request.entity_type)
        target_payload = qloo.get_insights(request.comparison_entity_id, entity_type=request.entity_type)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Qloo insights request failed") from exc

    plan = AnalysisPlan(
        source_entity_id=request.source_entity_id,
        comparison_entity_id=request.comparison_entity_id,
        entity_type=request.entity_type,
        regions=request.regions,
        annual_spend_per_person=request.annual_spend_per_person,
        preset_id=request.preset_id,
    )
    research = ResearchExecutionResults(
        source_affinities=_result_entity_ids(source_payload),
        comparison_affinities=_result_entity_ids(target_payload),
    )
    return XcOrchestrator().run(plan, research).to_dict()


@app.get("/health")
def health() -> dict[str, str]:
    # V21: Report live only when Qloo key is set and LiteLLM test call succeeds
    live = False
    try:
        qloo_key = os.environ.get("QLOO_API_KEY", "").strip()
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if qloo_key and gemini_key:
            # One real test call to confirm LiteLLM works
            from agents.llm import LLMWrapper
            wrapper = LLMWrapper()
            if wrapper.is_configured():
                # Minimal non-billing prompt
                try:
                    result = wrapper.complete("test", {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
                    live = result.get("ok") is True
                except Exception:
                    live = False
    except Exception:
        live = False
    return {"status": "live" if live else "ok", "live": live, "qloo_configured": bool(qloo_key), "llm_configured": bool(gemini_key)}


@app.get("/api/v1/presets", tags=["presets"], summary="List built-in analysis presets")
def presets() -> list[dict[str, Any]]:
    """Return the supported preset catalog without requiring Qloo credentials."""
    return list_presets()


@app.post("/api/v1/reports/analyze", dependencies=[Depends(require_report_auth)])
def analyze_report(
    request: AnalyzeRequest,
    qloo: QlooClient = Depends(get_qloo_client),
) -> dict[str, Any]:
    return _run_analysis(request, qloo)


@app.post(
    "/api/v1/reports",
    status_code=201,
    dependencies=[Depends(require_report_auth)],
    tags=["reports"],
    summary="Create a pending report",
)
def create_report(request: CreateReportRequest) -> dict[str, Any]:
    # The bundled presets describe analysis strategy, not particular brands. Validate
    # the requested preset and ensure the acquirer/target labels are not contradictory.
    preset_id = request.preset_id or "market_entry"
    try:
        get_preset(preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    report_id = str(uuid4())
    created_at = _now()
    _REPORTS[report_id] = {
        "id": report_id,
        "status": "pending",
        "created_at": created_at,
        "updated_at": created_at,
        "acquirer_brand": request.acquirer_brand,
        "target_brand": request.target_brand,
        "preset_id": preset_id,
        "inputs": {
            "source_entity_id": request.source_entity_id,
            "comparison_entity_id": request.comparison_entity_id,
            "entity_type": request.entity_type or "urn:entity:brand",
            "regions": request.regions,
            "annual_spend_per_person": request.annual_spend_per_person,
        },
        "result": None,
    }
    return _REPORTS[report_id]


@app.get(
    "/api/v1/reports",
    dependencies=[Depends(require_report_auth)],
    tags=["reports"],
    summary="List reports",
)
def list_reports() -> dict[str, list[dict[str, Any]]]:
    reports = sorted(_REPORTS.values(), key=lambda report: report["created_at"], reverse=True)
    return {"reports": reports}


@app.get(
    "/api/v1/reports/{report_id}",
    dependencies=[Depends(require_report_auth)],
    tags=["reports"],
    summary="Get a report",
)
def get_report(report_id: str) -> dict[str, Any]:
    return _report_or_404(report_id)


@app.post(
    "/api/v1/reports/{report_id}/generate",
    dependencies=[Depends(require_report_auth)],
    tags=["reports"],
    summary="Generate a report using Qloo and the xC orchestrator",
)
def generate_report(
    report_id: str,
    request: GenerateReportRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    report = _report_or_404(report_id)
    if report["status"] == "completed":
        return report

    inputs = dict(report["inputs"])
    if request is not None:
        for name in (
            "source_entity_id",
            "comparison_entity_id",
            "entity_type",
            "regions",
            "annual_spend_per_person",
        ):
            value = getattr(request, name)
            if value is not None:
                inputs[name] = value

    required_inputs = (
        "source_entity_id",
        "comparison_entity_id",
        "regions",
        "annual_spend_per_person",
    )
    missing_inputs = [name for name in required_inputs if inputs.get(name) is None]
    missing_configuration = [] if settings.qloo_api_key else ["QLOO_API_KEY"]
    if missing_inputs or missing_configuration:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Report generation requires complete analysis inputs and Qloo configuration",
                "missing_inputs": missing_inputs,
                "missing_configuration": missing_configuration,
            },
        )

    analysis_request = AnalyzeRequest(
        source_entity_id=inputs["source_entity_id"],
        comparison_entity_id=inputs["comparison_entity_id"],
        entity_type=inputs.get("entity_type") or "urn:entity:brand",
        regions=inputs["regions"],
        annual_spend_per_person=inputs["annual_spend_per_person"],
        preset_id=report["preset_id"],
    )
    report["status"] = "generating"
    report["updated_at"] = _now()
    try:
        with QlooClient(settings.qloo_api_key) as qloo:
            result = _run_analysis(analysis_request, qloo)
    except HTTPException as exc:
        report["status"] = "failed"
        report["error"] = exc.detail
        report["updated_at"] = _now()
        raise

    # These labels are user-supplied report metadata, not fabricated analysis output.
    result.setdefault("acquirer", report["acquirer_brand"])
    result.setdefault("target", report["target_brand"])
    report["inputs"] = inputs
    report["result"] = result
    report.pop("error", None)
    report["status"] = "completed"
    report["updated_at"] = _now()
    return report


def _completed_report(report_id: str) -> dict[str, Any]:
    report = _report_or_404(report_id)
    if report["status"] != "completed" or not isinstance(report.get("result"), dict):
        raise HTTPException(status_code=409, detail="Report must be successfully generated before export")
    return report


@app.get(
    "/api/v1/reports/{report_id}/memo.md",
    dependencies=[Depends(require_report_auth)],
    tags=["reports"],
    summary="Download a completed report memo as Markdown",
)
def download_memo_markdown(report_id: str) -> Response:
    report = _completed_report(report_id)
    content = render_investment_memo_markdown(report["result"])
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report_id}-memo.md"'},
    )


@app.get(
    "/api/v1/reports/{report_id}/memo.pdf",
    dependencies=[Depends(require_report_auth)],
    tags=["reports"],
    summary="Download a completed report memo as PDF",
)
def download_memo_pdf(report_id: str) -> Response:
    report = _completed_report(report_id)
    content = render_investment_memo_pdf(report["result"])
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{report_id}-memo.pdf"'},
    )
