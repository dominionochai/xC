"""Deterministic Markdown and minimal-PDF memo exports.

The renderer accepts mapping-like or attribute-based analysis results. Missing
inputs are deliberately represented as ``not available`` rather than raising.
"""
from __future__ import annotations

import os
import re
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_SECTIONS = (
    "Executive summary",
    "Cultural fit",
    "Rebellion risk",
    "Bridge",
    "Locality",
    "TAM",
    "Methods and limitations",
    "Evidence appendix",
)
_DISCLAIMER = "assumption-driven screening, not investment advice"
_MISSING = "not available"


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    """Return the first present, non-None mapping key or object attribute."""
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            value = obj[name]
        else:
            value = getattr(obj, name, None)
        if value is not None:
            return value
    return default


def _clean(value: Any) -> str:
    if value is None:
        return _MISSING
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, Mapping):
        if not value:
            return _MISSING
        return "; ".join(f"{k}: {_clean(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        if not value:
            return _MISSING
        return "; ".join(_clean(item) for item in value)
    text = str(value).strip()
    return text if text else _MISSING


def _items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return list(value.items())
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _mapping_rows(value: Any, key_name: str = "name") -> list[dict[str, Any]]:
    """Normalize records and keyed mappings into simple table rows."""
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(item, Mapping):
                row = dict(item)
                row.setdefault(key_name, key)
            else:
                row = {key_name: key, "value": item}
            rows.append(row)
    else:
        for item in _items(value):
            if isinstance(item, Mapping):
                rows.append(dict(item))
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                rows.append({key_name: item[0], "value": item[1]})
            else:
                rows.append({key_name: item})
    return rows


def _md_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    if not rows:
        rows = [[_MISSING for _ in headers]]
    for row in rows:
        cells = [_clean(row[i]) if i < len(row) else _MISSING for i in range(len(headers))]
        lines.append("| " + " | ".join(cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |")
    return "\n".join(lines)


def _metric_provenance(result: Any, source: Any, key: Any) -> str:
    provenance = _get(result, "provenance")
    if isinstance(provenance, Mapping):
        for candidate in (key, str(key), "default"):
            entry = provenance.get(candidate)
            if entry is not None:
                return _clean(entry)
    if source is not None:
        entry = _get(source, "provenance", "source", "citation")
        if entry is not None:
            return _clean(entry)
    return _MISSING


def _score_rows(result: Any) -> list[list[Any]]:
    rows: list[list[Any]] = []
    sources = []
    for name in ("fit", "simulation", "locality", "tam"):
        item = _get(result, name)
        if item is not None:
            sources.append((name, item))
    for name, source in sources:
        if isinstance(source, Mapping):
            for key, value in source.items():
                k = str(key).lower()
                if any(token in k for token in ("score", "index", "rate", "size", "estimate", "verdict")) and not isinstance(value, (Mapping, list, tuple)):
                    rows.append([f"{name}.{key}", value, _metric_provenance(result, source, key)])
    for key, value in (_get(result, "headline_numbers", default={}) or {}).items() if isinstance(_get(result, "headline_numbers", default={}), Mapping) else []:
        rows.append([key, value, _metric_provenance(result, result, key)])
    return rows


def _render_axes(result: Any) -> str:
    fit = _get(result, "fit")
    axes = _get(result, "contrast_axes", default=_get(fit, "contrast_axes", "axes"))
    rows = []
    for row in _mapping_rows(axes, "axis"):
        label = _get(row, "axis", "name", "label", default=_MISSING)
        value = _get(row, "value", "score", "fit", "result", default=_MISSING)
        rows.append([label, value, _get(row, "provenance", "source", "citation", default=_MISSING)])
    return _md_table(["Axis", "Assessment", "Provenance"], rows)


def _render_communities(result: Any) -> str:
    communities = _get(result, "communities")
    rows = []
    for row in _mapping_rows(communities, "community"):
        rows.append([
            _get(row, "community", "name", "segment", default=_MISSING),
            _get(row, "score", "index", "risk", "description", "value", default=_MISSING),
            _get(row, "evidence", "status", "provenance", default=_MISSING),
        ])
    return _md_table(["Community", "Assessment", "Evidence / provenance"], rows)


def _render_channels(result: Any) -> str:
    channels = _get(result, "channels", default=_get(_get(result, "simulation"), "channels"))
    rows = []
    for row in _mapping_rows(channels, "channel"):
        status = _get(row, "status", "verification", "evidence_status", default=None)
        if status is None:
            status = "Verified" if _get(row, "verified", default=False) else "Hypothesis"
        rows.append([
            _get(row, "channel", "name", "platform", default=_MISSING),
            _get(row, "hypothesis", "description", "value", default=_MISSING),
            status,
            _get(row, "evidence", "source", "provenance", default=_MISSING),
        ])
    return _md_table(["Channel", "Claim", "Hypothesis / Verified", "Evidence"], rows)


def _render_simulation(result: Any) -> str:
    simulation = _get(result, "simulation")
    distribution = _get(simulation, "distribution", "summary", "distribution_summary", default=simulation)
    fields = ("runs", "count", "mean", "median", "p10", "p50", "p90", "min", "max", "standard_deviation", "stddev")
    rows = []
    if isinstance(distribution, Mapping):
        rows = [[key, value] for key, value in distribution.items()]
    elif distribution is not None:
        rows = [["Summary", distribution]]
    else:
        rows = [[field, _MISSING] for field in fields]
    if not rows:
        rows = [["Summary", _MISSING]]
    return _md_table(["Distribution statistic", "Value"], rows)


def _render_bridge(result: Any) -> str:
    bridge = _get(result, "bridge")
    steps = _get(bridge, "steps", "actions", default=bridge)
    if isinstance(steps, Mapping):
        ordered = list(steps.values())
    else:
        ordered = _items(steps)
    rows = []
    for index in range(3):
        step = ordered[index] if index < len(ordered) else None
        if isinstance(step, Mapping):
            objective = _get(step, "objective", "goal", "action", "name", default=_MISSING)
            lift = _get(step, "lift", "expected_lift", "impact", default=_MISSING)
            number = _get(step, "step", "number", default=index + 1)
        else:
            objective = step if step is not None else _MISSING
            lift = _MISSING
            number = index + 1
        rows.append([number, objective, lift])
    return _md_table(["Step", "Objective", "Lift"], rows)


def _render_locality(result: Any) -> tuple[str, str]:
    locality = _get(result, "locality")
    locations = _get(locality, "locations", "markets", "table", default=locality)
    rows = []
    for row in _mapping_rows(locations, "location"):
        rows.append([
            _get(row, "location", "market", "name", "region", default=_MISSING),
            _get(row, "score", "index", "value", "fit", default=_MISSING),
            _get(row, "population", "audience", "size", default=_MISSING),
            _get(row, "caveat", "notes", "limitations", default=_MISSING),
        ])
    caveats = _get(locality, "caveats", "limitations", "notes", default=_get(result, "locality_caveats"))
    return _md_table(["Location", "Assessment", "Audience / size", "Caveats"], rows), _clean(caveats)


def _render_tam(result: Any) -> tuple[str, str, str]:
    tam = _get(result, "tam")
    scenarios = _get(tam, "scenarios", "estimates", default=None)
    scenario_rows = []
    for row in _mapping_rows(scenarios, "scenario"):
        scenario_rows.append([
            _get(row, "scenario", "name", "case", default=_MISSING),
            _get(row, "value", "tam", "estimate", "market_size", default=_MISSING),
            _get(row, "assumptions", "basis", "description", default=_MISSING),
        ])
    assumptions = _get(tam, "assumptions", "assumption_table")
    assumption_rows = []
    for row in _mapping_rows(assumptions, "assumption"):
        assumption_rows.append([
            _get(row, "assumption", "name", "input", default=_MISSING),
            _get(row, "value", "estimate", default=_MISSING),
            _get(row, "source", "provenance", "notes", default=_MISSING),
        ])
    sensitivity = _get(tam, "sensitivity", "sensitivities", "sensitivity_analysis")
    return (
        _md_table(["Scenario", "Estimate", "Assumptions / basis"], scenario_rows),
        _md_table(["Assumption", "Value", "Source / notes"], assumption_rows),
        _clean(sensitivity),
    )


def render_markdown(result: Any, fixture_mode: bool = False) -> str:
    """Render an analysis result as a stable, human-readable Markdown memo."""
    fit = _get(result, "fit")
    summary = _get(result, "executive_summary", "summary")
    verdict = _get(result, "verdict", default=_get(fit, "verdict", default=_get(summary, "verdict")))
    headline_rows = _score_rows(result)
    if not headline_rows:
        headline_rows = [["Headline numbers", _MISSING, _MISSING]]
    rebellion = _get(result, "rebellion", "rebellion_risk")
    simulation = _render_simulation(result)
    bridge = _render_bridge(result)
    locality_table, locality_caveats = _render_locality(result)
    tam_scenarios, tam_assumptions, tam_sensitivity = _render_tam(result)
    provenance = _get(result, "provenance")
    evidence = _get(result, "evidence", "evidence_ledger")
    evidence_rows = []
    for row in _mapping_rows(evidence, "id"):
        evidence_rows.append([
            _get(row, "id", "evidence_id", "ref", default=_MISSING),
            _get(row, "claim", "description", "statement", default=_MISSING),
            _get(row, "source", "url", "citation", default=_MISSING),
            _get(row, "hash", "sha256", "digest", default=_MISSING),
            _get(row, "hash_chain_status", "chain_status", "status", default=_MISSING),
        ])
    warnings = _get(result, "warnings")
    methods = _get(result, "methods", "methodology")
    anchors = _get(result, "methodology_anchors", default=_get(methods, "anchors", "methodology_anchors", default=_get(provenance, "methodology_anchors", "anchors")))
    lines = ["# Memo", ""]
    if fixture_mode:
        lines.extend(["**FIXTURE DATA - NOT LIVE QLOO OUTPUT**", ""])
    lines.extend([
        "## Executive summary", "",
        f"- Verdict: {_clean(verdict)}",
        f"- Summary: {_clean(summary)}",
        "",
        "Headline numbers (with provenance):",
        _md_table(["Metric", "Value", "Provenance"], headline_rows),
        "",
        "## Cultural fit", "",
        f"- Fit assessment: {_clean(_get(fit, 'assessment', 'summary', 'score', 'value', default=fit))}",
        "",
        "Contrast axes:",
        _render_axes(result),
        "",
        "## Rebellion risk", "",
        f"- Index: {_clean(_get(rebellion, 'index', 'score', 'value', default=_get(result, 'rebellion_index')))}",
        f"- Components: {_clean(_get(rebellion, 'components', default=_get(result, 'rebellion_components')))}",
        "",
        "Simulation distribution summary:", simulation,
        "",
        "Communities:", _render_communities(result),
        "",
        "Channels (Hypothesis / Verified distinction):", _render_channels(result),
        "",
        "## Bridge", "",
        "Three steps with objectives and lifts:", bridge,
        "",
        "## Locality", "",
        locality_table,
        "",
        f"Caveats: {locality_caveats}",
        "",
        "## TAM", "",
        "Scenarios:", tam_scenarios,
        "",
        "Assumptions table:", tam_assumptions,
        "",
        f"Sensitivity: {tam_sensitivity}",
        "",
        "## Methods and limitations", "",
        f"- Methodology: {_clean(methods)}",
        f"- Methodology anchors: {_clean(anchors)}",
        f"- Provenance: {_clean(provenance)}",
        f"- Warnings: {_clean(warnings)}",
        "",
        "## Evidence appendix", "",
        _md_table(["Ledger ID", "Claim", "Source", "Hash", "Hash chain status"], evidence_rows),
        "",
        _DISCLAIMER,
        "",
    ])
    return "\n".join(lines)


def _pdf_lines(markdown: str, width: int = 92) -> list[tuple[str, bool]]:
    lines: list[tuple[str, bool]] = []
    for raw in markdown.splitlines():
        text = raw.strip()
        if not text:
            lines.append(("", False))
            continue
        heading = text.startswith("#")
        text = re.sub(r"^#{1,6}\\s*", "", text)
        text = text.replace("**", "").replace("`", "")
        # Keep Markdown table separators legible and wrap oversized cells safely.
        wrapped = textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False) or [""]
        lines.extend((part, heading) for part in wrapped)
    return lines


def _pdf_escape(text: str) -> bytes:
    # Standard Type 1 fonts use WinAnsi; replace unsupported glyphs for portability.
    safe = text.encode("cp1252", errors="replace").decode("cp1252")
    safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return safe.encode("cp1252")


def render_pdf(result: Any, fixture_mode: bool = False, output_path: Any = None) -> bytes:
    """Render a deterministic, dependency-free PDF 1.4 memo and optionally save it."""
    markdown = render_markdown(result, fixture_mode=fixture_mode)
    logical_lines = _pdf_lines(markdown)
    page_capacity = 48
    chunks = [logical_lines[i:i + page_capacity] for i in range(0, len(logical_lines), page_capacity)] or [[]]
    page_count = len(chunks)
    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    page_ids = [5 + 2 * i for i in range(page_count)]
    objects[2] = ("<< /Type /Pages /Kids [" + " ".join(f"{page_id} 0 R" for page_id in page_ids) + f"] /Count {page_count} >>").encode("ascii")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    objects[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    for page_index, chunk in enumerate(chunks):
        page_id = page_ids[page_index]
        stream_id = page_id + 1
        commands = []
        y = 756
        for text, is_heading in chunk:
            font = "/F2" if is_heading else "/F1"
            size = 11 if is_heading else 9
            if text:
                commands.append(f"BT {font} {size} Tf 48 {y} Td (".encode("ascii") + _pdf_escape(text) + b") Tj ET")
            y -= 14 if is_heading else 12
        footer = f"Page {page_index + 1} of {page_count}"
        commands.append(b"BT /F1 8 Tf 500 24 Td (" + _pdf_escape(footer) + b") Tj ET")
        stream = b"\n".join(commands) + b"\n"
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_id} 0 R >>"
        ).encode("ascii")
        objects[stream_id] = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream"
    max_id = max(objects)
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (max_id + 1)
    for obj_id in range(1, max_id + 1):
        offsets[obj_id] = len(output)
        output.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        output.extend(objects[obj_id])
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {max_id + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, max_id + 1):
        output.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    pdf_bytes = bytes(output)
    if output_path is not None:
        Path(os.fspath(output_path)).write_bytes(pdf_bytes)
    return pdf_bytes
