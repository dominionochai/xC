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
]
