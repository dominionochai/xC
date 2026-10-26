from typing import Literal
from pydantic import BaseModel, Field
BridgeStatus = Literal['not_needed', 'found', 'not_found']
class BridgeStep(BaseModel): name: Literal['Familiarization', 'Bridge adoption', 'Conversion']; affinity_lift: float = Field(ge=0, le=1); evidence_refs: list[str]
class BridgeResult(BaseModel): status: BridgeStatus; steps: list[BridgeStep]; friction_before: float; friction_after: float; friction_reduction_pct: float; warnings: list[str]; evidence_refs: list[str]; provenance: list[dict]; assumptions: dict; fit_affinity: float; tau: float
