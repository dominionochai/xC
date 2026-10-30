"""Contrast-tag community construction using categories or co-weighting."""
from collections import OrderedDict
from collections.abc import Mapping


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _co_weight(a, b, co_occurrence_fn):
    if callable(co_occurrence_fn):
        try:
            return _number(co_occurrence_fn(a["tag"], b["tag"]))
        except Exception:
            return 0.0
    return max(0.0, a["weight"]) * max(0.0, b["weight"])


def _share(group, total):
    return sum(max(0.0, entry["weight"]) for entry in group) / total if total else 0.0


def _nearest(group, others, co_fn, total):
    def key(other):
        affinity = sum(_co_weight(a, b, co_fn) for a in group for b in other)
        return (affinity, _share(other, total))
    return max(others, key=key)


def _fold_small(groups, co_fn, total, min_share):
    groups = [list(group) for group in groups if group]
    while len(groups) > 1:
        small = [g for g in groups if _share(g, total) < min_share]
        if not small:
            break
        source = min(small, key=lambda g: (_share(g, total), -max(e["strength"] for e in g)))
        candidates = [g for g in groups if g is not source and _share(g, total) >= min_share]
        if not candidates:
            candidates = [g for g in groups if g is not source]
        if not candidates:
            break
        target = _nearest(source, candidates, co_fn, total)
        target.extend(source)
        groups.remove(source)
    return groups


def _community(group, total, label_fn):
    ordered = sorted(group, key=lambda e: (-e["strength"], e["tag"]))
    basis = [entry["tag"] for entry in ordered[:3]]
    labels = [entry["tag"] for entry in ordered]
    if callable(label_fn):
        label = label_fn(labels)
    else:
        label = " + ".join(basis[:2])
    return {
        "basis_tags": basis,
        "core_audience_share": _share(group, total),
        "anti_strength": sum(entry["strength"] for entry in group) / len(group),
        "evidence_refs": ["computed:communities:" + tag for tag in basis],
        "label": label,
    }


def build_communities(contrast_tags, tag_category_fn=None, max_communities=5,
                      min_community_share=0.05, co_occurrence_fn=None,
                      label_fn=None):
    """Build audience communities from ``{tag, strength, weight}`` entries.

    Category grouping is used only when it yields 2..max nonempty categories.
    Otherwise tags are greedily seeded by descending strength, then assigned
    to the strongest co-occurring community. Small shares are folded into the
    nearest larger community. Empty input never creates a synthetic group.
    """
    entries = []
    for raw in contrast_tags or ():
        if not isinstance(raw, Mapping) or raw.get("tag") is None:
            continue
        tag = str(raw["tag"])
        entries.append({"tag": tag, "strength": _number(raw.get("strength")),
                        "weight": _number(raw.get("weight"))})
    if not entries:
        return {"communities": [], "reason": "no_contrast_tags",
                "method": "co_weighting", "degraded": True}
    try:
        limit = max(1, int(max_communities))
    except (TypeError, ValueError, OverflowError):
        limit = 5
    total = sum(max(0.0, e["weight"]) for e in entries)
    if total <= 0:
        total = float(len(entries))
        for entry in entries:
            entry["weight"] = 1.0
    min_share = max(0.0, _number(min_community_share))

    categorized = OrderedDict()
    category_ok = callable(tag_category_fn)
    if category_ok:
        for entry in entries:
            try:
                category = tag_category_fn(entry["tag"])
            except Exception:
                category = None
            if category is None or category == "":
                category_ok = False
                break
            try:
                categorized.setdefault(category, []).append(entry)
            except TypeError:
                categorized.setdefault(str(category), []).append(entry)
    category_groups = list(categorized.values()) if category_ok else []
    if category_ok and 2 <= len(category_groups) <= limit:
        groups, method, degraded = category_groups, "category", False
    else:
        method, degraded = "co_weighting", True
        groups = []
        for entry in sorted(entries, key=lambda e: (-e["strength"], e["tag"])):
            if len(groups) < limit:
                groups.append([entry])
                continue
            target = max(groups, key=lambda g: (sum(_co_weight(entry, other, co_occurrence_fn) for other in g), _share(g, total)))
            target.append(entry)
    groups = _fold_small(groups, co_occurrence_fn, total, min_share)
    communities = [_community(group, total, label_fn) for group in groups]
    return {"communities": communities, "method": method, "degraded": degraded}
