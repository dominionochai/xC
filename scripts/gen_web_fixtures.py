#!/usr/bin/env python3
"""Generate the SYNTHETIC recorded runs the dashboard plays back when no live backend is reachable.

Every output carries "_notice": "SYNTHETIC FIXTURE - NOT QLOO OUTPUT" and mode "fixture".
Numbers are computed here from stated inputs (seeded Monte Carlo, TAM arithmetic, a real
SHA-256 evidence chain) so the files are internally consistent. They are NOT measurements.

Usage:  python3 scripts/gen_web_fixtures.py        (writes web/data/*.json)
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "data"
NOTICE = "SYNTHETIC FIXTURE - NOT QLOO OUTPUT"
T0 = "2026-10-30T09:00:00.000Z"

REGION_META = {
    "soho_nyc": ("SoHo, New York", 40.7233, -74.0030),
    "shibuya_tokyo": ("Shibuya, Tokyo", 35.6595, 139.7005),
    "mayfair_london": ("Mayfair, London", 51.5094, -0.1478),
}

AGE_BUCKETS = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]

PRESETS = {
    "porsche-kith": dict(
        label="Porsche x Kith", a="Porsche", b="Kith",
        description="Automotive heritage meets New York streetwear retail.",
        seed=42, fit=83.0, overlap=0.31, tags=(92, 127, 17),
        shared=["Heritage craftsmanship", "Collector culture", "Design-led luxury", "Weekend driving", "Classic Americana"],
        only_a=["Track performance", "German engineering", "Club events"],
        only_b=["Downtown streetwear", "Menswear drops", "Neighbourhood identity"],
        age_a=[17, 6, 9, 14, 8, -12], age_b=[11, 18, 12, 6, -9, -14],
        comms=[("Air-cooled purists", 0.22, 0.31, ["r/Porsche", "r/AirCooled"]),
               ("Track-day regulars", 0.12, 0.24, ["r/Porsche", "r/Cars"]),
               ("Drop-day loyalists", 0.18, 0.19, ["r/streetwear", "r/malefashionadvice"])],
        pander=(0.22, 0.35, 0.27), loc=(88, 74, 69), pops=(1_800_000, 1_400_000, 1_100_000),
        spend=480.0, pen=0.12, bridge=None,
        loc_note="Strong everywhere; the weakest ground is still above 65.",
    ),
    "coachella-jacquemus": dict(
        label="Coachella x Jacquemus", a="Coachella Music Festival", b="Jacquemus",
        description="Festival stage sponsorship meets a luxury fashion activation.",
        seed=42, fit=71.0, overlap=0.22, tags=(83, 119, 10),
        shared=["Fashion week attendance", "Creative producers", "Influencer culture", "Summer travel"],
        only_a=["Camping accommodations", "Electronic music producers", "Inclusivity"],
        only_b=["Surrealist art", "Leather goods", "Provence imagery"],
        age_a=[46, 10, 4, -8, -18, -24], age_b=[-6, 12, 25, 18, 4, -14],
        comms=[("Festival-first purists", 0.48, 0.36, ["r/coachella", "r/Music"]),
               ("Jacquemus core buyers", 0.39, 0.22, ["r/femalefashionadvice", "r/luxuryfashion"]),
               ("Local-scene regulars", 0.31, 0.18, ["r/popheads", "r/indieheads"])],
        pander=(0.60, 0.70, 0.64), loc=(81, 63, 42), pops=(1_800_000, 1_400_000, 1_100_000),
        spend=380.0, pen=0.09,
        bridge=dict(before=74.0, after=31.0, steps=[
            ("Familiarization", "Festival merchandise", "Emerging-designer capsules",
             "Seed fashion credibility inside the festival audience before any brand pairing is visible.",
             ["Emerging-designer capsule collections", "Festival pop-up boutiques"], 14.2),
            ("Bridge adoption", "Emerging-designer capsules", "Desert wellness retreats",
             "Move the shared audience into a setting both brands already own: slow, outdoors, design-aware.",
             ["Desert wellness retreats", "Design-led hospitality"], 17.8),
            ("Conversion", "Desert wellness retreats", "Jacquemus stage-side activation",
             "Introduce the Jacquemus activation to an audience that now recognises it as part of the festival.",
             ["Stage-side VIP activation", "Co-branded capsule drop"], 22.5)]),
        loc_note="North America welcomes the pairing. London is the market to avoid.",
    ),
    "lululemon-nfl": dict(
        label="Lululemon x NFL", a="Lululemon", b="National Football League",
        description="Activewear expansion into professional football licensing.",
        seed=42, fit=38.0, overlap=0.09, tags=(145, 111, 17),
        shared=["Resilience", "Performance athletes", "Teams and community"],
        only_a=["Mindfulness", "Yoga studios", "Canadian heritage"],
        only_b=["Football", "Game-day culture", "Fantasy leagues"],
        age_a=[4, 12, 16, 22, 8, -10], age_b=[8, 26, 19, 5, -9, -18],
        comms=[("Studio-yoga regulars", 0.41, 0.46, ["r/lululemon", "r/yoga"]),
               ("Gridiron traditionalists", 0.27, 0.30, ["r/nfl", "r/Fantasy_Football"]),
               ("Running-club core", 0.22, 0.17, ["r/running", "r/AdvancedRunning"])],
        pander=(0.38, 0.44, 0.52), loc=(54, 33, 47), pops=(1_800_000, 1_400_000, 1_100_000),
        spend=520.0, pen=0.07,
        bridge=dict(before=81.0, after=29.0, steps=[
            ("Familiarization", "Studio yoga", "Craft coffee",
             "Meet both audiences in a neutral weekday ritual with no sport or fitness message.",
             ["Specialty coffee roasters", "Neighbourhood cafés"], 12.6),
            ("Bridge adoption", "Craft coffee", "Recovery technology",
             "Move to recovery, where athletes and studio members already share products and language.",
             ["Percussive therapy devices", "Recovery studios"], 18.4),
            ("Conversion", "Recovery technology", "Boutique hospitality",
             "Finish in hospitality settings that host team events and wellness weekends alike.",
             ["Boutique hotels", "Team-event hospitality"], 21.9)]),
        loc_note="Weak fit everywhere. Tokyo is the hardest market.",
    ),
}


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def metric(value, prov, unit=None, ref=None, note=None):
    m = {"value": None if value is None else round(float(value), 4), "provenance": prov}
    if unit:
        m["unit"] = unit
    if ref:
        m["method_ref"] = ref
    if note:
        m["note"] = note
    return m


def simulate(comms, runs, seed, bins=24):
    rng = random.Random(seed)
    losses = []
    for _ in range(runs):
        loss = 0.0
        for _, p, share, _ in comms:
            k = 14.0
            f = rng.betavariate(max(p * k, 0.2), max((1 - p) * k, 0.2))
            loss += share * f
        losses.append(loss * 100 * 0.62)
    losses.sort()
    lo, hi = 0.0, math.ceil(losses[int(runs * 0.9995)] / 2) * 2
    counts = [0] * bins
    for v in losses:
        counts[min(bins - 1, int((v - lo) / (hi - lo) * bins))] += 1
    pct = lambda q: losses[int(q * (runs - 1))]
    return dict(lo=lo, hi=float(hi), counts=counts, mean=sum(losses) / runs, median=pct(.5), p5=pct(.05), p95=pct(.95), losses=losses)


def heat_cells(rng, lat, lon, ov, spread, n=420):
    """Synthetic hot-cell fields for A and B around a region centre. ov = how much they overlap (0..1)."""
    ax, ay = lat + rng.uniform(-.0006, .0006), lon + rng.uniform(-.0006, .0006)
    sep = (1 - ov) * spread * 1.6
    bx, by = ax + sep * rng.choice([-1, 1]) * .8, ay + sep * rng.choice([-1, 1]) * .8
    cells = []
    for i in range(n):
        la = lat + rng.gauss(0, spread)
        lo = lon + rng.gauss(0, spread)
        da = math.exp(-(((la - ax) ** 2 + (lo - ay) ** 2) / (2 * (spread * .8) ** 2)))
        db = math.exp(-(((la - bx) ** 2 + (lo - by) ** 2) / (2 * (spread * .8) ** 2)))
        cells.append({"lat": round(la, 5), "lon": round(lo, 5),
                      "a": round(min(1, max(0, da + rng.gauss(0, .05))), 3),
                      "b": round(min(1, max(0, db + rng.gauss(0, .05))), 3)})
    return {"cell_note": "values normalised 0..1 within each area", "cells": cells}


def build(pid, c):
    rng = random.Random(7)
    runs = 5000
    comms = c["comms"]
    sim = simulate(comms, runs, c["seed"])
    mean_loss = sim["mean"] / 100
    # --- locality
    regions, rr = [], list(zip(REGION_META.items(), c["loc"], c["pops"]))
    glob = round(sum(c["loc"]) / 3, 1)
    for (key, (label, lat, lon)), aff, pop in rr:
        spread = {"soho_nyc": .0042, "shibuya_tokyo": .0050, "mayfair_london": .0046}[key]
        r = {"key": key, "label": label,
             "affinity": metric(aff, "modeled", "index_0_100", "locality-overlap-v1"),
             "friction": metric(100 - aff, "modeled", "index_0_100", "locality-overlap-v1"),
             "delta_vs_global": metric(round(aff - glob, 1), "modeled", "index_points", "locality-overlap-v1"),
             "sample_note": f"{rng.randint(260, 980)} heatmap cells compared",
             "heat": heat_cells(rng, lat, lon, aff / 100, spread)}
        regions.append(r)
    # --- TAM
    def tam(loss, pen_mult=1.0, spend_mult=1.0, pop_mult=1.0, aff_mult=1.0):
        t = 0.0
        for (_, aff, pop) in [(0, a, p) for a, p in zip(c["loc"], c["pops"])]:
            t += pop * pop_mult * c["pen"] * pen_mult * c["spend"] * spend_mult * min(100, aff * aff_mult) / 100 * (1 - loss)
        return t
    base = tam(mean_loss)
    low, high = tam(sim["p95"] / 100), tam(sim["p5"] / 100)
    baseline = sum(p * c["pen"] * c["spend"] for p in c["pops"])
    sens = []
    for key, kw in (("penetration_rate", "pen_mult"), ("annual_spend_per_customer_usd", "spend_mult"),
                    ("regional_populations", "pop_mult"), ("regional_affinity", "aff_mult")):
        sens.append({"assumption_key": key, "low_usd": round(tam(mean_loss, **{kw: .7})), "high_usd": round(tam(mean_loss, **{kw: 1.3}))})
    sens.append({"assumption_key": "ip_loss", "low_usd": round(low), "high_usd": round(high)})
    # --- evidence ledger (real hash chain)
    claims = [
        ("qloo./search", "call:1", f"{c['a']} resolved to a Qloo brand entity."),
        ("qloo./search", "call:2", f"{c['b']} resolved to a Qloo brand entity."),
        ("qloo./v2/insights", "call:3", f"Pairwise affinity between the two brands is {c['fit']:.0f} out of 100."),
        ("qloo./entities", "call:4", f"The brands share {c['tags'][2]} tags out of {c['tags'][0] + c['tags'][1] - c['tags'][2]}."),
        ("qloo./v2/insights", "call:5", "Age and gender indices were read for both audiences."),
        ("model.community", "derive:1", f"{len(comms)} communities were derived from tags that only one brand carries."),
        ("model.rebellion", "derive:2", f"The simulation ran {runs} times with seed {c['seed']}."),
        ("model.rebellion", "derive:3", f"Mean IP value at risk is {sim['mean']:.1f} percent of the core franchise."),
        ("qloo./v2/insights", "call:6", "Heatmaps for SoHo, Shibuya and Mayfair were fetched for both brands."),
        ("model.locality", "derive:4", "Regional fit is the overlap of the two brands' hot cells inside each area."),
        ("assumption", "assume:1", f"Penetration is assumed at {c['pen']:.0%} of the catchment."),
        ("assumption", "assume:2", f"Annual spend is assumed at ${c['spend']:.0f} per customer."),
        ("model.tam", "derive:5", f"Base expansion is ${base / 1e6:,.0f} million."),
    ]
    if c["bridge"]:
        claims.insert(8, ("qloo./v2/insights", "call:7", "Middleman categories were queried to find a three-step bridge."))
        claims.insert(9, ("model.bridge", "derive:6", f"The bridge cuts friction from {c['bridge']['before']:.0f} to {c['bridge']['after']:.0f}."))
    evidence, prev = [], None
    for i, (src, ref, claim) in enumerate(claims):
        ts = f"2026-10-30T09:00:{(i * 2 + 3) % 60:02d}.000Z"
        entry = {"index": i, "timestamp": ts, "source": src, "reference": ref, "claim": claim, "payload": {"ref": ref}, "previous_hash": prev}
        entry["current_hash"] = sha({k: entry[k] for k in ("index", "timestamp", "source", "reference", "claim", "payload", "previous_hash")})
        prev = entry["current_hash"]
        evidence.append(entry)
    ev = lambda *needles: [e["index"] for e in evidence if any(n in e["claim"] or n in e["reference"] for n in needles)]
    # --- communities
    communities = []
    for i, (label, p, share, subs) in enumerate(comms):
        communities.append({
            "id": f"c{i + 1}", "label": label,
            "basis": {"tags": (c["only_a"] if i % 2 == 0 else c["only_b"])[:3], "entities": [], "demographics": None},
            "rebellion_probability": metric(p, "modeled", "probability_0_1", "rebellion-sim-v1"),
            "core_audience_share": metric(share, "modeled", "probability_0_1", "communities-v1"),
            "evidence_refs": ev("communities were derived", "Mean IP value"),
            "channels": [{"name": s, "kind": "subreddit", "url": None, "provenance": "hypothesis", "evidence": None} for s in subs]})
    communities.sort(key=lambda x: -x["rebellion_probability"]["value"])
    # --- pandering index
    cont, over, gap = c["pander"]
    pandering = round(100 * (0.4 * cont + 0.3 * over + 0.3 * gap), 1)
    # --- bridge
    if c["bridge"]:
        b = c["bridge"]
        bridge = {"status": "found",
                  "steps": [{"number": i + 1, "phase": ph, "from_category": fr, "to_category": to, "objective": obj,
                             "entities": [{"id": f"syn-{i}{j}", "name": n} for j, n in enumerate(ents)],
                             "affinity_lift": metric(lift, "modeled", "index_points", "bridge-v1"),
                             "evidence_refs": ev("bridge", "Middleman")} for i, (ph, fr, to, obj, ents, lift) in enumerate(b["steps"])],
                  "friction_before": metric(b["before"], "modeled", "index_0_100", "bridge-v1"),
                  "friction_after": metric(b["after"], "modeled", "index_0_100", "bridge-v1"),
                  "friction_reduction_pct": metric(round((b["before"] - b["after"]) / b["before"] * 100, 1), "modeled", "percent", "bridge-v1")}
    else:
        f = 100 - c["fit"]
        bridge = {"status": "not_needed", "steps": [], "friction_before": metric(f, "modeled", "index_0_100", "bridge-v1"),
                  "friction_after": metric(f, "modeled", "index_0_100", "bridge-v1"), "friction_reduction_pct": metric(0, "modeled", "percent", "bridge-v1")}
    # --- verdict
    risk = sim["mean"]
    if c["fit"] >= 70 and risk < 12:
        verdict, vtxt = "proceed", "The two audiences already overlap. The deal can go ahead without a bridge, and the main risk is contained."
    else:
        verdict, vtxt = "proceed_with_remediation", ("The deal is workable only with the three-step bridge. Without it, one or more fan communities are likely to rebel." if c["bridge"]
                                                       else "The deal is workable, but fan rebellion needs a plan before announcement.")
    conf = 0.78 if c["bridge"] is None else 0.71
    shared_n, a_n, b_n = c["tags"][2], c["tags"][0] - c["tags"][2], c["tags"][1] - c["tags"][2]
    nm = lambda x: x
    assumptions = [
        {"key": "penetration_rate", "label": "Penetration of the catchment", "value": c["pen"], "unit": "fraction", "provenance": "assumed"},
        {"key": "annual_spend_per_customer_usd", "label": "Annual spend per customer", "value": c["spend"], "unit": "usd", "provenance": "assumed"},
        {"key": "regional_populations", "label": "Adult catchment, three regions", "value": " / ".join(f"{p / 1e6:.1f}M" for p in c["pops"]), "unit": "people", "provenance": "assumed"},
        {"key": "regional_affinity", "label": "Regional affinity (overlap)", "value": " / ".join(str(x) for x in c["loc"]), "unit": "index_0_100", "provenance": "modeled"},
        {"key": "ip_loss", "label": "IP value lost to rebellion", "value": round(mean_loss, 4), "unit": "fraction", "provenance": "modeled"},
    ]
    report = {
        "_notice": NOTICE, "schema_version": "1.0", "run_id": f"fixture-{pid}", "mode": "fixture", "generated_at": T0, "seed": c["seed"],
        "acquirer": {"name": c["a"], "entity_id": f"syn-{pid[:3]}-a", "type": "urn:entity:brand"},
        "target": {"name": c["b"], "entity_id": f"syn-{pid[:3]}-b", "type": "urn:entity:brand"},
        "headline": {"verdict": verdict, "summary": vtxt, "summary_source": "template", "confidence": metric(conf, "modeled", "probability_0_1", "verdict-v1")},
        "fit": {
            "affinity": metric(c["fit"], "measured", "index_0_100", "pair-affinity-v1"),
            "tag_overlap": metric(c["tags"][2] / (c["tags"][0] + c["tags"][1] - c["tags"][2]), "measured", "ratio_0_1", "tag-jaccard-v1"),
            "tag_counts": {"a_only": a_n, "shared": shared_n, "b_only": b_n},
            "shared_signals": [{"id": f"s{i}", "name": n, "type": "urn:tag", "weight": round(.9 - i * .11, 2), "evidence_refs": ev("share")} for i, n in enumerate(c["shared"])],
            "contrast_axes": [{"id": f"x{i}", "name": n, "side": "acquirer", "strength": round(.8 - i * .1, 2), "evidence_refs": ev("communities were derived")} for i, n in enumerate(c["only_a"])] +
                             [{"id": f"y{i}", "name": n, "side": "target", "strength": round(.8 - i * .1, 2), "evidence_refs": ev("communities were derived")} for i, n in enumerate(c["only_b"])],
            "demographics": {"acquirer": {"age": [{"bucket": k, "share": v / 100} for k, v in zip(AGE_BUCKETS, c["age_a"])], "gender": None, "provenance": "measured"},
                             "target": {"age": [{"bucket": k, "share": v / 100} for k, v in zip(AGE_BUCKETS, c["age_b"])], "gender": None, "provenance": "measured"}}},
        "rebellion": {
            "index": {"score": metric(pandering, "modeled", "index_0_100", "pandering-index-v1"),
                      "components": {"contradiction": metric(cont, "modeled", "ratio_0_1", "pandering-index-v1"),
                                     "overclaim": metric(over, "modeled", "ratio_0_1", "pandering-index-v1"),
                                     "alignment_gap": metric(gap, "modeled", "ratio_0_1", "pandering-index-v1")}},
            "simulation": {"runs": runs, "seed": c["seed"],
                           "distribution": {"lo": sim["lo"], "hi": sim["hi"], "counts": sim["counts"], "mean": round(sim["mean"], 3), "median": round(sim["median"], 3), "p5": round(sim["p5"], 3), "p95": round(sim["p95"], 3)},
                           "ip_value_at_risk_pct": {"mean": metric(sim["mean"], "modeled", "percent", "rebellion-sim-v1"), "p5": metric(sim["p5"], "modeled", "percent", "rebellion-sim-v1"), "p95": metric(sim["p95"], "modeled", "percent", "rebellion-sim-v1")},
                           "assumptions": [{"key": "kappa", "value": 20, "provenance": "assumed"}, {"key": "influence_lambda", "value": 0.2, "provenance": "assumed"}, {"key": "rounds", "value": 3, "provenance": "assumed"}, {"key": "theta", "value": 0.15, "provenance": "assumed"}],
                           "method_ref": "rebellion-sim-v1"},
            "communities": communities},
        "bridge": bridge,
        "locality": {"regions": regions, "global_affinity": metric(glob, "modeled", "index_0_100", "locality-overlap-v1"), "caveats": [
            "Heatmap values are normalised inside each area, so regions are compared by overlap, never by raw value.", c["loc_note"]], "method_ref": "locality-overlap-v1"},
        "tam": {"currency": "USD", "baseline_usd": metric(baseline, "modeled", "usd", "tam-v1"),
                "expansion_usd": {"low": metric(low, "modeled", "usd", "tam-v1"), "base": metric(base, "modeled", "usd", "tam-v1"), "high": metric(high, "modeled", "usd", "tam-v1")},
                "assumptions": assumptions, "sensitivity": sens, "method_ref": "tam-v1"},
        "evidence": evidence,
        "evidence_verification": {"valid": True, "records_checked": len(evidence), "error": None},
        "analyst_review": {"approved": True, "risk_level": "medium" if verdict != "proceed" else "low",
                           "findings": [f"{communities[0]['label']} carries the highest rebellion probability at {communities[0]['rebellion_probability']['value']:.0%}.",
                                        "Channels listed for each community are hypotheses and were not verified."],
                           "recommendations": ["Pilot in the strongest region first.", "Brief the named communities before the announcement."]},
        "phases": [{"phase": p, "status": "complete", "duration_ms": d} for p, d in (("NORMALIZATION", 3900), ("GRAPH_QUERYING", 11200), ("BRIDGE_DISCOVERY", 6400), ("ADVERSARIAL_AUDIT", 9800), ("SYNTHESIS", 2600))],
        "warnings": [{"code": "channels_unverified", "message": "Community channels are hypotheses, not verified sources.", "section": "rebellion"}],
        "memo": {"markdown_path": f"/api/v1/reports/fixture-{pid}/memo.md", "pdf_path": f"/api/v1/reports/fixture-{pid}/memo.pdf"},
    }
    return report, sim, evidence


def events_for(pid, c, report, sim):
    seq = [0]
    t = [0]
    out = []

    def ev(typ, phase, data, delay=300):
        seq[0] += 1
        t[0] += delay
        out.append({"delay_ms": delay, "event": {"seq": seq[0], "ts": f"2026-10-30T09:00:{(t[0] // 1000) % 60:02d}.{t[0] % 1000:03d}Z", "run_id": report["run_id"], "type": typ, "phase": phase, "data": data}})

    call = [0]

    def tool(phase, endpoint, params, count, ms, summary, suspect=False):
        call[0] += 1
        cid = f"call-{call[0]}"
        ev("tool.call", phase, {"call_id": cid, "tool": "qloo." + endpoint.strip("/").split("/")[-1], "endpoint": endpoint, "params": params}, 250)
        ev("tool.result", phase, {"call_id": cid, "status": 200, "latency_ms": ms, "result_count": count, "suspect_empty": suspect, "cache_hit": False, "summary": summary, "payload_preview": None}, ms)

    ev("run.started", None, {"report_id": report["run_id"], "mode": "fixture", "seed": c["seed"], "simulation_runs": 5000, "acquirer": report["acquirer"], "target": report["target"]}, 100)
    P = ["NORMALIZATION", "GRAPH_QUERYING", "BRIDGE_DISCOVERY", "ADVERSARIAL_AUDIT", "SYNTHESIS"]
    T = ["Catalog and entity normalization", "Extraction and multi-domain graph querying", "Cross-system latent bridge discovery", "Adversarial backlash and pandering audit", "Dollarized TAM and remediation synthesis"]
    a, b = c["a"], c["b"]
    ev("phase.started", P[0], {"title": T[0]}, 200)
    ev("agent.note", P[0], {"agent": "normalizer", "text": f"Resolving '{a}' and '{b}' against Qloo's brand index and rejecting any match whose name does not agree with the query."}, 400)
    tool(P[0], "/search", {"query": a, "types": "urn:entity:brand"}, 1, 1800, f"{a} matched exactly. Confidence 0.97.")
    tool(P[0], "/search", {"query": b, "types": "urn:entity:brand"}, 1, 1650, f"{b} matched exactly. Confidence 0.95.")
    ev("ledger.entry", P[0], report["evidence"][0], 150)
    ev("ledger.entry", P[0], report["evidence"][1], 100)
    ev("phase.completed", P[0], {"duration_ms": 3900, "status": "complete"}, 200)

    ev("phase.started", P[1], {"title": T[1]}, 200)
    ev("agent.note", P[1], {"agent": "graph analyst", "text": "Reading pairwise affinity, the full tag sets and both audiences' age and gender indices."}, 400)
    tool(P[1], "/v2/insights", {"signal.interests.entities": "…", "filter.type": "urn:entity:brand", "filter.entities": "…"}, 1, 1900, f"Pairwise affinity {c['fit']:.1f}.")
    ev("metric.updated", P[1], {"key": "fit.affinity", "metric": report["fit"]["affinity"]}, 150)
    tool(P[1], "/entities", {"entity_ids": "…"}, c["tags"][0], 1200, f"{c['tags'][0]} tags for {a}.")
    tool(P[1], "/entities", {"entity_ids": "…"}, c["tags"][1], 1250, f"{c['tags'][1]} tags for {b}.")
    ev("metric.updated", P[1], {"key": "fit.tag_overlap", "metric": report["fit"]["tag_overlap"]}, 150)
    tool(P[1], "/v2/insights", {"signal.interests.entities": "…", "filter.type": "urn:demographics"}, 1, 1000, "Age and gender indices for both audiences.")
    tool(P[1], "/v2/insights", {"signal.interests.entities": "…", "filter.type": "urn:heatmap", "filter.location.query": "SoHo, New York"}, 29, 2050, "29 heatmap cells.")
    tool(P[1], "/v2/insights", {"signal.interests.entities": "…", "filter.type": "urn:heatmap", "filter.location.query": "Shibuya, Tokyo"}, 477, 2100, "477 heatmap cells.")
    tool(P[1], "/v2/insights", {"signal.interests.entities": "…", "filter.type": "urn:heatmap", "filter.location.query": "Mayfair, London"}, 950, 2200, "950 heatmap cells.")
    for i in (2, 3, 4, 8 if not c["bridge"] else 10):
        ev("ledger.entry", P[1], report["evidence"][min(i, len(report["evidence"]) - 1)], 120)
    ev("warning", P[1], {"code": "heatmap_normalised", "message": "Heatmap values are normalised per area; regions are compared by overlap.", "section": "locality"}, 200)
    ev("phase.completed", P[1], {"duration_ms": 11200, "status": "complete"}, 200)

    ev("phase.started", P[2], {"title": T[2]}, 200)
    if c["bridge"]:
        ev("agent.note", P[2], {"agent": "bridge scout", "text": "Direct fit is weak. Searching middleman categories for the weakest link and a three-step path that closes it."}, 400)
        for st in report["bridge"]["steps"]:
            tool(P[2], "/v2/insights", {"signal.interests.entities": "…", "filter.type": "urn:entity:brand", "take": 50}, 50, 1900, f"Candidates for {st['to_category']}.")
        ev("metric.updated", P[2], {"key": "bridge.friction_before", "metric": report["bridge"]["friction_before"]}, 200)
        ev("metric.updated", P[2], {"key": "bridge.friction_after", "metric": report["bridge"]["friction_after"]}, 200)
        ev("metric.updated", P[2], {"key": "bridge.friction_reduction_pct", "metric": report["bridge"]["friction_reduction_pct"]}, 200)
    else:
        ev("agent.note", P[2], {"agent": "bridge scout", "text": f"Direct fit is {c['fit']:.0f}. No bridge required."}, 400)
    ev("phase.completed", P[2], {"duration_ms": 6400, "status": "complete"}, 200)

    ev("phase.started", P[3], {"title": T[3]}, 200)
    ev("agent.note", P[3], {"agent": "adversary", "text": "Deriving fan communities from tags only one brand carries, then simulating how each reacts."}, 400)
    ev("simulation.started", P[3], {"runs": 5000, "seed": c["seed"], "communities": len(report["rebellion"]["communities"])}, 200)
    counts = report["rebellion"]["simulation"]["distribution"]["counts"]
    lo, hi = report["rebellion"]["simulation"]["distribution"]["lo"], report["rebellion"]["simulation"]["distribution"]["hi"]
    losses = sim["losses"]
    rng = random.Random(3)
    sample = losses[:]
    rng.shuffle(sample)
    steps = 28
    for s in range(1, steps + 1):
        n = int(5000 * s / steps)
        part = sample[:n]
        part_sorted = sorted(part)
        hist = [0] * len(counts)
        for v in part:
            hist[min(len(counts) - 1, int((v - lo) / (hi - lo) * len(counts)))] += 1
        ev("simulation.progress", P[3], {"completed": n, "total": 5000, "running": {"mean": round(sum(part) / n, 3), "p5": round(part_sorted[int(.05 * (n - 1))], 3), "p95": round(part_sorted[int(.95 * (n - 1))], 3)}, "histogram": {"lo": lo, "hi": hi, "counts": hist}}, 170)
    for cm in report["rebellion"]["communities"]:
        ev("simulation.community", P[3], {"community": cm}, 260)
    ev("metric.updated", P[3], {"key": "rebellion.index", "metric": report["rebellion"]["index"]["score"]}, 150)
    ev("metric.updated", P[3], {"key": "rebellion.ip_value_at_risk_pct.mean", "metric": report["rebellion"]["simulation"]["ip_value_at_risk_pct"]["mean"]}, 150)
    ev("ledger.entry", P[3], report["evidence"][5], 120)
    ev("ledger.entry", P[3], report["evidence"][6], 120)
    ev("ledger.entry", P[3], report["evidence"][7], 120)
    ev("phase.completed", P[3], {"duration_ms": 9800, "status": "complete"}, 200)

    ev("phase.started", P[4], {"title": T[4]}, 200)
    ev("agent.note", P[4], {"agent": "synthesist", "text": "Converting regional fit into dollars with stated assumptions, then writing the verdict from the computed numbers."}, 400)
    for r in report["locality"]["regions"]:
        ev("metric.updated", P[4], {"key": f"locality.region.{r['key']}.affinity", "metric": r["affinity"]}, 160)
    ev("metric.updated", P[4], {"key": "tam.expansion_usd.low", "metric": report["tam"]["expansion_usd"]["low"]}, 160)
    ev("metric.updated", P[4], {"key": "tam.expansion_usd.base", "metric": report["tam"]["expansion_usd"]["base"]}, 160)
    ev("metric.updated", P[4], {"key": "tam.expansion_usd.high", "metric": report["tam"]["expansion_usd"]["high"]}, 160)
    ev("metric.updated", P[4], {"key": "headline.confidence", "metric": report["headline"]["confidence"]}, 160)
    ev("ledger.entry", P[4], report["evidence"][-1], 120)
    ev("phase.completed", P[4], {"duration_ms": 2600, "status": "complete"}, 200)
    ev("report.completed", None, {"result": {"$ref": f"report.{pid}.json"}}, 300)
    ev("run.finished", None, {"status": "completed", "duration_ms": 33900}, 120)
    return {"_notice": NOTICE, "events": out}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    presets = []
    for pid, c in PRESETS.items():
        report, sim, _ = build(pid, c)
        (OUT / f"report.{pid}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        (OUT / f"events.{pid}.json").write_text(json.dumps(events_for(pid, c, report, sim), ensure_ascii=False), encoding="utf-8")
        presets.append({"id": pid, "label": c["label"], "acquirer_brand": c["a"] if pid != "coachella-jacquemus" else "Coachella", "target_brand": c["b"] if pid != "lululemon-nfl" else "NFL", "description": c["description"]})
        print(pid, "fit", c["fit"], "ip mean %.1f p5 %.1f p95 %.1f" % (sim["mean"], sim["p5"], sim["p95"]), "tam base $%.0fM" % (report["tam"]["expansion_usd"]["base"]["value"] / 1e6))
    (OUT / "presets.json").write_text(json.dumps({"_notice": NOTICE, "presets": presets}, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
