"""Deterministic, offline contract tests for engine simulation."""
import importlib
import inspect
import json
import unittest


class FakeQloo:
    def __init__(self, response=None):
        self.response = response if response is not None else {}
        self.call_count = 0

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        def call(*args, **kwargs):
            self.call_count += 1
            return self.response
        return call


def _api():
    errors = []
    for name in ("src.engine", "engine", "xc.engine", "xC.engine", "src.xc.engine", "app.engine"):
        try:
            module = importlib.import_module(name)
            cls = getattr(module, "Engine", getattr(module, "QlooEngine", None))
            return module, cls
        except ImportError as exc:
            errors.append(exc)
    raise ImportError("Could not import the engine module") from (errors[-1] if errors else None)


def _engine(cls, module):
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


def _invoke(target, names, **kwargs):
    fn = next((getattr(target, n) for n in names if callable(getattr(target, n, None))), None)
    if fn is None:
        raise AttributeError("No callable found for " + ", ".join(names))
    sig = inspect.signature(fn)
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    accepted = {k: v for k, v in kwargs.items() if k in params}
    if accepted:
        return fn(**accepted)
    positional = [p for p in params.values() if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    if len(positional) == 1:
        return fn(kwargs)
    return fn()


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


def _find_key(value, keys):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in keys:
                return item
        for item in value.values():
            found = _find_key(item, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_key(item, keys)
            if found is not None:
                return found
    return None


def _numbers(value):
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return sum((_numbers(v) for v in value.values()), [])
    if isinstance(value, (list, tuple)):
        return sum((_numbers(v) for v in value), [])
    return []


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.module, self.cls = _api()
        self.engine, self.fake = _engine(self.cls, self.module)
        self.operation = self.engine if self.cls is not None else self.module

    def simulate(self, seed):
        return _plain(_invoke(self.operation, ("simulate", "simulation", "run_simulation"),
            communities=[0.6, 0.4], audience=[0.8, 0.2], a=[0.8, 0.2],
            alignment_gap=0.5, fit_ratio=[0.9, 0.5], seed=seed, runs=200,
            iterations=200, n=200))

    def test_seed_42_golden_input_and_distribution_invariants(self):
        result = self.simulate(42)
        quantiles = _find_key(result, {"quantiles", "quantile"})
        self.assertIsNotNone(quantiles, result)
        qvalues = _numbers(quantiles)
        self.assertGreaterEqual(len(qvalues), 2)
        self.assertEqual(qvalues, sorted(qvalues))

        probabilities = _find_key(result, {"probabilities", "probability", "probs"})
        self.assertIsNotNone(probabilities, result)
        for probability in _numbers(probabilities):
            self.assertGreaterEqual(probability, 0.0)
            self.assertLessEqual(probability, 1.0)

        histogram = _find_key(result, {"histogram", "hist"})
        self.assertIsNotNone(histogram, result)
        hi = _find_key(histogram, {"hi", "high", "max"})
        self.assertIsNotNone(hi, histogram)
        self.assertGreaterEqual(hi, 20)
        self.assertEqual(hi % 5, 0)
        counts = _find_key(histogram, {"counts", "count", "frequencies"})
        self.assertIsNotNone(counts, histogram)
        self.assertEqual(sum(_numbers(counts)), 200)

    def test_same_seed_is_byte_identical(self):
        first = json.dumps(self.simulate(42), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        second = json.dumps(self.simulate(42), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_different_seeds_differ(self):
        self.assertNotEqual(self.simulate(42), self.simulate(43))


if __name__ == "__main__":
    unittest.main()
