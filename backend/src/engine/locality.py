"""Geographic affinity ladder with explicit provider-resolution caveat."""
import math

CAVEAT = "neighborhood granularity not supported by the data provider"


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _score(value):
    if isinstance(value, dict):
        for key in ("affinity", "score", "value"):
            if value.get(key) is not None:
                value = value[key]; break
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vector(value):
    if isinstance(value, dict):
        # Prefer explicit cell/value sequences, but also support keyed cell maps.
        for key in ("cells", "values", "heatmap", "data"):
            if key in value:
                return _vector(value[key])
        result = []
        for item in value.values(): result.extend(_vector(item))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value: result.extend(_vector(item))
        return result
    try: return [float(value)]
    except (TypeError, ValueError): return []


def _cosine(left, right):
    n = min(len(left), len(right))
    a, b = left[:n], right[:n]
    na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(x*x for x in b))
    if na == 0 or nb == 0: return 0.0
    return sum(x*y for x, y in zip(a, b)) / (na * nb)


def run(qloo, budget, regions, global_affinity=None):
    warnings, evidence, provenance = [], [], []
    exhausted = False
    def call(method, *args):
        nonlocal exhausted
        if getattr(qloo, "call_count", 0) >= getattr(budget, "max_calls", 0):
            exhausted = True
            return None
        try:
            value = getattr(qloo, method)(*args)
            evidence.append({"source": "qloo", "method": method, "arguments": list(args), "result": value})
            provenance.append({"source": "qloo", "method": method})
            return value
        except Exception as exc:
            warnings.append("qloo_" + method + "_failed:" + type(exc).__name__)
            return None
    if isinstance(regions, dict):
        regions = regions.get("regions", [regions])
    results = []
    for region in regions or []:
        name = _get(region, "region", _get(region, "name", region if isinstance(region, str) else None))
        name = str(name) if name is not None else ""
        affinity = None; level = None; caveat = None
        raw = call("region_affinity", name)
        affinity = _score(raw)
        if affinity is not None: level = 1
        if affinity is None and not exhausted:
            heatmap = call("region_heatmap", name)
            if heatmap is not None:
                try:
                    if isinstance(heatmap, dict) and ("left" in heatmap or "a" in heatmap):
                        left = _vector(heatmap.get("left", heatmap.get("a")))
                        right = _vector(heatmap.get("right", heatmap.get("b")))
                    elif isinstance(heatmap, (list, tuple)) and len(heatmap) == 2:
                        left, right = _vector(heatmap[0]), _vector(heatmap[1])
                    else:
                        left = _vector(_get(heatmap, "source", [])); right = _vector(_get(heatmap, "target", []))
                    if left or right:
                        affinity = _cosine(left, right); level = 2
                except Exception:
                    warnings.append("region_heatmap_invalid:" + name)
        if affinity is None and not exhausted:
            raw = call("city_affinity", name)
            affinity = _score(raw)
            if affinity is not None:
                level = 3; caveat = CAVEAT
        if affinity is None:
            row = {"region": name, "affinity": None, "reason": "all_levels_failed", "ladder_level": None, "friction": None, "delta_vs_global": None, "provenance": []}
        else:
            baseline = _score(global_affinity)
            row = {"region": name, "affinity": affinity, "ladder_level": level, "friction": 100 - affinity, "delta_vs_global": (affinity - baseline if baseline is not None else None), "provenance": [{"source": "qloo", "method": {1: "region_affinity", 2: "region_heatmap_cosine", 3: "city_affinity"}[level]}]}
            if caveat: row["caveat"] = caveat
        results.append(row)
        if exhausted:
            warnings.append("budget_exhausted:locality")
            break
    return {"locality": results, "regions": results, "warnings": warnings, "evidence": evidence, "provenance": provenance}
