"""P4 additions: assumptions surfacing, metrics mapping, pandering index."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.methods.rebellion import simulate_rebellion
from backend.src.services.market_strategy import pandering_authenticity_risk


class SimulationAssumption(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    value: Any = None
    provenance: str = "assumed"


class SimulationAssumptions(BaseModel):
    model_config = ConfigDict(extra="allow")
    assumptions: list[SimulationAssumption] = Field(default_factory=list)
    runs: int | None = None
    seed: int | None = None


def simulate_rebellion_full(communities, alignment_gap, seed=42, runs=5000, kappa=20, kappa2=10, influence_lambda=0.2, influence_rounds=3, theta=0.15, value_weights=None, community_tag_sets=None, fit_ratios=None, emitter=None):
    """Run simulate_rebellion and surface seed, runs and assumptions on the simulation."""
    result = simulate_rebellion(
        communities, alignment_gap,
        seed=seed, runs=runs, kappa=kappa, kappa2=kappa2,
        influence_lambda=influence_lambda, influence_rounds=influence_rounds,
        theta=theta, value_weights=value_weights,
        community_tag_sets=community_tag_sets, fit_ratios=fit_ratios,
    )
    simulation = result.get("simulation")
    names = [c.get("name") for c in (communities or [])]
    if emitter is not None:
        emitter.emit("simulation.started", {"runs": runs, "seed": seed, "communities": names})
    if simulation is not None:
        simulation["seed"] = seed
        simulation["runs"] = runs
        simulation["assumptions"] = [
            {"name": "kappa", "value": kappa, "provenance": "assumed"},
            {"name": "kappa2", "value": kappa2, "provenance": "assumed"},
            {"name": "lambda", "value": influence_lambda, "provenance": "assumed"},
            {"name": "rounds", "value": influence_rounds, "provenance": "assumed"},
            {"name": "theta", "value": theta, "provenance": "assumed"},
            {"name": "histogram_bins", "value": 24, "provenance": "assumed"},
        ]
        if emitter is not None:
            for snap in simulation.get("snapshots", []):
                emitter.emit("simulation.progress", snap)
            for name, prob in simulation.get("per_community_rebellion_probability", {}).items():
                share = next((c.get("share") for c in (communities or []) if c.get("name") == name), None)
                emitter.emit("simulation.community", {"name": name, "rebellion_probability": prob, "core_audience_share": share})
    return result


def map_simulation_metrics(simulation, communities):
    """Map rebellion simulation outputs to Metric-shaped entries, provenance modeled.
    ip_value_at_risk_pct is the p95 of the loss distribution (95% value at risk)."""
    metrics = []
    if not simulation:
        return metrics
    hist = simulation["histogram"]
    metrics.append({
        "name": "rebellion_distribution",
        "value": {"bins": hist["bins"], "lo": hist["lo"], "hi": hist["hi"], "counts": hist["counts"],
                  "mean": simulation["mean"], "median": simulation["median"],
                  "p5": simulation["p5"], "p95": simulation["p95"]},
        "provenance": "modeled",
        "method_ref": "rebellion-monte-carlo-v1",
    })
    metrics.append({"name": "ip_value_at_risk_pct", "value": simulation["p95"], "provenance": "modeled", "method_ref": "rebellion-monte-carlo-v1"})
    shares = {c.get("name"): c.get("share") for c in communities or []}
    for name, prob in simulation.get("per_community_rebellion_probability", {}).items():
        metrics.append({"name": f"rebellion_probability:{name}", "value": prob, "provenance": "modeled", "method_ref": "rebellion-monte-carlo-v1"})
        metrics.append({"name": f"core_audience_share:{name}", "value": shares.get(name), "provenance": "modeled", "method_ref": "rebellion-monte-carlo-v1"})
    return metrics


def rebellion_pandering_index(co_occurrence, anti_co_occurrence, affinity_vector):
    """Map the Pandering & Authenticity Risk index onto rebellion.index."""
    risk = pandering_authenticity_risk(co_occurrence, anti_co_occurrence, affinity_vector)
    return {
        "score": risk.score,
        "components": {
            "contradiction": risk.contradiction,
            "overclaim": risk.overclaim,
            "alignment_gap": risk.alignment_gap,
        },
        "method_ref": "pandering-index-v1",
    }
