#!/usr/bin/env python3
"""Conservative xC Qloo discovery probe; see docs/PROBE.md.

Only repository-known GET routes/parameters are sent. The P1-P13 questions
are a discovery checklist, not claims about unverified live API behavior.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.qloo import QlooClient, QlooError, TransportResponse, normalize_entities
from backend.qloo.normalize import result_items

QUESTIONS = (
    ("P1", "Does the configured host accept the supplied credential for a known GET route?"),
    ("P2", "Does GET /search work with the already-used query and types parameters?"),
    ("P3", "Does search return a results array, and what is its observed size?"),
    ("P4", "Does a search result expose a usable entity identifier/name?"),
    ("P5", "Does GET /v2/insights respond for the first returned entity?"),
    ("P6", "Does the existing signal.interests.entities request shape receive a response?"),
    ("P7", "Does the existing filter.type=urn:tag request shape receive a response?"),
    ("P8", "What result count is returned when the existing take parameter is set to 5?"),
    ("P9", "Are insight results direct objects or nested under an entity object?"),
    ("P10", "Do observed insight items contain identity/name fields?"),
    ("P11", "Is the results key missing, empty, or populated in each observed response?"),
    ("P12", "What HTTP status/retry-after metadata did these calls expose?"),
    ("P13", "Are locale/geography parameter names and semantics verified? (Not trialled.)"),
)


def _answer(status: str, evidence: str) -> dict[str, str]:
    return {"status": status, "evidence": evidence}


def _initial_answers() -> dict[str, dict[str, str]]:
    return {pid: _answer("not_tested", "No live observation available.") for pid, _ in QUESTIONS}


def _shape(payload: Any) -> str:
    if not isinstance(payload, dict) or "results" not in payload:
        return "results key missing"
    value = payload.get("results")
    if isinstance(value, list):
        return f"results array ({len(value)} item(s))"
    if isinstance(value, dict):
        return "results object"
    return f"results is {type(value).__name__}"


def run_probe(client: QlooClient, term: str = "coffee") -> dict[str, Any]:
    """Run at most one search and one insights query; raw data is returned
    separately for the caller to store only under ``.qloo-probe/``.
    """
    if not isinstance(term, str) or not term.strip():
        raise ValueError("term must be a non-empty string")
    answers = _initial_answers()
    raw: dict[str, Any] = {}
    try:
        search = client.get("/search", {"query": term.strip(), "types": "urn:entity:brand"})
        raw["search"] = search
        items = result_items(search)
        answers["P1"] = _answer("observed", "The authenticated GET /search returned a JSON object (2xx).")
        answers["P2"] = _answer("observed", "The combined known query/types request returned a JSON object; individual parameter effects were not isolated.")
        answers["P3"] = _answer("observed", _shape(search))
        entities = normalize_entities(search)
        if entities:
            candidate = entities[0]
            answers["P4"] = _answer("observed", "At least one normalized candidate had a usable identifier/name.")
            try:
                insights = client.get("/v2/insights", {
                    "signal.interests.entities": candidate["id"],
                    "filter.type": "urn:tag",
                    "take": 5,
                })
                raw["insights"] = insights
                insight_items = result_items(insights)
                answers["P5"] = _answer("observed", "The combined known insights request returned a JSON object (2xx).")
                answers["P6"] = _answer("observed", "The existing signal.interests.entities field was sent in a successful combined request; its effect was not isolated.")
                answers["P7"] = _answer("observed", "The existing filter.type=urn:tag field was sent in a successful combined request; its effect was not isolated.")
                answers["P8"] = _answer("observed", f"take=5 was requested; {_shape(insights)}. This observation does not prove a server-side cap.")
                nested = sum(1 for item in insight_items if isinstance(item, dict) and isinstance(item.get("entity"), dict))
                direct = sum(1 for item in insight_items if isinstance(item, dict) and not isinstance(item.get("entity"), dict))
                answers["P9"] = _answer("observed", f"Observed {nested} nested and {direct} non-nested object item(s).")
                normalized = normalize_entities(insights)
                answers["P10"] = _answer("observed", f"{len(normalized)} insight item(s) normalized to identity/name fields.")
                answers["P11"] = _answer("observed", _shape(insights))
            except QlooError as error:
                for pid in ("P5", "P6", "P7", "P8", "P9", "P10", "P11"):
                    answers[pid] = _answer("failed", f"Insights probe did not complete: {error}")
        else:
            answers["P4"] = _answer("not_tested", "Search returned no usable entity candidate; insights were not requested.")
            for pid in ("P5", "P6", "P7", "P8", "P9", "P10", "P11"):
                answers[pid] = _answer("not_tested", "No usable search candidate; insights fields/shapes were not tested.")
    except QlooError as error:
        answers["P1"] = _answer("failed", f"Search probe did not complete: {error}")
        answers["P2"] = _answer("failed", "Known search request did not complete.")
        answers["P3"] = _answer("not_tested", "No search payload was returned.")
        answers["P4"] = _answer("not_tested", "No search payload was returned.")

    log = client.call_log
    statuses = [str(row.get("status")) for row in log if not row.get("cached")]
    retry_values = [str(row["retry_after_seconds"]) for row in log if "retry_after_seconds" in row]
    answers["P12"] = _answer("observed", f"Observed network status code(s): {', '.join(statuses) or 'none'}; numeric Retry-After value(s): {', '.join(retry_values) or 'none'}. Rate limiting was not induced.")
    answers["P13"] = _answer("not_tested", "No locale/geography parameters were sent; names and semantics require an approved spec and separate safe trial.")
    return {"questions": {pid: question for pid, question in QUESTIONS},
            "answers": answers, "network_attempts": client.calls_used,
            "call_log": log, "_raw": raw}


def _redact(value: Any, secret: str | None) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if str(key).lower() in {"api_key", "x-api-key", "authorization"}:
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = _redact(item, secret)
        return cleaned
    if isinstance(value, list):
        return [_redact(item, secret) for item in value]
    if isinstance(value, str) and secret:
        return value.replace(secret, "[REDACTED]")
    return value


def write_outputs(report: dict[str, Any], api_key: str) -> list[str]:
    """Write raw response payloads/report only inside the git-ignored folder."""
    directory = ROOT / ".qloo-probe"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = report.get("_raw", {})
    files: list[str] = []
    for name, payload in raw.items():
        filename = f"{stamp}-{name}.json"
        with (directory / filename).open("w", encoding="utf-8") as handle:
            json.dump(_redact(payload, api_key), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        files.append(filename)
    safe_report = {key: value for key, value in report.items() if key != "_raw"}
    safe_report["raw_files"] = files
    with (directory / f"{stamp}-report.json").open("w", encoding="utf-8") as handle:
        json.dump(_redact(safe_report, api_key), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return files


def print_summary(report: dict[str, Any]) -> None:
    for pid, question in QUESTIONS:
        answer = report["answers"][pid]
        print(f"{pid} [{answer['status']}]: {question}\n  {answer['evidence']}")


class _SyntheticTransport:
    def __init__(self) -> None:
        synthetic = ROOT / "tests" / "synthetic"
        self.responses = [
            json.loads((synthetic / "search_response.json").read_text(encoding="utf-8")),
            json.loads((synthetic / "insights_response.json").read_text(encoding="utf-8")),
        ]
        self.paths: list[str] = []

    def get(self, url: str, *, params: Any, headers: Any, timeout: float) -> TransportResponse:
        self.paths.append(url)
        body = json.dumps(self.responses.pop(0)).encode("utf-8")
        return TransportResponse(200, {"Content-Type": "application/json"}, body)


def selftest() -> None:
    """Run a deterministic, offline smoke test; does not create output files."""
    synthetic = _SyntheticTransport()
    client = QlooClient("synthetic-never-a-real-key", transport=synthetic,
                        retries=0, pacing_seconds=0, cache_ttl=0, call_budget=2)
    report = run_probe(client)
    assert len(report["answers"]) == 13
    assert report["answers"]["P1"]["status"] == "observed"
    assert report["answers"]["P5"]["status"] == "observed"
    assert report["answers"]["P13"]["status"] == "not_tested"
    assert client.calls_used == 2 and len(synthetic.paths) == 2
    assert all("synthetic-never-a-real-key" not in json.dumps(row) for row in client.call_log)
    print("Qloo probe selftest: PASS (synthetic fixtures only; no network, no files)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true", help="run offline synthetic smoke test")
    parser.add_argument("--term", default="coffee", help="search term for the bounded live probe")
    args = parser.parse_args(argv)
    if args.selftest:
        selftest()
        return 0
    api_key = os.environ.get("QLOO_API_KEY", "").strip()
    if not api_key:
        print("No live probe run: set QLOO_API_KEY to enable it. No credentials are printed or written.", file=sys.stderr)
        return 2
    client = QlooClient(api_key, retries=1, pacing_seconds=0.4,
                        cache_ttl=0, call_budget=4)
    report = run_probe(client, args.term)
    files = write_outputs(report, api_key)
    print_summary(report)
    print("Raw responses and report saved under .qloo-probe/ (git-ignored).")
    print("Files: " + ", ".join(files))
    return 0 if not any(row["status"] == "failed" for row in report["answers"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
