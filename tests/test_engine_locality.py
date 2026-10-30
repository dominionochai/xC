"""Offline unittest coverage for locality granularity handling."""
import importlib
import inspect
import unittest


CAVEAT = "neighborhood granularity not supported by the data provider"


class FakeQloo:
    def __init__(self, response=None):
        self.response = response
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


def _locality(target, **kwargs):
    fn = next((getattr(target, name) for name in ("locality", "resolve_locality", "get_locality") if callable(getattr(target, name, None))), None)
    if fn is None:
        raise AttributeError("Engine has no locality operation")
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


def _strings(value):
    if isinstance(value, dict):
        return sum((_strings(v) for v in value.values()), [])
    if isinstance(value, (list, tuple)):
        return sum((_strings(v) for v in value), [])
    return [value] if isinstance(value, str) else []


def _status(value):
    value = _plain(value)
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"status", "state", "outcome"} and isinstance(item, str):
                return item.lower().replace("-", "_")
        for item in value.values():
            result = _status(item)
            if result:
                return result
    return None


class LocalityTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.fake = _engine()
        self.target = self.engine

    def query(self, level, response):
        self.fake.response = response
        return _plain(_locality(self.target, level=level, granularity=level,
            locality_level=level, levels=[level], location="San Francisco",
            query="San Francisco", localities=response, results=response))

    def test_level_one_locality_succeeds(self):
        result = self.query(1, [{"id": "loc-1", "name": "San Francisco", "level": 1}])
        self.assertIn(_status(result), {"success", "ok", "found"}, result)
        self.assertGreater(self.fake.call_count, 0)

    def test_level_three_returns_exact_provider_granularity_caveat(self):
        result = self.query(3, [{"id": "loc-3", "name": "Neighborhood", "level": 3}])
        self.assertIn(CAVEAT, " ".join(_strings(result)))
        self.assertGreater(self.fake.call_count, 0)

    def test_all_locality_levels_failed(self):
        result = self.query(1, None)
        self.assertIn(_status(result), {"failed", "failure", "error"}, result)


if __name__ == "__main__":
    unittest.main()
