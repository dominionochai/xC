"""Deterministic, presentation-only verdict and evidence coverage (M9)."""
from __future__ import annotations

import math
from typing import Any


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _penalty_count(value: Any) -> float:
    number = _finite_number(value)
    return max(0.0, number) if number is not None else 0.0


def verdict_and_confidence(
    fit_affinity: float | None,
    delta_vs_global: float | None,
    ip_at_risk_mean: float | None,
    anti_strength_max: float | None,
    bridge_status: str | None,
    expected_evidence_count: float | None,
    obtained_evidence_count: float | None,
    suspect_empty_count: int = 0,
    dropped_axes: int = 0,
    region_affinity_count: int | None = None,
    region_affinity_available_count: int | None = None,
) -> dict[str, Any]:
    """Return deterministic presentation rules and modeled data coverage.

    THRESHOLDS ARE PRESENTATION-ONLY AND UNCALIBRATED, not measurements or
    statistical confidence: proceed iff fit >= 55, delta >= 0 and mean IP risk
    <= 15; proceed_with_remediation iff fit >= 40, (delta >= 0 or bridge status
    is not ``not_found``), and mean IP risk <= 30; high_risk iff mean IP risk >
    30 or maximum anti-strength > 0.7. Insufficient data takes precedence when
    fit or mean IP risk is null, or fewer than half of a supplied region-affinity
    set is available. Evaluation order is insufficient_data, high_risk, proceed,
    then proceed_with_remediation (so proceed wins if both fit rules match).
    Confidence is evidence coverage clamped to [0, 1], less 0.15 per
    suspect-empty call and 0.10 per dropped axis, clamped again at zero. It is
    None when expected evidence is not positive or obtained coverage is unknown.
    """
    fit = _finite_number(fit_affinity)
    delta = _finite_number(delta_vs_global)
    ip_mean = _finite_number(ip_at_risk_mean)
    anti_max = _finite_number(anti_strength_max)
    expected = _finite_number(expected_evidence_count)
    obtained = _finite_number(obtained_evidence_count)
    suspect_penalty = -0.15 * _penalty_count(suspect_empty_count)
    dropped_penalty = -0.10 * _penalty_count(dropped_axes)

    confidence = None
    if expected is not None and expected > 0 and obtained is not None:
        coverage = min(1.0, max(0.0, obtained / expected))
        confidence = max(0.0, coverage + suspect_penalty + dropped_penalty)

    insufficient: list[str] = []
    if fit is None:
        insufficient.append("fit_affinity is null")
    if ip_mean is None:
        insufficient.append("ip_at_risk_mean is null")
    if region_affinity_count is not None or region_affinity_available_count is not None:
        if region_affinity_count is None or region_affinity_available_count is None:
            insufficient.append("region affinity coverage is unknown")
        else:
            total = max(0, int(region_affinity_count))
            available = max(0, int(region_affinity_available_count))
            if available < (total + 1) // 2:
                insufficient.append("fewer than half of region affinities are available")

    rules_applied: list[str] = []
    if insufficient:
        verdict = "insufficient_data"
        rules_applied.append("insufficient_data: " + "; ".join(insufficient))
    elif ip_mean > 30 or (anti_max is not None and anti_max > 0.7):
        verdict = "high_risk"
        if ip_mean > 30:
            rules_applied.append("ip_at_risk_mean>30 (presentation-only)")
        if anti_max is not None and anti_max > 0.7:
            rules_applied.append("anti_strength_max>0.7 (presentation-only)")
    elif (fit is not None and fit >= 55 and delta is not None and delta >= 0
          and ip_mean <= 15):
        verdict = "proceed"
        rules_applied.append(
            "fit_affinity>=55 and delta_vs_global>=0 and ip_at_risk_mean<=15 (presentation-only)"
        )
    elif (fit is not None and fit >= 40
          and ((delta is not None and delta >= 0)
               or (bridge_status is not None and bridge_status != "not_found"))
          and ip_mean <= 30):
        verdict = "proceed_with_remediation"
        rules_applied.append(
            "fit_affinity>=40 and (delta_vs_global>=0 or bridge_status!='not_found') "
            "and ip_at_risk_mean<=30 (presentation-only)"
        )
    else:
        # The design defines no affirmative verdict for remaining complete-data cases.
        verdict = None

    return {
        "verdict": verdict,
        "confidence": confidence,
        "rules_applied": rules_applied,
        "presentation_only": True,
        "penalties": {"suspect_empty": suspect_penalty, "dropped_axes": dropped_penalty},
    }
