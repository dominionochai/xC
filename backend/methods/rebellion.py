"""Assumption-based Monte Carlo simulation of community rebellion risk."""

import math
import random
from collections.abc import Mapping


CALIBRATION = "NONE - assumptions uncalibrated, see METHODS.md M5"


def map_build_communities_to_rebellion(build_output):
    """Map ``build_communities`` output to rebellion communities.

    Positive ``core_audience_share`` values become records containing the
    community name, simulation share, and its source ``basis_tags``. The
    builder normally returns a result mapping with a ``communities`` list;
    a list of community rows is also accepted directly.
    """
    if isinstance(build_output, Mapping):
        if "communities" in build_output:
            rows = build_output.get("communities") or []
        elif "core_audience_share" in build_output:
            rows = [build_output]
        else:
            rows = []
    elif isinstance(build_output, (list, tuple)):
        rows = build_output
    else:
        rows = []

    mapped = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        try:
            share = float(row.get("core_audience_share", 0.0))
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(share) or share <= 0.0:
            continue

        name = row.get("label") or row.get("name") or f"community_{index + 1}"
        basis_tags = row.get("basis_tags") or []
        if not isinstance(basis_tags, (list, tuple, set)):
            basis_tags = []
        mapped.append(
            {
                "name": name,
                "share": share,
                "community_tag_sets": list(basis_tags),
            }
        )
    return mapped


def _clamp(value, low, high):
    """Clamp a numeric value to an inclusive interval."""
    return max(low, min(high, value))


def _weighted_tags(tags):
    """Convert a tag collection to a positive-weight mapping."""
    if isinstance(tags, dict):
        return {key: max(0.0, float(value)) for key, value in tags.items()}
    if tags is None:
        return {}
    return {key: 1.0 for key in tags}


def _weighted_jaccard(left, right):
    """Return weighted Jaccard similarity for two tag mappings."""
    keys = set(left) | set(right)
    union = sum(max(left.get(key, 0.0), right.get(key, 0.0)) for key in keys)
    if union <= 0:
        return 0.0
    intersection = sum(min(left.get(key, 0.0), right.get(key, 0.0)) for key in keys)
    return intersection / union


def _nearest_rank(values, percentile):
    """Return a nearest-rank percentile from a nonempty sequence."""
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _by_community(values, communities, default):
    """Resolve a community-specific option supplied as a map or sequence."""
    if values is None:
        return [default] * len(communities)
    if isinstance(values, dict):
        return [values.get(item.get("name"), default) for item in communities]
    if isinstance(values, (int, float)):
        return [values] * len(communities)
    return [values[i] if i < len(values) else default for i in range(len(communities))]


def simulate_rebellion(
    communities,
    alignment_gap,
    seed=42,
    runs=5000,
    kappa=20,
    kappa2=10,
    influence_lambda=0.2,
    influence_rounds=3,
    theta=0.15,
    value_weights=None,
    community_tag_sets=None,
    fit_ratios=None,
):
    """Simulate assumed rebellion propensity and lost value for communities.

    The function is deterministic for a given input and uses only an injected
    data-free model.  Each run gets an independent ``random.Random(seed + r)``.
    """
    communities = list(communities or [])
    if not communities:
        return {"simulation": None, "warning": "no_communities"}

    shares = [float(item.get("share", 0.0)) for item in communities]
    anti_strengths = [float(item.get("anti_strength", 0.0)) for item in communities]
    names = [item.get("name", str(index)) for index, item in enumerate(communities)]
    weights = [float(value) for value in _by_community(value_weights, communities, 1.0)]
    fit_values = [float(value) for value in _by_community(fit_ratios, communities, 1.0)]
    denominator = sum(share * weight for share, weight in zip(shares, weights))
    if sum(shares) <= 0 or denominator <= 0:
        return {"simulation": None, "warning": "non_positive_total_share"}
    if runs <= 0:
        return {"simulation": None, "warning": "no_runs"}

    means = [
        _clamp(0.5 * anti + 0.3 * alignment_gap + 0.2 * (1.0 - fit), 0.01, 0.99)
        for anti, fit in zip(anti_strengths, fit_values)
    ]

    size = len(communities)
    if community_tag_sets is None:
        influence = [[1.0 if i == j else 0.0 for j in range(size)] for i in range(size)]
    else:
        tag_maps = [_weighted_tags(tags) for tags in community_tag_sets]
        if len(tag_maps) < size:
            tag_maps.extend([{} for _ in range(size - len(tag_maps))])
        influence = []
        for i in range(size):
            row = [_weighted_jaccard(tag_maps[i], tag_maps[j]) for j in range(size)]
            row_total = sum(row)
            if row_total <= 0:
                row = [1.0 if i == j else 0.0 for j in range(size)]
            else:
                row = [value / row_total for value in row]
            influence.append(row)

    losses = []
    rebellion_counts = [0] * size
    snapshots = []
    snapshot_interval = max(1, runs // 40)
    for r in range(runs):
        rng = random.Random(seed + r)
        propensities = [
            rng.betavariate(mean * kappa, (1.0 - mean) * kappa)
            for mean in means
        ]
        defections = [
            rng.betavariate(p * kappa2, (1.0 - p) * kappa2)
            for p in propensities
        ]
        for _ in range(max(0, influence_rounds)):
            prior = defections
            defections = [
                _clamp(
                    prior[i]
                    + influence_lambda
                    * sum(influence[i][j] * (prior[j] - prior[i]) for j in range(size)),
                    0.0,
                    1.0,
                )
                for i in range(size)
            ]
        for i, defection in enumerate(defections):
            if defection >= theta:
                rebellion_counts[i] += 1
        loss = sum(
            share * weight * defection
            for share, weight, defection in zip(shares, weights, defections)
        ) / denominator
        losses.append(100.0 * _clamp(loss, 0.0, 1.0))
        completed = r + 1
        if completed % snapshot_interval == 0:
            snapshots.append(
                {
                    "run": completed,
                    "mean": sum(losses) / len(losses),
                    "p5": _nearest_rank(losses, 0.05),
                    "p95": _nearest_rank(losses, 0.95),
                }
            )

    maximum = max(losses)
    histogram_hi = max(20, int(math.ceil(maximum / 5.0) * 5))
    counts = [0] * 24
    for loss in losses:
        bin_index = min(23, int(loss / histogram_hi * 24))
        counts[bin_index] += 1

    simulation = {
        "histogram": {"bins": 24, "lo": 0, "hi": histogram_hi, "counts": counts},
        "mean": sum(losses) / len(losses),
        "median": _nearest_rank(losses, 0.50),
        "p5": _nearest_rank(losses, 0.05),
        "p95": _nearest_rank(losses, 0.95),
        "per_community_rebellion_probability": {
            name: count / runs for name, count in zip(names, rebellion_counts)
        },
        "snapshots": snapshots,
    }
    parameters = {
        "seed": seed,
        "runs": runs,
        "kappa": kappa,
        "kappa2": kappa2,
        "influence_lambda": influence_lambda,
        "influence_rounds": influence_rounds,
        "theta": theta,
        "alignment_gap": alignment_gap,
        "value_weights": value_weights,
        "community_tag_sets": community_tag_sets,
        "fit_ratios": fit_ratios,
        "assumed": True,
    }
    return {"simulation": simulation, "parameters": parameters, "calibration": CALIBRATION}
