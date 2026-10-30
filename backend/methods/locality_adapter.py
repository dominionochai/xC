"""P6 locality adapter: contract mapping over the documented fallback ladder."""
from __future__ import annotations
from backend.methods.locality import _NEIGHBORHOOD_CAVEAT, locality_analysis
from backend.src.contract_locality import LocalityResult, RegionLocality
DEFAULT_REGIONS = ("soho_nyc", "shibuya_tokyo", "mayfair_london")
_IDENTICAL_CAVEAT = "identical affinity across all regions: location filter may be ignored for this entity type"
def run_locality_adapter(region_query_fn, heatmap_fn, city_fallback_fn, regions=DEFAULT_REGIONS, global_affinity=None) -> LocalityResult:
    raw = locality_analysis(region_query_fn=region_query_fn, heatmap_fn=heatmap_fn, city_fallback_fn=city_fallback_fn, regions=list(regions), global_affinity=global_affinity)
    warnings: list[str] = []
    rows: list[RegionLocality] = []
    evidence_refs: list[str] = []
    for name in raw:
        row = raw[name]
        if row.get("affinity") is None:
            warnings.append(name + ":all_levels_failed")
            rows.append(RegionLocality(region=name, affinity=None, ladder_level=None, friction=None, delta_vs_global=None, reason=row.get("reason"), provenance=[]))
            continue
        ladder = row.get("ladder_level")
        prov = [{"source": "methods.locality.locality_analysis", "method": {1: "region_query", 2: "heatmap_cosine", 3: "city_fallback"}[ladder]}]
        caveat = row.get("caveat")
        sample_note = caveat if ladder == 3 else None
        if ladder == 3:
            warnings.append(name + ":city_fallback:" + _NEIGHBORHOOD_CAVEAT)
        evidence_refs.append(name)
        rows.append(RegionLocality(region=name, affinity=row.get("affinity"), ladder_level=ladder, friction=row.get("friction"), delta_vs_global=row.get("delta_vs_global"), caveat=caveat, sample_note=sample_note, provenance=prov))
    resolved = [r for r in rows if r.affinity is not None]
    resolved_affinities = {r.affinity for r in resolved}
    suspect_empty = len(resolved) == len(rows) and len(resolved) > 1 and len(resolved_affinities) == 1
    if suspect_empty:
        warnings.append(_IDENTICAL_CAVEAT)
        for r in rows:
            r.caveat = _IDENTICAL_CAVEAT
            r.sample_note = _IDENTICAL_CAVEAT
    status = "resolved" if (len(resolved) == len(rows) and rows) else ("failed" if not resolved else "partial")
    assumptions = {"regions": list(regions), "ladder": ["region_query", "heatmap_cosine", "city_fallback"], "global_affinity": global_affinity, "suspect_empty_detection": "identical-region-values", "labels": {"affinity": "measured-or-modeled", "friction": "modeled-derived", "delta_vs_global": "modeled-derived"}}
    provenance = [{"source": "methods.locality.locality_analysis", "inputs": {"regions": list(regions), "global_affinity": global_affinity}}, {"source": "contract_locality.map"}, {"source": "locality_adapter.suspect_empty", "triggered": suspect_empty}]
    return LocalityResult(status=status, regions=rows, global_affinity=global_affinity, warnings=warnings, evidence_refs=evidence_refs, provenance=provenance, assumptions=assumptions)
async def make_qloo_locality_fns(client):
    """Wrap client region/heatmap/city methods as 0-100 callables. UNVERIFIED until P7: route selection must use the P14 probe result."""
    async def region_query_fn(region_name):
        try:
            value = await client.region_affinity(region_name)
            return _to_100(value)
        except Exception:
            return None
    async def heatmap_fn(region_name):
        try:
            return await client.region_heatmap(region_name)
        except Exception:
            return None
    async def city_fallback_fn(region_name):
        try:
            value = await client.city_affinity(region_name)
            return _to_100(value)
        except Exception:
            return None
    return region_query_fn, heatmap_fn, city_fallback_fn
def _to_100(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value * 100.0 if value <= 1.0 else value
