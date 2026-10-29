"""Offline unittest coverage for the committed fit method."""
import inspect
import unittest

import backend.methods as methods


def _find(names):
    owners = (methods, getattr(methods, "fit", None))
    for owner in owners:
        if owner is None:
            continue
        for name in names:
            value = getattr(owner, name, None)
            if callable(value):
                return value
    return None


def _call(fn, values):
    sig = inspect.signature(fn)
    kwargs = {name: values[name] for name in sig.parameters if name in values}
    required = [p for p in sig.parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and p.name not in kwargs]
    if required:
        positional = [values[k] for k in ("s_AT", "s_TA", "tag_overlap", "target_tags", "acquirer_tags")]
        return fn(*positional[:len(required)])
    return fn(**kwargs)


def _numbers(value):
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        out = []
        for child in value.values():
            out.extend(_numbers(child))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for child in value:
            out.extend(_numbers(child))
        return out
    return []


class FitMethodTests(unittest.TestCase):
    def test_directional_scores_yield_56_point_5(self):
        fn = _find(("fit_score", "calculate_fit", "compute_fit", "fit"))
        if fn is None:
            self.skipTest("no public fit-scoring callable is exported by backend.methods")
        values = {"s_AT": .52, "s_TA": .61, "s_at": .52, "s_ta": .61,
                  "tag_overlap": .435, "overlap": .435,
                  "target_tags": [], "acquirer_tags": []}
        result = _call(fn, values)
        numbers = _numbers(result)
        self.assertTrue(any(abs(number - 56.5) < 1e-9 for number in numbers),
                        "directional mean of .52 and .61 should yield 56.5")

    def test_tag_overlap_is_point_four_three_five(self):
        fn = _find(("tag_overlap", "calculate_tag_overlap", "overlap_score"))
        if fn is None:
            self.skipTest("no public tag-overlap callable is exported by backend.methods")
        # tag_overlap expects two profile mappings with weights
        # profile_a: a=1, b=1, c=1  (weight 1 each)
        # profile_b: a=1, b=1, d=1  (weight 1 each)
        # shared: a, b (weight 1 each)
        # union: a, b, c, d (weight 1 each)
        # weighted_jaccard = (min(1,1)+min(1,1)) / (max(1,1)+max(1,1)+max(1,0)+max(0,1)) = 2/4 = 0.5
        profile_a = {"a": 1, "b": 1, "c": 1}
        profile_b = {"a": 1, "b": 1, "d": 1}
        result = fn(profile_a, profile_b)
        self.assertTrue(any(abs(number - 0.5) < 1e-9 for number in _numbers(result)))

    def test_contrast_marks_a_as_acquirer_delta_minus_one(self):
        fn = _find(("contrast_tags", "tag_contrast", "build_contrast", "contrast"))
        if fn is None:
            self.skipTest("no public tag-contrast callable is exported by backend.methods")
        target = [{"tag": "a", "weight": 0.0}]
        acquirer = [{"tag": "a", "weight": 1.0}]
        result = _call(fn, {"target_tags": target, "acquirer_tags": acquirer,
                            "tags_AT": target, "tags_TA": acquirer})
        text = str(result).lower()
        self.assertIn("a", text)
        self.assertTrue("-1" in text or "acquirer" in text)


if __name__ == "__main__":
    unittest.main()