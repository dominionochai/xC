"""Offline deterministic tests for the M5 rebellion simulation."""

import unittest

from backend.methods.rebellion import simulate_rebellion


class RebellionSimulationTests(unittest.TestCase):
    def test_synthetic_two_community_distribution(self):
        communities = [
            {"name": "community_1", "share": 0.6, "anti_strength": 0.8},
            {"name": "community_2", "share": 0.4, "anti_strength": 0.2},
        ]
        result = simulate_rebellion(
            communities,
            alignment_gap=0.5,
            fit_ratios=[0.9, 0.5],
            seed=42,
            runs=200,
        )

        simulation = result["simulation"]
        self.assertIsNotNone(simulation)
        histogram = simulation["histogram"]
        self.assertEqual(histogram["bins"], 24)
        self.assertEqual(histogram["lo"], 0)
        self.assertGreaterEqual(histogram["hi"], 20)
        self.assertEqual(histogram["hi"] % 5, 0)
        self.assertEqual(sum(histogram["counts"]), 200)

        self.assertGreaterEqual(simulation["mean"], 0)
        self.assertLessEqual(simulation["mean"], 100)
        self.assertLessEqual(simulation["p5"], simulation["median"])
        self.assertLessEqual(simulation["median"], simulation["p95"])
        probabilities = simulation["per_community_rebellion_probability"]
        self.assertEqual(set(probabilities), {"community_1", "community_2"})
        for probability in probabilities.values():
            self.assertGreaterEqual(probability, 0)
            self.assertLessEqual(probability, 1)

        repeated = simulate_rebellion(
            communities,
            alignment_gap=0.5,
            fit_ratios=[0.9, 0.5],
            seed=42,
            runs=200,
        )
        self.assertEqual(simulation, repeated["simulation"])


if __name__ == "__main__":
    unittest.main()
