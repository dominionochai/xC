"""Compute a weighted, normalized fit score from Qloo signals."""
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


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def normalize_score(value: Any) -> float | None:
    """Convert a finite score to [0, 1]; values above 1 use a 0-100 scale."""
    number = _number(value)
    if number is None:
        return None
    if number > 1.0:
        number /= 100.0
    return min(1.0, max(0.0, number))


def _signals(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        raw = payload.get("components", payload.get("signals", payload.get("results")))
        if isinstance(raw, Mapping):
            return [{"name": key, "score": value} if not isinstance(value, Mapping)
                    else {"name": key, **value} for key, value in raw.items()]
        if isinstance(raw, (list, tuple)):
            return [dict(x) if isinstance(x, Mapping) else {"score": x} for x in raw]
        if any(key in payload for key in ("score", "affinity", "value")):
            return [dict(payload)]
    if isinstance(payload, (list, tuple)):
        return [dict(x) if isinstance(x, Mapping) else {"score": x} for x in payload]
    return []


def fit(qloo: Any, signals: Any = None, *, weights: Mapping[str, float] | None = None,
        budget: Any = None) -> dict[str, Any]:
    """Return a weighted fit score, component breakdown, provenance and warnings.

    The score is ``sum(normalized_component * effective_weight) / sum(weights)``.
    Missing or invalid component values are excluded, and coverage reports the
    fraction of supplied components that contributed to the score.
    """
    warnings: list[str] = []
    provenance: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    payload = signals
    method = next((getattr(qloo, name, None) for name in ("get_fit", "evaluate_fit")
                   if callable(getattr(qloo, name, None))), None)
    if method is not None:
        try:
            _budget_check(budget)
            try:
                fetched = method() if signals is None else method(signals)
            except TypeError:
                fetched = method()
            if fetched is not None:
                payload = fetched
            provenance.append({"source": "qloo", "method": getattr(method, "__name__", "get_fit")})
        except Exception as exc:
            warnings.append("qloo_fit_failed: " + type(exc).__name__)
    elif signals is None:
        warnings.append("qloo_fit_method_unavailable")
    rows = _signals(payload)
    scored: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        name = str(row.get("name", row.get("id", f"component_{index + 1}")))
        raw = row.get("score", row.get("affinity", row.get("value")))
        normalized = normalize_score(raw)
        configured = (weights or {}).get(name)
        if configured is None:
            configured = row.get("weight", 1.0)
        weight = _number(configured)
        if weight is None or weight < 0:
            warnings.append(f"invalid_weight:{name}")
            weight = 0.0
        scored.append({"name": name, "raw_score": raw, "score": normalized,
                       "weight": weight, "contributed": normalized is not None and weight > 0})
    valid = [row for row in scored if row["contributed"]]
    denominator = sum(row["weight"] for row in valid)
    score = (sum(row["score"] * row["weight"] for row in valid) / denominator
             if denominator else None)
    coverage = len(valid) / len(scored) if scored else 0.0
    if scored and not valid:
        warnings.append("no_valid_fit_components")
    for row in scored:
        evidence.append({"kind": "fit_component", **row})
    return {"score": score, "coverage": coverage, "components": scored,
            "formula": "weighted_mean(normalized_scores)", "provenance": provenance,
            "evidence": evidence, "warnings": warnings}
