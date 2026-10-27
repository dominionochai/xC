"""Pure, reusable W2 analysis methods."""

from .resolution import resolve_entity
from .fit import (
    fit_affinity,
    weighted_jaccard,
    tag_overlap,
    shared_signals,
    contrast_axes,
    demographic_normalized_differences,
    demographic_skew,
)
from .anti import anti_cooccurrence
from .communities import build_communities
from .rebellion import simulate_rebellion
from .bridge import build_bridge
from .locality import locality_analysis
from .tam import tam_expansion
from .verdict import verdict_and_confidence
from .evidence import validate_payload, make_ledger_entry, record_call

__all__ = [
    "resolve_entity",
    "fit_affinity",
    "weighted_jaccard",
    "tag_overlap",
    "shared_signals",
    "contrast_axes",
    "demographic_normalized_differences",
    "demographic_skew",
    "anti_cooccurrence",
    "build_communities",
    "simulate_rebellion",
    "build_bridge",
    "locality_analysis",
    "tam_expansion",
    "verdict_and_confidence",
    "validate_payload",
    "make_ledger_entry",
    "record_call",
]
