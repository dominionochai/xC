import unittest

from backend.methods.p4_additions import (
    simulate_rebellion_full,
    map_simulation_metrics,
    rebellion_pandering_index,
)


class P4AdditionsTests(unittest.TestCase):
    def _communities(self):
        return [
            {"name": "c1", "share": 0.6, "anti_strength": 0.8},
            {"name": "c2", "share": 0.4, "anti_strength": 0.2},
        ]

    def test_assumptions_surfaced(self):
        simulation = simulate_rebellion_full(self._communities(), alignment_gap=0.5, seed=42, runs=200)["simulation"]
        self.assertEqual(simulation["seed"], 42)
        self.assertEqual(simulation["runs"], 200)
        names = {a["name"] for a in simulation["assumptions"]}
        self.assertEqual(names, {"kappa", "kappa2", "lambda", "rounds", "theta", "histogram_bins"})
        for a in simulation["assumptions"]:
            self.assertEqual(a["provenance"], "assumed")

    def test_same_seed_identical(self):
        a = simulate_rebellion_full(self._communities(), alignment_gap=0.5, seed=42, runs=200)["simulation"]
        b = simulate_rebellion_full(self._communities(), alignment_gap=0.5, seed=42, runs=200)["simulation"]
        self.assertEqual(a, b)

    def test_different_seed_diffs(self):
        a = simulate_rebellion_full(self._communities(), alignment_gap=0.5, seed=1, runs=200)["simulation"]
        b = simulate_rebellion_full(self._communities(), alignment_gap=0.5, seed=2, runs=200)["simulation"]
        self.assertNotEqual(a["histogram"]["counts"], b["histogram"]["counts"])

    def test_null_path(self):
        result = simulate_rebellion_full([], alignment_gap=0.5)
        self.assertIsNone(result["simulation"])
        self.assertEqual(result["warning"], "no_communities")

    def test_map_simulation_metrics(self):
        result = simulate_rebellion_full(self._communities(), alignment_gap=0.5, seed=42, runs=200)
        metrics = map_simulation_metrics(result["simulation"], self._communities())
        names = [m["name"] for m in metrics]
        self.assertIn("ip_value_at_risk_pct", names)
        self.assertIn("rebellion_distribution", names)
        self.assertTrue(any(n.startswith("rebellion_probability:") for n in names))
        self.assertTrue(any(n.startswith("core_audience_share:") for n in names))
        for m in metrics:
            self.assertEqual(m["provenance"], "modeled")

    def test_emitter_events(self):
        class FakeEmitter:
            def __init__(self):
                self.events = []
            def emit(self, event_type, payload=None):
                self.events.append(event_type)

        emitter = FakeEmitter()
        simulate_rebellion_full(self._communities(), alignment_gap=0.5, seed=42, runs=200, emitter=emitter)
        self.assertIn("simulation.started", emitter.events)
        self.assertIn("simulation.community", emitter.events)
        progress = [e for e in emitter.events if e == "simulation.progress"]
        self.assertGreaterEqual(len(progress), 25)
        self.assertLessEqual(len(progress), 40)

    def test_pandering_worked_example(self):
        result = rebellion_pandering_index([0.2, 0.4], [0.5, 0.1], [0.3, 0.3])
        self.assertAlmostEqual(result["score"], 17.0, places=6)
        self.assertAlmostEqual(result["components"]["contradiction"], 0.3, places=8)
        self.assertAlmostEqual(result["components"]["overclaim"], 0.0, places=8)
        self.assertAlmostEqual(result["components"]["alignment_gap"], 0.1, places=8)
        self.assertEqual(result["method_ref"], "pandering-index-v1")

    def test_pandering_components(self):
        result = rebellion_pandering_index([0.9, 0.8], [0.6, 0.4], [0.2, 0.2])
        self.assertGreater(result["components"]["overclaim"], 0)
        self.assertGreater(result["components"]["contradiction"], 0)
        self.assertGreater(result["components"]["alignment_gap"], 0)
