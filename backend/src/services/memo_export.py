"""Deterministic Markdown and PDF exports for investment analysis reports."""
from __future__ import annotations

import json
import re
import textwrap
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


def _json_safe(value: Any) -> Any:
    """Convert report values to a stable, JSON-serializable representation."""
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, indent=2, default=str)


def _first(report: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = report.get(key)
        if value is not None and value != "":
            return value
    return None


def _display(value: Any) -> str:
    if value is None:
        return "Not provided"
    if isinstance(value, Mapping) or isinstance(value, (list, tuple)):
        return _json(value)
    return str(value)


def _collect_evidence(value: Any, path: str = "") -> list[tuple[str, Any]]:
    """Find explicitly named evidence/citation/reference fields at any depth."""
    found: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            name = str(key)
            normalized = name.lower().replace("-", "_")
            current = f"{path}.{name}" if path else name
            if any(token in normalized for token in ("evidence", "citation", "source_ref", "reference")):
                if item not in (None, "", [], {}):
                    found.append((current, item))
            found.extend(_collect_evidence(item, current))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_collect_evidence(item, f"{path}[{index}]"))
    return found


def _section_items(value: Any) -> list[str]:
    if value is None:
        return ["- Not provided"]
    if isinstance(value, Mapping):
        return [f"- **{key}:** {_display(value[key]).replace(chr(10), '<br>')}" for key in sorted(value, key=str)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [f"- {_display(item).replace(chr(10), '<br>')}" for item in value] or ["- Not provided"]
    return [f"- {_display(value)}"]


def render_investment_memo_markdown(report: Mapping[str, Any]) -> str:
    """Render all supplied report data in a stable, readable investment memo."""
    acquirer = _first(report, "acquirer", "buyer", "source_entity_name", "source_entity_id", "source", "company_name", "company")
    target = _first(report, "target", "target_name", "comparison_entity_name", "comparison_entity_id", "investment_target")
    if isinstance(acquirer, Mapping):
        acquirer = _first(acquirer, "name", "label", "id")
    if isinstance(target, Mapping):
        target = _first(target, "name", "label", "id")

    tam = _first(report, "tam", "market_sizing", "market_size", "market")
    risk = _first(report, "risk", "risk_index", "risk_assessment", "adversarial_review")
    if risk is None and isinstance(report.get("affinity"), Mapping):
        risk = _first(report["affinity"], "risk", "risk_level", "risk_index")
    regional = _first(report, "regional_scores", "region_scores", "affinity_scores", "scores_by_region", "regional_analysis")
    if regional is None and isinstance(report.get("affinity"), Mapping):
        regional = _first(report["affinity"], "regional_scores", "region_scores", "scores")
    bridge = _first(report, "bridge_steps", "transition_bridge", "transition_path", "bridge", "transition_campaign")
    if isinstance(bridge, Mapping):
        bridge = _first(bridge, "steps", "path", "bridge_steps") or bridge

    evidence = _collect_evidence(report)
    lines = [
        "# Investment Memo", "",
        f"**Acquirer:** {_display(acquirer)}  ",
        f"**Target:** {_display(target)}", "",
        "## Executive summary", "",
        f"- Acquirer: {_display(acquirer)}",
        f"- Target: {_display(target)}", "",
        "## Total addressable market (TAM)", "",
    ]
    lines.extend(_section_items(tam))
    lines.extend(["", "## Risk assessment", ""])
    lines.extend(_section_items(risk))
    lines.extend(["", "## Regional scores", ""])
    lines.extend(_section_items(regional))
    lines.extend(["", "## Bridge steps", ""])
    lines.extend(_section_items(bridge))
    lines.extend(["", "## Evidence references", ""])
    if evidence:
        lines.extend(f"- **{path}:** {_display(item).replace(chr(10), '<br>')}" for path, item in evidence)
    else:
        lines.append("- Not provided")
    lines.extend(["", "## Complete report data", "", "```json", _json(report), "```", ""])
    return "\n".join(lines)


def _pdf_escape(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "replace").decode("ascii")
    return normalized.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def render_investment_memo_pdf(report: Mapping[str, Any]) -> bytes:
    """Render the Markdown memo as a dependency-free, valid multi-page PDF 1.4."""
    markdown = render_investment_memo_markdown(report)
    plain_lines: list[str] = []
    for line in markdown.splitlines():
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = re.sub(r"```.*", "", line)
        line = line.replace("**", "").replace("`", "")
        plain_lines.extend(textwrap.wrap(line, width=88, break_long_words=True, break_on_hyphens=False) if line else [""])
    pages = [plain_lines[index:index + 56] for index in range(0, len(plain_lines), 56)] or [[]]

    page_ids = [4 + 2 * index for index in range(len(pages))]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] /Count {len(pages)} >>").encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, page in enumerate(pages):
        page_id, stream_id = 4 + 2 * index, 5 + 2 * index
        commands = ["BT", "/F1 9 Tf", "48 760 Td", "12 TL"]
        for line in page:
            commands.extend((f"({_pdf_escape(line)}) Tj", "T*"))
        commands.append("ET")
        stream = "\n".join(commands).encode("ascii")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>".encode("ascii")
        )
        objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(output)
