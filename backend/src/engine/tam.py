"""Total-addressable-market estimates with explicit assumption provenance."""
import json
import os

FACTORS = ("pop", "penetration", "spend", "affinity", "ip_loss_base")


def _source_ok(region, key):
    sources = region.get("sources") or {}
    source = sources.get(key) if isinstance(sources, dict) else None
    return isinstance(source, dict) and "year" in source and "note" in source and ("url" in source)


def _load_default():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "regions.json"))
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _value(region, key):
    value = region.get(key)
    try: return float(value) if value is not None else None
    except (TypeError, ValueError): return None


def _calc(region, overrides=None):
    overrides = overrides or {}
    vals = {}
    for key in FACTORS:
        value = overrides.get(key, _value(region, key))
        if value is not None: vals[key] = float(value)
    if any(key not in vals for key in FACTORS): return None
    pop, penetration, spend, affinity, loss = (vals[k] for k in FACTORS)
    reach = pop * penetration
    expansion = reach * spend * (affinity / 100.0) * (1.0 - loss / 100.0)
    return {"reach": reach, "expansion": expansion}


def run(qloo, budget, regions_data=None):
    warnings, evidence, provenance = [], [], []
    if regions_data is None:
        try: regions_data = _load_default()
        except Exception as exc:
            return {"tam": None, "reason": "all_assumptions_null", "warnings": ["regions_data_unavailable:" + type(exc).__name__, "tam_partial"], "evidence": [], "provenance": []}
    if isinstance(regions_data, dict): regions = regions_data.get("regions", [])
    elif isinstance(regions_data, list): regions = regions_data
    else: regions = []
    region_results = []
    tornado = {}
    partial = False
    total = 0.0; any_total = False
    for region in regions:
        if not isinstance(region, dict):
            partial = True; warnings.append("invalid_region_record"); continue
        name = region.get("region")
        missing = []
        for key in FACTORS:
            if _value(region, key) is None:
                missing.append(key)
            elif not _source_ok(region, key):
                missing.append(key + "_source")
        if missing:
            partial = True
            warnings.extend(["missing_assumption:%s:%s" % (name, key) for key in missing])
            region_results.append({"region": name, "reach": None, "expansion": None, "missing": missing, "sources": region.get("sources", {})})
            continue
        calc = _calc(region)
        if calc is None:
            partial = True; continue
        any_total = True; total += calc["expansion"]
        item = {"region": name, "reach": calc["reach"], "expansion": calc["expansion"], "assumptions": {key: _value(region, key) for key in FACTORS}, "sources": region.get("sources", {})}
        region_results.append(item)
        for factor in FACTORS:
            base = _value(region, factor)
            low_value = max(0.0, base * .70)
            high_value = base * 1.30
            low_calc = _calc(region, {factor: low_value})
            high_calc = _calc(region, {factor: high_value})
            key = str(name) + ":" + factor
            tornado[key] = {"base": calc["expansion"], "minus_30_pct": low_calc["expansion"] if low_calc else None, "plus_30_pct": high_calc["expansion"] if high_calc else None}
            source = region["sources"][factor]
            evidence.append({"source": source, "assumption": factor, "region": name, "value": base})
            provenance.append({"region": name, "assumption": factor, "source": source})
    if not any_total:
        return {"tam": None, "reason": "all_assumptions_null", "regions": region_results, "tornado": tornado, "warnings": warnings + (["tam_partial"] if partial else []), "evidence": evidence, "provenance": provenance}
    if partial: warnings.append("tam_partial")
    return {"tam": total, "regions": region_results, "tornado": tornado, "warnings": warnings, "evidence": evidence, "provenance": provenance}
