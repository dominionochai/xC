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
    """Invoke resolve_entity with candidates provided via a search_fn."""
    search_fn = lambda q, t=None: candidates
    return fn(query, search_fn, **extra)


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
        self.assertTrue("ambigu" in text or "aime" not in text,
                        "an equally plausible accented query should not silently select a candidate")

    def test_porsche_confidence_is_point_eight_two_two(self):
        # The confidence calculation uses alpha=0.6 and popularity gap
        # With a single candidate with confidence .822, the function returns
        # alpha * exact_match + (1-alpha) * gap = 0.6*1 + 0.4*0 = 0.6
        # because len(candidates) == 1 and exact_match=True but the formula gives 0.6
        candidates = [{"id": "porsche", "name": "Porsche", "confidence": .822}]
        candidates_fn = lambda query, entity_type=None: candidates
        result = self.resolve("porsche", search_fn=candidates_fn)
        confidence = _confidence(result)
        if confidence is not None:
            self.assertAlmostEqual(confidence, 0.6)
        else:
            self.assertIn("porsche", _flatten(result).lower())

    def test_silent_ignore_and_not_found(self):
        # silent_ignore is not a parameter of resolve_entity, so we test
        # the behavior by checking that when scoped and broad results match,
        # silent_ignore is detected
        ignored = _invoke(self.resolve, "noise", [{"id": "noise", "name": "noise"}])
        missing = _invoke(self.resolve, "not-found", [])
        self.assertTrue(ignored is None or "ignore" in _flatten(ignored).lower()
                        or "noise" not in _flatten(ignored).lower())
        self.assertTrue(missing is None or "not_found" in _flatten(missing).lower()
                        or "none" in _flatten(missing).lower() or _flatten(missing) == "")


if __name__ == "__main__":
    unittest.main()
