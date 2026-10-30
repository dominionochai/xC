"""Run the W3 engine phases and assemble a resilient report."""
from __future__ import annotations

import importlib
import inspect

from . import contract

_PHASES = (
    "resolve",
    "fit",
    "contrast",
    "communities",
    "simulation",
    "bridge",
    "locality",
    "tam",
)


def _value(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _call_count(qloo):
    count = _value(qloo, "call_count")
    if callable(count):
        try:
            count = count()
        except Exception:
            return None
    try:
        return int(count) if count is not None else None
    except (TypeError, ValueError):
        return None


def _max_calls(budget):
    limit = _value(budget, "max_calls")
    try:
        return int(limit) if limit is not None else None
    except (TypeError, ValueError):
        return None


def _missing_optional_inputs(module, inputs):
    declared = getattr(module, "OPTIONAL_INPUTS", ())
    if isinstance(declared, str):
        declared = (declared,)
    if not isinstance(declared, (list, tuple, set, frozenset)):
        declared = ()
    return [name for name in declared if not isinstance(inputs, dict) or inputs.get(name) is None]


def _contract_payload(results, provenance, evidence, warnings, partial):
    return {
        "results": results,
        "phase_results": results,
        "phases": results,
        "data": results,
        "provenance": provenance,
        "evidence": evidence,
        "warnings": warnings,
        "partial": bool(partial),
        "status": "partial" if partial else "complete",
    }


def _assemble_contract(payload):
    assembler = contract.assemble
    signature = inspect.signature(assembler)
    params = signature.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs = {
            "results": payload["results"],
            "provenance": payload["provenance"],
            "evidence": payload["evidence"],
            "warnings": payload["warnings"],
            "partial": payload["partial"],
        }
    else:
        aliases = {
            "results": "results",
            "phase_results": "phase_results",
            "phases": "phases",
            "data": "data",
            "provenance": "provenance",
            "evidence": "evidence",
            "warnings": "warnings",
            "partial": "partial",
            "status": "status",
            "payload": None,
            "report": None,
        }
        kwargs = {}
        for name, parameter in params.items():
            if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if name in aliases:
                key = aliases[name]
                kwargs[name] = payload if key is None else payload[key]
        required = [
            p for p in params.values()
            if p.default is inspect.Parameter.empty
            and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        ]
        if not kwargs and len(required) == 1:
            parameter = required[0]
            kwargs[parameter.name] = payload
    return assembler(**kwargs)


def _report_result(payload):
    result_type = getattr(contract, "ReportResult", None)
    if result_type is None:
        return payload
    try:
        signature = inspect.signature(result_type)
        params = signature.parameters
        aliases = {
            "results": payload["results"],
            "phase_results": payload["phase_results"],
            "phases": payload["phases"],
            "data": payload["data"],
            "provenance": payload["provenance"],
            "evidence": payload["evidence"],
            "warnings": payload["warnings"],
            "partial": payload["partial"],
            "status": payload["status"],
        }
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return result_type(
                results=payload["results"],
                provenance=payload["provenance"],
                evidence=payload["evidence"],
                warnings=payload["warnings"],
                partial=payload["partial"],
            )
        kwargs = {name: aliases[name] for name in params if name in aliases}
        return result_type(**kwargs)
    except Exception:
        return payload


def run(qloo, budget, inputs: dict):
    """Execute available phases in order, retaining partial output on failures."""
    source = inputs if isinstance(inputs, dict) else {}
    results = {}
    provenance = []
    evidence = []
    warnings = []
    partial = False

    if not isinstance(inputs, dict) or not inputs:
        warnings.append("optional_inputs_missing")
        partial = True

    for name in _PHASES:
        try:
            module = importlib.import_module("." + name, package=__package__)
        except ImportError:
            warnings.append("phase_unavailable:" + name)
            partial = True
            continue

        missing = _missing_optional_inputs(module, source)
        for key in missing:
            warnings.append("optional_input_missing:" + key)
            partial = True

        count = _call_count(qloo)
        limit = _max_calls(budget)
        if count is not None and limit is not None and count >= limit:
            warnings.append("budget_exhausted:" + name)
            partial = True
            continue

        phase_run = getattr(module, "run", None)
        if not callable(phase_run):
            warnings.append("phase_unavailable:" + name)
            partial = True
            continue

        try:
            result = phase_run(qloo, budget, source)
        except Exception as exc:
            warnings.append("phase_error:" + name + ":" + type(exc).__name__)
            partial = True
            continue

        results[name] = result
        phase_warnings = _as_list(_value(result, "warnings", []))
        warnings.extend(str(item) for item in phase_warnings if item is not None)
        provenance.extend(_as_list(_value(result, "provenance", [])))
        evidence.extend(_as_list(_value(result, "evidence", [])))
        if bool(_value(result, "partial", False)):
            partial = True
        if result is None:
            warnings.append("phase_empty:" + name)
            partial = True

    warnings = list(dict.fromkeys(warnings))
    payload = _contract_payload(results, provenance, evidence, warnings, partial)
    try:
        assembled = _assemble_contract(payload)
        if assembled is not None:
            return assembled
        warnings.append("contract_assembly_empty")
    except Exception as exc:
        warnings.append("contract_assembly_failed:" + type(exc).__name__)

    payload = _contract_payload(results, provenance, evidence, list(dict.fromkeys(warnings)), True)
    return _report_result(payload)
