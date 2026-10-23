"""FastAPI endpoints for health and Qloo-backed report analysis."""
from __future__ import annotations

import math
from typing import Any, Iterator

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

from .qloo_client import QlooClient
from .settings import Settings, get_settings
from .src.auth import require_report_auth
from .src.orchestration import AnalysisPlan, ResearchExecutionResults, XcOrchestrator
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/presets", tags=["presets"], summary="List built-in analysis presets")
def presets() -> list[dict[str, Any]]:
    """Return the supported preset catalog without requiring Qloo credentials."""
    return list_presets()


@app.post("/api/v1/reports/analyze", dependencies=[Depends(require_report_auth)])
def analyze_report(
    request: AnalyzeRequest,
    qloo: QlooClient = Depends(get_qloo_client),
) -> dict[str, object]:
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
