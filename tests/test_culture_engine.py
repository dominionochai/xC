"""Offline unit tests for the culture affinity engine."""
import unittest

from engine.culture_engine import DOMAINS, compare_cultures


class CultureEngineTests(unittest.TestCase):
    def empty_signatures(self):
        return {domain: [] for domain in DOMAINS}

    def test_fixed_domains_are_exact_and_ignore_unapproved_domains(self):
        a, t = self.empty_signatures(), self.empty_signatures()
        t["unapproved_domain"] = ["ignored"]
        result = compare_cultures("A", "T", a, t)
        self.assertEqual(result["fixed_domains"], [
            "brand", "artist", "movie", "tv_show", "podcast", "book", "place", "destination", "person"
        ])
        self.assertEqual(set(result["domains"]), set(DOMAINS))
        self.assertEqual(result["affinity_item_count"], 0)

    def test_directional_means_use_measured_affinity(self):
        a, t = self.empty_signatures(), self.empty_signatures()
        a["brand"], t["brand"] = ["a1", "a2"], ["t1", "t2"]
        values = {("A", "t1"): .4, ("A", "t2"): .8, ("T", "a1"): .2, ("T", "a2"): .6}
        result = compare_cultures("A", "T", a, t,
                                  affinity=lambda source, item, domain: values[(source, item)])
        brand = result["domains"]["brand"]
        self.assertAlmostEqual(brand["F_k"], .6)
        self.assertAlmostEqual(brand["C_k"], .4)
        self.assertEqual([row["affinity"] for row in brand["T_items"]], [.4, .8])

    def test_anti_uses_global_lower_tercile_and_is_a_share(self):
        a, t = self.empty_signatures(), self.empty_signatures()
        t["artist"] = ["i1", "i2", "i3", "i4"]
        values = {"i1": 1, "i2": 2, "i3": 3, "i4": 4}
        result = compare_cultures("A", "T", a, t, affinity=lambda *_args: values[_args[1]])
        self.assertEqual(result["anti_cutoff"], 2.0)
        self.assertAlmostEqual(result["domains"]["artist"]["Anti_k"], .25)
        self.assertFalse(result["anti_axis_flagged"])

    def test_fewer_than_three_affinities_uses_lowest_and_flags_axis(self):
        a, t = self.empty_signatures(), self.empty_signatures()
        t["book"] = ["one", "two"]
        values = {"one": 7, "two": 9}
        result = compare_cultures("A", "T", a, t, affinity=lambda *_args: values[_args[1]])
        self.assertEqual(result["anti_cutoff"], 7.0)
        self.assertTrue(result["anti_axis_flagged"])
        self.assertEqual(result["domains"]["book"]["Anti_k"], 0.0)

    def test_rank_n_switch_ranks_within_batch_and_keeps_raw_measurements(self):
        a, t = self.empty_signatures(), self.empty_signatures()
        t["movie"] = ["low", "mid", "high"]
        def batch(_source, items, _domain):
            values = {"low": 10, "mid": 20, "high": 30}
            return {item: values[item] for item in items}
        result = compare_cultures("A", "T", a, t, batch_affinity=batch, normalization_family="rank_n")
        movie = result["domains"]["movie"]
        self.assertEqual(result["normalization_family"], "rank_n")
        self.assertAlmostEqual(movie["F_k"], 2 / 3)
        self.assertEqual([row["affinity"] for row in movie["T_items"]], [10.0, 20.0, 30.0])
        self.assertEqual([row["normalized_affinity"] for row in movie["T_items"]], [1/3, 2/3, 1.0])

    def test_single_call_fallback_counts_calls_and_reports_budget_implication(self):
        a, t = self.empty_signatures(), self.empty_signatures()
        for domain in DOMAINS:
            a[domain] = [f"a-{domain}-{i}" for i in range(5)]
            t[domain] = [f"t-{domain}-{i}" for i in range(5)]
        calls = []
        result = compare_cultures("A", "T", a, t,
                                  affinity=lambda source, item, domain: calls.append((source, item, domain)) or 1)
        budget = result["call_budget"]
        self.assertEqual(len(calls), 90)
        self.assertEqual(budget["calls_used"], 90)
        self.assertEqual(budget["calls_if_single_fallback"], 90)
        self.assertEqual(budget["mode"], "sequential_single_call_fallback")
        self.assertIn("up to 90 calls", budget["call_budget_implication"])

    def test_batch_cap_loops_over_signature_items(self):
        a, t = self.empty_signatures(), self.empty_signatures()
        a["place"] = [f"a{i}" for i in range(5)]
        t["place"] = [f"t{i}" for i in range(5)]
        calls = []
        def batch(source, items, domain):
            calls.append((source, tuple(items), domain))
            return {item: 0.5 for item in items}
        result = compare_cultures("A", "T", a, t, batch_affinity=batch, batch_cap=2)
        self.assertEqual([len(call[1]) for call in calls], [2, 2, 1, 2, 2, 1])
        self.assertEqual(result["call_budget"]["calls_used"], 6)
        self.assertEqual(result["call_budget"]["calls_if_single_fallback"], 10)


if __name__ == "__main__":
    unittest.main()
