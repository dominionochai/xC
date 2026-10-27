"""Pure fit, weighted-overlap, signal, and demographic comparison helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable


def _weights(values: Any) -> dict[str, float]:
    """Coerce a mapping to finite, non-negative numeric weights."""
    if not isinstance(values, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, raw in values.items():
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError):
            continue
        if value >= 0:
            result[str(key)] = value
    return result


def _score_values(values: Any) -> list[float]:
    """Flatten numeric score values one level, ignoring invalid/missing data."""
    if isinstance(values, Mapping):
        values = values.values()
    if isinstance(values, (int, float)) and not isinstance(values, bool):
        values = [values]
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes)):
        return []
    output: list[float] = []
    for value in values:
        if isinstance(value, Mapping):
            output.extend(_score_values(value))
        else:
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if 0.0 <= number <= 1.0:
                output.append(number)
    return output


def fit_affinity(
    scores: Any,
    comparison_scores: Any = None,
    notes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return a percentage affinity as 100 times the mean available score.

    Either input may be a scalar, sequence, or mapping of per-domain scores.
    Missing directions are reported explicitly and are not treated as zero.
    """
    values = _score_values(scores)
    other = _score_values(comparison_scores) if comparison_scores is not None else []
    combined = values + other
    result_notes = list(notes or [])
    if comparison_scores is None:
        result_notes.append("comparison direction missing; affinity uses available scores only")
    if not combined:
        result_notes.append("no valid affinity scores")
        return {"score": None, "notes": result_notes}
    return {"score": round(100.0 * sum(combined) / len(combined), 1), "notes": result_notes}


def weighted_jaccard(left: Any, right: Any) -> float:
    """Compute weighted Jaccard similarity over the union of signal keys."""
    a, b = _weights(left), _weights(right)
    keys = set(a) | set(b)
    denominator = sum(max(a.get(key, 0.0), b.get(key, 0.0)) for key in keys)
    if denominator == 0:
        return 0.0
    return sum(min(a.get(key, 0.0), b.get(key, 0.0)) for key in keys) / denominator


def tag_overlap(profile_a: Any, profile_b: Any) -> float | None:
    """Return weighted Jaccard overlap for two tag profiles.

    The overlap is the sum of per-tag minimum weights divided by the sum of
    per-tag maximum weights. Return ``None`` when either profile has no
    positive, valid weights.
    """
    a, b = _weights(profile_a), _weights(profile_b)
    if not any(a.values()) or not any(b.values()):
        return None
    keys = set(a) | set(b)
    denominator = sum(max(a.get(key, 0.0), b.get(key, 0.0)) for key in keys)
    if denominator == 0:
        return None
    numerator = sum(min(a.get(key, 0.0), b.get(key, 0.0)) for key in keys)
    return numerator / denominator


def shared_signals(
    profile_a: Any,
    profile_b: Any,
    top: int | None = None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List common positive signals, sorted by descending shared/minimum weight.

    ``limit`` is retained as a keyword-only compatibility alias for ``top``.
    """
    a, b = _weights(profile_a), _weights(profile_b)
    shared = [
        {
            "signal": key,
            "left_weight": a[key],
            "right_weight": b[key],
            "weight": min(a[key], b[key]),
        }
        for key in set(a) & set(b)
        if min(a[key], b[key]) > 0
    ]
    shared.sort(key=lambda row: (-row["weight"], row["signal"]))
    count = top if top is not None else limit
    return shared if count is None else shared[: max(0, int(count))]


def contrast_axes(profile_a: Any, profile_b: Any) -> list[dict[str, Any]]:
    """Return tag differences, with positive deltas indicating target strength.

    ``profile_a`` is the acquirer and ``profile_b`` is the target. Strength is
    the signed delta divided by the largest weight in either profile.
    """
    acquirer, target = _weights(profile_a), _weights(profile_b)
    largest_weight = max((*acquirer.values(), *target.values()), default=0.0)
    rows: list[dict[str, Any]] = []
    for tag in set(acquirer) | set(target):
        delta = target.get(tag, 0.0) - acquirer.get(tag, 0.0)
        strength = delta / largest_weight if largest_weight else 0.0
        rows.append(
            {
                "tag": tag,
                "delta": delta,
                "side": "target" if delta > 0 else "acquirer",
                "strength": strength,
            }
        )
    return sorted(rows, key=lambda row: (-abs(row["strength"]), row["tag"]))


def demographic_normalized_differences(acquirer: Any, target: Any) -> list[dict[str, Any]]:
    """Compare normalized demographic shares; difference is target minus acquirer.

    The comparison is performed independently for each supplied prompt/category.
    """
    acq = acquirer if isinstance(acquirer, Mapping) else {}
    tgt = target if isinstance(target, Mapping) else {}
    output: list[dict[str, Any]] = []
    for prompt in sorted(set(acq) | set(tgt), key=str):
        av = _weights(acq.get(prompt, {}))
        tv = _weights(tgt.get(prompt, {}))
        asum, tsum = sum(av.values()), sum(tv.values())
        for key in sorted(set(av) | set(tv)):
            a_share = av.get(key, 0.0) / asum if asum else 0.0
            t_share = tv.get(key, 0.0) / tsum if tsum else 0.0
            output.append({
                "prompt": prompt, "group": key, "acquirer_share": a_share,
                "target_share": t_share, "difference": t_share - a_share})
    return output


def demographic_skew(demo_a: Any, demo_b: Any) -> dict[str, float] | None:
    """Return per-bucket differences in normalized shares (demo_b minus demo_a).

    Return ``None`` if either demographic mapping is missing or has no positive
    valid total to normalize.
    """
    a, b = _weights(demo_a), _weights(demo_b)
    total_a, total_b = sum(a.values()), sum(b.values())
    if not total_a or not total_b:
        return None
    return {
        bucket: b.get(bucket, 0.0) / total_b - a.get(bucket, 0.0) / total_a
        for bucket in sorted(set(a) | set(b))
    }
