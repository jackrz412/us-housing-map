"""Unit tests for the backtest statistics (pipeline/backtest.py), with known answers."""
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import backtest as bt  # noqa: E402


class Outcome(unittest.TestCase):
    def series(self, before, after):
        s = {m: before for m in bt.month_range("2017-01", "2019-12")}
        s.update({m: 9.9 for m in bt.month_range("2020-01", "2022-12")})  # ignored
        s.update({m: after for m in bt.month_range("2023-01", "2025-12")})
        return s

    def test_month_range(self):
        self.assertEqual(len(bt.month_range("2017-01", "2019-12")), 36)
        self.assertEqual(bt.month_range("2024-11", "2025-02"),
                         ["2024-11", "2024-12", "2025-01", "2025-02"])

    def test_change_ignores_2020_2022(self):
        self.assertAlmostEqual(bt.outcome(self.series(0.5, 0.8), bt.WINDOW), 0.3)

    def test_missing_month_is_none(self):
        s = self.series(0.5, 0.8)
        del s["2024-06"]
        self.assertIsNone(bt.outcome(s, bt.WINDOW))
        self.assertIsNotNone(bt.outcome(s, ("2024-07", "2025-12")))

    def test_read_cfpb_drops_connecticut_and_national(self):
        months = bt.month_range("2017-01", "2017-02")
        rows = ["RegionType,State,Name,FIPSCode," + ",".join(months),
                "National,,United States,-----,1.0,1.1",
                "County,AL,Baldwin County,'01003',0.5,0.6",
                "County,CT,Capitol Planning Region,'09110',0.7,0.8"]
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("\n".join(rows) + "\n")
        self.assertEqual(bt.read_cfpb(Path(f.name)), {"01003": {"2017-01": 0.5, "2017-02": 0.6}})


class Statistics(unittest.TestCase):
    def test_ranks_average_ties(self):
        self.assertEqual(bt.ranks([10, 20, 20, 5]), [2.0, 3.5, 3.5, 1.0])

    def test_spearman_monotone(self):
        self.assertAlmostEqual(bt.spearman([1, 2, 3, 4], [1, 8, 27, 64]), 1.0)
        self.assertAlmostEqual(bt.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_spearman_known_value(self):
        # d = (0, 1, -1, 0, 0): rho = 1 - 6 * 2 / (5 * 24) = 0.9
        self.assertAlmostEqual(bt.spearman([1, 2, 3, 4, 5], [1, 3, 2, 4, 5]), 0.9)

    def test_spearman_with_ties(self):
        # Pearson of ranks [1.5, 1.5, 3] and [1, 2, 3].
        self.assertAlmostEqual(bt.spearman([1, 1, 2], [1, 2, 3]), 0.8660254, places=6)

    def test_quintiles_sizes_and_means(self):
        # 12 counties: sizes 3, 3, 2, 2, 2; outcome = measure / 10.
        pairs = [(f"{i:05d}", i, i / 10) for i in range(12, 0, -1)]
        q = bt.quintiles(pairs)
        self.assertEqual([g["n"] for g in q], [3, 3, 2, 2, 2])
        self.assertAlmostEqual(q[0]["mean_change"], 0.2)    # 1, 2, 3
        self.assertAlmostEqual(q[4]["mean_change"], 1.15)   # 11, 12
        self.assertAlmostEqual(bt.q5_minus_q1(pairs), 0.95)

    def test_quintile_ties_broken_by_fips(self):
        pairs = [("00002", 1, 1.0), ("00001", 1, -1.0)] + [(f"1{i:04d}", 2 + i, 0.0)
                                                            for i in range(8)]
        q = bt.quintiles(pairs)
        self.assertEqual(q[0]["mean_change"], 0.0)          # -1 and +1 together
        self.assertEqual(q[0]["share_rose"], 0.5)

    def test_percentile(self):
        self.assertAlmostEqual(bt.percentile([0, 10, 20, 30, 40], 50), 20)
        self.assertAlmostEqual(bt.percentile([0, 10], 97.5), 9.75)

    def test_bootstrap_ci_brackets_and_reproducible(self):
        rows = [(i, i + random.Random(i).gauss(0, 20)) for i in range(200)]

        def stat(s):
            return bt.spearman([r[0] for r in s], [r[1] for r in s])
        a = bt.bootstrap_ci(rows, stat, random.Random(1), n_boot=200)
        b = bt.bootstrap_ci(rows, stat, random.Random(1), n_boot=200)
        self.assertEqual(a, b)
        self.assertLess(a[0], stat(rows))
        self.assertGreater(a[1], stat(rows))


class PartialSpearman(unittest.TestCase):
    def test_residuals(self):
        # y = 2x + 1 exactly: residuals are zero.
        self.assertEqual(bt.ols_residuals([3, 5, 7], [1, 2, 3]), [0.0, 0.0, 0.0])

    def test_matches_first_order_formula(self):
        # Residual correlation equals (r_xy - r_xz r_yz) / sqrt((1 - r_xz^2)(1 - r_yz^2))
        # on the ranks.
        rng = random.Random(3)
        z = [rng.random() for _ in range(80)]
        x = [zi + rng.gauss(0, 0.5) for zi in z]
        y = [zi + xi + rng.gauss(0, 0.5) for zi, xi in zip(z, x)]
        rx, ry, rz = bt.ranks(x), bt.ranks(y), bt.ranks(z)
        rxy, rxz, ryz = bt.pearson(rx, ry), bt.pearson(rx, rz), bt.pearson(ry, rz)
        expected = (rxy - rxz * ryz) / ((1 - rxz ** 2) * (1 - ryz ** 2)) ** 0.5
        self.assertAlmostEqual(bt.partial_spearman(x, y, z), expected)

    def test_removes_shared_baseline(self):
        # x and y both just track z: raw rho is high, partial rho is near 0.
        rng = random.Random(5)
        z = list(range(300))
        x = [zi + rng.gauss(0, 30) for zi in z]
        y = [zi + rng.gauss(0, 30) for zi in z]
        self.assertGreater(bt.spearman(x, y), 0.8)
        self.assertLess(abs(bt.partial_spearman(x, y, z)), 0.15)


class Evaluate(unittest.TestCase):
    def test_orientation_and_paired_comparison(self):
        counties = [f"{i:05d}" for i in range(50)]
        outcomes = {f: i / 10 for i, f in enumerate(counties)}
        m = {name: {f: None for f in counties} for name in bt.MEASURES}
        for i, f in enumerate(counties):
            m["burden"][f] = float(i)               # perfect ranking
            m["pti"][f] = float(i % 7)               # weak
            m["lower_income"][f] = -(100.0 - i)      # income falls as outcome rises
        r = bt.evaluate(m, outcomes, seed=1)
        self.assertAlmostEqual(r["measures"]["burden"]["rho"], 1.0)
        self.assertAlmostEqual(r["measures"]["lower_income"]["rho"], 1.0)
        self.assertEqual(r["measures"]["d"]["n"], 0)
        self.assertGreater(r["burden_vs_inputs"]["pti"]["rho_diff"], 0)
        self.assertGreater(r["burden_vs_inputs"]["pti"]["rho_diff_ci"][0], 0)


if __name__ == "__main__":
    unittest.main()
