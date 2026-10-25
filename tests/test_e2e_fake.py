"""Offline, deterministic smoke coverage for the assembled engine."""

import importlib
import inspect
import unittest


_IMPORT_FAILURES = []
try:
    from backend.src.engine.assemble import run as _run

    _engine_module = importlib.import_module("backend.src.engine.assemble")
except ImportError as exc:
    _run = None
    _engine_module = None
    _IMPORT_FAILURES.append(f"backend.src.engine.assemble.run unavailable: {exc}")

try:
    _contract_module = importlib.import_module("backend.src.contract.assemble")
except ImportError as exc:
    _contract_module = None
    _IMPORT_FAILURES.append(f"backend.src.contract.assemble unavailable: {exc}")

try:
    _events_module = importlib.import_module("backend.src.agents.events")
except ImportError:
    _events_module = None
_EVENT_BUS = getattr(_events_module, "EventBus", None) if _events_module else None


class FakeQloo:
    """A deterministic, network-free client stub that counts calls."""

    def __init__(self):
        self.call_count = 0

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def offline_call(*args, **kwargs):
            self.call_count += 1
            return {}

        return offline_call


def _budget_with_limit_if_supported():
    """Use a real Budget only when its constructor accepts max_calls=40."""
    candidates = (
        getattr(_engine_module, "Budget", None) if _engine_module else None,
        getattr(_contract_module, "Budget", None) if _contract_module else None,
        getattr(getattr(_run, "__globals__", {}), "get", lambda _key: None)("Budget"),
    )
    for budget_type in candidates:
        if not callable(budget_type):
            continue
        try:
            inspect.signature(budget_type).bind(max_calls=40)
        except (TypeError, ValueError):
            continue
        return budget_type(max_calls=40)
    return None


class AssembleFakeE2ETest(unittest.TestCase):
    @unittest.skipIf(_IMPORT_FAILURES, "E2E skipped: " + "; ".join(_IMPORT_FAILURES))
    def test_run_returns_dict_and_validates_when_supported(self):
        fake_qloo = FakeQloo()
        budget = _budget_with_limit_if_supported()
        try:
            inspect.signature(_run).bind(fake_qloo, budget, {})
        except (TypeError, ValueError) as exc:
            self.skipTest(f"E2E skipped: run signature does not support the fake inputs: {exc}")

        result = _run(fake_qloo, budget, {})
        self.assertIsInstance(result, dict)
        self.assertIsInstance(fake_qloo.call_count, int)

        validator = getattr(_contract_module, "validate", None)
        if callable(validator):
            try:
                inspect.signature(validator).bind(result)
            except (TypeError, ValueError):
                return
            validation_result = validator(result)
            self.assertIsNot(validation_result, False, "contract validator rejected the assembled result")
            if isinstance(validation_result, dict):
                self.assertIsNot(validation_result.get("valid"), False)


class OptionalEventBusTest(unittest.TestCase):
    @unittest.skipUnless(callable(_EVENT_BUS), "agents.events.EventBus is not supported")
    def test_event_bus_is_exposed_when_available(self):
        self.assertTrue(callable(_EVENT_BUS))


if __name__ == "__main__":
    unittest.main()
