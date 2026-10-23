"""Gated phase runner and deterministic xC orchestration."""
from __future__ import annotations
from typing import Any
from ...analytics import affinity_clash, affinity_graph, dollarized_tam, find_transition_bridge, geographic_market_split
from ...services.presets import get_preset
from .gates import gate_adversarial_review, gate_cultural_analysis, gate_input, gate_qloo_extraction, gate_report
from .session import PHASE_ORDER, XcModelSession
from .types import AnalysisPhase, AnalysisPhaseResult, AnalysisPlan, AnalystReview, ResearchExecutionResults, XcRunResult

class PhaseRoleRunner:
    """Executes a concrete deterministic role for each analysis phase."""
    def run_phase(self, phase: AnalysisPhase, session: XcModelSession) -> AnalysisPhaseResult:
        plan = session.plan
        if phase is AnalysisPhase.INTAKE:
            data: dict[str, Any] = {"source_entity_id": plan.source_entity_id, "comparison_entity_id": plan.comparison_entity_id, "entity_type": plan.entity_type, "preset": get_preset(plan.preset_id)}
        elif phase is AnalysisPhase.QLOO_EXTRACTION:
            data = {"source_affinities": list(session.research.source_affinities), "comparison_affinities": list(session.research.comparison_affinities), "source_count": len(session.research.source_affinities), "comparison_count": len(session.research.comparison_affinities)}
        elif phase is AnalysisPhase.CULTURAL_ANALYSIS:
            source, target = session.research.source_affinities, session.research.comparison_affinities
            graph = affinity_graph(plan.source_entity_id, plan.comparison_entity_id, source, target)
            clash = affinity_clash(source, target)
            risk = clash["risk"]
            data = {
                "affinity": clash,
                "transition_bridge": find_transition_bridge(plan.source_entity_id, plan.comparison_entity_id, graph, max_hops=3),
                "geographic_market_split": geographic_market_split(plan.regions),
                "tam": dollarized_tam(sum(plan.regions.values()), plan.annual_spend_per_person),
                "fanbacklash_risk": {"risk": risk, "score": clash["clash_score"] if risk != "unknown" else None, "method": "jaccard-affinity-clash-v1", "shared_entities": len(clash["shared_entities"]), "affinity_overlap": clash["jaccard_similarity"], "interpretation": "Directional affinity-based proxy; validate with audience research."},
            }
        elif phase is AnalysisPhase.ADVERSARIAL_REVIEW:
            risk = session.output_for(AnalysisPhase.CULTURAL_ANALYSIS)["fanbacklash_risk"]["risk"]
            findings, recommendations = [], []
            if risk == "unknown":
                findings.append("Affinity coverage is insufficient to estimate fanbacklash risk.")
                recommendations.append("Validate cultural fit with local audience research before launch.")
            elif risk == "high":
                findings.append("Low affinity overlap produces a high deterministic fanbacklash proxy.")
                recommendations.append("Test positioning with existing fans and prepare a mitigation plan.")
            elif risk == "medium":
                findings.append("Affinity overlap indicates a moderate cultural-clash proxy.")
                recommendations.append("Run a targeted concept test in priority regions.")
            else:
                findings.append("Affinity overlap indicates a low cultural-clash proxy.")
                recommendations.append("Continue monitoring audience response after launch.")
            data = {"approved": True, "risk_level": risk, "findings": findings, "recommendations": recommendations}
        elif phase is AnalysisPhase.XC_REPORT:
            data = {key: session.output_for(AnalysisPhase.CULTURAL_ANALYSIS)[key] for key in ("affinity", "transition_bridge", "geographic_market_split", "tam", "fanbacklash_risk")}
        else:
            raise ValueError(f"unsupported analysis phase: {phase}")
        return AnalysisPhaseResult(phase=phase, status="complete", data=data)

class XcOrchestrator:
    """Run five gated phases and preserve the original report fields at top level."""
    def __init__(self, runner: PhaseRoleRunner | None = None) -> None:
        self.runner = runner or PhaseRoleRunner()
    def run(self, plan: AnalysisPlan, research: ResearchExecutionResults) -> XcRunResult:
        gate_input(plan)
        session = XcModelSession(plan, research)
        review: AnalystReview | None = None
        report: dict[str, Any] | None = None
        for phase in PHASE_ORDER:
            result = self.runner.run_phase(phase, session)
            if phase is AnalysisPhase.QLOO_EXTRACTION:
                gate_qloo_extraction(research)
            elif phase is AnalysisPhase.CULTURAL_ANALYSIS:
                gate_cultural_analysis(result)
            elif phase is AnalysisPhase.ADVERSARIAL_REVIEW:
                review = AnalystReview(bool(result.data.get("approved")), str(result.data.get("risk_level", "unknown")), tuple(result.data.get("findings", ())), tuple(result.data.get("recommendations", ())))
                gate_adversarial_review(review)
            elif phase is AnalysisPhase.XC_REPORT:
                gate_report(result.data)
                report = dict(result.data)
            session.record(result)
        if review is None or report is None:
            raise RuntimeError("orchestration completed without a reviewed report")
        return XcRunResult(session.run_id, plan.preset_id, report, tuple(session.phase_results), review)
