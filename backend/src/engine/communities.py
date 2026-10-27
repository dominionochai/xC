"""Contrast-tag community construction with bounded Qloo access."""
from collections import defaultdict


def _get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _tags(value):
    found = []
    if isinstance(value, dict):
        for key in ("tags", "contrast_tags", "items", "axes"):
            if key in value:
                found.extend(_tags(value[key]))
        if not found and value.get("tag") is not None:
            found.append(value["tag"])
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            found.extend(_tags(item))
    elif value is not None:
        found.append(value)
    out = []
    seen = set()
    for item in found:
        if isinstance(item, dict):
            item = item.get("tag") or item.get("name") or item.get("id")
        if item is not None and str(item) not in seen:
            seen.add(str(item)); out.append(str(item))
    return out


def run(qloo, budget, contrast_axes, max_communities=5, min_community_share=.05):
    warnings, evidence, provenance = [], [], []
    exhausted = False
    def call(method, *args):
        nonlocal exhausted
        if _get(budget, "max_calls", 0) <= getattr(qloo, "call_count", 0):
            exhausted = True
            return None
        try:
            result = getattr(qloo, method)(*args)
            evidence.append({"source": "qloo", "method": method, "arguments": list(args), "result": result})
            provenance.append({"source": "qloo", "method": method})
            return result
        except Exception as exc:
            warnings.append("qloo_" + method + "_failed:" + type(exc).__name__)
            return None
    tags = _tags(contrast_axes)
    if not tags:
        return {"communities": [], "reason": "no_contrast_tags", "warnings": warnings, "evidence": evidence, "provenance": provenance}
    categories = defaultdict(list)
    for tag in tags:
        category = call("category", tag)
        if exhausted: break
        if category is not None and str(category).strip():
            categories[str(category)].append(tag)
    groups = [list(v) for _, v in sorted(categories.items()) if v]
    groups = [g for g in groups if len(g) < len(tags)]
    if not (2 <= len(groups) <= max_communities):
        groups = [[tag] for tag in tags]
        weights = {}
        for i, a in enumerate(tags):
            for b in tags[i + 1:]:
                value = call("co_weight", a, b)
                if exhausted: break
                try:
                    if isinstance(value, dict): value = value.get("weight", value.get("score"))
                    weights[(a, b)] = float(value) if value is not None else 0.0
                except (TypeError, ValueError): weights[(a, b)] = 0.0
            if exhausted: break
        # Greedily merge the strongest connected pair until the requested cap.
        while len(groups) > max(1, max_communities):
            candidates = []
            for i, left in enumerate(groups):
                for j in range(i + 1, len(groups)):
                    right = groups[j]
                    vals = [weights.get((a, b), weights.get((b, a), 0.0)) for a in left for b in right]
                    candidates.append((max(vals) if vals else 0.0, i, j))
            if not candidates: break
            strength, i, j = max(candidates, key=lambda x: (x[0], -x[1], -x[2]))
            if strength <= 0: break
            groups[i] = groups[i] + groups[j]
            del groups[j]
        if len(groups) > max_communities:
            groups = groups[:max_communities]
            for tag in tags:
                if not any(tag in g for g in groups):
                    groups[-1].append(tag)
    # Fold any leftover tags into their strongest available group.
    present = {t for group in groups for t in group}
    for tag in tags:
        if tag in present: continue
        if not groups: groups = [[tag]]; continue
        choices = []
        for i, group in enumerate(groups):
            vals = [weights.get((tag, t), weights.get((t, tag), 0.0)) for t in group] if 'weights' in locals() else []
            choices.append((max(vals) if vals else 0.0, i))
        groups[max(choices)[1]].append(tag)
    # Shares are tag-count shares; small groups fold to the nearest larger group.
    total = max(1, len(tags))
    shares = [len(g) / total for g in groups]
    for i in sorted(range(len(groups)), key=lambda x: shares[x]):
        if i >= len(groups) or shares[i] >= min_community_share or len(groups) <= 1: continue
        choices = []
        for j, group in enumerate(groups):
            if i == j or shares[j] < shares[i]: continue
            vals = [weights.get((a, b), weights.get((b, a), 0.0)) for a in groups[i] for b in group] if 'weights' in locals() else []
            choices.append((max(vals) if vals else 0.0, shares[j], j))
        j = max(choices)[2] if choices else max((j for j in range(len(groups)) if j != i), key=lambda j: shares[j], default=None)
        if j is not None:
            groups[j].extend(groups[i]); groups[i] = []; shares[j] += shares[i]; shares[i] = 0
    result = [{"id": "community_%d" % (i + 1), "tags": group, "share": len(group) / total} for i, group in enumerate(groups) if group]
    if exhausted: warnings.append("budget_exhausted:communities")
    if not result: return {"communities": [], "reason": "no_contrast_tags", "warnings": warnings, "evidence": evidence, "provenance": provenance}
    return {"communities": result, "warnings": warnings, "evidence": evidence, "provenance": provenance}
