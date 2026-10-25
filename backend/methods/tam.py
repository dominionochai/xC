"""Source-aware TAM expansion calculations (M8).

Units: population is people; penetration is a fraction from 0 to 1; spend is
annual USD per customer; affinity is a score from 0 to 100; ip_loss values
are fractions from 0 to 1.  sensitivity_range is a ratio from 0 to 1.
"""
from __future__ import annotations

import math
from typing import Any

_ASSUMPTION_FIELDS = (
    "pop", "penetration", "spend", "affinity", "ip_loss_base",
    "ip_loss_low", "ip_loss_high",
)
_CENTRAL_FIELDS = ("pop", "penetration", "spend", "affinity", "ip_loss_base")
_BASELINE_FIELDS = ("pop", "penetration", "spend")
_FRACTION_FIELDS = {"penetration", "ip_loss_base", "ip_loss_low", "ip_loss_high"}


def _number(value: Any) -> float | None:
    """Return finite numeric input, excluding booleans and malformed values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _has_citation(sources: Any, field: str) -> bool:
    """A sourced assumption requires a non-empty URL and year."""
    if not isinstance(sources, dict):
        return False
    citation = sources.get(field)
    if not isinstance(citation, dict):
        return False
    url, year = citation.get("url"), citation.get("year")
    return (isinstance(url, str) and bool(url.strip()) and year is not None
            and bool(str(year).strip()))


def _calculate(
    values: dict[str, float],
    changed_field: str | None = None,
    multiplier: float = 1.0,
    loss_field: str = "ip_loss_base",
) -> float:
    """Calculate regional expansion, optionally varying one assumption."""
    changed = dict(values)
    if changed_field is not None:
        varied = changed[changed_field] * multiplier
        # Sensitivity cases for bounded inputs stay within their defined units.
        if changed_field in _FRACTION_FIELDS:
            varied = min(1.0, max(0.0, varied))
        elif changed_field == "affinity":
            varied = min(100.0, max(0.0, varied))
        changed[changed_field] = varied
    reach = changed["pop"] * changed["penetration"]
    # ip_loss is already a fraction; do not infer percent-vs-fraction units.
    return (reach * changed["spend"] * (changed["affinity"] / 100.0)
            * (1.0 - changed[loss_field]))


def tam_expansion(
    regions: list[dict[str, Any]], sensitivity_range: float = 0.30
) -> dict[str, Any]:
    """Compute sourced regional TAM, sensitivity bounds, and warnings.

    Missing or invalid assumptions are not imputed.  Every assumption used in
    the calculation must have a citation containing both URL and year.
    """
    sensitivity = _number(sensitivity_range)
    if sensitivity is None or not 0.0 <= sensitivity <= 1.0:
        return {
            "tam": None,
            "reason": "invalid_value:sensitivity_range",
            "warnings": ["invalid_value:sensitivity_range"],
            "expansion": {},
            "tornado": {},
            "tam_partial": True,
        }

    prepared: list[dict[str, Any]] = []
    warnings: list[str] = []
    any_sourced_value = False
    for raw in regions or []:
        region = raw if isinstance(raw, dict) else {}
        name = str(region.get("region", ""))
        sources = region.get("sources", {})
        values: dict[str, float | None] = {}
        row_warnings: list[str] = []
        for field in _ASSUMPTION_FIELDS:
            value = _number(region.get(field))
            if value is not None:
                if field in _FRACTION_FIELDS and not 0.0 <= value <= 1.0:
                    row_warnings.append(f"invalid_value:{field}:{name}")
                    value = None
                elif field == "affinity" and not 0.0 <= value <= 100.0:
                    row_warnings.append(f"invalid_value:{field}:{name}")
                    value = None
            elif region.get(field) is not None:
                row_warnings.append(f"invalid_value:{field}:{name}")

            if not _has_citation(sources, field):
                row_warnings.append(f"missing_source:{field}:{name}")
                value = None
            elif value is None and region.get(field) is None:
                row_warnings.append(f"missing_value:{field}:{name}")
            elif value is not None:
                any_sourced_value = True
            values[field] = value
        warnings.extend(row_warnings)
        prepared.append({"region": name, "values": values, "warnings": row_warnings})

    if not any_sourced_value:
        return {
            "tam": None,
            "reason": "all_assumptions_null",
            "expansion": {},
            "tornado": {},
            "tam_partial": True,
            "warnings": warnings,
        }

    expansion: dict[str, dict[str, Any]] = {}
    baseline_values: list[float] = []
    expansion_values: list[float] = []
    complete_rows: list[dict[str, float]] = []
    tam_partial = False
    for item in prepared:
        name, values = item["region"], item["values"]
        base_complete = all(values[field] is not None for field in _BASELINE_FIELDS)
        central_complete = all(values[field] is not None for field in _CENTRAL_FIELDS)
        all_complete = all(values[field] is not None for field in _ASSUMPTION_FIELDS)
        reach = (float(values["pop"]) * float(values["penetration"])
                 if values["pop"] is not None and values["penetration"] is not None
                 else None)
        baseline = (float(values["pop"]) * float(values["penetration"])
                    * float(values["spend"]) if base_complete else None)
        calculated: dict[str, Any] = {
            "reach": reach,
            "expansion": None,
            "expansion_low": None,
            "expansion_high": None,
            "partial": not all_complete,
            "warnings": list(item["warnings"]),
        }
        if baseline is not None:
            baseline_values.append(baseline)
        if all_complete:
            numeric = {field: float(values[field]) for field in _ASSUMPTION_FIELDS}
            calculated["expansion"] = _calculate(numeric)
            calculated["expansion_low"] = _calculate(numeric, loss_field="ip_loss_low")
            calculated["expansion_high"] = _calculate(numeric, loss_field="ip_loss_high")
            expansion_values.append(float(calculated["expansion"]))
            complete_rows.append(numeric)
        else:
            tam_partial = True
        expansion[name] = calculated

    tornado: dict[str, dict[str, float]] = {}
    for field in _CENTRAL_FIELDS:
        if not complete_rows:
            break
        low = sum(_calculate(row, field, 1.0 - sensitivity) for row in complete_rows)
        high = sum(_calculate(row, field, 1.0 + sensitivity) for row in complete_rows)
        tornado[field] = {"low": low, "high": high}

    return {
        "baseline_total": sum(baseline_values) if baseline_values else None,
        "expansion": expansion,
        "total_expansion": sum(expansion_values) if expansion_values else None,
        "tam_partial": tam_partial,
        "warnings": warnings,
        "tornado": tornado,
    }
