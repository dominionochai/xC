# P4 addendum (2026-10-26)

- map_build_communities_to_rebellion maps build_communities output to simulate_rebellion input; communities with non-positive core_audience_share are excluded, never fabricated.
- simulate_rebellion_full (backend/methods/p4_additions.py) runs simulate_rebellion and surfaces rebellion.simulation.{seed, runs, assumptions[]}; assumptions are kappa, kappa2, lambda (influence_lambda), rounds (influence_rounds), theta, histogram_bins, all with provenance "assumed" (model parameters, not measured data).
- ip_value_at_risk_pct is modeled as p95 of the simulated loss distribution (95% value at risk).
- Pandering & Authenticity Index (pandering-index-v1): score = 100 * (0.50*mean(A) + 0.30*max(0, mean(C)-mean(F)) + 0.20*mean(|C_i-F_i|)), bounded 0-100, where A=anti_co_occurrence (contradiction), C=co_occurrence, F=affinity. Components: contradiction=mean(A), overclaim=max(0,mean(C)-mean(F)), alignment_gap=mean(|C_i-F_i|).
- Event stream via emitter: simulation.started, simulation.progress (from the snapshot list, 25-40 events at runs=200-5000), simulation.community.
- Empty communities -> rebellion.simulation=null plus warning no_communities.
