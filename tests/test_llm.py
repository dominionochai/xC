import os
import re
import unittest

from agents.llm import LLMWrapper, fallback_plan, template_narrate


class TestLLMFallbacks(unittest.TestCase):
    ENV_KEYS = (
        "XC_LLM_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
    )

    def setUp(self):
        self._saved_env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        for key in self.ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_wrapper_is_unconfigured_without_provider_environment(self):
        self.assertFalse(LLMWrapper().is_configured())

    def test_normalization_fallback_uses_template_summary(self):
        result = fallback_plan(
            "NORMALIZATION",
            {"input": "Normalize the sample records: alpha, beta."},
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("summary_source"), "template")

    def test_normalization_template_narration_is_brief(self):
        narration = template_narrate(
            "NORMALIZATION",
            evidence_refs=[],
            summary="Normalization completed for the sample records.",
        )
        self.assertIsInstance(narration, str)
        sentences = [
            sentence
            for sentence in re.split(r"(?<=[.!?])\s+", narration.strip())
            if sentence
        ]
        self.assertGreaterEqual(len(sentences), 1)
        self.assertLessEqual(len(sentences), 2)


if __name__ == "__main__":
    unittest.main()
