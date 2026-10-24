"""Source-aware, assumption-labelled M8 TAM expansion arithmetic."""

import json
import math
from pathlib import Path

try:
    from backend.src.engine.budget import Budget
except ImportError:  # budget.py is provided by the integrating application.
    class Budget:
        """Import-compatible fallback for standalone use."""
        def __init__(self, max_calls=40): self.max_calls = max_calls

FIELDS = ("pop", "penetration", "spend", "affinity", "ip_loss_base", "ip_loss_low", "ip_loss_high")
CENTRAL = ("pop", "penetration", "spend", "affinity", "ip_loss_base")


def _number(x):
    if isinstance(x, bool): return None
    try:
        n = float(x)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError): return None


def _regions(data):
    if data is None:
        path = Path(__file__).resolve().parents[3] / "backend" / "data" / "regions.json"
        try:
            with path.open(encoding="utf-8") as stream: data = json.load(stream)
        except (OSError, ValueError): return []
    if isinstance(data, dict): data = data.get("regions", data)
    if isinstance(data, dict):
        return [dict(value, region=value.get("region", key)) for key, value in data.items() if isinstance(value, dict)]
    return data if isinstance(data, list) else []


def _source_ok(entry):
    if not isinstance(entry, dict) or entry.get("year") is None: return False, False
    url, note = entry.get("url"), entry.get("note", "")
    if isinstance(url, str) and url.strip(): return True, False
    if isinstance(note, str) and note.lower().startswith("est:"): return True, True
    return False, False


def _calc(v, field=None, multiplier=1.0):
    x = dict(v)
    if field == "ip_loss_base": x[field] = max(0.0, min(100.0, x[field] * multiplier))
    elif field is not None: x[field] *= multiplier
    return x["pop"] * x["penetration"] * x["spend"] * (x["affinity"] / 100.0) * (1.0-x["ip_loss_base"]/100.0)


def run(qloo, budget, regions_data=None):
    """Return regional reach, expansion, tornado sensitivity, and provenance.

    M8 is computed from the supplied source ledger; it intentionally has no
    Qloo dependency. The ``qloo`` and ``budget`` arguments preserve the engine API.
    """
    warnings, rows, valid_assumptions = [], [], 0
    for entry in _regions(regions_data):
        if not isinstance(entry, dict): continue
        name = str(entry.get("region", entry.get("name", "")))
        sources = entry.get("sources", {}) if isinstance(entry.get("sources", {}), dict) else {}
        values, provenance = {}, {}
        for field in FIELDS:
            value = _number(entry.get(field))
            ok, estimated = _source_ok(sources.get(field))
            if not ok or value is None:
                values[field] = None
                warnings.append("missing_source:%s:%s" % (field, name) if not ok else "missing_value:%s:%s" % (field, name))
                continue
            values[field] = value
            valid_assumptions += 1
            provenance[field] = dict(sources[field])
            if estimated: warnings.append("estimated_assumption:%s:%s" % (field, name))
        reach = values["pop"] * values["penetration"] if values["pop"] is not None and values["penetration"] is not None else None
        baseline = values["pop"] * values["penetration"] * values["spend"] if all(values[k] is not None for k in ("pop", "penetration", "spend")) else None
        complete = all(values[k] is not None for k in FIELDS)
        expansion = _calc(values) if complete else None
        low = high = None
        if complete:
            low_values, high_values = dict(values), dict(values)
            low_values["ip_loss_base"] = values["ip_loss_high"]
            high_values["ip_loss_base"] = values["ip_loss_low"]
            low, high = _calc(low_values), _calc(high_values)
        rows.append({"region": name, "reach": reach, "baseline": baseline,
                     "expansion": expansion, "expansion_low": low, "expansion_high": high,
                     "partial": not complete, "assumptions": values, "sources": provenance})
    complete = [r for r in rows if r["expansion"] is not None]
    if valid_assumptions == 0:
        return {"tam": None, "reason": "all_assumptions_null", "regions": rows,
                "tam_partial": True, "warnings": warnings, "tornado": {}, "provenance": "M8 source-ledger arithmetic"}
    total = sum(r["expansion"] for r in complete) if complete else None
    base = sum(r["baseline"] for r in rows if r["baseline"] is not None) or None
    tornado = {}
    for field in CENTRAL:
        vals = [r["assumptions"] for r in complete]
        if vals:
            tornado[field] = {"low": sum(_calc(v, field, 0.70) for v in vals),
                              "high": sum(_calc(v, field, 1.30) for v in vals)}
    return {"tam": total, "reason": None if total is not None else "no_complete_regions",
            "baseline": base, "regions": rows, "tam_partial": len(complete) != len(rows) or bool(warnings),
            "warnings": warnings, "tornado": tornado, "provenance": "M8 source-ledger arithmetic"}
