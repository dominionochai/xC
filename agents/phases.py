"""Deterministic W4 phase agents; LLMs may select structure, never budgets."""
from __future__ import annotations

from typing import Any, Mapping

PHASES = ("NORMALIZATION", "GRAPH_QUERYING", "BRIDGE_DISCOVERY", "ADVERSARIAL_AUDIT", "SYNTHESIS")
_SHAPES = {
    "NORMALIZATION": {"entities": list, "passes": int},
    "GRAPH_QUERYING": {"domains": list, "pool_sizes": dict},
    "BRIDGE_DISCOVERY": {"triple_attempts": int},
    "ADVERSARIAL_AUDIT": {"communities": list, "runs": int, "seed": int},
    "SYNTHESIS": {"sections": list},
}


def _items(value: Any) -> list:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def validate_plan(phase: str, plan: Mapping[str, Any]) -> dict:
    """Validate required phase fields and enforce engine-owned numeric values."""
    phase = str(phase).upper()
    if phase not in _SHAPES or not isinstance(plan, Mapping):
        raise ValueError("unknown phase or plan is not a mapping")
    out = dict(plan)
    for key, typ in _SHAPES[phase].items():
        if key not in out or not isinstance(out[key], typ) or (typ is int and isinstance(out[key], bool)):
            raise ValueError(f"invalid {phase}.{key}")
    if phase == "GRAPH_QUERYING" and not all(isinstance(k, str) and isinstance(v, int) and v >= 0 for k, v in out["pool_sizes"].items()):
        raise ValueError("invalid GRAPH_QUERYING.pool_sizes")
    if phase in ("NORMALIZATION", "BRIDGE_DISCOVERY", "ADVERSARIAL_AUDIT"):
        out["numbers_from"] = "engine"
    return out


class PhaseAgent:
    phase = ""

    def __init__(self, llm: Any = None):
        self.llm = llm

    def plan(self, qloo: Any, budget: Any, inputs: Any = None) -> dict:
        inputs = inputs if isinstance(inputs, Mapping) else {}
        if self.phase == "NORMALIZATION":
            raw = {"entities": _items(inputs.get("entities")), "passes": 1,
                   "numbers_from": "engine", "summary_source": "template"}
        elif self.phase == "GRAPH_QUERYING":
            raw = {"domains": _items(inputs.get("domains")), "pool_sizes": {},
                   "summary_source": "template"}
        elif self.phase == "BRIDGE_DISCOVERY":
            raw = {"triple_attempts": min(12, max(0, int(getattr(budget, "max_calls", 12)))),
                   "numbers_from": "engine", "summary_source": "template"}
        elif self.phase == "ADVERSARIAL_AUDIT":
            raw = {"communities": _items(inputs.get("communities")), "runs": 1, "seed": 0,
                   "numbers_from": "engine", "summary_source": "template"}
        else:
            raw = {"sections": _items(inputs.get("sections")) or ["summary", "evidence", "limitations"],
                   "summary_source": "template"}
        # Optional LLM output is accepted only for structural selectors. Never copy any number.
        if self.llm is not None:
            chooser = getattr(self.llm, "choose_structure", None)
            if callable(chooser):
                try:
                    choices = chooser(self.phase, qloo=qloo, inputs=dict(inputs))
                    if isinstance(choices, Mapping):
                        for key in ("entities", "domains", "communities", "sections"):
                            if key in raw and isinstance(choices.get(key), list):
                                raw[key] = choices[key]
                        raw["summary_source"] = "template"
                except Exception:
                    pass
        return validate_plan(self.phase, raw)

    def execute(self, qloo: Any, budget: Any) -> Any:
        """Run a compatible deterministic engine/tool function, returning a safe fallback."""
        import importlib
        import inspect
        modules = ("backend.src.engine.resolve", "backend.src.engine.fit", "backend.src.engine.contrast",
                   "backend.src.engine.communities", "backend.src.engine.bridge",
                   "backend.src.engine.simulation", "backend.src.engine.tam", "agents.tools")
        candidates = {
            "NORMALIZATION": ("normalize", "normalise", "resolve"),
            "GRAPH_QUERYING": ("fit", "contrast", "query"),
            "BRIDGE_DISCOVERY": ("bridge", "discover_bridges"),
            "ADVERSARIAL_AUDIT": ("tam", "simulate", "audit", "communities"),
            "SYNTHESIS": ("assemble", "synthesize", "synthesise", "build_report"),
        }[self.phase]
        for module_name in modules:
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue
            for name in candidates:
                fn = getattr(module, name, None)
                if not callable(fn):
                    continue
                try:
                    params = inspect.signature(fn).parameters
                    args = [qloo, budget][:len(params)]
                    return fn(*args)
                except Exception:
                    continue
        return {"phase": self.phase, "status": "unavailable", "evidence": []}

    def narrate(self, result: Any) -> str:
        if isinstance(result, Mapping):
            status = str(result.get("status", "completed"))
            phase = str(result.get("phase", self.phase)).lower().replace("_", " ")
            return f"The {phase} phase {status}. Findings are limited to the returned evidence and engine outputs."
        return f"The {self.phase.lower().replace('_', ' ')} phase completed. Findings are limited to deterministic engine outputs."


class NormalizationAgent(PhaseAgent): phase = "NORMALIZATION"
class GraphQueryingAgent(PhaseAgent): phase = "GRAPH_QUERYING"
class BridgeDiscoveryAgent(PhaseAgent): phase = "BRIDGE_DISCOVERY"
class AdversarialAuditAgent(PhaseAgent): phase = "ADVERSARIAL_AUDIT"
class SynthesisAgent(PhaseAgent): phase = "SYNTHESIS"

AGENTS = {agent.phase: agent for agent in (NormalizationAgent, GraphQueryingAgent, BridgeDiscoveryAgent, AdversarialAuditAgent, SynthesisAgent)}


def validate_narration(text: str, evidence_refs: Any, ledger: Any) -> str:
    """Reject narration citing references absent from the evidence ledger."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("narration must be non-empty text")
    refs = evidence_refs or []
    if isinstance(ledger, Mapping):
        known = set(ledger.keys())
    else:
        known = set()
        for item in ledger or []:
            if isinstance(item, Mapping):
                ref = item.get("id", item.get("ref"))
                if ref is not None:
                    known.add(ref)
            else:
                known.add(item)
    missing = [ref for ref in refs if ref not in known]
    if missing:
        raise ValueError(f"evidence references absent from ledger: {missing!r}")
    return text
