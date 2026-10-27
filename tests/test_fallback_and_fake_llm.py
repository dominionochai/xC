"""Deterministic checks for the template fallback and unconfigured LLM path."""
import importlib
import inspect
import os
import unittest

from agents.llm import LLMWrapper, fallback_plan, template_narrate


_ENV_KEYS = (
    "XC_LLM_MODEL",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
)


class FallbackAndFakeLLMTests(unittest.TestCase):
    def setUp(self):
        self._saved_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_llm_wrapper_is_unconfigured_without_credentials(self):
        wrapper = LLMWrapper()
        configured = getattr(wrapper, "is_configured", None)
        if callable(configured):
            configured = configured()
        if configured is None:
            configured = getattr(wrapper, "configured", None)
            if callable(configured):
                configured = configured()
        self.assertIsNotNone(
            configured,
            "LLMWrapper should expose is_configured or configured state",
        )
        self.assertFalse(configured)

    def test_fallback_plan_uses_template_summary_and_narration_is_text(self):
        plan = fallback_plan()
        if isinstance(plan, dict):
            summary_source = plan.get("summary_source")
        else:
            summary_source = getattr(plan, "summary_source", None)
        self.assertEqual(summary_source, "template")

        narration = template_narrate(plan)
        self.assertIsInstance(narration, str)
        self.assertTrue(narration.strip())

    def test_validate_narration_rejects_hallucinated_evidence_reference(self):
        try:
            phases = importlib.import_module("agents.phases")
        except ImportError:
            self.skipTest("agents.phases is not available")
        validator = getattr(phases, "validate_narration", None)
        if validator is None:
            self.skipTest("agents.phases.validate_narration is not available")

        hallucinated = "Unsupported claim [E999]."
        supported_evidence = [{"id": "E1", "text": "A supported fact."}]
        allowed_refs = {"E1"}
        values = {
            "text": hallucinated,
            "narration": hallucinated,
            "content": hallucinated,
            "claim": hallucinated,
            "evidence": supported_evidence,
            "sources": supported_evidence,
            "facts": supported_evidence,
            "refs": allowed_refs,
            "evidence_refs": allowed_refs,
            "allowed_refs": allowed_refs,
            "allowed_evidence_refs": allowed_refs,
        }
        signature = inspect.signature(validator)
        positional, keywords = [], {}
        for parameter in signature.parameters.values():
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                continue
            if parameter.name in values:
                value = values[parameter.name]
            elif parameter.default is not inspect.Parameter.empty:
                continue
            else:
                self.fail("Cannot supply required validate_narration argument: " + parameter.name)
            if parameter.kind is parameter.KEYWORD_ONLY:
                keywords[parameter.name] = value
            else:
                positional.append(value)

        try:
            result = validator(*positional, **keywords)
        except (ValueError, AssertionError):
            return

        if isinstance(result, bool):
            self.assertFalse(result, "hallucinated evidence reference was accepted")
            return
        if isinstance(result, tuple) and result and isinstance(result[0], bool):
            self.assertFalse(result[0], "hallucinated evidence reference was accepted")
            return
        if isinstance(result, dict):
            for key in ("valid", "is_valid", "accepted"):
                if key in result:
                    self.assertFalse(result[key], "hallucinated evidence reference was accepted")
                    return
        if hasattr(result, "valid"):
            self.assertFalse(result.valid, "hallucinated evidence reference was accepted")
            return
        self.fail("validate_narration returned no recognizable rejection result")

    @unittest.skip("Transport injection is not verified; do not invent a fake-output interface.")
    def test_malformed_fake_output(self):
        pass

    @unittest.skip("Transport injection is not verified; do not invent a timeout interface.")
    def test_fake_transport_timeout(self):
        pass


if __name__ == "__main__":
    unittest.main()
