"""Offline tests for report assembly and budget exhaustion."""

import importlib
import inspect
import unittest

try:
    from xc.engine.budget import Budget
except ImportError:
    from xc.engine import Budget

try:
    from xc.engine.assemble import assemble_report
except ImportError:
    from xc.engine import assemble_report


class FakeQloo:
    """A deterministic Qloo stand-in with no network or credentials."""

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: {
            "items": [{"id": f"offline-{name}", "score": 0.9}],
            "evidence": [{"source": "FakeQloo", "phase": name, "ref": "offline-fixture"}],
            "provenance": {"provider": "FakeQloo", "phase": name},
        }


def _assemble(budget):
    qloo = FakeQloo()
    signature = inspect.signature(assemble_report)
    values = {
        "qloo": qloo, "fake_qloo": qloo, "client": qloo,
        "provider": qloo, "api": qloo,
        "budget": budget, "engine_budget": budget,
        "query": "synthetic offline query", "prompt": "synthetic offline query",
        "request": "synthetic offline query", "subject": "synthetic offline query",
    }
    kwargs = {name: values[name] for name in signature.parameters if name in values}
    missing = [
        p.name for p in signature.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and p.name not in kwargs
    ]
    if missing:
        raise AssertionError("Unmapped required assemble_report parameters: " + ", ".join(missing))
    return assemble_report(**kwargs)


def _field(result, name):
    if isinstance(result, dict):
        return result.get(name)
    return getattr(result, name, None)


def _report_result_type():
    for module_name in ("xc.engine", "xc.engine.assemble", "xc.engine.models", "xc.engine.result"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        candidate = getattr(module, "ReportResult", None)
        if isinstance(candidate, type):
            return candidate
    return None


class EngineAssembleTests(unittest.TestCase):
    def test_budget_40_assembles_report_with_provenance_and_evidence(self):
        result = _assemble(Budget(40))
        result_type = _report_result_type()
        if result_type is not None:
            self.assertIsInstance(result, result_type)
        self.assertIsNotNone(result)
        self.assertTrue(_field(result, "provenance"), "assembled report has no provenance")
        self.assertTrue(_field(result, "evidence"), "assembled report has no evidence")

    def test_budget_exhaustion_is_partial_and_warned_not_raised(self):
        # Any budget exception must be captured by assembly and returned as a
        # partial result with a diagnostic warning rather than propagated.
        result = _assemble(Budget(1))
        self.assertIsNotNone(result)
        self.assertTrue(_field(result, "partial"))
        self.assertTrue(_field(result, "warnings"))


if __name__ == "__main__":
    unittest.main()
