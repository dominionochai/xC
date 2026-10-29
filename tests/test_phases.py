"""Contract tests for the deterministic W4 phase agents."""
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from agents.phases import AGENTS, PHASES, validate_narration


class PhaseAgentTests(unittest.TestCase):
    def setUp(self):
        self.qloo = SimpleNamespace()
        self.budget = SimpleNamespace(max_calls=4)
        self.inputs = {
            "NORMALIZATION": {"entities": ["artist"]},
            "GRAPH_QUERYING": {"domains": ["music"]},
            "BRIDGE_DISCOVERY": {},
            "ADVERSARIAL_AUDIT": {"communities": ["listeners"]},
            "SYNTHESIS": {"sections": ["summary"]},
        }

    def test_all_phase_plans_are_deterministic_without_an_llm(self):
        numeric_phases = {
            "NORMALIZATION",
            "BRIDGE_DISCOVERY",
            "ADVERSARIAL_AUDIT",
        }
        for phase in PHASES:
            with self.subTest(phase=phase):
                # Instantiate the repository's concrete class with its default
                # (unconfigured) LLM rather than testing a duplicate plan.
                agent = AGENTS[phase]()
                self.assertIsNone(agent.llm)
                first = agent.plan(
                    self.qloo, self.budget, self.inputs[phase]
                )
                second = agent.plan(
                    self.qloo, self.budget, self.inputs[phase]
                )

                self.assertEqual(first, second)
                self.assertEqual(first["summary_source"], "template")
                if phase in numeric_phases:
                    self.assertEqual(first["numbers_from"], "engine")
                elif "numbers_from" in first:
                    self.assertEqual(first["numbers_from"], "engine")

    def test_execute_accepts_fake_engine_functions(self):
        candidates = {
            "NORMALIZATION": ("normalize", "normalise", "resolve"),
            "GRAPH_QUERYING": ("fit", "contrast", "query"),
            "BRIDGE_DISCOVERY": ("bridge", "discover_bridges"),
            "ADVERSARIAL_AUDIT": ("tam", "simulate", "audit", "communities"),
            "SYNTHESIS": ("assemble", "synthesize", "synthesise", "build_report"),
        }
        for phase in PHASES:
            with self.subTest(phase=phase):
                expected = {"phase": phase, "status": "fake-engine"}
                fake_module = ModuleType("fake_phase_engine")

                def fake_engine(qloo, budget, result=expected):
                    return result

                setattr(fake_module, candidates[phase][0], fake_engine)
                agent = AGENTS[phase]()
                with patch("importlib.import_module", return_value=fake_module):
                    result = agent.execute(self.qloo, self.budget)
                self.assertIsInstance(result, dict)
                self.assertEqual(result, expected)

    def test_validate_narration_rejects_missing_ledger_references(self):
        with self.assertRaises(ValueError):
            validate_narration(
                "The claim is supported [E-missing].",
                ["E-missing"],
                [{"id": "E-present"}],
            )

    def test_validate_narration_accepts_references_in_the_ledger(self):
        text = "The claim is supported [E-1]."
        self.assertEqual(
            validate_narration(text, ["E-1"], [{"id": "E-1"}]), text
        )


if __name__ == "__main__":
    unittest.main()
