"""Pydantic v2 public models for xC reports, requests, and events."""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


NonEmpty: TypeAlias = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Percent: TypeAlias = Annotated[float, Field(ge=0, le=100)]
Ratio: TypeAlias = Annotated[float, Field(ge=0, le=1)]


class OutputModel(BaseModel):
    """All response/report payloads reject undeclared fields."""

    model_config = ConfigDict(extra="forbid")


class InputModel(BaseModel):
    """Requests remain forward-compatible with clients sending extra options."""

    model_config = ConfigDict(extra="allow")


class Evidence(OutputModel):
    source: str
    detail: str | None = None
    value: Any = None


class Provenance(OutputModel):
    sources: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class Metric(OutputModel):
    name: str = ""
    label: str | None = None
    value: float | None = None
    unit: str | None = None
    provenance: NonEmpty


class EntityRef(OutputModel):
    id: str | None = None
    entity_id: str | None = None
    name: str = ""
    entity_type: str | None = None
    type: str | None = None
    slug: str | None = None
    url: str | None = None


class Signal(OutputModel):
    name: str = ""
    label: str | None = None
    value: float | None = None
    percent: Percent | None = None
    index: Percent | None = None
    ratio: Ratio | None = None
    confidence: Ratio | None = None
    description: str | None = None
    provenance: str | None = None


class ContrastAxis(OutputModel):
    name: str = ""
    label: str | None = None
    left: str | None = None
    right: str | None = None
    low: float | None = None
    high: float | None = None
    delta: float | None = None
    percent: Percent | None = None
    index: Percent | None = None
    ratio: Ratio | None = None


class Demographics(OutputModel):
    age: str | None = None
    gender: str | None = None
    income: str | None = None
    ethnicity: str | None = None
    education: str | None = None
    location: str | None = None
    segment: str | None = None
    percent: Percent | None = None
    index: Percent | None = None
    ratio: Ratio | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Channel(OutputModel):
    id: str | None = None
    name: str = ""
    channel: str | None = None
    description: str | None = None
    audience: str | None = None
    reach: float | None = None
    percent: Percent | None = None
    index: Percent | None = None
    ratio: Ratio | None = None
    cost: float | None = Field(default=None, ge=0)


class Community(OutputModel):
    id: str | None = None
    name: str = ""
    label: str | None = None
    description: str | None = None
    audience: str | None = None
    size: float | None = None
    percent: Percent | None = None
    share_percent: Percent | None = None
    index: Percent | None = None
    ratio: Ratio | None = None
    penetration_rate: Ratio | None = None
    demographics: Demographics | None = None
    signals: list[Signal] = Field(default_factory=list)


class BridgeStep(OutputModel):
    step: int | None = Field(default=None, ge=0)
    source: EntityRef | str | None = None
    target: EntityRef | str | None = None
    from_entity: EntityRef | str | None = None
    to_entity: EntityRef | str | None = None
    entity: EntityRef | str | None = None
    via: EntityRef | str | None = None
    label: str | None = None
    affinity: Ratio | None = None
    ratio: Ratio | None = None
    index: Percent | None = None
    description: str | None = None


class RegionResult(OutputModel):
    region: str = ""
    region_id: str | None = None
    name: str | None = None
    population: float | None = None
    audience_size: float | None = None
    percent: Percent | None = None
    share_percent: Percent | None = None
    index: Percent | None = None
    ratio: Ratio | None = None
    penetration_rate: Ratio | None = None
    metrics: list[Metric] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)


class Assumption(OutputModel):
    key: str = ""
    name: str | None = None
    value: Any = None
    unit: str | None = None
    description: str | None = None
    source: str | None = None
    confidence: Ratio | None = None
    percent: Percent | None = None
    index: Percent | None = None
    ratio: Ratio | None = None


class Sensitivity(OutputModel):
    name: str = ""
    parameter: str | None = None
    metric: str | None = None
    low: float | None = None
    high: float | None = None
    impact: float | None = None
    impact_percent: Percent | None = None
    percent: Percent | None = None
    index: Percent | None = None
    ratio: Ratio | None = None
    elasticity: Ratio | None = None
    description: str | None = None


class LedgerEntry(OutputModel):
    id: str | None = None
    claim: str = ""
    statement: str | None = None
    source: str | None = None
    sources: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    value: Any = None
    confidence: Ratio | None = None
    status: str | None = None
    created_at: str | None = None


