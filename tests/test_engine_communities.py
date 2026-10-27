"""Contract tests for category communities and degenerate fallback."""
import unittest

from engine.communities import communities


class FakeQloo:
    """Deterministic API double with a visible request count."""
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.call_count = 0

    def _call(self, *args, **kwargs):
        self.call_count += 1
        return self.responses.pop(0) if self.responses else {"results": []}

    search = _call
    search_entities = _call
    lookup = _call
    request = _call


def _invoke(fn, values):
    import inspect
    aliases = {
        "items": "items", "entities": "items", "nodes": "items", "records": "items",
        "qloo": "qloo", "client": "qloo", "api": "qloo",
        "method": "method", "strategy": "method", "group_by": "method",
        "co_weights": "co_weights", "weights": "co_weights",
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


def _groups(result):
    if isinstance(result, dict):
        for key in ("groups", "communities", "clusters"):
            if key in result:
                value = result[key]
                return list(value.values()) if isinstance(value, dict) else list(value)
    for key in ("groups", "communities", "clusters"):
        value = getattr(result, key, None)
        if value is not None:
            return list(value.values()) if isinstance(value, dict) else list(value)
    if isinstance(result, (list, tuple)):
        return list(result)
    raise AssertionError("community result did not expose groups")


class CommunitiesTests(unittest.TestCase):
    def test_category_grouping_creates_three_communities(self):
        qloo = FakeQloo()
        items = [
            {"id": "p1", "category": "pop"},
            {"id": "p2", "category": "pop"},
            {"id": "j1", "category": "jazz"},
            {"id": "j2", "category": "jazz"},
            {"id": "c1", "category": "classical"},
            {"id": "c2", "category": "classical"},
        ]
        result = _invoke(communities, {
            "items": items, "qloo": qloo, "method": "category",
            "co_weights": None,
        })
        groups = _groups(result)
        self.assertEqual(len(groups), 3)
        rendered = repr(result).lower()
        self.assertIn("pop", rendered)
        self.assertIn("jazz", rendered)
        self.assertIn("classical", rendered)

    def test_degenerate_categories_fall_back_to_co_weighting(self):
        qloo = FakeQloo()
        items = [
            {"id": "a", "category": "same"},
            {"id": "b", "category": "same"},
            {"id": "c", "category": "same"},
        ]
        result = _invoke(communities, {
            "items": items, "qloo": qloo, "method": "category",
            "co_weights": {"a": {"b": 0.9}, "b": {"c": 0.7}},
        })
        self.assertIn("co_weighting", repr(result).lower())


if __name__ == "__main__":
    unittest.main()
