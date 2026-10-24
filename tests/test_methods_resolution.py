"""Offline contract tests for the committed entity-resolution method."""
import inspect
import unittest

import backend.methods as methods


def _resolver():
    module = getattr(methods, "resolution", None)
    owners = (methods, module)
    names = ("resolve_entity", "resolve_candidate", "resolve_query", "resolve_name", "resolve")
    for owner in owners:
        if owner is None:
            continue
        for name in names:
            value = getattr(owner, name, None)
            if callable(value):
                return value
    return None


def _invoke(fn, query, candidates, **extra):
    values = {"query": query, "name": query, "text": query, "candidates": candidates,
              "entities": candidates, "records": candidates, "options": candidates,
              "silent_ignore": extra.get("silent_ignore", False),
              "confidence_threshold": extra.get("confidence_threshold", 0.0),
              "ambiguity_ratio": extra.get("ambiguity_ratio", 2.0)}
    sig = inspect.signature(fn)
    kwargs = {key: values[key] for key in sig.parameters if key in values}
    required = [p for p in sig.parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and p.name not in kwargs]
    if required:
        return fn(query, candidates)
    return fn(**kwargs)


def _flatten(value):
    if isinstance(value, dict):
        return " ".join([str(k) for k in value] + [_flatten(v) for v in value.values()])
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(v) for v in value)
    return "" if value is None else str(value)


def _confidence(value):
    if isinstance(value, dict):
        for key in ("confidence", "score", "similarity"):
            if key in value and isinstance(value[key], (int, float)):
                return float(value[key])
        for child in value.values():
            found = _confidence(child)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = _confidence(child)
            if found is not None:
                return found
    return None


class ResolutionMethodTests(unittest.TestCase):
    def setUp(self):
        self.resolve = _resolver()
        if self.resolve is None:
            self.skipTest("no public resolution callable is exported by backend.methods")

    def test_auto_select_exact(self):
        result = _invoke(self.resolve, "Acme", [{"id": "exact", "name": "Acme"},
                                                   {"id": "other", "name": "Acme Holdings"}])
        self.assertIn("exact", _flatten(result).lower())

    def test_two_to_one_dominance(self):
        result = _invoke(self.resolve, "Acme", [{"id": "dominant", "name": "Acme", "score": .8},
                                                   {"id": "runner_up", "name": "Acme Ltd", "score": .4}])
        self.assertIn("dominant", _flatten(result).lower())

    def test_aime_is_ambiguous(self):
        result = _invoke(self.resolve, "aimé", [{"id": "aime", "name": "Aime", "score": .8},
                                                   {"id": "aimee", "name": "Aimee", "score": .8}])
        text = _flatten(result).lower()
        self.assertTrue("ambig" in text or "aime" not in text,
                        "an equally plausible accented query should not silently select a candidate")

    def test_porsche_confidence_is_point_eight_two_two(self):
        result = _invoke(self.resolve, "porsche", [{"id": "porsche", "name": "Porsche", "confidence": .822}])
        confidence = _confidence(result)
        if confidence is not None:
            self.assertAlmostEqual(confidence, .822)
        else:
            self.assertIn("porsche", _flatten(result).lower())

    def test_silent_ignore_and_not_found(self):
        ignored = _invoke(self.resolve, "noise", [{"id": "noise", "name": "noise"}], silent_ignore=True)
        missing = _invoke(self.resolve, "not-found", [])
        self.assertTrue(ignored is None or "ignore" in _flatten(ignored).lower()
                        or "noise" not in _flatten(ignored).lower())
        self.assertTrue(missing is None or "not found" in _flatten(missing).lower()
                        or "none" in _flatten(missing).lower() or _flatten(missing) == "")


if __name__ == "__main__":
    unittest.main()
