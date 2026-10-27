"""Validation gates between orchestration phases."""
from __future__ import annotations
import math
from collections.abc import Mapping
from .types import AnalysisPhaseResult, AnalysisPlan, AnalystReview, ResearchExecutionResults

class GateError(ValueError):
    """Raised when a phase's required inputs or outputs are unusable."""

def gate_input(plan: AnalysisPlan) -> None:
    for name in ("source_entity_id", "comparison_entity_id", "entity_type", "preset_id"):
        value = getattr(plan, name)
        if not isinstance(value, str) or not value.strip():
            raise GateError(f"{name} must be a non-empty string")
    if not isinstance(plan.regions, Mapping) or not plan.regions:
        raise GateError("regions must contain at least one region")
    for region, population in plan.regions.items():
        if not isinstance(region, str) or not region.strip() or type(population) is not int or population < 0:
            raise GateError("regions require non-empty names and non-negative integer populations")
    spend = plan.annual_spend_per_person
    if isinstance(spend, bool) or not isinstance(spend, (int, float)) or not math.isfinite(spend) or spend < 0:
        raise GateError("annual spend per person must be finite and non-negative")

def gate_qloo_extraction(research: ResearchExecutionResults) -> None:
    for name in ("source_affinities", "comparison_affinities"):
        values = getattr(research, name, None)
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise GateError(f"{name} must be a list of strings")

def gate_cultural_analysis(result: AnalysisPhaseResult) -> None:
    data = result.data
    required = {"affinity", "transition_bridge", "geographic_market_split", "tam", "fanbacklash_risk"}
    missing = required.difference(data)
    if missing:
        raise GateError(f"cultural analysis is missing: {', '.join(sorted(missing))}")
    if not isinstance(data["affinity"], Mapping) or not isinstance(data["tam"], Mapping):
        raise GateError("affinity and TAM outputs must be objects")
    if data["transition_bridge"] is not None and not isinstance(data["transition_bridge"], list):
        raise GateError("transition_bridge must be a list or null")
    if not isinstance(data["geographic_market_split"], list) or not isinstance(data["fanbacklash_risk"], Mapping):
        raise GateError("regional split and fanbacklash outputs have invalid shapes")

def gate_adversarial_review(review: AnalystReview) -> None:
    if not isinstance(review, AnalystReview) or not review.approved:
        raise GateError("adversarial review did not approve the analysis")
    if review.risk_level not in {"low", "medium", "high", "unknown"}:
        raise GateError("adversarial review has an invalid risk level")

def gate_report(report: Mapping[str, object]) -> None:
    required = {"affinity", "transition_bridge", "geographic_market_split", "tam", "fanbacklash_risk"}
    if not required.issubset(report):
        raise GateError("report is missing one or more required output sections")
    if not isinstance(report["tam"], Mapping) or not isinstance(report["geographic_market_split"], list):
        raise GateError("report TAM and regional split have invalid shapes")
    if report["transition_bridge"] is not None and not isinstance(report["transition_bridge"], list):
        raise GateError("report transition bridge must be a list or null")
    if not isinstance(report["fanbacklash_risk"], Mapping):
        raise GateError("report fanbacklash risk must be an object")
