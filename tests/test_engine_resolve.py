"""Contract tests for deterministic entity resolution behavior."""
import unittest

from engine.budget import Budget
from engine.resolve import resolve


class FakeQloo:
    """Small deterministic Qloo stand-in; every API request is counted."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def _call(self, *args, **kwargs):
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return {"results": []}

    search = _call
    search_entities = _call
    lookup = _call
    request = _call


def _invoke(fn, values):
    """Bind common public parameter spellings without coupling to internals."""
    import inspect
    aliases = {
        "query": "query", "text": "query", "name": "query", "entity": "query",
        "qloo": "qloo", "client": "qloo", "api": "qloo",
        "budget": "budget", "mode": "mode", "strategy": "mode",
    }
    sig = inspect.signature(fn)
    kwargs = {}
    has_kwargs = False
    for p in sig.parameters.values():
        if p.kind == p.VAR_KEYWORD:
            has_kwargs = True
        elif p.name in aliases and aliases[p.name] in values:
            kwargs[p.name] = values[aliases[p.name]]
    if has_kwargs:
        kwargs.update({k: v for k, v in values.items() if k not in kwargs})
    return fn(**kwargs)


def _text(value):
    return repr(value).lower()


class ResolveTests(unittest.TestCase):
    def test_strong_auto_match_selects_expected_entity(self):
        qloo = FakeQloo([{"results": [
            {"id": "artist-1", "name": "The Example", "score": 0.99},
            {"id": "artist-2", "name": "Example Tribute", "score": 0.31},
        ]}])
        result = _invoke(resolve, {"query": "The Example", "qloo": qloo,
                                   "budget": Budget(max_calls=5), "mode": "auto"})
        self.assertIn("artist-1", _text(result))
        self.assertIn("strong", _text(result))
        self.assertEqual(qloo.call_count, 1)

    def test_close_candidates_are_reported_as_ambiguous(self):
        qloo = FakeQloo([{"results": [
            {"id": "one", "name": "Mercury", "score": 0.82},
            {"id": "two", "name": "Mercury", "score": 0.81},
        ]}])
        result = _invoke(resolve, {"query": "Mercury", "qloo": qloo,
                                   "budget": Budget(max_calls=5), "mode": "auto"})
        self.assertIn("ambiguous", _text(result))

    def test_empty_response_has_suspect_empty_warning(self):
        qloo = FakeQloo([{"results": []}])
        result = _invoke(resolve, {"query": "Unknown item", "qloo": qloo,
                                   "budget": Budget(max_calls=5), "mode": "auto"})
        self.assertIn("suspect-empty", _text(result).replace("_", "-"))
        self.assertEqual(qloo.call_count, 1)

    def test_budget_exhaustion_returns_partial_without_raising(self):
        qloo = FakeQloo([{"results": [
            {"id": "first", "name": "Alpha", "score": 0.7},
        ]}])
        result = _invoke(resolve, {"query": "Alpha", "qloo": qloo,
                                   "budget": Budget(max_calls=1), "mode": "auto"})
        text = _text(result)
        self.assertIn("partial", text)
        self.assertIn("budget_exhausted:resolve", text)
        self.assertLessEqual(qloo.call_count, 1)


if __name__ == "__main__":
    unittest.main()
