#!/usr/bin/env python3
"""xC full Qloo probe: bounded, stdlib-only, key from the environment only.

Answers the open questions the pillars depend on (type format, array style,
silent-ignore behaviour, take cap, location filtering, heatmap, demographics,
explainability, trends, tags, trending, entities, pair-affinity forms).

Safety:
  * The key is read from QLOO_API_KEY, sent only as the X-Api-Key header, and is
    never printed, logged or written.
  * Raw responses go to .qloo-probe/full-<timestamp>/raw/ (git-ignored). Do NOT
    commit or paste them.
  * The console prints SHAPES and COUNTS only (key names, types, item counts,
    overlaps), never response values.
  * Hard call cap: --budget (default 40). Pacing between calls: --pace seconds.

Usage:
  python scripts/qloo_probe_full.py --dry-run          # list planned calls, no network
  python scripts/qloo_probe_full.py --budget 40
Optional: QLOO_API_HOST (default https://hackathon.api.qloo.com).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = os.environ.get("QLOO_API_HOST", "https://hackathon.api.qloo.com").rstrip("/")
ROOT = Path(__file__).resolve().parent.parent
BRAND = "urn:entity:brand"


# ----------------------------------------------------------------- shapes ---
def items_of(body):
    """Return (container_keys, items): items found anywhere under `results`."""
    if not isinstance(body, dict):
        return [], []
    res = body.get("results")
    if isinstance(res, list):
        return ["<list>"], [x for x in res if isinstance(x, dict)]
    if isinstance(res, dict):
        out = []
        for v in res.values():
            if isinstance(v, list):
                out.extend(x for x in v if isinstance(x, dict))
        return list(res.keys()), out
    return [], []


def ident(it):
    if isinstance(it.get("entity"), dict):
        it = it["entity"]
    return str(it.get("entity_id") or it.get("id") or it.get("name") or json.dumps(it, sort_keys=True)[:60])


def describe(body):
    if not isinstance(body, dict):
        return "non-object"
    keys, items = items_of(body)
    item_keys = sorted(items[0].keys())[:12] if items else []
    return f"top={sorted(body.keys())[:8]} results_keys={keys[:8]} n={len(items)} item_keys={item_keys}"


# ------------------------------------------------------------------ client ---
class Probe:
    def __init__(self, key, budget, pace, outdir):
        self.key, self.budget, self.pace, self.used = key, budget, pace, 0
        self.raw = outdir / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.rows = []
        self.cache = {}

    def get(self, label, path, params):
        if self.used >= self.budget:
            self.rows.append({"label": label, "status": None, "note": "skipped: budget"})
            return None
        self.used += 1
        qs = urllib.parse.urlencode(params, safe=",:")
        url = f"{BASE}{path}" + (f"?{qs}" if qs else "")
        req = urllib.request.Request(url, headers={"X-Api-Key": self.key, "Accept": "application/json"})
        status, body, retry_after, t0 = None, None, None, time.time()
        for attempt in (0, 1):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    status, body = r.status, json.loads(r.read().decode("utf-8", "replace") or "null")
                break
            except urllib.error.HTTPError as e:
                status = e.code
                retry_after = e.headers.get("Retry-After")
                try:
                    body = json.loads(e.read().decode("utf-8", "replace"))
                except Exception:
                    body = None
                if status == 429 and attempt == 0 and retry_after and retry_after.isdigit() and int(retry_after) <= 10:
                    time.sleep(int(retry_after))
                    continue
                break
            except Exception as e:  # network/JSON failure: record the type only
                status, body = None, {"_error": type(e).__name__}
                break
        ms = int((time.time() - t0) * 1000)
        n = len(self.rows)
        (self.raw / f"{n:02d}-{label}.json").write_text(
            json.dumps({"request": {"path": path, "params": params}, "status": status, "body": body}, indent=2),
            encoding="utf-8")
        keys, items = items_of(body)
        row = {"label": label, "path": path, "params": params, "status": status, "ms": ms,
               "shape": describe(body), "n": len(items), "ids": [ident(i) for i in items], "retry_after": retry_after}
        self.rows.append(row)
        time.sleep(self.pace)
        return row


def compare(a, b):
    """Verdict comparing result id lists of row b against baseline a."""
    if not a or not b or a.get("status") != 200 or b.get("status") != 200:
        return "error" if b and b.get("status") not in (200, None) else "n/a"
    if b["n"] == 0:
        return "empty"
    return "same_as_baseline" if a["ids"] == b["ids"] else "differs_from_baseline"


# ------------------------------------------------------------- experiments ---
def plan(p, entity_names):
    """Run the experiments in order. Returns list of (question, verdict-text)."""
    R = {}
    out = []

    def run(label, path, params):
        R[label] = p.get(label, path, params)
        return R[label]

    def first_id(row):
        return row["ids"][0] if row and row["ids"] else None

    # 1. search forms
    run("search_urn", "/search", [("query", entity_names[0]), ("types", BRAND)])
    run("search_plain", "/search", [("query", entity_names[0]), ("types", "brand")])
    run("search_none", "/search", [("query", entity_names[0])])
    out.append(("S1 search: types=urn vs plain vs none (result counts)",
                f"urn={R['search_urn']['n'] if R['search_urn'] else '-'} "
                f"plain={R['search_plain']['n'] if R['search_plain'] else '-'} "
                f"none={R['search_none']['n'] if R['search_none'] else '-'}"))
    A = first_id(R["search_urn"]) or first_id(R["search_none"])
    run("search_b", "/search", [("query", entity_names[1]), ("types", BRAND)])
    B = first_id(R["search_b"])
    out.append(("S2 two brands resolved to ids", f"A={'yes' if A else 'NO'} B={'yes' if B else 'NO'}"))
    if not A:
        return out

    base = [("signal.interests.entities", A), ("filter.type", BRAND), ("take", "10")]
    run("ins_base", "/v2/insights", base)
    run("ins_plain_type", "/v2/insights", [("signal.interests.entities", A), ("filter.type", "brand"), ("take", "10")])
    out.append(("I1 filter.type urn vs plain", f"plain vs urn: {compare(R['ins_base'], R['ins_plain_type'])}"))
    run("ins_tags", "/v2/insights", [("signal.interests.entities", A), ("filter.type", "urn:tag"), ("take", "10")])
    out.append(("I2 tag insights shape", R["ins_tags"]["shape"] if R["ins_tags"] else "-"))

    if B:
        run("arr_comma", "/v2/insights", [("signal.interests.entities", f"{A},{B}"), ("filter.type", BRAND), ("take", "10")])
        run("arr_repeat", "/v2/insights", [("signal.interests.entities", A), ("signal.interests.entities", B),
                                           ("filter.type", BRAND), ("take", "10")])
        out.append(("A1 array style: comma vs single-id baseline", compare(R["ins_base"], R["arr_comma"])))
        out.append(("A2 array style: repeated vs single-id baseline", compare(R["ins_base"], R["arr_repeat"])))
        out.append(("A3 comma vs repeated give same ids?",
                    "same" if R["arr_comma"] and R["arr_repeat"] and R["arr_comma"]["ids"] == R["arr_repeat"]["ids"] else "different"))
        run("pair_filter_entities", "/v2/insights", base + [("filter.entities", B)])
        run("pair_filter_entity_ids", "/v2/insights", base + [("filter.entity_ids", B)])
        out.append(("P1 pair form filter.entities (exploratory)", compare(R["ins_base"], R["pair_filter_entities"])))
        out.append(("P2 pair form filter.entity_ids (exploratory)", compare(R["ins_base"], R["pair_filter_entity_ids"])))

    run("bogus", "/v2/insights", base + [("filter.zz_bogus", "1")])
    out.append(("Q1 unknown param silently ignored?", f"status={R['bogus']['status'] if R['bogus'] else '-'} {compare(R['ins_base'], R['bogus'])}"))
    run("take50", "/v2/insights", [("signal.interests.entities", A), ("filter.type", BRAND), ("take", "50")])
    run("take60", "/v2/insights", [("signal.interests.entities", A), ("filter.type", BRAND), ("take", "60")])
    out.append(("Q2 take cap", f"take=50 -> n={R['take50']['n'] if R['take50'] else '-'}; take=60 -> "
                f"status={R['take60']['status'] if R['take60'] else '-'} n={R['take60']['n'] if R['take60'] else '-'}"))

    run("loc_query", "/v2/insights", base + [("filter.location.query", "Tokyo")])
    run("loc_signal", "/v2/insights", base + [("signal.location.query", "Tokyo")])
    out.append(("L1 brand + filter.location.query=Tokyo", compare(R["ins_base"], R["loc_query"])))
    out.append(("L2 brand + signal.location.query=Tokyo", compare(R["ins_base"], R["loc_signal"])))
    place = [("signal.interests.entities", A), ("filter.type", "urn:entity:place"), ("take", "10")]
    run("place_nolocation", "/v2/insights", place)
    run("place_tokyo", "/v2/insights", place + [("filter.location.query", "Tokyo")])
    out.append(("L3 place type + location differs from no-location?", compare(R["place_nolocation"], R["place_tokyo"])))

    run("heat_nolocation", "/v2/insights", [("signal.interests.entities", A), ("filter.type", "urn:heatmap"), ("take", "10")])
    run("heat_tokyo", "/v2/insights", [("signal.interests.entities", A), ("filter.type", "urn:heatmap"),
                                       ("filter.location.query", "Tokyo"), ("take", "10")])
    out.append(("H1 heatmap shape", R["heat_tokyo"]["shape"] if R["heat_tokyo"] else "-"))
    out.append(("H2 heatmap Tokyo vs no location", compare(R["heat_nolocation"], R["heat_tokyo"])))

    run("demographics", "/v2/insights", [("signal.interests.entities", A), ("filter.type", "urn:demographics")])
    out.append(("D1 demographics shape", R["demographics"]["shape"] if R["demographics"] else "-"))
    run("explain", "/v2/insights", base + [("feature.explainability", "true")])
    out.append(("E1 explainability adds item keys?",
                f"base={R['ins_base']['shape'].split('item_keys=')[-1] if R['ins_base'] else '-'} | "
                f"explain={R['explain']['shape'].split('item_keys=')[-1] if R['explain'] else '-'}"))
    run("trends", "/v2/insights", base + [("bias.trends", "high")])
    out.append(("T1 bias.trends=high changes ranking?", compare(R["ins_base"], R["trends"])))

    run("tags_endpoint", "/v2/tags", [("filter.query", "luxury"), ("take", "5")])
    out.append(("G1 /v2/tags?filter.query shape", R["tags_endpoint"]["shape"] if R["tags_endpoint"] else "-"))
    run("trending", "/v2/trending", [("filter.type", BRAND), ("take", "5")])
    out.append(("G2 /v2/trending shape", R["trending"]["shape"] if R["trending"] else "-"))
    run("entities", "/entities", [("entity_ids", A)])
    out.append(("G3 /entities?entity_ids shape", R["entities"]["shape"] if R["entities"] else "-"))
    return out


PLANNED = ["search x3 (urn/plain/none)", "search second brand", "insights baseline", "insights plain type",
           "insights tags", "array comma", "array repeat", "pair forms x2", "bogus param", "take 50 / 60",
           "location brand x2", "location place x2", "heatmap x2", "demographics", "explainability",
           "bias.trends", "/v2/tags", "/v2/trending", "/entities"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=int, default=40)
    ap.add_argument("--pace", type=float, default=0.4)
    ap.add_argument("--brand-a", default="Porsche")
    ap.add_argument("--brand-b", default="Aime Leon Dore")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.dry_run:
        print(f"host: {BASE}\nbudget cap: {a.budget} calls\nplanned groups:")
        for x in PLANNED:
            print("  -", x)
        return 0
    key = os.environ.get("QLOO_API_KEY", "").strip()
    if not key:
        print("QLOO_API_KEY is not set. Nothing was sent.", file=sys.stderr)
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = ROOT / ".qloo-probe" / f"full-{stamp}"
    p = Probe(key, a.budget, a.pace, outdir)
    findings = plan(p, [a.brand_a, a.brand_b])
    print(f"\nHost {BASE}  calls used {p.used}/{a.budget}\n")
    print("CALLS (label, http status, ms, item count)")
    for r in p.rows:
        print(f"  {r['label']:<24} status={r.get('status')} ms={r.get('ms', '-')} n={r.get('n', '-')} {r.get('note', '')}")
    print("\nFINDINGS")
    for q, v in findings:
        print(f"  {q}\n      -> {v}")
    (outdir / "summary.json").write_text(json.dumps(
        {"host": BASE, "calls_used": p.used,
         "calls": [{k: v for k, v in r.items() if k not in ("ids", "params")} for r in p.rows],
         "findings": findings}, indent=2), encoding="utf-8")
    print(f"\nSaved shapes-only summary and raw responses under {outdir.relative_to(ROOT)} (git-ignored). Do not commit or paste raw files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
