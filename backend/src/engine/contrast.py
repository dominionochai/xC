"""Compare two entities with partial-safe Qloo evidence."""
from typing import Any

def contrast(qloo: Any, left: Any, right: Any, budget: Any = None) -> dict[str, Any]:
    out = {"left": left, "right": right, "differences": {}, "provenance": {"sources": ["qloo"]}, "evidence": [], "warnings": []}
    for label, entity in (("left", left), ("right", right)):
        if not hasattr(qloo, "profile"):
            out["warnings"].append("missing_qloo_method:profile")
            break
        if budget is not None and getattr(qloo, "call_count", 0) >= budget.max_calls:
            out["warnings"].append("budget_exhausted:contrast")
            break
        try:
            profile = qloo.profile(entity)
            out[label + "_profile"] = profile
            out["evidence"].append({"source": "qloo.profile", "detail": str(entity), "value": profile})
        except Exception:
            out["warnings"].append("qloo_error:profile")
    a, b = out.get("left_profile"), out.get("right_profile")
    if isinstance(a, dict) and isinstance(b, dict):
        for key in set(a) | set(b):
            if a.get(key) != b.get(key): out["differences"][key] = {"left": a.get(key), "right": b.get(key)}
    return out
