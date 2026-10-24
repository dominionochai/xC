"""Deterministic W2 stochastic simulation; outputs are explicitly uncalibrated."""
import random
import math

CALIBRATION = "NONE - assumptions uncalibrated, see METHODS.md M5"


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _clamp(value, low=.01, high=.99):
    try: return max(low, min(high, float(value)))
    except (TypeError, ValueError): return low


def _number(obj, keys, default=0.0):
    for key in keys:
        value = _get(obj, key)
        if value is not None:
            try: return float(value)
            except (TypeError, ValueError): pass
    return default


def run(qloo, budget, communities, alignment_gap, seed=42, runs=5000):
    communities = list(communities or [])
    if not communities:
        return {"simulation": None, "warning": "no_communities", "warnings": ["no_communities"], "evidence": [], "provenance": []}
    warnings, evidence, provenance = [], [], [{"source": "model", "method": "assumption-based W2 simulation"}]
    try: gap = _clamp(alignment_gap, 0, 1)
    except Exception: gap = .5
    rows = []
    for index, community in enumerate(communities):
        tags = _get(community, "tags", []) or []
        fit_ratio = _number(community, ("fit_ratio", "fit", "affinity"), 0.0)
        if fit_ratio > 1: fit_ratio /= 100.0
        fit_ratio = _clamp(fit_ratio, 0, 1)
        alignment = _number(community, ("alignment", "alignment_score"), 1.0 - gap)
        alignment = _clamp(alignment, 0, 1)
        share = _number(community, ("share", "weight", "size"), 1.0 / len(communities))
        if share <= 0: share = 1.0 / len(communities)
        # Higher alignment and fit reduce modeled mismatch; retain the specified gap term.
        a_i = alignment
        m = _clamp(.5 * a_i + .3 * gap + .2 * (1.0 - fit_ratio))
        rows.append({"id": _get(community, "id", "community_%d" % (index + 1)), "tags": list(tags), "share": share, "fit_ratio": fit_ratio, "m": m})
    total_share = sum(row["share"] for row in rows) or 1.0
    for row in rows: row["share"] /= total_share
    # Similarity weights are computed locally from tag overlap; no Qloo calls are needed.
    n = len(rows)
    matrix = [[0.0] * n for _ in range(n)]
    have_tag_sets = any(row["tags"] for row in rows)
    if have_tag_sets:
        for i, left in enumerate(rows):
            for j, right in enumerate(rows):
                if i == j: matrix[i][j] = 1.0
                else:
                    a, b = set(map(str, left["tags"])), set(map(str, right["tags"]))
                    matrix[i][j] = len(a & b) / len(a | b) if a | b else 0.0
                denom = sum(matrix[i])
                if denom: matrix[i] = [v / denom for v in matrix[i]]
    else:
        matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    rng = random.Random(seed)
    count = max(0, int(runs))
    losses, rebel_counts = [], [0] * n
    snapshots = []
    max_loss = 0.0
    for trial in range(count):
        probs = []
        for row in rows:
            m = row["m"]
            first = rng.betavariate(max(.001, m * 20), max(.001, (1 - m) * 20))
            p = rng.betavariate(max(.001, first * 10), max(.001, (1 - first) * 10))
            probs.append(_clamp(p))
        for _ in range(3):
            probs = [_clamp(.8 * probs[i] + .2 * sum(matrix[i][j] * probs[j] for j in range(n))) for i in range(n)]
        ds = [abs(probs[i] - rows[i]["fit_ratio"]) for i in range(n)]
        for i, d in enumerate(ds):
            if d >= .15: rebel_counts[i] += 1
        denominator = sum(rows[i]["share"] * max(.001, rows[i]["fit_ratio"]) for i in range(n))
        loss = sum(rows[i]["share"] * max(.001, rows[i]["fit_ratio"]) * ds[i] for i in range(n)) / denominator if denominator else 0.0
        losses.append(loss); max_loss = max(max_loss, loss)
        if count and (trial + 1) % max(1, count // 40) == 0:
            snapshots.append({"run": trial + 1, "loss": loss, "rebelling": [rows[i]["id"] for i, d in enumerate(ds) if d >= .15]})
    ordered = sorted(losses)
    def percentile(p):
        if not ordered: return None
        pos = (len(ordered) - 1) * p
        lo = int(pos); hi = min(lo + 1, len(ordered)); frac = pos - lo
        return ordered[lo] * (1 - frac) + ordered[hi] * frac
    hi = max(20, int(math.ceil(max_loss / 5.0) * 5))
    bins = [0] * 24
    if ordered:
        for value in ordered:
            idx = min(23, int(value / hi * 24))
            bins[max(0, idx)] += 1
    sim = {"runs": count, "seed": seed, "mean": (sum(losses) / count if count else None), "median": percentile(.5), "p5": percentile(.05), "p95": percentile(.95), "histogram": {"bins": bins, "count": 24, "lo": 0, "hi": hi}, "per_community_rebellion_probability": {rows[i]["id"]: (rebel_counts[i] / count if count else None) for i in range(n)}, "snapshots": snapshots, "parameters": {"m": "clamp(.5*a_i+.3*g+.2*(1-fit_ratio_i),.01,.99)", "beta_1": "Beta(m*20,(1-m)*20)", "beta_2": "Beta(p*10,(1-p)*10)", "influence_rounds": 3, "lambda": .2, "rebel_threshold": .15, "weight_matrix": "tag Jaccard row-normalized; identity when no tag sets"}, "calibration": CALIBRATION}
    return {"simulation": sim, "warnings": warnings, "evidence": evidence, "provenance": provenance}
