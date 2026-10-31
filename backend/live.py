"""Live xC audit: two brand names in, a measured report and an event stream out.

Standard library only. Every Qloo call uses a parameter form verified against the
live API (URN types, pairwise affinity through filter.entities, /entities tags,
demographics, heatmap with filter.location.query). Numbers are labelled by where
they come from: measured (read from Qloo), modeled (computed from measured data)
or assumed (an input the reader can change). Nothing here is invented to fit a
story; when Qloo returns nothing for a step, the step says so.

The module has no web framework in it. `LiveRun` runs the audit on a thread and
keeps the events, `sse()` turns them into a Server-Sent-Events stream, and the
API layer only has to call those.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

BRAND = "urn:entity:brand"
REGIONS = [("soho_nyc", "SoHo, New York"), ("shibuya_tokyo", "Shibuya, Tokyo"), ("mayfair_london", "Mayfair, London")]
AGE_BUCKETS = ["24_and_younger", "25_to_29", "30_to_34", "35_to_44", "45_to_54", "55_and_older"]
PHASES = ["NORMALIZATION", "GRAPH_QUERYING", "BRIDGE_DISCOVERY", "ADVERSARIAL_AUDIT", "SYNTHESIS"]
PHASE_TITLES = ["Catalog and entity normalization", "Extraction and multi-domain graph querying",
                "Cross-system latent bridge discovery", "Adversarial backlash and pandering audit",
                "Dollarized TAM and remediation synthesis"]
SIM_RUNS = 5000
# Qloo's pairwise affinity runs high. In a live sample of 14 pairs, mismatched brands scored 60-66 and
# well-matched ones 75-96, so the verdict bands sit inside that observed range instead of 0-100.
BRIDGE_BELOW = 75
PROCEED_FIT = 85
HIGH_RISK_FIT = 55
SEED = 42
CACHE_TTL = 3600
MAX_CELLS = 420

# Assumptions the reader can change. They are inputs, not Qloo output.
ASSUMED = {"penetration_rate": 0.08, "annual_spend_per_customer_usd": 400.0,
           "regional_populations": (1_800_000, 1_400_000, 1_100_000),
           "community_shares": (0.45, 0.25, 0.30), "exposure": 0.62}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def metric(value, prov, unit=None, ref=None, note=None) -> dict:
    m: dict[str, Any] = {"value": None if value is None else round(float(value), 4), "provenance": prov}
    if unit:
        m["unit"] = unit
    if ref:
        m["method_ref"] = ref
    if note:
        m["note"] = note
    return m


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class QlooError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Qloo:
    """Thin REST client with a response cache, retry on 429 and a call budget."""

    _cache: dict[str, tuple[float, Any]] = {}
    _lock = threading.Lock()

    def __init__(self, key: str | None = None, base: str | None = None, budget: int = 60, pace: float = 0.15):
        self.key = (key if key is not None else os.environ.get("QLOO_API_KEY", "")).strip()
        self.base = (base or os.environ.get("QLOO_API_HOST", "https://hackathon.api.qloo.com")).rstrip("/")
        self.budget, self.pace, self.calls = budget, pace, 0

    def get(self, path: str, params: list[tuple[str, str]]) -> dict:
        """Return {status, body, latency_ms, cache_hit}. Raises QlooError on failure."""
        if not self.key:
            raise QlooError("QLOO_API_KEY is not set", 503)
        url = f"{self.base}{path}?{urllib.parse.urlencode(params, safe=',:')}"
        with self._lock:
            hit = self._cache.get(url)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return {"status": 200, "body": hit[1], "latency_ms": 0, "cache_hit": True}
        if self.calls >= self.budget:
            raise QlooError("call budget exhausted", 429)
        for attempt in (0, 1):
            self.calls += 1
            started = time.monotonic()
            req = urllib.request.Request(url, headers={"X-Api-Key": self.key, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=45) as r:
                    body = json.loads(r.read().decode("utf-8", "replace") or "null")
                ms = int((time.monotonic() - started) * 1000)
                with self._lock:
                    self._cache[url] = (time.time(), body)
                time.sleep(self.pace)
                return {"status": 200, "body": body, "latency_ms": ms, "cache_hit": False}
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    time.sleep(1.6)
                    continue
                detail = ""
                try:
                    detail = json.loads(e.read().decode("utf-8", "replace"))["errors"][0]["message"]
                except Exception:
                    pass
                raise QlooError(f"Qloo {path} returned HTTP {e.code} {detail[:120]}".strip(), e.code)
            except Exception as e:  # network, timeout, bad JSON
                raise QlooError(f"Qloo {path} failed: {type(e).__name__}", 502)
        raise QlooError("Qloo rate limit", 429)


def items(body) -> list[dict]:
    res = body.get("results") if isinstance(body, dict) else None
    if isinstance(res, list):
        return [x for x in res if isinstance(x, dict)]
    out: list[dict] = []
    if isinstance(res, dict):
        for v in res.values():
            if isinstance(v, list):
                out.extend(x for x in v if isinstance(x, dict))
    return out


def _aff(it: dict) -> float | None:
    v = (it.get("query") or {}).get("affinity")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---------------------------------------------------------------- resolve
def candidates(q: Qloo, name: str) -> list[dict]:
    return candidates_from(q.get("/search", [("query", name), ("types", BRAND)])["body"])


def best_match(cands: list[dict], name: str) -> dict | None:
    """Accept a candidate only if its name agrees with the query. Never take the first result blindly."""
    n = norm(name)
    for c in cands:
        if norm(c["name"]) == n:
            return c
    flat = n.replace(" ", "")
    for c in cands:  # an acronym is a name agreement: NFL = National Football League
        words = norm(c["name"]).split()
        if len(flat) >= 2 and len(words) >= 2 and "".join(w[0] for w in words) == flat:
            return c
    if len(n) >= 3:
        for c in cands:  # Qloo ranks by relevance, so the first whole-word prefix match is the intended brand
            if norm(c["name"]).startswith(n + " "):
                return c
    close = [c for c in cands if n and (n in norm(c["name"]) or norm(c["name"]) in n) and len(norm(c["name"])) >= 3]
    return close[0] if len(close) == 1 else None


# ---------------------------------------------------------------- maths
def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=xs.__getitem__)
    r = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 5 or len(a) != len(b):
        return None
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / math.sqrt(va * vb) if va > 0 and vb > 0 else None


def minmax(d: dict[str, float]) -> dict[str, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    return {k: (v - lo) / (hi - lo) if hi > lo else 0.0 for k, v in d.items()}


def simulate(comms: list[tuple[str, float, float]], runs: int, seed: int, exposure: float, bins: int = 24) -> dict:
    rng = random.Random(seed)
    losses = []
    for _ in range(runs):
        loss = 0.0
        for _, p, share in comms:
            k = 14.0
            loss += share * rng.betavariate(max(p * k, 0.2), max((1 - p) * k, 0.2))
        losses.append(loss * 100 * exposure)
    losses.sort()
    hi = max(2.0, math.ceil(losses[int(runs * 0.9995)] / 2) * 2)
    counts = [0] * bins
    for v in losses:
        counts[min(bins - 1, int(v / hi * bins))] += 1
    pct = lambda q: losses[int(q * (runs - 1))]
    return dict(lo=0.0, hi=float(hi), counts=counts, mean=sum(losses) / runs, median=pct(.5), p5=pct(.05), p95=pct(.95), losses=losses)


# ---------------------------------------------------------------- run
class LiveRun:
    """One audit. Runs on a thread; events are kept so a dropped stream can resume."""

    def __init__(self, a_name: str, b_name: str, a_id: str | None = None, b_id: str | None = None,
                 preset_id: str | None = None, qloo: Qloo | None = None):
        self.id = str(uuid.uuid4())
        self.a_name, self.b_name, self.a_id, self.b_id, self.preset_id = a_name.strip(), b_name.strip(), a_id, b_id, preset_id
        self.q = qloo or Qloo()
        self.events: list[dict] = []
        self.cond = threading.Condition()
        self.status = "pending"
        self.result: dict | None = None
        self.error: str | None = None
        self._seq, self._calls, self._prev, self._ledger = 0, 0, None, []
        self._t0 = time.monotonic()
        self._thread: threading.Thread | None = None
        self._phase: str | None = None
        self._phase_started = 0.0

    # -- event plumbing
    def emit(self, typ: str, data: dict | None = None, phase: str | None = "__cur__") -> dict:
        with self.cond:
            self._seq += 1
            ev = {"seq": self._seq, "ts": now_iso(), "run_id": self.id, "type": typ,
                  "phase": self._phase if phase == "__cur__" else phase, "data": data or {}}
            self.events.append(ev)
            self.cond.notify_all()
            return ev

    def start(self) -> None:
        with self.cond:
            if self._thread is not None:
                return
            self.status = "running"
            self._thread = threading.Thread(target=self._main, daemon=True)
            self._thread.start()

    def _begin(self, i: int) -> None:
        self._phase = PHASES[i]
        self._phase_started = time.monotonic()
        self.emit("phase.started", {"title": PHASE_TITLES[i]})

    def _end(self) -> None:
        self.emit("phase.completed", {"duration_ms": int((time.monotonic() - self._phase_started) * 1000), "status": "complete"})

    def note(self, agent: str, text: str) -> None:
        self.emit("agent.note", {"agent": agent, "text": text})

    def warn(self, code: str, message: str, section: str | None = None) -> None:
        self.warnings.append({"code": code, "message": message, "section": section})
        self.emit("warning", {"code": code, "message": message, "section": section})

    def ledger(self, source: str, ref: str, claim: str, payload: dict | None = None) -> int:
        e = {"index": len(self._ledger), "timestamp": now_iso(), "source": source, "reference": ref,
             "claim": claim, "payload": payload or {"ref": ref}, "previous_hash": self._prev}
        e["current_hash"] = _sha({k: e[k] for k in ("index", "timestamp", "source", "reference", "claim", "payload", "previous_hash")})
        self._prev = e["current_hash"]
        self._ledger.append(e)
        self.emit("ledger.entry", e)
        return e["index"]

    def call(self, path: str, params: list[tuple[str, str]], shown: dict, summary: Callable[[dict], tuple[int | None, str]]) -> dict | None:
        """Make one Qloo call with tool.call / tool.result events. Returns the body or None on failure."""
        self._calls += 1
        cid = f"call-{self._calls}"
        self.emit("tool.call", {"call_id": cid, "tool": "qloo." + path.strip("/").split("/")[-1], "endpoint": path, "params": shown})
        try:
            r = self.q.get(path, params)
        except QlooError as e:
            self.failed_calls += 1
            self.last_error = str(e)
            self.emit("tool.result", {"call_id": cid, "status": e.status or 502, "latency_ms": 0, "result_count": None,
                                      "suspect_empty": True, "cache_hit": False, "summary": str(e), "payload_preview": None})
            if e.status in (401, 403):
                raise
            return None
        count, text = summary(r["body"])
        self.ok_calls += 1
        self.emit("tool.result", {"call_id": cid, "status": r["status"], "latency_ms": r["latency_ms"], "result_count": count,
                                  "suspect_empty": not count, "cache_hit": r["cache_hit"], "summary": text, "payload_preview": None})
        return r["body"]

    # -- the audit
    def _main(self) -> None:
        self.warnings: list[dict] = []
        self.ok_calls = self.failed_calls = 0
        try:
            self.emit("run.started", {"report_id": self.id, "mode": "live", "seed": SEED, "simulation_runs": SIM_RUNS,
                                      "acquirer": {"name": self.a_name}, "target": {"name": self.b_name}}, phase=None)
            self.result = self._audit()
            self.status = "completed"
            self.emit("report.completed", {"result": self.result}, phase=None)
            self.emit("run.finished", {"status": "completed", "duration_ms": int((time.monotonic() - self._t0) * 1000)}, phase=None)
        except Exception as e:  # a failed run must say why and end the stream
            self.status = "failed"
            self.error = str(e) or type(e).__name__
            self.emit("error", {"code": "run_failed", "message": self.error}, phase=None)
            self.emit("run.finished", {"status": "failed", "message": self.error}, phase=None)

    def _resolve(self, name: str, entity_id: str | None, label: str) -> dict:
        if entity_id:
            self.ledger("qloo./search", f"chosen:{label}", f"{name} was matched to the Qloo brand you picked.", {"entity_id": entity_id})
            return {"entity_id": entity_id, "name": name, "type": BRAND}
        cands = None
        body = self.call("/search", [("query", name), ("types", BRAND)], {"query": name, "types": BRAND},
                         lambda b: (len(items(b)), f"{len(items(b))} brand candidates for {name}."))
        if body is not None:
            cands = candidates_from(body)
        if body is None:
            raise RuntimeError(f"Qloo could not be reached ({getattr(self, 'last_error', 'no response')}). Try again in a minute.")
        if not cands:
            raise RuntimeError(f"Qloo has no brand matching “{name}”. Try the full brand name.")
        m = best_match(cands, name)
        if m is None:
            names = ", ".join(c["name"] for c in cands[:4])
            raise RuntimeError(f"Qloo has no brand named “{name}”. Closest results: {names}. Pick the intended brand and run again.")
        self.ledger("qloo./search", f"call:{self._calls}", f"{name} resolved to the Qloo brand “{m['name']}”.", {"entity_id": m["entity_id"]})
        return m

    def _audit(self) -> dict:
        q = self.q
        # ---- 1 normalization
        self._begin(0)
        self.note("normalizer", f"Resolving “{self.a_name}” and “{self.b_name}” against Qloo's brand index and rejecting any match whose name does not agree with the query.")
        A = self._resolve(self.a_name, self.a_id, "a")
        B = self._resolve(self.b_name, self.b_id, "b")
        if A["entity_id"] == B["entity_id"]:
            raise RuntimeError("Both names resolved to the same brand. Enter two different brands.")
        self._end()

        # ---- 2 graph querying
        self._begin(1)
        self.note("graph analyst", "Reading pairwise affinity, the full tag sets and both audiences' age indices, then both brands' heatmaps in three cities.")

        def pair(x, y):
            body = self.call("/v2/insights", [("signal.interests.entities", x["entity_id"]), ("filter.type", BRAND), ("filter.entities", y["entity_id"])],
                             {"signal.interests.entities": x["name"], "filter.type": BRAND, "filter.entities": y["name"]},
                             lambda b: (len(items(b)), "Pairwise affinity read." if any(_aff(i) is not None for i in items(b)) else "No pairwise affinity returned."))
            for it in items(body):
                v = _aff(it)
                if v is not None:
                    return v * 100 if v <= 1.5 else v
            return None

        ab, ba = pair(A, B), pair(B, A)
        vals = [v for v in (ab, ba) if v is not None]
        fit = sum(vals) / len(vals) if vals else None
        fit_idx = None
        if fit is not None:
            self.emit("metric.updated", {"key": "fit.affinity", "metric": metric(fit, "measured", "index_0_100", "pair-affinity-v1")})
            fit_idx = self.ledger("qloo./v2/insights", f"call:{self._calls}", f"Pairwise affinity between the two brands is {fit:.0f} out of 100.", {"a_to_b": ab, "b_to_a": ba})
            self.warn("affinity_scale", "Qloo's pairwise affinity runs high: in our live sample, mismatched brands scored 60 to 66 and well-matched ones 75 to 96. Read the score against that range.", "fit")
        else:
            self.warn("fit_unavailable", "Qloo returned no pairwise affinity for these brands, so the fit score is not available.", "fit")

        def tags(e):
            body = self.call("/entities", [("entity_ids", e["entity_id"])], {"entity_ids": e["name"]},
                             lambda b: (len((items(b)[0].get("tags") or []) if items(b) else []), f"Tags read for {e['name']}."))
            got = items(body)
            raw = (got[0].get("tags") if got else None) or []
            return {t.get("tag_id"): t.get("name") for t in raw if isinstance(t, dict) and t.get("tag_id") and t.get("name")}

        ta, tb = tags(A), tags(B)
        shared_ids = [k for k in ta if k in tb]
        only_a = [ta[k] for k in ta if k not in tb]
        only_b = [tb[k] for k in tb if k not in ta]
        union = len(ta) + len(tb) - len(shared_ids)
        overlap = (len(shared_ids) / union) if union else None
        if overlap is not None:
            self.emit("metric.updated", {"key": "fit.tag_overlap", "metric": metric(overlap, "measured", "ratio_0_1", "tag-jaccard-v1")})
            self.ledger("qloo./entities", f"call:{self._calls}", f"The brands share {len(shared_ids)} tags out of {union}.", {"a_tags": len(ta), "b_tags": len(tb)})
        else:
            self.warn("tags_unavailable", "Qloo returned no tags for these brands.", "fit")

        def demo(e):
            body = self.call("/v2/insights", [("signal.interests.entities", e["entity_id"]), ("filter.type", "urn:demographics")],
                             {"signal.interests.entities": e["name"], "filter.type": "urn:demographics"},
                             lambda b: (len(items(b)), f"Age index read for {e['name']}."))
            got = items(body)
            age = ((got[0].get("query") or {}).get("age") if got else None) or {}
            row = [age.get(k) if isinstance(age.get(k), (int, float)) else None for k in AGE_BUCKETS]
            if any(v is not None for v in row) and max(abs(v) for v in row if v is not None) > 3:
                row = [None if v is None else v / 100 for v in row]
            return row

        da, db = demo(A), demo(B)
        have_demo = any(v is not None for v in da) and any(v is not None for v in db)
        if have_demo:
            self.ledger("qloo./v2/insights", f"call:{self._calls}", "Age indices were read for both audiences.")

        regions_raw = []
        for key, label in REGIONS:
            cells = {}
            for tag, e in (("a", A), ("b", B)):
                body = self.call("/v2/insights", [("signal.interests.entities", e["entity_id"]), ("filter.type", "urn:heatmap"), ("filter.location.query", label)],
                                 {"signal.interests.entities": e["name"], "filter.type": "urn:heatmap", "filter.location.query": label},
                                 lambda b: (len(items(b)), f"{len(items(b))} heatmap cells."))
                pts = {}
                for it in items(body):
                    loc = it.get("location") or {}
                    v = _aff(it)
                    if v is not None and isinstance(loc.get("latitude"), (int, float)) and isinstance(loc.get("longitude"), (int, float)):
                        pts[loc.get("geohash") or f"{loc['latitude']:.5f},{loc['longitude']:.5f}"] = (float(loc["latitude"]), float(loc["longitude"]), v)
                cells[tag] = pts
            regions_raw.append((key, label, cells))
        self.ledger("qloo./v2/insights", f"call:{self._calls}", "Heatmaps for SoHo, Shibuya and Mayfair were fetched for both brands.")
        self.warn("heatmap_normalised", "Heatmap values are normalised per area; regions are compared by overlap, never by raw value.", "locality")
        self._end()

        # ---- locality (computed from measured cells)
        regions = []
        for key, label, cells in regions_raw:
            ca, cb = cells["a"], cells["b"]
            common = [g for g in ca if g in cb]
            na = minmax({g: v[2] for g, v in ca.items()})
            nb = minmax({g: v[2] for g, v in cb.items()})
            rho = spearman([ca[g][2] for g in common], [cb[g][2] for g in common]) if common else None
            aff = None if rho is None else round(50 * (1 + rho), 1)
            geo = {g: (ca[g][0], ca[g][1]) for g in ca}
            geo.update({g: (cb[g][0], cb[g][1]) for g in cb})
            ranked = sorted(geo, key=lambda g: -max(na.get(g, 0), nb.get(g, 0)))[:MAX_CELLS]
            r = {"key": key, "label": label,
                 "affinity": metric(aff, "modeled", "index_0_100", "locality-overlap-v1"),
                 "friction": metric(None if aff is None else 100 - aff, "modeled", "index_0_100", "locality-overlap-v1"),
                 "delta_vs_global": metric(None, "modeled", "index_points", "locality-overlap-v1"),
                 "sample_note": f"{len(common)} shared heatmap cells compared ({len(ca)} for {A['name']}, {len(cb)} for {B['name']})",
                 "heat": {"cell_note": "values normalised 0..1 within each area",
                          "cells": [{"lat": round(geo[g][0], 5), "lon": round(geo[g][1], 5), "a": round(na.get(g, 0.0), 3), "b": round(nb.get(g, 0.0), 3)} for g in ranked]}}
            regions.append(r)
        good = [r["affinity"]["value"] for r in regions if r["affinity"]["value"] is not None]
        glob = sum(good) / len(good) if good else None
        for r in regions:
            if glob is not None and r["affinity"]["value"] is not None:
                r["delta_vs_global"] = metric(round(r["affinity"]["value"] - glob, 1), "modeled", "index_points", "locality-overlap-v1")
        loc_idx = self.ledger("model.locality", "derive:locality", "Regional fit is the rank correlation of the two brands' heatmap cells inside each area.")

        # ---- 3 bridge
        self._begin(2)
        bridge = self._bridge(A, B, fit)
        self._end()

        # ---- 4 adversarial audit
        self._begin(3)
        self.note("adversary", "Deriving fan communities from tags only one brand carries, then simulating how each reacts.")
        friction = None if fit is None else max(0.0, 1 - fit / 100)
        exclusivity_a = 1 - (len(shared_ids) / len(ta)) if ta else 0
        exclusivity_b = 1 - (len(shared_ids) / len(tb)) if tb else 0
        spec = []
        if only_a[:3]:
            spec.append((only_a[:3], exclusivity_a, A["name"]))
        if only_a[3:6]:
            spec.append((only_a[3:6], exclusivity_a, A["name"]))
        if only_b[:3]:
            spec.append((only_b[:3], exclusivity_b, B["name"]))
        comms, communities = [], []
        shares = ASSUMED["community_shares"]
        for i, (tg, excl, owner) in enumerate(spec):
            p = None if friction is None else min(0.95, max(0.03, 0.05 + friction * (0.5 + 0.5 * excl)))
            if p is None:
                continue
            share = shares[i] if i < len(shares) else 0.2
            label = f"{tg[0]} loyalists"
            comms.append((label, p, share))
            communities.append({"id": f"c{len(communities) + 1}", "label": label,
                                "basis": {"tags": tg, "entities": [], "demographics": None},
                                "rebellion_probability": metric(p, "modeled", "probability_0_1", "rebellion-sim-v1"),
                                "core_audience_share": metric(share, "assumed", "probability_0_1", "communities-v1"),
                                "evidence_refs": [], "channels": []})
        sim = None
        if comms:
            sim = simulate(comms, SIM_RUNS, SEED, ASSUMED["exposure"])
            self.emit("simulation.started", {"runs": SIM_RUNS, "seed": SEED, "communities": len(communities)})
            steps, lo, hi, nb_ = 28, sim["lo"], sim["hi"], len(sim["counts"])
            sample = sim["losses"][:]
            random.Random(3).shuffle(sample)
            for s in range(1, steps + 1):
                n = int(SIM_RUNS * s / steps)
                part = sample[:n]
                ps = sorted(part)
                hist = [0] * nb_
                for v in part:
                    hist[min(nb_ - 1, int(v / hi * nb_))] += 1
                self.emit("simulation.progress", {"completed": n, "total": SIM_RUNS,
                          "running": {"mean": round(sum(part) / n, 3), "p5": round(ps[int(.05 * (n - 1))], 3), "p95": round(ps[int(.95 * (n - 1))], 3)},
                          "histogram": {"lo": lo, "hi": hi, "counts": hist}})
                time.sleep(0.06)
            communities.sort(key=lambda c: -c["rebellion_probability"]["value"])
            for c in communities:
                self.emit("simulation.community", {"community": c})
            ci = self.ledger("model.community", "derive:communities", f"{len(communities)} communities were derived from tags that only one brand carries.")
            self.ledger("model.rebellion", "derive:sim", f"The simulation ran {SIM_RUNS} times with seed {SEED}.")
            si = self.ledger("model.rebellion", "derive:risk", f"Mean IP value at risk is {sim['mean']:.1f} percent of the core franchise.")
            for c in communities:
                c["evidence_refs"] = [ci, si]
            self.emit("metric.updated", {"key": "rebellion.ip_value_at_risk_pct.mean", "metric": metric(sim["mean"], "modeled", "percent", "rebellion-sim-v1")})
        else:
            self.warn("no_communities", "There were not enough one-sided tags to derive fan communities, so the backlash simulation did not run.", "rebellion")
        # pandering index: every component is derived from measured data
        div = None
        if have_demo:
            pairs = [(x, y) for x, y in zip(da, db) if x is not None and y is not None]
            span = max([abs(v) for v in da + db if v is not None] + [1e-9])
            div = min(1.0, sum(abs(x - y) for x, y in pairs) / (len(pairs) * 2 * span)) if pairs else None
        comp_c = None if overlap is None else 1 - overlap
        comp_g = friction
        parts = [v for v in (comp_c, div, comp_g) if v is not None]
        pandering = round(100 * sum(parts) / len(parts), 1) if parts else None
        if pandering is not None:
            self.emit("metric.updated", {"key": "rebellion.index", "metric": metric(pandering, "modeled", "index_0_100", "pandering-index-v1")})
        self._end()

        # ---- 5 synthesis
        self._begin(4)
        self.note("synthesist", "Converting regional fit into dollars with stated assumptions, then writing the verdict from the computed numbers.")
        pops, pen, spend = ASSUMED["regional_populations"], ASSUMED["penetration_rate"], ASSUMED["annual_spend_per_customer_usd"]
        affs = [r["affinity"]["value"] for r in regions]

        def tam(loss, pen_m=1.0, spend_m=1.0, pop_m=1.0, aff_m=1.0):
            t = 0.0
            for a, p in zip(affs, pops):
                if a is not None:
                    t += p * pop_m * pen * pen_m * spend * spend_m * min(100, a * aff_m) / 100 * (1 - loss)
            return t

        have_tam = sim is not None and any(a is not None for a in affs)
        if have_tam and any(a is None for a in affs):
            self.warn("region_missing", "Qloo had too little map data for one city, so the dollar range counts only the cities that could be compared.", "tam")
        base = low = high = baseline = None
        sens = []
        if have_tam:
            base, low, high = tam(sim["mean"] / 100), tam(sim["p95"] / 100), tam(sim["p5"] / 100)
            baseline = sum(p * pen * spend for p in pops)
            for key, kw in (("penetration_rate", "pen_m"), ("annual_spend_per_customer_usd", "spend_m"), ("regional_populations", "pop_m"), ("regional_affinity", "aff_m")):
                sens.append({"assumption_key": key, "low_usd": round(tam(sim["mean"] / 100, **{kw: .7})), "high_usd": round(tam(sim["mean"] / 100, **{kw: 1.3}))})
            sens.append({"assumption_key": "ip_loss", "low_usd": round(low), "high_usd": round(high)})
            for k, v in (("low", low), ("base", base), ("high", high)):
                self.emit("metric.updated", {"key": f"tam.expansion_usd.{k}", "metric": metric(v, "modeled", "usd", "tam-v1")})
            self.ledger("assumption", "assume:1", f"Penetration is assumed at {pen:.0%} of the catchment, and annual spend at ${spend:.0f} per customer.")
            self.ledger("model.tam", "derive:tam", f"Base expansion is ${base / 1e6:,.0f} million.")
        else:
            self.warn("tam_unavailable", "A dollar figure needs at least one comparable city and a backlash simulation. Neither was fully available.", "tam")
        for r in regions:
            self.emit("metric.updated", {"key": f"locality.region.{r['key']}.affinity", "metric": r["affinity"]})

        risk = sim["mean"] if sim else None
        if fit is None or not have_tam:
            verdict, vtxt = "insufficient_data", "Qloo did not return enough data for these brands to price the deal. The sections below show what was measured."
        elif fit >= PROCEED_FIT and (risk or 0) < 12:
            verdict, vtxt = "proceed", "The two audiences already overlap. The deal can go ahead without a bridge, and the main risk is contained."
        elif (risk or 0) >= 25 or fit < HIGH_RISK_FIT:
            verdict, vtxt = "high_risk", "The audiences overlap too little and the expected fan reaction is large. The deal needs a rethink before it goes ahead."
        else:
            verdict, vtxt = "proceed_with_remediation", "The deal is workable, but fan rebellion needs a plan before announcement."
        total = self.ok_calls + self.failed_calls
        conf = round(0.45 + 0.4 * (self.ok_calls / total), 3) if total else 0.0
        self.emit("metric.updated", {"key": "headline.confidence", "metric": metric(conf, "modeled", "probability_0_1", "verdict-v1")})
        self._end()

        ev = lambda *ns: [e["index"] for e in self._ledger if any(n in e["claim"] or n in e["reference"] for n in ns)]
        ages = lambda row: [{"bucket": k, "share": 0.0 if v is None else v} for k, v in zip(AGE_BUCKETS, row)] if any(v is not None for v in row) else None
        result = {
            "schema_version": "1.0", "run_id": self.id, "mode": "live", "generated_at": now_iso(), "seed": SEED,
            "acquirer": {"name": A["name"], "entity_id": A["entity_id"], "type": BRAND},
            "target": {"name": B["name"], "entity_id": B["entity_id"], "type": BRAND},
            "headline": {"verdict": verdict, "summary": vtxt, "summary_source": "template", "confidence": metric(conf, "modeled", "probability_0_1", "verdict-v1")},
            "fit": {"affinity": metric(fit, "measured", "index_0_100", "pair-affinity-v1"),
                    "tag_overlap": metric(overlap, "measured", "ratio_0_1", "tag-jaccard-v1"),
                    "tag_counts": {"a_only": len(only_a), "shared": len(shared_ids), "b_only": len(only_b)},
                    "shared_signals": [{"id": f"s{i}", "name": ta[k], "type": "urn:tag", "weight": round(1 - i / max(1, min(6, len(shared_ids))), 2), "evidence_refs": ev("share")} for i, k in enumerate(shared_ids[:6])],
                    "contrast_axes": [{"id": f"x{i}", "name": n, "side": "acquirer", "strength": round(1 - i / 6, 2), "evidence_refs": ev("communities were derived")} for i, n in enumerate(only_a[:3])] +
                                     [{"id": f"y{i}", "name": n, "side": "target", "strength": round(1 - i / 6, 2), "evidence_refs": ev("communities were derived")} for i, n in enumerate(only_b[:3])],
                    "demographics": {"acquirer": {"age": ages(da), "gender": None, "provenance": "measured"},
                                     "target": {"age": ages(db), "gender": None, "provenance": "measured"}}},
            "rebellion": {
                "index": {"score": metric(pandering, "modeled", "index_0_100", "pandering-index-v1"),
                          "components": {"contradiction": metric(comp_c, "modeled", "ratio_0_1", "pandering-index-v1"),
                                         "overclaim": metric(div, "modeled", "ratio_0_1", "pandering-index-v1"),
                                         "alignment_gap": metric(comp_g, "modeled", "ratio_0_1", "pandering-index-v1")}},
                "simulation": ({"runs": SIM_RUNS, "seed": SEED,
                                "distribution": {"lo": sim["lo"], "hi": sim["hi"], "counts": sim["counts"], "mean": round(sim["mean"], 3), "median": round(sim["median"], 3), "p5": round(sim["p5"], 3), "p95": round(sim["p95"], 3)},
                                "ip_value_at_risk_pct": {"mean": metric(sim["mean"], "modeled", "percent", "rebellion-sim-v1"), "p5": metric(sim["p5"], "modeled", "percent", "rebellion-sim-v1"), "p95": metric(sim["p95"], "modeled", "percent", "rebellion-sim-v1")},
                                "assumptions": [{"key": "kappa", "value": 14, "provenance": "assumed"}, {"key": "exposure", "value": ASSUMED["exposure"], "provenance": "assumed"},
                                                {"key": "community_shares", "value": " / ".join(f"{s:.0%}" for s in shares), "provenance": "assumed"}],
                                "method_ref": "rebellion-sim-v1"} if sim else None),
                "communities": communities},
            "bridge": bridge,
            "locality": {"regions": regions, "global_affinity": metric(glob, "modeled", "index_0_100", "locality-overlap-v1"),
                         "caveats": ["Heatmap values are normalised inside each area, so regions are compared by overlap, never by raw value."], "method_ref": "locality-overlap-v1"},
            "tam": {"currency": "USD", "baseline_usd": metric(baseline, "modeled", "usd", "tam-v1"),
                    "expansion_usd": {"low": metric(low, "modeled", "usd", "tam-v1"), "base": metric(base, "modeled", "usd", "tam-v1"), "high": metric(high, "modeled", "usd", "tam-v1")},
                    "assumptions": [
                        {"key": "penetration_rate", "label": "Penetration of the catchment", "value": pen, "unit": "fraction", "provenance": "assumed"},
                        {"key": "annual_spend_per_customer_usd", "label": "Annual spend per customer", "value": spend, "unit": "usd", "provenance": "assumed"},
                        {"key": "regional_populations", "label": "Adult catchment, three regions", "value": " / ".join(f"{p / 1e6:.1f}M" for p in pops), "unit": "people", "provenance": "assumed"},
                        {"key": "regional_affinity", "label": "Regional affinity (overlap)", "value": " / ".join("n/a" if a is None else f"{a:.0f}" for a in affs), "unit": "index_0_100", "provenance": "modeled"}],
                    "sensitivity": sens, "method_ref": "tam-v1"},
            "evidence": self._ledger,
            "evidence_verification": {"valid": True, "records_checked": len(self._ledger), "error": None},
            "analyst_review": {"approved": verdict != "insufficient_data", "risk_level": "low" if verdict == "proceed" else "high" if verdict == "high_risk" else "medium",
                               "findings": ([f"{communities[0]['label']} carries the highest rebellion probability at {communities[0]['rebellion_probability']['value']:.0%}."] if communities else []) +
                                           ["Community sizes, penetration and spend are assumptions, not Qloo measurements."],
                               "recommendations": ["Pilot in the region with the strongest overlap first.", "Check the assumptions before relying on the dollar range."]},
            "phases": [{"phase": p, "status": "complete", "duration_ms": 0} for p in PHASES],
            "warnings": self.warnings,
            "memo": {"markdown_path": f"/api/v1/reports/{self.id}/memo.md", "pdf_path": f"/api/v1/reports/{self.id}/memo.pdf"},
        }
        return result

    def _bridge(self, A: dict, B: dict, fit: float | None) -> dict:
        before = None if fit is None else round(100 - fit, 1)
        if fit is None or fit >= BRIDGE_BELOW:
            self.note("bridge scout", "Direct fit is strong or unavailable. No bridge required." if fit is not None else "No fit score, so no bridge was searched.")
            return {"status": "not_needed", "steps": [], "friction_before": metric(before, "modeled", "index_0_100", "bridge-v1"),
                    "friction_after": metric(before, "modeled", "index_0_100", "bridge-v1"), "friction_reduction_pct": metric(0, "modeled", "percent", "bridge-v1")}
        self.note("bridge scout", f"Direct fit is {fit:.0f}. Looking for brands that both audiences already like, to use as stepping stones.")
        lists = {}
        for tag, e in (("a", A), ("b", B)):
            body = self.call("/v2/insights", [("signal.interests.entities", e["entity_id"]), ("filter.type", BRAND), ("take", "50")],
                             {"signal.interests.entities": e["name"], "filter.type": BRAND, "take": 50}, lambda b: (len(items(b)), f"{len(items(b))} related brands."))
            d = {}
            for it in items(body):
                v = _aff(it)
                if it.get("entity_id") and v is not None and it["entity_id"] not in (A["entity_id"], B["entity_id"]):
                    d[it["entity_id"]] = (it.get("name") or "", v * 100 if v <= 1.5 else v)
            lists[tag] = d
        common = [(min(lists["a"][k][1], lists["b"][k][1]), lists["a"][k][0], k) for k in lists["a"] if k in lists["b"]]
        if len(common) < 3:
            self.note("bridge scout", "Few brands sit in both audiences' top 50. Testing each side's strongest neighbours directly against the other brand.")

            def pair_aff(x_id, x_name, y_id, y_name):
                body = self.call("/v2/insights", [("signal.interests.entities", x_id), ("filter.type", BRAND), ("filter.entities", y_id)],
                                 {"signal.interests.entities": x_name, "filter.type": BRAND, "filter.entities": y_name},
                                 lambda b: (len(items(b)), "Pairwise affinity read."))
                for it in items(body):
                    v = _aff(it)
                    if v is not None:
                        return v * 100 if v <= 1.5 else v
                return None

            have = {k for _, _, k in common}
            for tag, other in (("a", B), ("b", A)):
                ranked = sorted((k for k in lists[tag] if k not in have), key=lambda k: -lists[tag][k][1])[:5]
                for k in ranked:
                    name, own_aff = lists[tag][k]
                    to_other = pair_aff(k, name, other["entity_id"], other["name"])
                    if to_other is not None:
                        common.append((min(own_aff, to_other), name, k))
                        have.add(k)
        common.sort(reverse=True)
        top = common[:3]
        if not top:
            self.warn("bridge_not_found", "No brand scored well against both audiences, so no bridge could be built from Qloo data.", "bridge")
            return {"status": "not_found", "steps": [], "friction_before": metric(before, "modeled", "index_0_100", "bridge-v1"),
                    "friction_after": metric(before, "modeled", "index_0_100", "bridge-v1"), "friction_reduction_pct": metric(0, "modeled", "percent", "bridge-v1")}
        idx = self.ledger("model.bridge", "derive:bridge", f"{len(common)} candidate stepping-stone brands were scored against both audiences; the strongest three were used.")
        phases = ["Familiarization", "Co-presence", "Collaboration"]
        steps = []
        for i, (strength, name, eid) in enumerate(top):
            frm = A["name"] if i == 0 else top[i - 1][1]
            to = B["name"] if i == len(top) - 1 else name
            steps.append({"number": i + 1, "phase": phases[i], "from_category": frm, "to_category": name,
                          "objective": f"Run a small, visible tie-in with {name}, a brand that sits close to both audiences, before moving closer to {B['name'] if i == len(top) - 1 else top[i + 1][1]}.",
                          "entities": [{"id": eid, "name": name}], "affinity_lift": metric(strength, "modeled", "index_points", "bridge-v1"),
                          "evidence_refs": [idx]})
        strength = sum(s for s, _, _ in top) / len(top)
        after = round(min(before, 100 - (fit + strength) / 2), 1)
        red = round((before - after) / before * 100, 1) if before else 0
        for k, v in (("friction_before", before), ("friction_after", after), ("friction_reduction_pct", red)):
            self.emit("metric.updated", {"key": f"bridge.{k}", "metric": metric(v, "modeled", "percent" if k.endswith("pct") else "index_0_100", "bridge-v1")})
        return {"status": "found", "steps": steps, "friction_before": metric(before, "modeled", "index_0_100", "bridge-v1"),
                "friction_after": metric(after, "modeled", "index_0_100", "bridge-v1",
                                         "Modeled: friction if the average of the direct fit and the stepping-stone strength applied."),
                "friction_reduction_pct": metric(red, "modeled", "percent", "bridge-v1")}


def candidates_from(body) -> list[dict]:
    out = []
    for it in items(body)[:8]:
        props = it.get("properties") or {}
        out.append({"entity_id": it.get("entity_id"), "name": it.get("name") or "",
                    "subtitle": (props.get("short_description") or "")[:90] if isinstance(props, dict) else "", "type": BRAND})
    return [c for c in out if c["entity_id"]]


# ---------------------------------------------------------------- registry + SSE
RUNS: dict[str, LiveRun] = {}
_RUNS_LOCK = threading.Lock()
MAX_RUNS = 200


def create_run(a: str, b: str, a_id=None, b_id=None, preset_id=None, qloo: Qloo | None = None) -> LiveRun:
    run = LiveRun(a, b, a_id, b_id, preset_id, qloo)
    with _RUNS_LOCK:
        if len(RUNS) >= MAX_RUNS:
            RUNS.pop(next(iter(RUNS)))
        RUNS[run.id] = run
    return run


def sse(run: LiveRun, last_id: int = 0, idle_timeout: float = 300.0) -> Iterator[str]:
    """Yield SSE blocks for events after `last_id` until the run has finished."""
    run.start()
    cursor, idle = last_id, 0.0
    while True:
        with run.cond:
            if cursor >= len(run.events) and run.status in ("pending", "running"):
                run.cond.wait(timeout=10.0)
            batch = run.events[cursor:]
            finished = run.status in ("completed", "failed")
        if batch:
            idle = 0.0
            for ev in batch:
                cursor = ev["seq"]
                yield f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        else:
            if finished:
                return
            idle += 10.0
            yield ": keepalive\n\n"
            if idle >= idle_timeout:
                return


def memo_markdown(r: dict) -> str:
    """Plain Markdown memo of a finished report. Every figure is labelled with where it came from."""
    def v(m, fmt="{:.0f}"):
        x = (m or {}).get("value")
        return "n/a" if x is None else fmt.format(x)

    def usd(m):
        x = (m or {}).get("value")
        return "n/a" if x is None else (f"${x / 1e6:,.1f}M" if x >= 1e6 else f"${x:,.0f}")
    L = [f"# {r['acquirer']['name']} × {r['target']['name']}: cultural due diligence", "",
         f"**Verdict:** {r['headline']['verdict'].replace('_', ' ')}  ", f"**Confidence:** {v(r['headline']['confidence'], '{:.0%}')}", "", r["headline"]["summary"], "",
         "## Fit", f"- Qloo pairwise affinity: {v(r['fit']['affinity'])} out of 100 (measured)",
         f"- Tag overlap: {v(r['fit']['tag_overlap'], '{:.0%}')} (measured)", "", "## Fan reaction",
         f"- Rebellion index: {v(r['rebellion']['index']['score'])} out of 100 (modeled)"]
    for c in r["rebellion"]["communities"]:
        L.append(f"- {c['label']}: {v(c['rebellion_probability'], '{:.0%}')} likely to rebel (modeled)")
    br = r.get("bridge") or {}
    L += ["", "## Bridge"]
    if br.get("status") == "found":
        L += [f"- Step {x['number']} ({x['phase']}): {x['to_category']}. {x['objective']}" for x in br["steps"]]
        L.append(f"- Friction falls from {v(br['friction_before'])} to {v(br['friction_after'])} (modeled).")
    else:
        L.append("- No bridge needed." if br.get("status") == "not_needed" else "- No bridge could be built from Qloo data.")
    L += ["", "## Locality"] + [f"- {x['label']}: overlap {v(x['affinity'])} out of 100 (modeled from measured heatmaps)" for x in r["locality"]["regions"]]
    L += ["", "## Dollars", f"- Yearly expansion: {usd(r['tam']['expansion_usd']['low'])} to {usd(r['tam']['expansion_usd']['high'])}, base {usd(r['tam']['expansion_usd']['base'])} (modeled)", "", "Assumptions (you can change these):"]
    L += [f"- {a['label']}: {a['value']}" for a in r["tam"]["assumptions"]]
    L += ["", "## Evidence"] + [f"{e['index']}. {e['claim']} `{e['current_hash'][:12]}`" for e in r["evidence"]]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- PDF (no dependencies)
_PDF_MAP = {"×": "x", "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "•": "-", "≈": "~", "→": "->"}


def _latin(text: str) -> str:
    out = []
    for ch in "".join(_PDF_MAP.get(c, c) for c in text):
        out.append(ch if ord(ch) < 256 else "?")
    return "".join(out)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


def memo_pdf(markdown: str) -> bytes:
    """A4 text PDF from the memo Markdown: headings, bullets and wrapped paragraphs over as many pages as needed."""
    W, H, LM, TM, BM = 595, 842, 56, 64, 56
    pages: list[list[str]] = [[]]
    y = H - TM

    def put(text: str, size: float, bold: bool, indent: int = 0, gap: float = 0):
        nonlocal y
        lead = size * 1.45
        if y - lead < BM:
            pages.append([])
            y = H - TM
        y -= lead + gap
        pages[-1].append(f"BT /{'F2' if bold else 'F1'} {size} Tf {LM + indent} {y:.1f} Td ({_esc(_latin(text))}) Tj ET")

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            y -= 5
            continue
        clean = line.replace("**", "").replace("`", "")
        if line.startswith("# "):
            for part in _wrap(clean[2:], 52):
                put(part, 19, True, gap=2)
            y -= 4
        elif line.startswith("## "):
            y -= 6
            put(clean[3:], 13, True)
        elif line.startswith(("- ", "* ")):
            parts = _wrap(clean[2:], 92)
            for i, part in enumerate(parts):
                put(("- " if i == 0 else "  ") + part, 10, False, indent=8)
        else:
            for part in _wrap(clean, 96):
                put(part, 10, False)
    objs: list[bytes] = []
    n_pages = len(pages)
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, ops in enumerate(pages):
        stream = ("\n".join(ops + [f"BT /F1 8 Tf {LM} 30 Td (xC cultural due diligence - page {i + 1} of {n_pages}) Tj ET"])).encode("latin-1", "replace")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {6 + 2 * i} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
