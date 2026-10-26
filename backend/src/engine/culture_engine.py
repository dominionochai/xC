"""Deterministic, adapter-driven culture affinity comparison.

Consumes normalized signature IDs and scores; it does not parse Qloo payloads
or guess endpoint shapes. Qloo endpoint availability, response shape, batch cap,
and score semantics remain UNVERIFIED until P14. Select rank_n only when probe
evidence establishes per-call min-max scores; one normalization family is used
for an entire run.

Adapter contracts: affinity(source_id, item_id, domain) -> numeric score;
batch_affinity(source_id, item_ids, domain) -> {item_id: numeric score}.
"""
from collections.abc import Callable, Mapping, Sequence
from math import ceil, isfinite
from typing import Any

DOMAINS = ("brand", "artist", "movie", "tv_show", "podcast", "book", "place", "destination", "person")
SIGNATURE_ITEMS_PER_DOMAIN = 5
NORMALIZATION_RAW = "raw"
NORMALIZATION_RANK_N = "rank_n"
NORMALIZATION_FAMILIES = (NORMALIZATION_RAW, NORMALIZATION_RANK_N)
QLOO_VERIFICATION = (
    "UNVERIFIED until P14: Qloo affinity endpoint availability, response shape, "
    "batch cap, and score semantics. No Qloo response shape is assumed here."
)

AffinityCall = Callable[[str, str, str], int | float]
BatchAffinityCall = Callable[[str, Sequence[str], str], Mapping[str, int | float]]


def _signature_items(signatures: Mapping[str, Sequence[str]], domain: str) -> tuple[str, ...]:
    raw = signatures.get(domain, ())
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError(f"signature items for {domain!r} must be a sequence of IDs")
    items = tuple(raw[:SIGNATURE_ITEMS_PER_DOMAIN])
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise TypeError(f"signature item IDs for {domain!r} must be non-empty strings")
        if item in seen:
            raise ValueError(f"duplicate signature item ID {item!r} in domain {domain!r}")
        seen.add(item)
    return items


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("affinity callback must return a numeric score")
    score = float(value)
    if not isfinite(score):
        raise ValueError("affinity scores must be finite")
    return score


