"""Offline unittest coverage for bridge discovery and budgets."""
import importlib
import inspect
import unittest


class FakeQloo:
    def __init__(self, response=None):
        self.response = [] if response is None else response
        self.call_count = 0

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        def call(*args, **kwargs):
            self.call_count += 1
            return self.response
        return call


def _engine():
    for name in ("src.engine", "engine", "xc.engine", "xC.engine", "src.xc.engine", "app.engine"):
        try:
            module = importlib.import_module(name)
            cls = getattr(module, "Engine", getattr(module, "QlooEngine", None))
            fake = FakeQloo()
            if cls is None:
                return module, fake
            params = inspect.signature(cls).parameters
            for key in ("qloo", "client", "provider", "qloo_client"):
                if key in params:
                    return cls(**{key: fake}), fake
            try:
                return cls(qloo=fake), fake
            except TypeError:
                try:
                    return cls(fake), fake
                except TypeError:
                    return cls(), fake
        except ImportError:
            continue
    raise ImportError("Could not import the engine module")


def _call(target, **kwargs):
    fn = next((getattr(target, name) for name in ("bridge", "find_bridge", "bridge_search") if callable(getattr(target, name, None))), None)
    if fn is None:
        raise AttributeError("Engine has no bridge operation")
    params = inspect.signature(fn).parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    accepted = {key: value for key, value in kwargs.items() if key in params}
    if accepted:
        return fn(**accepted)
    positional = [p for p in params.values() if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    return fn(kwargs) if len(positional) == 1 else fn()


def _plain(value):
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump())
    if hasattr(value, "dict") and callable(value.dict):
        return _plain(value.dict())
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _plain(vars(value))
    return value


def _status(value):
    value = _plain(value)
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"status", "state", "outcome", "bridge_status"} and isinstance(item, str):
                return item.lower().replace("-", "_")
        for item in value.values():
            found = _status(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _status(item)
            if found:
                return found
    elif isinstance(value, str):
        normalized = value.lower().replace("-", "_")
        if normalized in {"found", "not_found", "not_needed", "partial"}:
            return normalized
    return None


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.fake = _engine()
        self.target = self.engine

    def bridge(self, **overrides):
        inputs = dict(fit=20, fit_score=20, fit_ratio=0.2,
                      bridges=[{"id": "bridge-1", "name": "Bridge"}],
                      candidates=[{"id": "bridge-1", "name": "Bridge"}],
                      bridge_candidates=[{"id": "bridge-1", "name": "Bridge"}],
                      budget=10, call_budget=10)
        inputs.update(overrides)
        return _plain(_call(self.target, **inputs))

    def test_weak_fit_finds_bridge(self):
        result = self.bridge()
        self.assertEqual(_status(result), "found", result)

    def test_no_bridge_returns_not_found(self):
        result = self.bridge(bridges=[], candidates=[], bridge_candidates=[])
        self.assertEqual(_status(result), "not_found", result)

    def test_fit_seventy_does_not_need_bridge(self):
        result = self.bridge(fit=70, fit_score=70, fit_ratio=0.70)
        self.assertEqual(_status(result), "not_needed", result)

    def test_budget_exhaustion_is_partial(self):
        result = self.bridge(budget=1, call_budget=1,
            bridges=[{"id": "b1"}, {"id": "b2"}],
            candidates=[{"id": "b1"}, {"id": "b2"}],
            bridge_candidates=[{"id": "b1"}, {"id": "b2"}])
        self.assertEqual(_status(result), "partial", result)
        self.assertLessEqual(self.fake.call_count, 1)


if __name__ == "__main__":
    unittest.main()
