"""Power calculators + NI margin tests (textbook values)."""

import unittest

from backend.agents.power_calc import (
    _ndtri,
    ni_margin_check,
    sample_size_means,
    sample_size_proportions,
)


class NormalTests(unittest.TestCase):
    def test_known_quantiles(self):
        self.assertAlmostEqual(_ndtri(0.975), 1.96, places=2)
        self.assertAlmostEqual(_ndtri(0.8), 0.84, places=2)
        self.assertAlmostEqual(_ndtri(0.5), 0.0, places=6)

    def test_bad_p(self):
        with self.assertRaises(ValueError):
            _ndtri(1.5)


class ProportionsTests(unittest.TestCase):
    def test_textbook_n(self):
        out = sample_size_proportions(0.5, 0.4)
        self.assertEqual(out["n_per_group"], 388)
        self.assertEqual(out["total"], 776)

    def test_dropout_inflates(self):
        out = sample_size_proportions(0.5, 0.4, dropout=0.2)
        self.assertEqual(out["n_per_group_with_dropout"], 485)
        self.assertGreater(out["total"], 776)

    def test_equal_rates_rejected(self):
        with self.assertRaises(ValueError):
            sample_size_proportions(0.3, 0.3)

    def test_bad_alpha(self):
        with self.assertRaises(ValueError):
            sample_size_proportions(0.5, 0.4, alpha=2.0)


class MeansTests(unittest.TestCase):
    def test_textbook_n(self):
        out = sample_size_means(5, 10)
        self.assertEqual(out["n_per_group"], 63)

    def test_zero_delta_rejected(self):
        with self.assertRaises(ValueError):
            sample_size_means(0, 10)


class NiTests(unittest.TestCase):
    def test_preserved_pass(self):
        out = ni_margin_check(0.4, 0.15)
        self.assertAlmostEqual(out["preserved_fraction"], 0.625)
        self.assertTrue(out["pass"])

    def test_too_wide_fails(self):
        out = ni_margin_check(0.4, 0.25)
        self.assertFalse(out["pass"])

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            ni_margin_check(0, 0.1)
        with self.assertRaises(ValueError):
            ni_margin_check(0.4, -0.1)


if __name__ == "__main__":
    unittest.main()
