"""Behavioral statistical checks, runnable with unittest discovery."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from statistics_core import (compare_proportions, posterior_probability,
                             relative_uplift_interval, sample_size, srm,
                             two_proportion_z, wilson_interval)


class StatisticsTests(unittest.TestCase):
    def test_wilson_known_value_and_boundaries(self):
        lower, upper = wilson_interval(50, 100)
        self.assertAlmostEqual(lower, .4038315, places=6)
        self.assertAlmostEqual(upper, .5961685, places=6)
        self.assertAlmostEqual(wilson_interval(0, 100)[0], 0)
        self.assertAlmostEqual(wilson_interval(100, 100)[1], 1)

    def test_z_matches_known_result_and_symmetry(self):
        result = two_proportion_z(100, 1000, 150, 1000)
        self.assertAlmostEqual(result["z"], 3.380617, places=5)
        self.assertTrue(result["significant"])
        opposite = two_proportion_z(150, 1000, 100, 1000)
        self.assertAlmostEqual(result["p_value"], opposite["p_value"])
        self.assertEqual(two_proportion_z(100, 1000, 100, 1000)["p_value"], 1)

    def test_sparse_not_treated_as_no_difference(self):
        result = compare_proportions(0, 100, 0, 100, relative_mde=.1)
        self.assertFalse(result["z_test"]["valid"])
        self.assertFalse(result["equivalent"])
        self.assertIsNone(result["relative_uplift"]["uplift"])

    def test_sample_size_power_mde_and_comparisons(self):
        base = sample_size(.1, .1)
        self.assertTrue(14000 < base["per_arm"][0] < 15000)
        self.assertGreater(sample_size(.1, .05)["total"], base["total"] * 3)
        self.assertGreater(sample_size(.1, .1, power=.9)["total"], base["total"])
        triple = sample_size(.1, .1, arms=3)
        self.assertGreater(triple["per_arm"][0], base["per_arm"][0])
        self.assertEqual(triple["alpha_per_comparison"], .025)

    def test_unequal_allocation_and_srm(self):
        planned = sample_size(.1, .1, allocation=[.8, .2])
        self.assertAlmostEqual(planned["per_arm"][0] / planned["per_arm"][1], 4, places=3)
        self.assertFalse(srm([8000, 2000], [.8, .2])["mismatch"])
        self.assertTrue(srm([5000, 5000], [.8, .2])["mismatch"])
        self.assertFalse(srm([1, 1], [.5, .5])["valid"])

    def test_posterior_reproducible_and_handles_extremes(self):
        equal = posterior_probability(0, 100, 0, 100)
        self.assertAlmostEqual(equal["probability"], .5, delta=.005)
        self.assertEqual(equal, posterior_probability(0, 100, 0, 100))
        strong = posterior_probability(10000, 100000, 20000, 100000)
        self.assertGreater(strong["probability"], .999)
        self.assertLess(strong["mc_interval"][0], 1)

    def test_equivalence_requires_precision(self):
        self.assertFalse(compare_proportions(100, 1000, 100, 1000, .1)["equivalent"])
        self.assertTrue(compare_proportions(100000, 1000000, 100000, 1000000, .1)["equivalent"])
        result = relative_uplift_interval(1000, 10000, 1500, 10000)
        self.assertAlmostEqual(result["uplift"], .5)
        self.assertGreater(result["ci"][0], 0)

    def test_invalid_inputs(self):
        for args in [(11, 10), (-1, 10), (1, 0), (1.5, 10), (True, 10)]:
            with self.assertRaises(ValueError):
                wilson_interval(*args)
        for kwargs in [{"baseline": 0, "relative_mde": .1},
                       {"baseline": .9, "relative_mde": .2},
                       {"baseline": .1, "relative_mde": -.1},
                       {"baseline": .1, "relative_mde": .1, "allocation": [.4, .4]}]:
            with self.assertRaises(ValueError):
                sample_size(**kwargs)


if __name__ == "__main__":
    unittest.main()
