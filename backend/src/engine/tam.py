"""Thin adapter from regional inputs and Qloo locality to the M8 method."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from backend.src import contract
from backend.methods.tam import tam_expansion
from backend.src.engine.locality import run as run_locality

_FACTORS = ("pop", "penetration", "spend", "affinity", "ip_loss_base", "ip_loss_low", "ip_loss_high")
_PROVENANCE = "backend.methods.tam.tam_expansion"

def _as_list(value: Any) -> list[Any]:
    if value is None: return []
    return list(value) if isinstance(value, (list, tuple)) else [value]

def _default_regions() -> Any:
    path = Path(__file__).resolve().parents[2] / "data" / "regions.json"
    with path.open("r", encoding="utf-8") as source: return json.load(source)

def run(qloo: Any, budget: Any, regions_data: Any = None) -> contract.ReportResult:
    """Load region inputs, enrich with locality results, invoke M8, type its report."""
    source = _default_regions() if regions_data is None else regions_data
    records = source.get("regions", []) if isinstance(source, dict) else source
    if not isinstance(records, list): records = []
    locality_result = run_locality(qloo, budget, records)
    locality_rows = locality_result.get("locality", []) if isinstance(locality_result, dict) else []
    locality_by_name = {str(row.get("region")): row for row in locality_rows if isinstance(row, dict)}
    inputs = []
    for record in records:
        if not isinstance(record, dict): continue
        item = dict(record)
        local = locality_by_name.get(str(item.get("region")))
        if local is not None:
            item["affinity"] = local.get("affinity")
        inputs.append(item)
    calculated = tam_expansion(inputs)
    calculated = calculated if isinstance(calculated, dict) else {}
    expansion_by_name = calculated.get("expansion", {})
    expansion_by_name = expansion_by_name if isinstance(expansion_by_name, dict) else {}
    metrics = [contract.Metric(name="tam_expansion", value=calculated.get("total_expansion"), unit="USD", provenance=_PROVENANCE)]
    if "baseline_total" in calculated:
        metrics.append(contract.Metric(name="baseline_total", value=calculated.get("baseline_total"), unit="USD", provenance=_PROVENANCE))
    regions = []
    assumptions = []
    for record in inputs:
        name = str(record.get("region", ""))
        result = expansion_by_name.get(name, {})
        result = result if isinstance(result, dict) else {}
        region_metrics = [
            contract.Metric(name="reach", value=result.get("reach"), unit="people", provenance=_PROVENANCE),
            contract.Metric(name="expansion", value=result.get("expansion"), unit="USD", provenance=_PROVENANCE),
        ]
        regions.append(contract.RegionResult(region=name, population=record.get("pop"), audience_size=result.get("reach"), metrics=region_metrics))
        sources = record.get("sources", {})
        sources = sources if isinstance(sources, dict) else {}
        for factor in _FACTORS:
            citation = sources.get(factor, {})
            citation = citation if isinstance(citation, dict) else {}
            assumptions.append(contract.Assumption(key=f"{name}:{factor}", value=record.get(factor), source=citation.get("url")))
    sensitivity = []
    tornado = calculated.get("tornado", {})
    tornado = tornado if isinstance(tornado, dict) else {}
    for name, bounds in tornado.items():
        if not isinstance(bounds, dict): continue
        sensitivity.append(contract.Sensitivity(name=str(name), parameter=str(name), metric="tam_expansion", low=bounds.get("low"), high=bounds.get("high")))
    warnings = [str(item) for item in _as_list(calculated.get("warnings")) + _as_list(locality_result.get("warnings") if isinstance(locality_result, dict) else None)]
    partial = bool(calculated.get("tam_partial", calculated.get("total_expansion") is None))
    if calculated.get("total_expansion") is None and not warnings:
        warnings.append("tam_partial:no sourced assumptions produced a TAM value")
    provenance = _as_list(calculated.get("provenance")) + _as_list(locality_result.get("provenance") if isinstance(locality_result, dict) else None)
    return contract.ReportResult.model_validate({
        "status": "partial" if partial else "complete", "partial": partial,
        "results": {"tam": calculated}, "metrics": metrics, "regions": regions,
        "assumptions": assumptions, "sensitivity": sensitivity, "warnings": warnings,
        "provenance": provenance,
    })
