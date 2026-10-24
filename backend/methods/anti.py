"""Offline anti-co-occurrence scoring for target/acquirer signatures."""
from collections.abc import Mapping
import math


def _pick(record, names, default=None):
    for name in names:
        if record.get(name) is not None:
            return record[name]
    return default


def _entity(record, side):
    nested = record.get(side)
    if isinstance(nested, Mapping):
        nested = _pick(nested, ("entity_id", "id", "source_entity_id"))
    return _pick(record, (side + "_entity_id", side + "_source_entity_id", side + "_id"), nested)


def _items(record, side, cap):
    value = record.get(side + "_items") or ()
    if isinstance(value, (str, bytes)):
        value = [value]
    try:
        return list(value)[:cap]
    except TypeError:
        return []


def _score(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _lower_tercile(values):
    """Empirical lower-tercile boundary (mean after trimming lowest third)."""
    values = sorted(values)
    kept = values[max(1, len(values) // 3):]
    return sum(kept) / len(kept)


def anti_cooccurrence(items_by_domain, scorer, signature_items_per_domain=5):
    """Compute F/C directional means and target-item anti-affinity share.

    Each domain record has target_items/acquirer_items and source IDs such as
    target_entity_id/acquirer_entity_id (target_id/acquirer_id aliases work).
    The scorer is called as scorer(source_entity_id, item_id). Item order is
    preserved and capped on each side. Cutoff is derived from all finite
    scores collected in this run; fewer than three use the observed minimum.
    """
    if not isinstance(items_by_domain, Mapping) or not items_by_domain:
        return {"domains": {}, "cutoff": None, "normalization": "raw",
                "cutoff_fallback": False, "axis_uses_min_observed_fallback": False,
                "cutoff_note": None}
    try:
        cap = max(0, int(signature_items_per_domain))
    except (TypeError, ValueError, OverflowError):
        cap = 5
    all_scores, rows = [], {}
    for domain, raw in items_by_domain.items():
        rec = raw if isinstance(raw, Mapping) else {}
        targets, acquirers = _items(rec, "target", cap), _items(rec, "acquirer", cap)
        target_id, acquirer_id = _entity(rec, "target"), _entity(rec, "acquirer")
        target_scores, acquirer_scores = [], []
        if callable(scorer):
            if acquirer_id is not None:
                for item in targets:
                    try:
                        value = _score(scorer(acquirer_id, item))
                    except Exception:
                        value = None
                    if value is not None:
                        target_scores.append(value)
                        all_scores.append(value)
            if target_id is not None:
                for item in acquirers:
                    try:
                        value = _score(scorer(target_id, item))
                    except Exception:
                        value = None
                    if value is not None:
                        acquirer_scores.append(value)
                        all_scores.append(value)
        rows[domain] = (len(targets), target_scores, acquirer_scores)
    fallback = 0 < len(all_scores) < 3
    cutoff = min(all_scores) if fallback else (_lower_tercile(all_scores) if all_scores else None)
    minmax = bool(all_scores) and min(all_scores) >= 0 and max(all_scores) <= 1.01
    result = {}
    for domain, (target_count, target_scores, acquirer_scores) in rows.items():
        dropped = target_count < 3
        if dropped:
            anti, reason = None, "warning: fewer than 3 target items; anti axis dropped"
        elif not target_scores or cutoff is None:
            dropped = True
            anti, reason = None, "warning: no usable target-item affinities; anti axis dropped"
        else:
            anti = sum(value < cutoff for value in target_scores) / len(target_scores)
            reason = None
        result[domain] = {
            "F": sum(target_scores) / len(target_scores) if target_scores else None,
            "C": sum(acquirer_scores) / len(acquirer_scores) if acquirer_scores else None,
            "Anti": anti, "dropped": dropped, "reason": reason,
        }
    output = {
        "domains": result, "cutoff": cutoff,
        "normalization": "minmax" if minmax else "raw",
        "cutoff_fallback": fallback,
        "axis_uses_min_observed_fallback": fallback,
        "cutoff_note": ("minimum observed affinity used because fewer than three values were scored" if fallback else None),
    }
    if minmax:
        output["recommendation"] = "rank"
    return output
