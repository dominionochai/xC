"""Bridge discovery and weakest-edge affinity scoring."""


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _id(item):
    return _get(item, "entity_id", _get(item, "id", _get(item, "entityId")))


def _items(value):
    if isinstance(value, dict):
        for key in ("results", "entities", "items", "data"):
            if isinstance(value.get(key), (list, tuple)): return list(value[key])
        return [value]
    return list(value) if isinstance(value, (list, tuple)) else []


def _score(value):
    if isinstance(value, dict):
        value = value.get("affinity", value.get("score", value.get("weight")))
    try:
        value = float(value)
        return value / 100.0 if value > 1 else value
    except (TypeError, ValueError):
        return None


def run(qloo, budget, fit_affinity, target_id, acquirer_id, pool=None):
    warnings, evidence, provenance, widening_log = [], [], [], []
    exhausted = False
    def call(method, *args):
        nonlocal exhausted
        if getattr(qloo, "call_count", 0) >= getattr(budget, "max_calls", 0):
            exhausted = True
            return None
        try:
            value = getattr(qloo, method)(*args)
            evidence.append({"source": "qloo", "method": method, "arguments": list(args), "result": value})
            provenance.append({"source": "qloo", "method": method})
            return value
        except Exception as exc:
            warnings.append("qloo_" + method + "_failed:" + type(exc).__name__)
            return None
    try: fit = float(fit_affinity)
    except (TypeError, ValueError): fit = 0.0
    result_base = {"fit_affinity": fit, "friction_before": 100 - fit, "evidence": evidence, "provenance": provenance, "warnings": warnings, "widening_log": widening_log}
    if fit >= 60:
        return dict(result_base, status="not_needed", triple=None, edges=None, weakest_edge=None, friction_after=100-fit, friction_reduction_pct=0.0)
    candidates = []
    if pool is None:
        for entity_id in (acquirer_id, target_id):
            hits = _items(call("search", str(entity_id)))
            if exhausted: break
            candidates.extend(hits)
    else:
        candidates = _items(pool)
    unique = {}
    for item in candidates:
        entity_id = _id(item)
        if entity_id is not None and str(entity_id) not in (str(target_id), str(acquirer_id)):
            unique[str(entity_id)] = item
    entities = []
    for entity_id, item in unique.items():
        prof = call("profile", entity_id)
        if exhausted: break
        merged = dict(item) if isinstance(item, dict) else {"entity_id": entity_id}
        if isinstance(prof, dict): merged.update(prof)
        merged.setdefault("entity_id", entity_id)
        category = _get(merged, "category", _get(merged, "category_name"))
        if not category:
            tags_value = call("tags_for", entity_id)
            if exhausted: break
            tags = _items(tags_value)
            for tag in tags:
                tagname = _get(tag, "tag", _get(tag, "name", tag))
                category_value = call("category", tagname)
                if exhausted: break
                if category_value:
                    category = category_value
                    break
        merged["_category"] = str(category) if category else None
        entities.append(merged)
    widening_log.append({"stage": "initial_pool", "candidate_count": len(entities), "distinct_categories": len({e.get("_category") for e in entities if e.get("_category")})})
    best = None
    pairs = []
    for left in entities:
        for right in entities:
            if _id(left) == _id(right): continue
            lc, rc = left.get("_category"), right.get("_category")
            if lc and rc and lc == rc: continue
            pairs.append((left, right))
    for left, right in pairs:
        a_id, b_id = _id(left), _id(right)
        with_a = _score(call("affinity", acquirer_id, a_id))
        if exhausted: break
        between = _score(call("affinity", a_id, b_id))
        if exhausted: break
        with_t = _score(call("affinity", b_id, target_id))
        if exhausted: break
        if None in (with_a, between, with_t): continue
        weakest = min(with_a, between, with_t)
        candidate = {"m1": a_id, "m2": b_id, "m1_category": left.get("_category"), "m2_category": right.get("_category")}
        if best is None or weakest > best["weakest"]:
            best = {"triple": candidate, "edges": {"with_acquirer": with_a, "between": between, "with_target": with_t}, "weakest": weakest}
    widening_log.append({"stage": "distinct_category_pairs", "pair_count": len(pairs), "evaluated": bool(best)})
    if exhausted: warnings.append("budget_exhausted:bridge")
    if best is None or best["weakest"] <= fit / 100.0:
        return dict(result_base, status="not_found", triple=best["triple"] if best else None, edges=best["edges"] if best else None, weakest_edge=best["weakest"] if best else None, friction_after=100-fit, friction_reduction_pct=0.0)
    before = 100 - fit
    after = 100 - 100 * best["weakest"]
    reduction = max(0.0, 100 * (before - after) / before) if before else 0.0
    return dict(result_base, status="found", triple=best["triple"], edges=best["edges"], weakest_edge=best["weakest"], friction_after=after, friction_reduction_pct=reduction)
