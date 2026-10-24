"""M7 regional-affinity analysis with an explicit fallback ladder."""

import math

try:
    from backend.src.engine.budget import Budget
except ImportError:  # budget.py is provided by the integrating application.
    class Budget:
        """Import-compatible fallback for standalone use."""
        def __init__(self, max_calls=40): self.max_calls = max_calls

CAVEAT = "neighborhood granularity not supported by the data provider"
_STOP = object()


def _score(raw):
    if isinstance(raw, dict):
        for key in ("affinity", "score", "value"):
            if key in raw: return _score(raw[key])
        if isinstance(raw.get("data"), dict): return _score(raw["data"])
        return None
    if isinstance(raw, bool): return None
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError): return None


def _vectors(raw):
    if isinstance(raw, (list, tuple)) and len(raw) == 2: return raw[0], raw[1]
    if isinstance(raw, dict):
        left = next((raw[k] for k in ("a", "A", "acquirer", "target_cells", "a_cells") if k in raw), None)
        right = next((raw[k] for k in ("t", "T", "target", "acquirer_cells", "t_cells") if k in raw), None)
        if left is None and isinstance(raw.get("data"), dict): return _vectors(raw["data"])
        return left, right
    return None, None


def _cosine(left, right):
    try:
        a, b = [float(x) for x in left], [float(x) for x in right]
        if len(a) != len(b) or not a: return None
        den = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
        return 0.0 if den == 0 else 100.0 * max(-1.0, min(1.0, sum(x*y for x,y in zip(a,b))/den))
    except (TypeError, ValueError): return None


def run(qloo, budget, regions, global_affinity=None):
    """Resolve each requested region using provider, heatmap, then city data.

    Every provider request is budget-checked immediately before invocation.
    Missing/partial results fall through the ladder and never raise.
    """
    names = []
    for item in regions or []:
        name = item.get("region", item.get("name")) if isinstance(item, dict) else item
        if name is not None: names.append(str(name))
    results, warnings = {}, []
    limit = getattr(budget, "max_calls", float("inf"))
    def call(method, name, phase):
        if getattr(qloo, "call_count", 0) >= limit:
            warning = "budget_exhausted:%s" % phase
            if warning not in warnings: warnings.append(warning)
            return _STOP
        try: return getattr(qloo, method)(name)
        except Exception:
            warnings.append("qloo_call_failed:%s:%s" % (method, name))
            return None
    for name in names:
        value, level, caveat, provenance = None, None, None, []
        raw = call("region_affinity", name, "region_affinity")
        if raw is not _STOP:
            value = _score(raw)
            if value is not None: level = 1; provenance.append("qloo.region_affinity:%s" % name)
        if value is None and raw is not _STOP:
            raw = call("region_heatmap", name, "region_heatmap")
            if raw is not _STOP:
                a, b = _vectors(raw)
                value = _cosine(a, b) if a is not None and b is not None else None
                if value is not None: level = 2; provenance.append("qloo.region_heatmap:%s" % name)
        if value is None and raw is not _STOP:
            raw = call("city_affinity", name, "city_affinity")
            if raw is not _STOP:
                value = _score(raw)
                if value is not None:
                    level, caveat = 3, CAVEAT
                    provenance.append("qloo.city_affinity:%s" % name)
        if value is None:
            results[name] = {"affinity": None, "reason": "all_levels_failed", "provenance": provenance}
            continue
        results[name] = {"affinity": value, "ladder_level": level,
                         "friction": 100.0-value,
                         "delta_vs_global": value-float(global_affinity) if _score(global_affinity) is not None else None,
                         "provenance": provenance}
        if caveat is not None: results[name]["caveat"] = caveat
    return {"regions": results, "warnings": warnings,
            "partial": bool(warnings), "provenance": "M7 locality ladder"}
