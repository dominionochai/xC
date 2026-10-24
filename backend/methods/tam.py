"""Source-aware TAM expansion calculations (M8)."""
from __future__ import annotations

import math
from typing import Any


_ASSUMPTION_FIELDS = ("pop", "penetration", "spend", "affinity", "ip_loss_base", "ip_loss_low", "ip_loss_high")
_CENTRAL_FIELDS = ("pop", "penetration", "spend", "affinity", "ip_loss_base")
_BASELINE_FIELDS = ("pop", "penetration", "spend")


def _number(value: Any) -> float | None:
    """Return finite numeric values, excluding booleans and malformed inputs."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _has_citation(sources: Any, field: str) -> bool:
    """A citation requires a non-empty URL and year."""
    if not isinstance(sources, dict):
        return False
    citation = sources.get(field)
    if not isinstance(citation, dict):
        return False
    url, year = citation.get("url"), citation.get("year")
    return isinstance(url, str) and bool(url.strip()) and year is not None and bool(str(year).strip())


def _calculate(values: dict[str, float], changed_field: str | None = None,
               multiplier: float = 1.0, loss_field: str = "ip_loss_base") -> float:
    """Calculate regional expansion, optionally varying one assumption."""
    changed = dict(values)
    if changed_field is not None:
        changed[changed_field] *= multiplier
    return (changed["pop"] * changed["penetration"] * changed["spend"]
            * (changed["affinity"] / 100.0)
            * (1.0 - changed[loss_field] / 100.0))


def tam_expansion(regions: list[dict[str, Any]], sensitivity_range: float = 0.30) -> dict[str, Any]:
    """Compute sourced regional TAM, bounds, baseline, and +/- tornado values.

    Every assumption is usable only when its matching ``sources`` item has both
    ``url`` and ``year``. Otherwise it is null and warns
    ``missing_source:<field>:<region>``; no defaults are invented. Reach and
    baseline are modeled as population * penetration and reach * spend.
    Expansion uses affinity and IP-loss percentages; low/high use the supplied
    p95/p5 IP-loss bounds. All seven assumptions are required for a complete
    regional expansion. Tornado estimates vary central assumptions by the
    stated relative sensitivity (default +/-30%).
    """
    sensitivity = _number(sensitivity_range)
    if sensitivity is None or sensitivity < 0:
        sensitivity = 0.30

    prepared: list[dict[str, Any]] = []
    warnings: list[str] = []
    any_sourced_value = False
    for raw in regions or []:
        region = raw if isinstance(raw, dict) else {}
        name = str(region.get("region", ""))
        source_map = region.get("sources", {})
        values: dict[str, float | None] = {}
        region_warnings: list[str] = []
        for field in _ASSUMPTION_FIELDS:
            value = _number(region.get(field))
            if not _has_citation(source_map, field):
                value = None
                region_warnings.append(f"missing_source:{field}:{name}")
            elif value is None:
                region_warnings.append(f"missing_value:{field}:{name}")
            else:
                any_sourced_value = True
            values[field] = value
        prepared.append({"region": name, "values": values, "warnings": region_warnings})
        warnings.extend(region_warnings)

    if not any_sourced_value:
        return {"tam": None, "reason": "all_assumptions_null"}

    expansion: dict[str, dict[str, Any]] = {}
    baseline_values: list[float] = []
    expansion_values: list[float] = []
    complete_rows: list[dict[str, float]] = []
    tam_partial = False
    for item in prepared:
        name, values, row_warnings = item["region"], item["values"], item["warnings"]
        reach = None
        if values["pop"] is not None and values["penetration"] is not None:
            reach = values["pop"] * values["penetration"]
        if all(values[field] is not None for field in _BASELINE_FIELDS):
            baseline_values.append(values["pop"] * values["penetration"] * values["spend"])
        partial = any(values[field] is None for field in _ASSUMPTION_FIELDS)
        tam_partial = tam_partial or partial
        calculated: dict[str, float | None] = {"expansion": None, "expansion_low": None, "expansion_high": None}
        if not partial:
            numeric = {field: float(values[field]) for field in _ASSUMPTION_FIELDS}
            calculated["expansion"] = _calculate(numeric)
            calculated["expansion_low"] = _calculate(numeric, loss_field="ip_loss_low")
            calculated["expansion_high"] = _calculate(numeric, loss_field="ip_loss_high")
            expansion_values.append(calculated["expansion"])
            complete_rows.append(numeric)
        expansion[name] = {"reach": reach, **calculated, "partial": partial, "warnings": list(row_warnings)}

    tornado: dict[str, dict[str, float | None]] = {}
    for field in _CENTRAL_FIELDS:
        if complete_rows:
            low_total = sum(_calculate(row, field, 1.0 - sensitivity) for row in complete_rows)
            high_total = sum(_calculate(row, field, 1.0 + sensitivity) for row in complete_rows)
            tornado[field] = {"low": low_total, "high": high_total}

    return {
        "baseline_total": sum(baseline_values) if baseline_values else None,
        "expansion": expansion,
        "total_expansion": sum(expansion_values) if expansion_values else None,
        "tam_partial": tam_partial,
        "warnings": warnings,
        "tornado": tornado,
    }
