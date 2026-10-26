"""Adapter from audience communities to the assumption-based rebellion model."""

from collections.abc import Mapping
import math

from backend.methods.rebellion import simulate_rebellion


# The M5 simulator requires anti_strength for every community and a top-level
# alignment_gap. Builder output supplies anti_strength; these are safe fallbacks.
REBELLION_COMMUNITY_DEFAULTS = {
    "anti_strength": 0.5,
    "fit_ratio": 1.0,
    "alignment_gap": 0.5,
}


def _community_rows(communities):
    """Accept either build_communities' result or its community list."""
    if isinstance(communities, Mapping):
        communities = communities.get("communities")
    if communities is None:
        return []
    return list(communities)


def _number(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def map_rebellion_communities(communities):
    """Map builder communities to simulator share/name/tag-set records.

    Returns ``{"communities": [...], "guarded": bool}``. Non-positive or
    invalid shares are clamped to zero and reported through ``guarded``; each
    mapped community retains the three-field mapper contract.
    """
    mapped = []
    guarded = False
    for index, community in enumerate(_community_rows(communities)):
        if not isinstance(community, Mapping):
            guarded = True
            continue
        raw_share = community.get("core_audience_share", community.get("share", 0.0))
        share = _number(raw_share, default=0.0)
        if share <= 0.0:
            guarded = True
            share = 0.0
        name = community.get("label", community.get("name"))
        if name is None or name == "":
            name = "community_%d" % (index + 1)
        tags = community.get(
            "basis_tags",
            community.get("community_tag_sets", community.get("tags", [])),
        )
        if tags is None:
            tags = []
        elif isinstance(tags, str):
            tags = [tags]
        else:
            tags = list(tags)
        mapped.append(
            {
                "share": share,
                "name": str(name),
                "community_tag_sets": tags,
            }
        )
    return {"communities": mapped, "guarded": guarded}


def run_rebellion_pipeline(
    communities,
    alignment_gap=REBELLION_COMMUNITY_DEFAULTS["alignment_gap"],
    seed=42,
    runs=5000,
    kappa=20,
    kappa2=10,
    influence_lambda=0.2,
    influence_rounds=3,
    theta=0.15,
    value_weights=None,
    fit_ratios=None,
):
    """Map build_communities output and run the deterministic M5 simulator.

    Empty or missing input is a no-op (``None``). The simulator receives its
    community records and tag sets separately, as required by its API.
    """
    rows = _community_rows(communities)
    if not rows:
        return None

    mapping = map_rebellion_communities(rows)
    mapped = mapping["communities"]
    if not mapped:
        return None

    simulator_communities = []
    tag_sets = []
    for source, item in zip(rows, mapped):
        anti_strength = (
            _number(source.get("anti_strength"), REBELLION_COMMUNITY_DEFAULTS["anti_strength"])
            if isinstance(source, Mapping)
            else REBELLION_COMMUNITY_DEFAULTS["anti_strength"]
        )
        simulator_communities.append(
            {
                "share": item["share"],
                "name": item["name"],
                "anti_strength": anti_strength,
            }
        )
        tag_sets.append(item["community_tag_sets"])

    if fit_ratios is None:
        fit_ratios = [REBELLION_COMMUNITY_DEFAULTS["fit_ratio"]] * len(mapped)
    result = simulate_rebellion(
        simulator_communities,
        alignment_gap=alignment_gap,
        seed=seed,
        runs=runs,
        kappa=kappa,
        kappa2=kappa2,
        influence_lambda=influence_lambda,
        influence_rounds=influence_rounds,
        theta=theta,
        value_weights=value_weights,
        community_tag_sets=tag_sets,
        fit_ratios=fit_ratios,
    )
    result["guarded"] = mapping["guarded"]
    return result
