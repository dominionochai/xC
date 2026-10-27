"""Affinity/tag fit scoring."""
from typing import Any

def fit(qloo: Any, entity: Any, audience: Any = None, budget: Any = None) -> dict[str, Any]:
    result = {"score": None, "affinity": None, "tags": [], "metrics": {}, "provenance": {"sources": ["qloo"]}, "evidence": [], "warnings": []}
    for method, args, key in (("tags_for", (entity,), "tags"), ("affinity", (entity, audience), "affinity")):
        if not hasattr(qloo, method):
            result["warnings"].append(f"missing_qloo_method:{method}")
            continue
        if budget is not None and getattr(qloo, "call_count", 0) >= budget.max_calls:
            result["warnings"].append("budget_exhausted:fit")
            break
        try:
            value = getattr(qloo, method)(*args)
            result[key] = value
            result["evidence"].append({"source": f"qloo.{method}", "value": value})
        except Exception:
            result["warnings"].append(f"qloo_error:{method}")
    affinity = result["affinity"]
    if isinstance(affinity, (int, float)):
        result["metrics"]["affinity"] = float(affinity)
        result["score"] = float(affinity)
    elif isinstance(affinity, dict):
        vals = [v for v in affinity.values() if isinstance(v, (int, float))]
        if vals:
            result["metrics"]["affinity_mean"] = sum(vals) / len(vals)
            result["score"] = result["metrics"]["affinity_mean"]
    return result
