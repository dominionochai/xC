#!/usr/bin/env python3
"""Run the live xC audit from the terminal against the real Qloo API. No website, no FastAPI.

It runs the same pipeline the app runs (backend/live.py) for several brand pairs, prints the
Qloo calls as they happen, then a summary of what came back and a list of CHECKS that would
make the page look empty or wrong. Nothing secret is printed or saved.

Usage (PowerShell, from the repo root, with the venv active):
  $env:QLOO_API_KEY="<key>"
  python scripts\\xc_terminal_test.py                       # a default set of pairs
  python scripts\\xc_terminal_test.py --pair "Tesla|Patagonia" --pair "Gucci|Nike"
  python scripts\\xc_terminal_test.py --quiet               # summary only
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAIRS = ["Nike|Adidas", "Porsche|Kith", "Coachella|Jacquemus", "Lululemon|NFL",
                 "Tesla|Patagonia", "Gucci|McDonald's", "Spotify|Red Bull", "Apple|Netflix"]


def load_live():
    spec = importlib.util.spec_from_file_location("xc_live", ROOT / "backend" / "live.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["xc_live"] = mod
    spec.loader.exec_module(mod)
    return mod


def val(m):
    return None if not isinstance(m, dict) else m.get("value")


def short(params):
    out = []
    for k, v in (params or {}).items():
        out.append(f"{k.replace('signal.interests.entities', 'sig').replace('filter.', '')}={str(v)[:22]}")
    return " ".join(out)


def run_pair(live, a, b, quiet):
    print("\n" + "=" * 78)
    print(f"{a}  x  {b}")
    print("=" * 78)
    run = live.create_run(a, b)
    started = time.time()
    seen = 0
    for block in live.sse(run):
        m = re.search(r"^data: (.*)$", block, re.M)
        if not m:
            continue
        ev = json.loads(m.group(1))
        seen += 1
        t, d = ev["type"], ev["data"]
        if quiet:
            continue
        if t == "phase.started":
            print(f"\n[{ev['phase']}] {d.get('title')}")
        elif t == "tool.call":
            print(f"  GET {d['endpoint']:<14} {short(d.get('params'))}")
        elif t == "tool.result":
            flag = "  <-- EMPTY/FAILED" if d.get("suspect_empty") else ""
            print(f"      {d['status']}  {d['latency_ms'] / 1000:.1f}s  {d.get('result_count')} results{flag}  {d.get('summary', '')[:70]}")
        elif t == "warning":
            print(f"  ! {d['message']}")
        elif t == "error":
            print(f"  ERROR: {d['message']}")
    secs = time.time() - started
    print(f"\nrun {run.status} in {secs:.0f}s, {seen} events, {run.q.calls} Qloo calls")
    res = run.result
    if run.status != "completed" or not res:
        print(f"RESULT: FAILED -> {run.error}")
        return {"pair": f"{a}|{b}", "status": "failed", "error": run.error, "checks": [f"run failed: {run.error}"]}

    fit, ov = val(res["fit"]["affinity"]), val(res["fit"]["tag_overlap"])
    tc = res["fit"]["tag_counts"]
    print(f"{res['acquirer']['name']} x {res['target']['name']}   verdict: {res['headline']['verdict']}  confidence {val(res['headline']['confidence'])}")
    print(f"  fit (Qloo pair affinity)  {fit if fit is None else round(fit, 1)}   tag overlap {ov if ov is None else round(ov, 3)}   tags: only A {tc['a_only']}, shared {tc['shared']}, only B {tc['b_only']}")
    print(f"  shared tags: {', '.join(s['name'] for s in res['fit']['shared_signals'][:5])}")
    print(f"  only A:      {', '.join(x['name'] for x in res['fit']['contrast_axes'] if x['side'] == 'acquirer')}")
    print(f"  only B:      {', '.join(x['name'] for x in res['fit']['contrast_axes'] if x['side'] == 'target')}")
    for r in res["locality"]["regions"]:
        print(f"  {r['label']:<18} overlap {val(r['affinity'])}   cells drawn {len(r['heat']['cells'])}   ({r['sample_note']})")
    for c in res["rebellion"]["communities"]:
        print(f"  community {c['label']:<34} rebel {val(c['rebellion_probability'])}")
    sim = res["rebellion"].get("simulation")
    print(f"  IP value at risk: {None if not sim else round(sim['distribution']['mean'], 1)}%   rebellion index {val(res['rebellion']['index']['score'])}")
    print(f"  bridge: {res['bridge']['status']}   steps: {[s['to_category'] for s in res['bridge']['steps']]}")
    tam = res["tam"]["expansion_usd"]
    print(f"  dollars (low/base/high): {val(tam['low'])} / {val(tam['base'])} / {val(tam['high'])}")
    print(f"  evidence entries: {len(res['evidence'])}   warnings: {[w['code'] for w in res['warnings']]}")

    checks = []
    if fit is None:
        checks.append("no pairwise affinity from Qloo (fit missing)")
    if not tc["shared"] and not tc["a_only"]:
        checks.append("no tags returned for either brand")
    for r in res["locality"]["regions"]:
        n = len(r["heat"]["cells"])
        if n == 0:
            checks.append(f"{r['label']}: Qloo returned no heatmap cells, so that panel is blank")
        elif val(r["affinity"]) is None:
            checks.append(f"{r['label']}: heatmap returned but the two brands share too few cells to compare")
        elif n < 15:
            checks.append(f"{r['label']}: only {n} heatmap cells, the panel will look sparse")
    if not res["rebellion"]["communities"]:
        checks.append("no communities derived (not enough one-sided tags), so no simulation")
    if val(tam["base"]) is None:
        checks.append("no dollar figure (needs fit, simulation and all three regions)")
    if not res["fit"]["demographics"]["acquirer"]["age"] or not res["fit"]["demographics"]["target"]["age"]:
        checks.append("age chart missing for at least one brand")
    print("  CHECKS: " + ("all good" if not checks else ""))
    for c in checks:
        print(f"   - {c}")
    return {"pair": f"{a}|{b}", "status": "completed", "verdict": res["headline"]["verdict"], "fit": fit,
            "tags": tc, "regions": {r["key"]: [val(r["affinity"]), len(r["heat"]["cells"])] for r in res["locality"]["regions"]},
            "tam_base": val(tam["base"]), "bridge": res["bridge"]["status"], "checks": checks, "calls": run.q.calls, "seconds": round(secs)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pair", action="append", help='"Brand A|Brand B" (repeatable)')
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--out", default=str(ROOT / ".qloo-probe" / "terminal-test.json"))
    a = ap.parse_args(argv)
    if not os.environ.get("QLOO_API_KEY", "").strip():
        print("QLOO_API_KEY is not set. Nothing was sent.", file=sys.stderr)
        return 2
    live = load_live()
    pairs = [p.split("|", 1) for p in (a.pair or DEFAULT_PAIRS)]
    results = [run_pair(live, x.strip(), y.strip(), a.quiet) for x, y in pairs]
    print("\n" + "#" * 78 + "\nSUMMARY")
    for r in results:
        if r["status"] != "completed":
            print(f"  FAIL  {r['pair']:<32} {r['error']}")
        else:
            print(f"  {'OK  ' if not r['checks'] else 'WARN'}  {r['pair']:<32} fit {r['fit'] if r['fit'] is None else round(r['fit'])}  {r['verdict']:<26} bridge {r['bridge']:<10} {len(r['checks'])} checks  {r['seconds']}s")
    Path(a.out).parent.mkdir(exist_ok=True)
    Path(a.out).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDerived numbers saved to {a.out} (no key, no raw responses).")
    return 0 if all(r["status"] == "completed" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
