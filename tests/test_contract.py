"""Contract model regression tests; entirely offline."""

import importlib
import json
import unittest
from pathlib import Path

from pydantic import BaseModel, ValidationError

try:
    contract = importlib.import_module("xc.contract")
except ImportError:
    contract = importlib.import_module("xc.contract.models")

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "contract" / "xc-report.schema.json"
FIXTURE_DIR = ROOT / "web" / "src" / "lib" / "fixtures"
REPORT_FIXTURES = sorted(FIXTURE_DIR.glob("report.*.json")) if FIXTURE_DIR.is_dir() else []


def _model_classes():
    return [
        value for value in vars(contract).values()
        if isinstance(value, type) and issubclass(value, BaseModel) and value is not BaseModel
    ]


def _extra_mode(model):
    config = getattr(model, "model_config", None)
    if config is not None:
        return getattr(config, "get", lambda *_: None)("extra")
    return getattr(getattr(model, "__config__", None), "extra", None)


def _sample(schema):
    """Produce a small valid-ish JSON value from a Pydantic JSON schema."""
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    for alternative in schema.get("anyOf", schema.get("oneOf", [])):
        if alternative.get("type") != "null":
            return _sample(alternative)
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = schema.get("required", list(properties))
        return {key: _sample(properties.get(key, {})) for key in required}
    if kind == "array":
        return [_sample(schema.get("items", {}))]
    if kind == "integer":
        return max(0, schema.get("minimum", 0))
    if kind == "number":
        return max(0.0, schema.get("minimum", 0.0))
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "synthetic"


def _validate(model, payload):
    validator = getattr(model, "model_validate", None)
    return validator(payload) if validator else model.parse_obj(payload)


def _json_value(instance):
    dump = getattr(instance, "model_dump", None)
    if dump:
        return dump(mode="json")
    return json.loads(instance.json())


def _report_model():
    candidates = [m for m in _model_classes() if "report" in m.__name__.lower()]
    if not candidates:
        raise AssertionError("No report Pydantic model exported by xc.contract")
    forbidden = [m for m in candidates if str(_extra_mode(m)).lower().endswith("forbid")]
    return forbidden[0] if forbidden else candidates[0]


class ContractTests(unittest.TestCase):
    def test_synthetic_full_report_validates_and_output_rejects_extra_keys(self):
        model = _report_model()
        schema_method = getattr(model, "model_json_schema", None)
        schema = schema_method() if schema_method else model.schema()
        payload = _sample(schema)
        report = _validate(model, payload)
        with self.assertRaises(ValidationError):
            _validate(model, {**_json_value(report), "__unexpected_contract_test_key__": True})

    def test_input_models_tolerate_extra_keys(self):
        input_models = [m for m in _model_classes() if "input" in m.__name__.lower()]
        self.assertTrue(input_models, "No input Pydantic models exported by xc.contract")
        for model in input_models:
            schema_method = getattr(model, "model_json_schema", None)
            schema = schema_method() if schema_method else model.schema()
            payload = _sample(schema)
            try:
                _validate(model, {**payload, "__extra_contract_test_key__": "accepted"})
            except ValidationError as exc:
                self.fail(f"{model.__name__} rejected an extra input key: {exc}")

    @unittest.skipUnless(SCHEMA_PATH.is_file(), "docs/contract/xc-report.schema.json is absent")
    def test_optional_jsonschema_matches_report_model(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        model = _report_model()
        schema_method = getattr(model, "model_json_schema", None)
        report_schema = schema_method() if schema_method else model.schema()
        report = _validate(model, _sample(report_schema))
        with SCHEMA_PATH.open(encoding="utf-8") as stream:
            jsonschema.validate(instance=_json_value(report), schema=json.load(stream))

    @unittest.skipUnless(REPORT_FIXTURES, "web/src/lib/fixtures/report.*.json fixtures are absent")
    def test_optional_report_fixtures_validate(self):
        model = _report_model()
        for path in REPORT_FIXTURES:
            with self.subTest(fixture=path.name), path.open(encoding="utf-8") as stream:
                _validate(model, json.load(stream))


if __name__ == "__main__":
    unittest.main()
