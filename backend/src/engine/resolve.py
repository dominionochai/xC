"""Entity resolution phase."""
from typing import Any

def resolve(qloo: Any, query: str, entity_type: str | None = None, budget: Any = None) -> dict[str, Any]:
    out = {"matches": [], "selected": None, "confidence": 0.0, "provenance": {"sources": ["qloo"]}, "evidence": [], "warnings": []}
    if not query or not str(query).strip():
        out["warnings"].append("empty_query")
        return out
    if budget is not None and getattr(qloo, "call_count", 0) >= budget.max_calls:
        out["warnings"].append("budget_exhausted:resolve")
        return out
    try:
        rows = qloo.search(query, entity_type=entity_type) or []
        out["matches"] = rows
        out["evidence"] = [{"source": "qloo.search", "detail": str(query), "value": rows}]
        if len(rows) == 1:
            out["selected"], out["confidence"] = rows[0], 1.0
        elif rows:
            out["selected"], out["confidence"] = rows[0], 0.5
            out["warnings"].append("ambiguous_match")
    except Exception as exc:
        out["warnings"].append("qloo_error:resolve")
        out["error"] = str(exc)
    return out
