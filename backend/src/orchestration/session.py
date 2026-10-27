"""Per-run state and ordering guarantees for orchestration phases."""
from __future__ import annotations
from uuid import uuid4
from .types import AnalysisPhase, AnalysisPhaseResult, AnalysisPlan, ResearchExecutionResults

PHASE_ORDER = (AnalysisPhase.INTAKE, AnalysisPhase.QLOO_EXTRACTION, AnalysisPhase.CULTURAL_ANALYSIS, AnalysisPhase.ADVERSARIAL_REVIEW, AnalysisPhase.XC_REPORT)

class XcModelSession:
    """Lightweight deterministic session; no external model is required."""
    provider = "deterministic"
    def __init__(self, plan: AnalysisPlan, research: ResearchExecutionResults) -> None:
        self.run_id = str(uuid4())
        self.plan = plan
        self.research = research
        self.phase_results: list[AnalysisPhaseResult] = []
    def record(self, result: AnalysisPhaseResult) -> None:
        index = len(self.phase_results)
        if index >= len(PHASE_ORDER) or result.phase is not PHASE_ORDER[index]:
            expected = PHASE_ORDER[index].value if index < len(PHASE_ORDER) else "no further phase"
            raise ValueError(f"phase order violation: expected {expected}, received {result.phase.value}")
        self.phase_results.append(result)
    def output_for(self, phase: AnalysisPhase) -> dict[str, object]:
        for result in reversed(self.phase_results):
            if result.phase is phase:
                return dict(result.data)
        raise ValueError(f"phase {phase.value} has not completed")
