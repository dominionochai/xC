#!/usr/bin/env python3
"""Print the KEY STRUCTURE (names and value types, never values) of the latest
full-probe raw files, plus API error messages. Makes no network calls.

Usage:  python scripts/qloo_probe_keys.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABELS = ["ins_base", "pair_filter_entities", "heat_tokyo", "demographics", "explain",
          "loc_signal", "tags_endpoint", "entities"]


def paths(x, prefix="", depth=0, out=None):
    out = [] if out is None else out
    if depth > 4:
        return out
    if isinstance(x, dict):
        for k, v in x.items():
            p = f"{prefix}.{k}" if prefix else k
            out.append(f"{p}: {type(v).__name__}" + (f"[{len(v)}]" if isinstance(v, (list, dict)) else ""))
            paths(v, p, depth + 1, out)
    elif isinstance(x, list) and x:
        paths(x[0], prefix + "[0]", depth + 1, out)
    return out


def first_item(body):
    res = (body or {}).get("results")
    if isinstance(res, dict):
        for v in res.values():
            if isinstance(v, list) and v:
                return v[0]
    if isinstance(res, list) and res:
        return res[0]
    return None


def main():
    runs = sorted((ROOT / ".qloo-probe").glob("full-*"))
    if not runs:
        print("No full-probe run found under .qloo-probe", file=sys.stderr)
        return 1
    raw = runs[-1] / "raw"
    files = {f.name.split("-", 1)[1][:-5]: f for f in sorted(raw.glob("*.json"))}
    for label in LABELS:
        f = files.get(label)
        if not f:
            continue
        item = first_item(json.loads(f.read_text(encoding="utf-8")).get("body"))
        print(f"\n== {label}")
        for line in paths(item)[:40] if item is not None else ["(no items)"]:
            print("  ", line)
    for label in ("trending", "heat_nolocation", "ins_plain_type", "take60"):
        f = files.get(label)
        if f:
            body = json.loads(f.read_text(encoding="utf-8")).get("body")
            print(f"\n== {label} (error body)")
            print("  ", json.dumps(body)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
