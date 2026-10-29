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
        plan = fallback_plan("NORMALIZATION", {})
        if isinstance(plan, dict):
            summary_source = plan.get("summary_source")
        else:
            summary_source = getattr(plan, "summary_source", None)
        self.assertEqual(summary_source, "template")

        narration = template_narrate("NORMALIZATION", [], "summary")
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
        # Pass hallucinated ref E999 which is not in the ledger
        with self.assertRaises(ValueError) as cm:
            validator(hallucinated, ["E999"], supported_evidence)
        self.assertIn("evidence references absent from ledger", str(cm.exception))

    @unittest.skip("Transport injection is not verified; do not invent a fake-output interface.")
    def test_malformed_fake_output(self):
        pass

    @unittest.skip("Transport injection is not verified; do not invent a timeout interface.")
    def test_fake_transport_timeout(self):
        pass


if __name__ == "__main__":
    unittest.main()
