"""Pure, deterministic helpers for affinity and market sizing."""

from __future__ import annotations

from collections import deque
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence


def affinity_clash(left: Sequence[str], right: Sequence[str]) -> dict[str, object]:
    """Compute Jaccard overlap and a transparent clash/risk band for two sets."""
    left_set = {v.strip() for v in left if isinstance(v, str) and v.strip()}
    right_set = {v.strip() for v in right if isinstance(v, str) and v.strip()}
    union = left_set | right_set
    shared = sorted(left_set & right_set)
    similarity = len(shared) / len(union) if union else 0.0
    clash = 1.0 - similarity
    if not left_set or not right_set:
        risk = "unknown"
    elif clash < 0.25:
        risk = "low"
    elif clash < 0.60:
        risk = "medium"
    else:
        risk = "high"
    return {"shared_entities": shared, "jaccard_similarity": round(similarity, 4),
            "clash_score": round(clash, 4), "risk": risk}


def find_transition_bridge(source: str, target: str, graph: Mapping[str, Iterable[str]],
                           *, max_hops: int = 3) -> list[str] | None:
    """Return the lexicographically first shortest path of at most three hops."""
    if not 1 <= max_hops <= 3:
        raise ValueError("max_hops must be between 1 and 3")
    if source == target:
        return [source]
    queue: deque[tuple[str, list[str]]] = deque([(source, [source])])
    while queue:
        current, path = queue.popleft()
        if len(path) - 1 >= max_hops:
            continue
        for neighbor in sorted(set(graph.get(current, ()))):
            if neighbor in path:
                continue
            next_path = [*path, neighbor]
            if neighbor == target:
                return next_path
            queue.append((neighbor, next_path))
    return None


def affinity_graph(source: str, target: str, source_affinities: Sequence[str],
                   target_affinities: Sequence[str]) -> dict[str, set[str]]:
    """Build an undirected graph from two Qloo affinity result sets."""
    graph: dict[str, set[str]] = {}
    for seed, affinities in ((source, source_affinities), (target, target_affinities)):
        graph.setdefault(seed, set())
        for entity in affinities:
            if not isinstance(entity, str) or not entity.strip():
                continue
            entity = entity.strip()
            graph.setdefault(seed, set()).add(entity)
            graph.setdefault(entity, set()).add(seed)
    return graph


def geographic_market_split(population_by_region: Mapping[str, int]) -> list[dict[str, object]]:
    """Return populations and fractional shares, sorted by region name."""
    if not population_by_region:
        raise ValueError("at least one region is required")
    for region, population in population_by_region.items():
        if not isinstance(region, str) or not region.strip():
            raise ValueError("region names must be non-empty strings")
        if type(population) is not int or population < 0:
            raise ValueError("regional populations must be non-negative integers")
    total = sum(population_by_region.values())
    return [{"region": region, "population": population_by_region[region],
             "share_fraction": round(population_by_region[region] / total, 6) if total else 0.0}
            for region in sorted(population_by_region)]


def dollarized_tam(population: int, annual_spend_per_person: float) -> dict[str, object]:
    """Estimate annual TAM in USD from explicitly supplied population/spend inputs."""
    if type(population) is not int or population < 0:
        raise ValueError("population must be a non-negative integer")
    spend = Decimal(str(annual_spend_per_person))
    if not spend.is_finite() or spend < 0:
        raise ValueError("annual spend must be a finite, non-negative amount")
    tam = (Decimal(population) * spend).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"currency": "USD", "population": population,
            "annual_spend_per_person": float(spend), "tam_usd": float(tam)}