class EngineResult(OutputModel):
    data: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance | list[Any] | dict[str, Any] = Field(default_factory=Provenance)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReportResult(OutputModel):
    schema_version: int = 1
    status: str = "partial"
    results: dict[str, Any] = Field(default_factory=dict)
    phase_results: dict[str, Any] | None = None
    phases: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    provenance: Provenance | list[Any] | dict[str, Any] = Field(default_factory=Provenance)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    partial: bool = False
    metrics: list[Metric] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    contrast_axes: list[ContrastAxis] = Field(default_factory=list)
    demographics: Demographics | None = None
    channels: list[Channel] = Field(default_factory=list)
    communities: list[Community] = Field(default_factory=list)
    bridge: list[BridgeStep] = Field(default_factory=list)
    regions: list[RegionResult] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    sensitivity: list[Sensitivity] = Field(default_factory=list)
    ledger: list[LedgerEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_a_status(self) -> ReportResult:
        if not self.status.strip():
            raise ValueError("status must be non-empty")
        return self


# Historical public name retained for existing engine/report consumers.
EngineReport = ReportResult


class ReportRecord(OutputModel):
    id: str
    status: str = "pending"
    request: dict[str, Any] = Field(default_factory=dict)
    result: ReportResult | dict[str, Any] | None = None
    report: ReportResult | dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class Candidate(OutputModel):
    id: str | None = None
    entity_id: str | None = None
    name: str = ""
    entity_type: str | None = None
    type: str | None = None
    description: str | None = None
    confidence: Ratio | None = None
    popularity: float | None = None
    score: float | None = None
    url: str | None = None


class ResolveResponse(OutputModel):
    query: str = ""
    matches: list[Candidate] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    selected: Candidate | None = None
    confidence: Ratio | None = None
    provenance: Provenance | list[Any] | dict[str, Any] = Field(default_factory=Provenance)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Preset(OutputModel):
    id: str = ""
    name: str = ""
    description: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)


class ResolveRequest(InputModel):
    query: str
    entity_type: str | None = None
    limit: int = Field(default=5, ge=1, le=100)


class AssumptionOverrides(InputModel):
    seed: int | None = None
    simulation_runs: int | None = Field(default=None, ge=200, le=20000)
    penetration_rate: Ratio | None = None
    regional_populations: dict[str, int] | None = None
    annual_spend_per_customer_usd: float | None = Field(default=None, ge=0)
    core_audience_value_usd: float | None = Field(default=None, ge=0)


class CreateReportRequest(InputModel):
    query: str = ""
    entity_type: str | None = None
    seed: int
    simulation_runs: int = Field(default=1000, ge=200, le=20000)
    penetration_rate: Ratio = 0.0
    spend: float = Field(default=0.0, ge=0)
    core_value: float = Field(default=0.0, ge=0)
    region: str | None = None
    preset_id: str | None = None
    assumptions: AssumptionOverrides = Field(default_factory=AssumptionOverrides)


class SseEvent(OutputModel):
    event: str
    data: str | dict[str, Any]


class _EventPayload(OutputModel):
    event: str
    data: dict[str, Any] = Field(default_factory=dict)


class RunStartedEvent(_EventPayload):
    event: Literal["run.started"]


class PhaseStartedEvent(_EventPayload):
    event: Literal["phase.started"]


class PhaseCompletedEvent(_EventPayload):
    event: Literal["phase.completed"]


class ReportCompletedEvent(_EventPayload):
    event: Literal["report.completed"]
    data: dict[str, Any] | ReportResult


class WarningEvent(_EventPayload):
    event: Literal["warning"]


class ErrorEvent(_EventPayload):
    event: Literal["error"]


class RunFinishedEvent(_EventPayload):
    event: Literal["run.finished"]


class RunCancelledEvent(_EventPayload):
    event: Literal["run.cancelled"]


XcEvent: TypeAlias = Union[
    RunStartedEvent,
    PhaseStartedEvent,
    PhaseCompletedEvent,
    ReportCompletedEvent,
    WarningEvent,
    ErrorEvent,
    RunFinishedEvent,
    RunCancelledEvent,
]


def assemble_report(
    results: dict[str, Any], warnings: list[str] | None = None
) -> EngineReport:
    """Build the legacy engine report while deriving compact provenance."""
    evidence: list[Evidence] = []
    sources: list[str] = []
    for value in results.values():
        if isinstance(value, BaseModel):
            value = value.model_dump()
        if not isinstance(value, dict):
            continue
        for item in value.get("evidence", []) or []:
            try:
                evidence.append(item if isinstance(item, Evidence) else Evidence.model_validate(item))
            except Exception:
                continue
        provenance = value.get("provenance", {}) or {}
        if isinstance(provenance, BaseModel):
            provenance = provenance.model_dump()
        if isinstance(provenance, dict):
            sources.extend(str(item) for item in provenance.get("sources", []) or [])
    status = "empty" if not results else ("partial" if warnings else "complete")
    return EngineReport(
        status=status,
        results=results,
        provenance=Provenance(sources=list(dict.fromkeys(sources)), evidence=evidence),
        evidence=evidence,
        warnings=warnings or [],
    )


def assemble(result: dict[str, Any]) -> ReportResult:
    """Compatibility wrapper for the original contract's assembly helper."""
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
