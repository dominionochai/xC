"""Offline evidence-ledger helpers; no network or API-key handling."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def validate_payload(payload: Any) -> bool:
    """Reject raw-looking payloads using a simple recursive heuristic.

    Any string or mapping key containing ``raw`` (case-insensitive), or any
    list/tuple longer than 100 items, is rejected. This is only a guardrail;
    callers must provide derived values and IDs, never response bodies.
    """
    def looks_raw(value: Any) -> bool:
        if isinstance(value, str):
            return "raw" in value.casefold()
        if isinstance(value, Mapping):
            return any(looks_raw(key) or looks_raw(item) for key, item in value.items())
        if isinstance(value, (list, tuple)):
            return len(value) > 100 or any(looks_raw(item) for item in value)
        return False
    return not looks_raw(payload)


def make_ledger_entry(source: str, claim: str, payload: Any,
                      reference: str | None = None) -> dict[str, Any]:
    """Build a stable entry; payloads that look raw are refused."""
    if not validate_payload(payload):
        raise ValueError("payload looks like a raw API body")
    if reference is None:
        material = str(source) + str(claim) + json.dumps(payload, sort_keys=True)
        reference = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return {"source": source, "reference": reference, "claim": claim, "payload": payload}


def _parameter_names(params_names: Any) -> list[str]:
    """Extract names only; mapping values are deliberately discarded."""
    if isinstance(params_names, Mapping):
        values = params_names.keys()
    elif isinstance(params_names, str):
        values = [params_names]
    elif isinstance(params_names, (list, tuple, set)):
        values = params_names
    else:
        values = []
    return [name for name in values if isinstance(name, str)]


def _next_row_id(ledger: list[dict[str, Any]]) -> int:
    ids = [entry.get("row_id") for entry in ledger
           if isinstance(entry, dict) and isinstance(entry.get("row_id"), int)
           and not isinstance(entry.get("row_id"), bool)]
    return max(ids, default=0) + 1


def record_call(ledger: list[dict[str, Any]], method: str, path: str,
                params_names: Any, status: Any, cache_hit: bool,
                suspect_empty: bool, result_count: int | None,
                elapsed_ms: float | None, reference: str | None = None) -> dict[str, Any]:
    """Append a Qloo call with names only (never parameter values or API keys)."""
    payload = {
        "method": method,
        "path": path,
        "params_names": _parameter_names(params_names),
        "status": status,
        "cache_hit": bool(cache_hit),
        "suspect_empty": bool(suspect_empty),
        "result_count": result_count,
        "elapsed_ms": elapsed_ms,
    }
    entry = make_ledger_entry("qloo:" + str(path), "qloo call", payload, reference)
    entry["row_id"] = _next_row_id(ledger)
    ledger.append(entry)
    return entry


class EvidenceLedgerAdapter:
    """Append and verify the lightweight M10 ledger-entry format."""
    def __init__(self, ledger: list[dict[str, Any]] | None = None) -> None:
        self.ledger = ledger if ledger is not None else []

    def add_call(self, method: str, path: str, params_names: Any, status: Any,
                 cache_hit: bool, suspect_empty: bool, result_count: int | None,
                 elapsed_ms: float | None, reference: str | None = None) -> dict[str, Any]:
        return record_call(self.ledger, method, path, params_names, status,
                           cache_hit, suspect_empty, result_count, elapsed_ms, reference)

    def add_metric(self, method: str, claim: str, payload: Any,
                   reference: str | None = None) -> dict[str, Any]:
        """Append a computed metric under source ``computed:<method>``."""
        entry = make_ledger_entry("computed:" + str(method), claim, payload, reference)
        entry["row_id"] = _next_row_id(self.ledger)
        self.ledger.append(entry)
        return entry

    def verify(self) -> bool:
        """Return true only when all entries have required keys and clean payloads."""
        required = {"source", "reference", "claim", "payload"}
        return all(isinstance(entry, dict) and required.issubset(entry)
                   and validate_payload(entry["payload"]) for entry in self.ledger)


class XcLedgerBridge:
    """Use the repository XcEvidenceLedger when importable, otherwise the adapter."""
    def verify(self, ledger: list[dict[str, Any]]) -> bool:
        """Delegate to the existing verifier, with a local validation fallback."""
        try:
            try:
                from backend.src.services.evidence_ledger import XcEvidenceLedger
            except Exception:
                from backend.evidence_ledger import XcEvidenceLedger
            verifier = XcEvidenceLedger()
            if hasattr(verifier, "_records"):
                verifier._records = ledger
            report = verifier.verify()
            if isinstance(report, Mapping):
                return report.get("valid") is True
            return report is True
        except Exception:
            return EvidenceLedgerAdapter(ledger).verify()
