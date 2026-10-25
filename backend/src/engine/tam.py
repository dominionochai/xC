"""Thin adapter from region data and Qloo locality to the M8 TAM method."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.src import contract
from backend.methods.tam import tam_expansion
from backend.src.engine.locality import run as run_locality

_FACTORS = (("pop", "people"), ("penetration", "fraction"), ("spend", "USD/customer/year"), ("affinity", "0-100"), ("ip_loss_base", "fraction"), ("ip_loss_low", "fraction"), ("ip_loss_high", "fraction"))
_PROVENANCE = "backend.methods.tam.tam_expansion"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _default_regions() -> Any:
    path = Path(__file__).resolve().parents[2] / "data" / "regions.json"
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        result = dump(mode="python", exclude_none=True)
        return result if isinstance(result, dict) else {}
    return {}


def _region_payload(value: Any) -> Any:
    if value is None:
        return _default_regions()
    if isinstance(value, dict) and "regions_data" in value:
        return value.get("regions_data")
    if isinstance(value, dict) and "regions" in value:
        return value
    return value


def run(qloo: Any, budget: Any, regions_data: Any = None, overrides: Any = None) -> contract.ReportResult:
    """Call the TAM method and map its output to the public report contract."""
    if isinstance(regions_data, dict) and any(key in regions_data for key in ("assumption_overrides", "overrides")):
        phase_inputs = regions_data
        if overrides is None:
            overrides = phase_inputs.get("assumption_overrides", phase_inputs.get("overrides"))
        regions_data = phase_inputs.get("regions_data", phase_inputs.get("regions"))
    source = _region_payload(regions_data)
    records = source.get("regions", []) if isinstance(source, dict) else source
    if not isinstance(records, list):
        records = []
    override_values = _mapping(overrides)
    regional_populations = override_values.get("regional_populations") or {}
    if not isinstance(regional_populations, dict):
        regional_populations = {}
    assumptions: list[contract.Assumption] = []
    method_inputs: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        item = dict(record)
        region = str(item.get("region", ""))
        if region in regional_populations:
            item["pop"] = regional_populations[region]
            assumptions.append(contract.Assumption(key=f"{region}:pop", value=item["pop"], unit="people", source="assumed", description="Regional population request override; provenance assumed."))
        for key, field, unit in (("penetration_rate", "penetration", "fraction"), ("annual_spend_per_customer_usd", "spend", "USD/customer/year")):
            if override_values.get(key) is not None:
                item[field] = override_values[key]
                assumptions.append(contract.Assumption(key=f"{region}:{field}", value=item[field], unit=unit, source="assumed", description="Request override; provenance assumed."))
        item["core_audience_value_usd"] = override_values.get("core_audience_value_usd")
        method_inputs.append(item)
    locality_result = run_locality(qloo, budget, method_inputs)
    locality_result = locality_result if isinstance(locality_result, dict) else {}
    locality_rows = locality_result.get("locality", locality_result.get("regions", []))
    locality_by_name = {str(row.get("region")): row for row in locality_rows if isinstance(row, dict)} if isinstance(locality_rows, list) else {}
    for item in method_inputs:
        local = locality_by_name.get(str(item.get("region", "")))
        if local is not None:
            item["affinity"] = local.get("affinity")
        elif item.get("affinity") is None:
            item["affinity"] = None
        if item.get("affinity") is not None:
            assumptions.append(contract.Assumption(key=f"{item.get('region', '')}:affinity", value=item["affinity"], unit="0-100", source="Qloo locality", description="Regional affinity supplied by Qloo locality."))
    calculated = tam_expansion(method_inputs)
    calculated = calculated if isinstance(calculated, dict) else {}
    expansion = calculated.get("expansion")
    expansion = expansion if isinstance(expansion, dict) else {}
    metric_value = calculated.get("total_expansion")
    baseline_value = calculated.get("baseline_total")
    metric_values = [metric_value, baseline_value]
    no_sources_or_overrides = not assumptions and not any(
        isinstance((record.get("sources") if isinstance(record, dict) else None), dict)
        and any((record["sources"].get(field) or {}).get("url") for field, _ in _FACTORS if isinstance(record["sources"].get(field), dict))
        for record in records
    )
    if no_sources_or_overrides:
        metric_values = [None, None]
    metrics = [
        contract.Metric(name="tam_expansion", value=metric_values[0], unit="USD", provenance=_PROVENANCE),
        contract.Metric(name="baseline_total", value=metric_values[1], unit="USD", provenance=_PROVENANCE),
    ]
    regions = []
    for record in method_inputs:
        name = str(record.get("region", ""))
        result = expansion.get(name, {})
        result = result if isinstance(result, dict) else {}
        regions.append(contract.RegionResult(region=name, population=record.get("pop"), audience_size=result.get("reach"), metrics=[
            contract.Metric(name="reach", value=result.get("reach"), unit="people", provenance=_PROVENANCE),
            contract.Metric(name="expansion", value=result.get("expansion"), unit="USD", provenance=_PROVENANCE),
        ]))
        sources = record.get("sources") if isinstance(record.get("sources"), dict) else {}
        for factor, unit in _FACTORS:
            if record.get(factor) is not None and not any(a.key == f"{name}:{factor}" for a in assumptions):
                citation = sources.get(factor) if isinstance(sources.get(factor), dict) else {}
                assumptions.append(contract.Assumption(key=f"{name}:{factor}", value=record.get(factor), unit=unit, source=citation.get("url"), description=f"Source year: {citation.get('year')}" if citation.get("year") is not None else None))
    tornado = calculated.get("tornado")
    tornado = tornado if isinstance(tornado, dict) else {}
    sensitivity = [contract.Sensitivity(name=str(key), parameter=str(key), metric="tam_expansion", low=value.get("low"), high=value.get("high")) for key, value in tornado.items() if isinstance(value, dict)]
    warnings = [str(item) for item in _as_list(calculated.get("warnings")) + _as_list(locality_result.get("warnings"))]
    partial = bool(calculated.get("tam_partial", metric_values[0] is None)) or no_sources_or_overrides
    if no_sources_or_overrides:
        warnings.append("tam_partial:no sourced assumptions or overrides; TAM metrics are null")
    elif metric_values[0] is None and not warnings:
        warnings.append("tam_partial:method returned no sourced TAM estimate")
    tam_data = dict(calculated)
    tam_data["assumptions"] = [item.model_dump(mode="python") for item in assumptions]
    if no_sources_or_overrides:
        tam_data["total_expansion"] = None
        tam_data["baseline_total"] = None
    payload = {
        "status": "partial" if partial else "complete", "partial": partial,
        "results": {"tam": tam_data}, "metrics": metrics, "regions": regions,
        "assumptions": assumptions, "sensitivity": sensitivity, "warnings": list(dict.fromkeys(warnings)),
        "provenance": _as_list(calculated.get("provenance")) + _as_list(locality_result.get("provenance")),
    }
    return contract.ReportResult.model_validate(payload)
