"""Compare two Qloo entity score sets while preserving partial evidence."""
from __future__ import annotations

import inspect
import math
from typing import Any, Mapping


def _budget_check(budget: Any) -> None:
    """Check the operation budget immediately before a Qloo method call."""
    if budget is None:
        return
    check = getattr(budget, "check", None)
    result = check() if callable(check) else budget() if callable(budget) else budget
    if result is False:
        raise RuntimeError("Qloo call budget exhausted")


def _rows(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, Mapping):
        raw = value.get("entities", value.get("results", value.get("items")))
        if raw is None:
            raw = value
        if isinstance(raw, Mapping):
            iterable = [dict(item, id=key) if isinstance(item, Mapping) else
                        {"id": key, "score": item} for key, item in raw.items()]
        elif isinstance(raw, (list, tuple)):
            iterable = [dict(item) if isinstance(item, Mapping) else {"score": item}
                        for item in raw]
        else:
            iterable = []
    elif isinstance(value, (list, tuple)):
        iterable = [dict(item) if isinstance(item, Mapping) else {"score": item}
                    for item in value]
    else:
        iterable = []
    result: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(iterable):
        key = str(item.get("id", item.get("entity_id", item.get("name", f"item_{index + 1}"))))
        score = item.get("score", item.get("affinity", item.get("value")))
        try:
            number = float(score) if score is not None else None
            if number is not None and not math.isfinite(number):
                number = None
        except (TypeError, ValueError, OverflowError):
            number = None
        result[key] = {"id": key, "name": item.get("name"), "score": number}
    return result


def contrast(qloo: Any, left: Any, right: Any, *, budget: Any = None) -> dict[str, Any]:
    """Return pairwise differences for the union of two score sets.

    A missing score is represented as ``None`` and its delta is also ``None``;
    no zero-filling is used, so incomplete Qloo evidence remains explicit.
    """
    warnings: list[str] = []
    provenance: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    method = next((getattr(qloo, name, None) for name in ("get_contrast", "contrast_entities")
                   if callable(getattr(qloo, name, None))), None)
    payload = None
    if method is not None:
        try:
            _budget_check(budget)
            try:
                parameters = inspect.signature(method).parameters
            except (TypeError, ValueError):
                parameters = {"left": None, "right": None}
            if len(parameters) >= 2:
                payload = method(left, right)
            else:
                payload = method()
            provenance.append({"source": "qloo", "method": getattr(method, "__name__", "get_contrast")})
        except Exception as exc:
            warnings.append("qloo_contrast_failed: " + type(exc).__name__)
    elif left is None and right is None:
        warnings.append("qloo_contrast_method_unavailable")
    if isinstance(payload, Mapping):
        left_data = payload.get("left", left)
        right_data = payload.get("right", right)
    else:
        left_data, right_data = left, right
    left_rows, right_rows = _rows(left_data), _rows(right_data)
    output: list[dict[str, Any]] = []
    for key in sorted(set(left_rows) | set(right_rows)):
        lrow, rrow = left_rows.get(key), right_rows.get(key)
        lscore = lrow.get("score") if lrow else None
        rscore = rrow.get("score") if rrow else None
        delta = rscore - lscore if lscore is not None and rscore is not None else None
        row = {"id": key, "name": (lrow or rrow or {}).get("name"),
               "left": lscore, "right": rscore, "delta": delta}
        output.append(row)
        evidence.append({"kind": "contrast", **row})
    missing = sum(row["left"] is None or row["right"] is None for row in output)
    if missing:
        warnings.append("partial_scores_missing:" + str(missing))
    return {"comparisons": output, "provenance": provenance, "evidence": evidence,
            "warnings": warnings}