def _rank_n(values: Sequence[float]) -> list[float]:
    """Map scores to average ascending rank / N, preserving ties."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranked = [0.0] * len(values)
    cursor, count = 0, len(values)
    while cursor < count:
        end = cursor + 1
        while end < count and values[order[end]] == values[order[cursor]]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2.0
        for position in range(cursor, end):
            ranked[order[position]] = average_rank / count
        cursor = end
    return ranked


def _lower_tercile(values: Sequence[float]) -> tuple[float | None, bool]:
    if not values:
        return None, True
    ordered = sorted(values)
    if len(ordered) < 3:
        return ordered[0], True
    return ordered[ceil(len(ordered) / 3) - 1], False


def compare_cultures(
    entity_a_id: str,
    entity_t_id: str,
    signatures_a: Mapping[str, Sequence[str]],
    signatures_t: Mapping[str, Sequence[str]],
    *,
    affinity: AffinityCall | None = None,
    batch_affinity: BatchAffinityCall | None = None,
    batch_cap: int = SIGNATURE_ITEMS_PER_DOMAIN,
    normalization_family: str = NORMALIZATION_RAW,
) -> dict[str, Any]:
    """Compute F_k, C_k, and Anti_k with injected single/batch adapters.

    T items are measured against A (F_k), and A items against T (C_k). Anti_k
    is the share of T-item scores below the lower tercile of every scored item
    this run. Rank/N is performed separately inside each batch call. With
    single-call fallback each call has N=1, so rank/N is 1.0 (a flagged
    limitation, not inferred Qloo behavior).
    """
    if not isinstance(entity_a_id, str) or not entity_a_id.strip():
        raise ValueError("entity_a_id must be a non-empty string")
    if not isinstance(entity_t_id, str) or not entity_t_id.strip():
        raise ValueError("entity_t_id must be a non-empty string")
    if normalization_family not in NORMALIZATION_FAMILIES:
        raise ValueError(f"normalization_family must be one of {NORMALIZATION_FAMILIES!r}")
    if isinstance(batch_cap, bool) or not isinstance(batch_cap, int) or batch_cap <= 0:
        raise ValueError("batch_cap must be a positive integer")
    if not isinstance(signatures_a, Mapping) or not isinstance(signatures_t, Mapping):
        raise TypeError("signatures_a and signatures_t must be mappings by domain")

    a_items = {d: _signature_items(signatures_a, d) for d in DOMAINS}
    t_items = {d: _signature_items(signatures_t, d) for d in DOMAINS}
    item_count = sum(len(a_items[d]) + len(t_items[d]) for d in DOMAINS)
    if batch_affinity is None and item_count and affinity is None:
        raise ValueError("provide affinity for sequential fallback or batch_affinity")

    all_scores: list[float] = []
    calls_used = 0
    measured = {d: {"T_items": [], "A_items": []} for d in DOMAINS}

    def measure(source: str, ids: Sequence[str], domain: str, output: str) -> None:
        nonlocal calls_used
        if not ids:
            return
        chunks = (tuple(ids[i:i + batch_cap]) for i in range(0, len(ids), batch_cap))
        if batch_affinity is not None:
            for chunk in chunks:
                calls_used += 1
                response = batch_affinity(source, chunk, domain)
                if not isinstance(response, Mapping):
                    raise TypeError("batch_affinity must return a mapping of item IDs to scores")
                raw = []
                for item in chunk:
                    if item not in response:
                        raise ValueError(f"batch affinity omitted requested item {item!r}")
                    raw.append(_score(response[item]))
                used = _rank_n(raw) if normalization_family == NORMALIZATION_RANK_N else raw
                for item, value, normalized in zip(chunk, raw, used):
                    measured[domain][output].append({
                        "item_id": item, "affinity": value,
                        "normalized_affinity": normalized,
                    })
                    all_scores.append(normalized)
        else:
            assert affinity is not None
            for item in ids:
                calls_used += 1
                value = _score(affinity(source, item, domain))
                normalized = _rank_n([value])[0] if normalization_family == NORMALIZATION_RANK_N else value
                measured[domain][output].append({
                    "item_id": item, "affinity": value,
                    "normalized_affinity": normalized,
                })
                all_scores.append(normalized)

    for domain in DOMAINS:
        measure(entity_a_id, t_items[domain], domain, "T_items")
        measure(entity_t_id, a_items[domain], domain, "A_items")

    cutoff, anti_flagged = _lower_tercile(all_scores)
    domains: dict[str, dict[str, Any]] = {}
    for domain in DOMAINS:
        ts, ass = measured[domain]["T_items"], measured[domain]["A_items"]
        t_scores = [row["normalized_affinity"] for row in ts]
        a_scores = [row["normalized_affinity"] for row in ass]
        domains[domain] = {
            "F_k": sum(t_scores) / len(t_scores) if t_scores else None,
            "C_k": sum(a_scores) / len(a_scores) if a_scores else None,
            "Anti_k": (sum(value < cutoff for value in t_scores) / len(t_scores)
                       if t_scores and cutoff is not None else None),
            "anti_cutoff": cutoff,
            "anti_axis_flagged": anti_flagged,
            "T_items": ts,
            "A_items": ass,
        }

    batch_calls = sum(ceil(len(a_items[d]) / batch_cap) + ceil(len(t_items[d]) / batch_cap) for d in DOMAINS)
    if batch_affinity is None:
        mode = "sequential_single_call_fallback"
        note = (f"No batch callback supplied: one single-affinity call per signature item; {calls_used} call(s) "
                f"for these inputs (up to {len(DOMAINS) * 2 * SIGNATURE_ITEMS_PER_DOMAIN} calls when all 9 "
                "domains have 5 items on both sides).")
    else:
        mode = "batch"
        note = (f"Batch callback used with cap {batch_cap}; {calls_used} call(s) for these inputs. "
                f"Sequential fallback for these inputs would require {item_count} call(s).")

    return {
        "domains": domains,
        "fixed_domains": list(DOMAINS),
        "signature_items_per_domain": SIGNATURE_ITEMS_PER_DOMAIN,
        "normalization_family": normalization_family,
        "anti_cutoff": cutoff,
        "anti_axis_flagged": anti_flagged,
        "affinity_item_count": len(all_scores),
        "call_budget": {
            "mode": mode,
            "calls_used": calls_used,
            "calls_if_single_fallback": item_count,
            "batch_calls_at_configured_cap": batch_calls,
            "configured_batch_cap": batch_cap,
            "full_signature_single_fallback_calls": len(DOMAINS) * 2 * SIGNATURE_ITEMS_PER_DOMAIN,
            "call_budget_implication": note,
        },
        "qloo_verification": QLOO_VERIFICATION,
    }
