"""Contract tests for contrast output when profile axes are incomplete."""
import unittest

from engine.contrast import contrast


class FakeQloo:
    """Deterministic API double that records every request."""
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
        "profile": "profile", "source": "profile", "left": "profile", "a": "profile",
        "other": "other", "target": "other", "comparison": "other",
        "right": "other", "b": "other",
        "qloo": "qloo", "client": "qloo", "api": "qloo",
        "budget": "budget",
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


class ContrastTests(unittest.TestCase):
    def test_partial_profile_preserves_null_axes_and_emits_warning(self):
        qloo = FakeQloo()
        profile = {
            "id": "profile-a",
            "axes": {"genre": 0.8, "mood": None, "era": None},
            "warnings": [],
        }
        other = {
            "id": "profile-b",
            "axes": {"genre": 0.6, "mood": 0.4, "era": 0.7},
        }
        result = _invoke(contrast, {
            "profile": profile, "other": other, "qloo": qloo,
            "budget": None,
        })
        rendered = repr(result).lower()
        self.assertIn("null", rendered)
        self.assertIn("warning", rendered)
        self.assertIn("mood", rendered)
        self.assertIn("era", rendered)


if __name__ == "__main__":
    unittest.main()
