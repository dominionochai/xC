"""Offline tests for Qloo query-parameter construction and validation."""
import unittest
from urllib.parse import parse_qs

from backend.qloo import (
    ParamError,
    build_insights_params,
    build_search_params,
    encode_params,
    normalize_params,
    validate_base_url,
    validate_endpoint,
    validate_params,
)


class QlooParamsTests(unittest.TestCase):
    def test_search_builder_emits_query_types_take_and_extras(self):
        pairs = build_search_params(
            "Acme",
            entity_types=["brand", "artist"],
            take=5,
            extra={"filter.location.query": "Paris"},
        )
        self.assertEqual(
            pairs,
            [
                ("query", "Acme"),
                ("types", "brand"),
                ("types", "artist"),
                ("take", "5"),
                ("filter.location.query", "Paris"),
            ],
        )

    def test_insights_builder_emits_filter_and_signal_fields(self):
        pairs = build_insights_params(
            entity_types=["brand"],
            take=20,
            filters={"filter.type": "urn:tag"},
            signals={"signal.interests.entities": "brand:acme"},
        )
        self.assertEqual(
            pairs,
            [
                ("filter.type", "brand"),
                ("take", "20"),
                ("filter.type", "urn:tag"),
                ("signal.interests.entities", "brand:acme"),
            ],
        )

    def test_normalize_encode_validate_helpers(self):
        pairs = normalize_params({"query": "Acme", "take": 5})
        self.assertEqual(pairs, [("query", "Acme"), ("take", "5")])
        self.assertEqual(parse_qs(encode_params(pairs)), {"query": ["Acme"], "take": ["5"]})
        self.assertEqual(validate_endpoint("/search"), "/search")
        self.assertEqual(validate_base_url("https://api.example.test/"), "https://api.example.test")
        self.assertEqual(validate_params({"query": "Acme", "take": 5}), {"query": "Acme", "take": 5})

    def test_repeat_and_comma_array_styles_represent_the_same_values(self):
        repeated = encode_params(
            build_search_params("Acme", entity_types=["brand", "artist"], array_style="repeat")
        )
        comma = encode_params(
            build_search_params("Acme", entity_types=["brand", "artist"], array_style="comma")
        )
        self.assertEqual(parse_qs(repeated)["types"], ["brand", "artist"])
        self.assertEqual(parse_qs(comma)["types"][0].split(","), ["brand", "artist"])

    def test_invalid_combinations_raise_param_error(self):
        invalid_calls = (
            lambda: build_search_params("  "),
            lambda: build_search_params("Acme", extra={"query": "override"}),
            lambda: build_search_params("Acme", entity_types=[]),
            lambda: build_search_params("Acme", array_style="unknown"),
            lambda: build_insights_params(
                take=5, filters={"take": 10}, signals={"take": 15}
            ),
            lambda: normalize_params([("x", "one"), ("x", "two")]),
            lambda: validate_endpoint("https://evil.example/search"),
            lambda: validate_params({"array": ["not", "scalar"]}),
        )
        for call in invalid_calls:
            with self.subTest(call=call):
                with self.assertRaises(ParamError):
                    call()


if __name__ == "__main__":
    unittest.main()
