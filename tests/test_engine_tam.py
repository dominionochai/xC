"""Offline unittest coverage for TAM expansion and source completeness."""
import importlib
import inspect
import unittest


TAM_EXPANSION = "Total Addressable Market"


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


def _tam(target, **kwargs):
    fn = next((getattr(target, name) for name in ("tam", "expand_tam", "total_addressable_market", "market_size") if callable(getattr(target, name, None))), None)
    if fn is None:
        raise AttributeError("Engine has no TAM operation")
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


def _walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def _status(value):
    for key, item in _walk(_plain(value)):
        if key.lower() in {"status", "state", "outcome"} and isinstance(item, str):
            return item.lower().replace("-", "_")
    return None


class TamTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.fake = _engine()
        self.target = self.engine

    def test_tam_expands_exactly(self):
        result = _plain(_tam(self.target, term="TAM", acronym="TAM", query="TAM", metric="TAM"))
        expanded = [item for key, item in _walk(result)
                    if key.lower() in {"expansion", "expanded", "expanded_term", "full_form", "definition"}]
        self.assertIn(TAM_EXPANSION, expanded, result)

    def test_missing_sources_produce_partial_result_and_warning(self):
        self.fake.response = {"sources": [{"name": "source-a"}]}
        result = _plain(_tam(self.target, term="TAM", acronym="TAM", sources=["source-a", "source-b"],
                             available_sources=["source-a"], missing_sources=["source-b"],
                             required_sources=["source-a", "source-b"]))
        self.assertEqual(_status(result), "partial", result)
        warnings = [item for key, item in _walk(result) if "warning" in key.lower()]
        self.assertTrue(warnings, result)
        self.assertTrue(any("source" in str(warning).lower() or warning for warning in warnings), result)
        self.assertGreater(self.fake.call_count, 0)

    def test_all_null_tam_is_none_and_skips_provider(self):
        result = _plain(_tam(self.target, tam=None, value=None, metric=None, term=None,
                             sources=None, data={"tam": None, "value": None}))
        tam_values = [item for key, item in _walk(result) if key.lower() == "tam"]
        self.assertTrue(tam_values, result)
        self.assertIsNone(tam_values[0])
        self.assertEqual(self.fake.call_count, 0)


if __name__ == "__main__":
    unittest.main()
