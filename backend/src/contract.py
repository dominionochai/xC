"""Pydantic v2 public models and report validation."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Evidence(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    detail: str | None = None
    value: Any = None

class Provenance(BaseModel):
    model_config = ConfigDict(extra="allow")
    sources: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)

class EngineResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    data: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class EngineReport(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str = "partial"
    results: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_a_status(self):
        if self.status not in {"complete", "partial", "empty"}:
            raise ValueError("status must be complete, partial, or empty")
        return self

ReportResult = EngineReport

def assemble_report(results: dict[str, Any], warnings: list[str] | None = None) -> EngineReport:
    evidence: list[Evidence] = []
    sources: list[str] = []
    for value in results.values():
        if isinstance(value, BaseModel):
            value = value.model_dump()
        if isinstance(value, dict):
            for item in value.get("evidence", []) or []:
                try: evidence.append(Evidence.model_validate(item))
                except Exception: continue
            prov = value.get("provenance", {}) or {}
            if isinstance(prov, dict): sources.extend(str(s) for s in prov.get("sources", []) or [])
    status = "empty" if not results else ("partial" if warnings else "complete")
    return EngineReport(status=status, results=results, provenance=Provenance(sources=list(dict.fromkeys(sources)), evidence=evidence), evidence=evidence, warnings=warnings or [])

def assemble(result: dict) -> ReportResult:
    if not isinstance(result, dict):
        raise ValueError("result must be a dict")
    try:
        return assemble_report(result)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("invalid report result") from exc

def validate_report(value: Any) -> EngineReport:
    return EngineReport.model_validate(value)
