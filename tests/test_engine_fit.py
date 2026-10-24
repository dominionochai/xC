"""Contract tests for asymmetric, evidence-backed fit values."""
import unittest

from engine.fit import fit


class FakeQloo:
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
        "candidate": "candidate", "entity": "candidate", "target": "candidate",
        "item": "candidate", "right": "candidate", "b": "candidate",
        "qloo": "qloo", "client": "qloo", "api": "qloo",
        "evidence": "evidence", "provenance": "provenance",
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


def _value(result):
    if isinstance(result, dict):
        for key in ("value", "fit", "score"):
            if key in result and isinstance(result[key], (int, float)):
                return float(result[key])
    for key in ("value", "fit", "score"):
        val = getattr(result, key, None)
        if isinstance(val, (int, float)):
            return float(val)
    if isinstance(result, (int, float)):
        return float(result)
    raise AssertionError("fit result did not expose a numeric value")


class FitTests(unittest.TestCase):
    def setUp(self):
        self.qloo = FakeQloo()
        self.profile = {
            "id": "source", "value": 0.8,
            "evidence": [{"axis": "genre", "value": 0.8, "strength": "strong",
                          "source": "profile:genre"}],
            "provenance": ["profile:genre"],
        }
        self.strong = {
            "id": "strong-target", "value": 0.75, "match_strength": "strong",
            "evidence": [{"axis": "genre", "value": 0.75, "strength": "strong",
                          "source": "catalog:genre"}],
            "provenance": ["catalog:genre"],
        }
        self.weak = {
            "id": "weak-target", "value": 0.75, "match_strength": "weak",
            "evidence": [{"axis": "genre", "value": 0.75, "strength": "weak",
                          "source": "catalog:genre-weak"}],
            "provenance": ["catalog:genre-weak"],
        }

    def _fit(self, profile, candidate):
        return _invoke(fit, {"profile": profile, "candidate": candidate,
                             "qloo": self.qloo,
                             "evidence": candidate.get("evidence"),
                             "provenance": candidate.get("provenance")})

    def test_strong_evidence_produces_greater_value_than_weak_evidence(self):
        strong_value = _value(self._fit(self.profile, self.strong))
        weak_value = _value(self._fit(self.profile, self.weak))
        self.assertGreater(strong_value, weak_value)

    def test_fit_is_asymmetric_when_source_and_target_are_reversed(self):
        forward = _value(self._fit(self.profile, self.strong))
        reverse = _value(self._fit(self.strong, self.profile))
        self.assertNotEqual(forward, reverse)

    def test_result_retains_evidence_and_provenance(self):
        result = self._fit(self.profile, self.strong)
        rendered = repr(result)
        self.assertIn("profile:genre", rendered)
        self.assertIn("catalog:genre", rendered)
        self.assertIn("evidence", rendered.lower())
        self.assertIn("provenance", rendered.lower())


if __name__ == "__main__":
    unittest.main()
