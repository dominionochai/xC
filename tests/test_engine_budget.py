"""Offline regression coverage for engine budget exhaustion."""

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
    """Deterministic offline backend; every engine phase gets usable data."""

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: {
            "items": [{"id": name, "score": 1.0}],
            "evidence": [{"source": "fake-qloo", "phase": name}],
            "provenance": {"provider": "FakeQloo", "phase": name},
        }


def assemble(qloo, budget):
    """Supply only recognized arguments, keeping this helper offline."""
    signature = inspect.signature(assemble_report)
    values = {
        "qloo": qloo, "client": qloo, "provider": qloo, "api": qloo,
        "budget": budget, "engine_budget": budget,
        "query": "synthetic offline test", "prompt": "synthetic offline test",
    }
    kwargs = {name: values[name] for name in signature.parameters if name in values}
    missing = [
        p for p in signature.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        and p.name not in kwargs
    ]
    if missing:
        raise AssertionError("Unmapped required assemble_report parameters: " + ", ".join(p.name for p in missing))
    return assemble_report(**kwargs)


class EngineBudgetTests(unittest.TestCase):
    def test_exhaustion_across_phases_returns_partial_with_warning(self):
        # Deliberately tiny capacity forces exhaustion after work has begun;
        # it must be represented in the result instead of escaping as an error.
        result = assemble(FakeQloo(), Budget(1))
        self.assertTrue(result.partial)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
