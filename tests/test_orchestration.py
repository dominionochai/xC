"""Tests for the gated deterministic orchestration vertical slice."""
import unittest
from backend.src.orchestration import (
    AnalysisPhase, AnalysisPlan, ResearchExecutionResults, XcOrchestrator,
)
from backend.src.orchestration.gates import GateError, gate_input
from backend.src.services.presets import get_preset, list_presets

class OrchestrationTests(unittest.TestCase):
    def make_plan(self, **changes):
        values = dict(source_entity_id="source", comparison_entity_id="target", entity_type="urn:entity:brand", regions={"US": 800, "CA": 200}, annual_spend_per_person=15.5, preset_id="market_entry")
        values.update(changes)
        return AnalysisPlan(**values)

    def test_five_gated_phases_and_report_shapes(self):
        research = ResearchExecutionResults(["shared", "source-interest"], ["shared", "target-interest"])
        result = XcOrchestrator().run(self.make_plan(), research)
        self.assertEqual([phase.phase for phase in result.phases], list(AnalysisPhase))
        report = result.to_dict()
        self.assertEqual(report["transition_bridge"], ["source", "shared", "target"])
        self.assertEqual(report["tam"]["tam_usd"], 15500.0)
        self.assertEqual(report["geographic_market_split"][0]["region"], "CA")
        self.assertEqual(report["fanbacklash_risk"]["risk"], "medium")
        self.assertTrue(report["analyst_review"]["approved"])

    def test_empty_affinity_coverage_is_unknown_not_low(self):
        result = XcOrchestrator().run(self.make_plan(), ResearchExecutionResults([], []))
        self.assertEqual(result.report["fanbacklash_risk"]["risk"], "unknown")
        self.assertIsNone(result.report["fanbacklash_risk"]["score"])

    def test_input_gate_rejects_invalid_region_population(self):
        with self.assertRaises(GateError):
            gate_input(self.make_plan(regions={"US": -1}))

    def test_presets_are_three_known_copyable_options(self):
        presets = list_presets()
        self.assertEqual({preset["id"] for preset in presets}, {"brand_launch", "brand_repositioning", "market_entry"})
        preset = get_preset("market_entry")
        preset["name"] = "caller mutation"
        self.assertEqual(get_preset("market_entry")["name"], "Market entry")

if __name__ == "__main__":
    unittest.main()
