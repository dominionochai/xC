"""Construct a category-diverse cultural bridge from injected affinity scores."""


def _number(value):
    """Return a finite-looking float, or None for an unusable score."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _category(item_id, pool_by_id, category_fn, endpoint=None):
    """Resolve a category while keeping endpoint labels explicit if not injected."""
    if category_fn is not None:
        try:
            return category_fn(item_id)
        except Exception:
            pass
    if endpoint is not None:
        return "__endpoint_%s__" % endpoint
    item = pool_by_id.get(item_id, {})
    return item.get("category")


def _category_ok(cats, stage):
    """Apply the cumulative category-collision allowances for a widening stage."""
    a_cat, first_cat, second_cat, t_cat = cats
    pairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    allowed = set()
    if stage >= 1:
        allowed.add((1, 2))  # allow m1 == m2 category
    if stage >= 2:
        allowed.add((0, 1))  # then allow A == m1
    if stage >= 3:
        allowed.add((2, 3))  # then allow T == m2
    for left, right in pairs:
        if (left, right) not in allowed and cats[left] == cats[right]:
            return False
    return True


def _batch_scores(affinity_fn, pairs, max_calls):
    """Score middle edges using a batch call when supported, else bounded scalar calls."""
    if not pairs or max_calls <= 0:
        return {}
    try:
        batch_result = affinity_fn(pairs)
        if isinstance(batch_result, dict):
            scores = {}
            for pair in pairs:
                raw = batch_result.get(pair)
                if raw is None:
                    raw = batch_result.get("%s->%s" % pair)
                score = _number(raw)
                if score is not None:
                    scores[pair] = score
            if scores:
                return scores
        elif isinstance(batch_result, (list, tuple)) and len(batch_result) == len(pairs):
            scores = {}
            for pair, raw in zip(pairs, batch_result):
                score = _number(raw)
                if score is not None:
                    scores[pair] = score
            return scores
        elif len(pairs) == 1:
            score = _number(batch_result)
            if score is not None:
                return {pairs[0]: score}
    except TypeError:
        # A conventional two-argument callable rejects the one-argument batch form.
        pass
    except Exception:
        return {}

    scores = {}
    for first, second in pairs[:max_calls]:
        try:
            score = _number(affinity_fn(first, second))
        except Exception:
            continue
        if score is not None:
            scores[(first, second)] = score
    return scores


def build_bridge(
    fit_affinity,
    pool,
    affinity_fn,
    category_fn=None,
    tau=60,
    top_n=5,
    max_triple_calls=5,
    budget_note="~12 calls",
):
    """Build and score A -> m1 -> m2 -> T, using only injected data/functions."""
    if fit_affinity >= tau:
        return {"status": "not_needed"}

    pool = list(pool or [])
    pool_by_id = {item.get("id"): item for item in pool}
    first_candidates = sorted(
        pool,
        key=lambda item: _number(item.get("with_a")) if _number(item.get("with_a")) is not None else float("-inf"),
        reverse=True,
    )[:max(0, top_n)]
    second_candidates = sorted(
        pool,
        key=lambda item: _number(item.get("with_t")) if _number(item.get("with_t")) is not None else float("-inf"),
        reverse=True,
    )[:max(0, top_n)]
    pairs = [(left.get("id"), right.get("id")) for left in first_candidates for right in second_candidates]
    scored = _batch_scores(affinity_fn, pairs, max_triple_calls)

    endpoint_a = _category("A", pool_by_id, category_fn, endpoint="A")
    endpoint_t = _category("T", pool_by_id, category_fn, endpoint="T")
    candidates = []
    for left in first_candidates:
        for right in second_candidates:
            pair = (left.get("id"), right.get("id"))
            middle = scored.get(pair)
            left_score = _number(left.get("with_a"))
            right_score = _number(right.get("with_t"))
            if middle is None or left_score is None or right_score is None:
                continue
            weakest = min(left_score, middle, right_score)
            cats = (
                endpoint_a,
                _category(left.get("id"), pool_by_id, category_fn),
                _category(right.get("id"), pool_by_id, category_fn),
                endpoint_t,
            )
            candidates.append((weakest, left, right, middle, cats, pair))
    candidates.sort(key=lambda item: item[0], reverse=True)

    widening_log = []
    chosen = None
    labels = [
        "allow m1==m2 category",
        "allow A==m1",
        "allow T==m2",
    ]
    for stage in range(4):
        chosen = next((item for item in candidates if _category_ok(item[4], stage)), None)
        if chosen is not None:
            break
        if stage < 3:
            widening_log.append(labels[stage])

    scored_evidence = [
        {"from": first, "to": second, "affinity": score}
        for (first, second), score in scored.items()
    ]
    direct = float(fit_affinity) / 100.0
    if chosen is None or chosen[0] <= direct:
        weakest = chosen[0] if chosen is not None else None
        friction_before = 100.0 - float(fit_affinity)
        friction_after = 100.0 - 100.0 * weakest if weakest is not None else None
        reduction = (
            max(0.0, 100.0 * (friction_before - friction_after) / friction_before)
            if weakest is not None and friction_before > 0
            else 0.0
        )
        return {
            "status": "not_found",
            "triple": None,
            "edges": None,
            "weakest_edge": weakest,
            "friction_before": friction_before,
            "friction_after": friction_after,
            "friction_reduction_pct": reduction,
            "evidence": scored_evidence,
            "widening_log": widening_log,
            "budget_note": budget_note,
        }

    weakest, first, second, middle, _, _ = chosen
    edge_a = _number(first.get("with_a"))
    edge_t = _number(second.get("with_t"))
    friction_before = 100.0 - float(fit_affinity)
    friction_after = 100.0 - 100.0 * weakest
    reduction = (
        max(0.0, 100.0 * (friction_before - friction_after) / friction_before)
        if friction_before > 0
        else 0.0
    )
    return {
        "status": "found",
        "triple": {"m1": first.get("id"), "m2": second.get("id")},
        "edges": {"a_m1": edge_a, "m1_m2": middle, "m2_t": edge_t},
        "weakest_edge": weakest,
        "friction_before": friction_before,
        "friction_after": friction_after,
        "friction_reduction_pct": reduction,
        "evidence": [
            {"from": "A", "to": first.get("id"), "affinity": edge_a},
            {"from": first.get("id"), "to": second.get("id"), "affinity": middle},
            {"from": second.get("id"), "to": "T", "affinity": edge_t},
        ],
        "scored_edges": scored_evidence,
        "widening_log": widening_log,
        "budget_note": budget_note,
    }
