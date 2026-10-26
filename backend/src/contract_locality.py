from typing import Literal

from pydantic import BaseModel, Field


class RegionLocality(BaseModel):
    region: str
    affinity: float | None
    ladder_level: int | None = Field(default=None, ge=1, le=3)
    friction: float | None
    delta_vs_global: float | None
    caveat: str | None = None
    sample_note: str | None = None
    reason: str | None = None
    provenance: list[dict] = Field(default_factory=list)


class LocalityResult(BaseModel):
    status: Literal['resolved', 'partial', 'failed']
    regions: list[RegionLocality]
    global_affinity: float | None = None
    warnings: list = Field(default_factory=list)
    evidence_refs: list = Field(default_factory=list)
    provenance: list = Field(default_factory=list)
    assumptions: dict = Field(default_factory=dict)
