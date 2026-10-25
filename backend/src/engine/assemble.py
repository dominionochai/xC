"""Run W3 phases and assemble a validated report."""
from __future__ import annotations
import importlib
from collections.abc import Mapping
from typing import Any
from pydantic import BaseModel
from backend.src import contract

_PHASES = ("resolve", "fit", "contrast", "communities", "simulation", "bridge", "locality", "tam")

def _value(obj: Any, name: str, default: Any = None) -> Any:
    return obj.get(name, default) if isinstance(obj, Mapping) else getattr(obj, name, default)

def _as_list(value: Any) -> list[Any]:
    if value is None: return []
    return list(value) if isinstance(value, (list, tuple)) else [value]

def _call_count(qloo: Any) -> int | None:
    count = _value(qloo, "call_count")
    if callable(count):
        try: count = count()
        except Exception: return None
    try: return int(count) if count is not None else None
    except (TypeError, ValueError): return None

def _max_calls(budget: Any) -> int | None:
    limit = _value(budget, "max_calls")
    try: return int(limit) if limit is not None else None
    except (TypeError, ValueError): return None

def _missing_optional_inputs(module: Any, inputs: Mapping[str, Any]) -> list[str]:
    declared = getattr(module, "OPTIONAL_INPUTS", ())
    if isinstance(declared, str): declared = (declared,)
    if not isinstance(declared, (list, tuple, set, frozenset)): declared = ()
    return [name for name in declared if inputs.get(name) is None]

def assemble(phase_outputs: Mapping[str, Any], provenance: Any = None, evidence: Any = None, warnings: Any = None, partial: bool = False) -> contract.ReportResult:
    """Validate typed phase outputs into ReportResult; invalid values raise."""
    if not isinstance(phase_outputs, Mapping):
        raise TypeError("phase_outputs must be a mapping")
    results: dict[str, Any] = {}
    all_warnings = _as_list(warnings)
    all_provenance = _as_list(provenance)
    all_evidence = _as_list(evidence)
    for name, output in phase_outputs.items():
        if isinstance(output, BaseModel):
            output = output.model_dump(mode="python")
        elif isinstance(output, Mapping):
            output = dict(output)
        elif output is not None:
            raise TypeError(f"phase output {name!r} must be a mapping or Pydantic model")
        results[name] = output
        if output is None: continue
        all_warnings.extend(str(item) for item in _as_list(_value(output, "warnings", [])) if item is not None)
        all_provenance.extend(_as_list(_value(output, "provenance", [])))
        all_evidence.extend(_as_list(_value(output, "evidence", [])))
        partial = partial or bool(_value(output, "partial", False))
    all_warnings = list(dict.fromkeys(all_warnings))
    payload = {"status": "partial" if partial else "complete", "results": results,
        "phase_results": results, "phases": results, "data": results,
        "provenance": all_provenance, "evidence": all_evidence,
        "warnings": all_warnings, "partial": bool(partial)}
    return contract.ReportResult.model_validate(payload)

def run(qloo: Any, budget: Any, inputs: dict) -> contract.ReportResult:
    """Execute phases in order, retaining partial output for phase failures."""
    source = inputs if isinstance(inputs, dict) else {}
    results: dict[str, Any] = {}
    warnings: list[str] = []
    partial = False
    if not isinstance(inputs, dict) or not inputs:
        warnings.append("optional_inputs_missing"); partial = True
    for name in _PHASES:
        try: module = importlib.import_module("." + name, package=__package__)
        except ImportError:
            warnings.append("phase_unavailable:" + name); partial = True; continue
        for key in _missing_optional_inputs(module, source):
            warnings.append("optional_input_missing:" + key); partial = True
        count, limit = _call_count(qloo), _max_calls(budget)
        if count is not None and limit is not None and count >= limit:
            warnings.append("budget_exhausted:" + name); partial = True; continue
        phase_run = getattr(module, "run", None)
        if not callable(phase_run):
            warnings.append("phase_unavailable:" + name); partial = True; continue
        try: result = phase_run(qloo, budget, source)
        except Exception as exc:
            warnings.append("phase_error:" + name + ":" + type(exc).__name__); partial = True; continue
        results[name] = result
        if result is None:
            warnings.append("phase_empty:" + name); partial = True
        if bool(_value(result, "partial", False)): partial = True
    return assemble(results, warnings=warnings, partial=partial)
