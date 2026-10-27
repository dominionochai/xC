"""Typed values used by the xC orchestration pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

class AnalysisPhase(str, Enum):
    INTAKE = "INTAKE"
    QLOO_EXTRACTION = "QLOO_EXTRACTION"
    CULTURAL_ANALYSIS = "CULTURAL_ANALYSIS"
    ADVERSARIAL_REVIEW = "ADVERSARIAL_REVIEW"
    XC_REPORT = "XC_REPORT"

@dataclass(frozen=True)
class AnalysisPlan:
    source_entity_id: str
    comparison_entity_id: str
    entity_type: str
    regions: Mapping[str, int]
    annual_spend_per_person: float
    preset_id: str = "market_entry"

@dataclass(frozen=True)
class ResearchExecutionResults:
    source_affinities: list[str]
    comparison_affinities: list[str]

@dataclass(frozen=True)
class AnalystReview:
    approved: bool
    risk_level: str
    findings: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    def to_dict(self) -> dict[str, Any]:
        return {"approved": self.approved, "risk_level": self.risk_level, "findings": list(self.findings), "recommendations": list(self.recommendations)}

@dataclass(frozen=True)
class AnalysisPhaseResult:
    phase: AnalysisPhase
    status: str
    data: Mapping[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase.value, "status": self.status, "data": dict(self.data)}

@dataclass(frozen=True)
class XcRunResult:
    run_id: str
    preset_id: str
    report: Mapping[str, Any]
    phases: tuple[AnalysisPhaseResult, ...]
    analyst_review: AnalystReview
    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "preset_id": self.preset_id, **dict(self.report), "analyst_review": self.analyst_review.to_dict(), "phases": [phase.to_dict() for phase in self.phases]}
