"""Unit tests for the ZIP-to-county premium weighting (build_insurance.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import build_insurance as bi  # noqa: E402


class CountyPremiums(unittest.TestCase):
    def test_residential_weights(self):
        # 09001: 60% of addresses in a $1,000 ZIP, 40% in a $2,000 ZIP -> $1,400.
        premiums = {"01001": 1000.0, "01002": 2000.0}
        crosswalk = [("09001", "01001", 0.6), ("09001", "01002", 0.4)]
        self.assertEqual(bi.county_premiums(premiums, crosswalk)["09001"], (1400.0, 1.0))

    def test_renormalizes_over_covered_zips(self):
        # 70% covered: the mean is over the covered ZIPs only.
        premiums = {"01001": 1000.0, "01002": 2000.0}
        crosswalk = [("09001", "01001", 0.35), ("09001", "01002", 0.35), ("09001", "99999", 0.3)]
        self.assertEqual(bi.county_premiums(premiums, crosswalk)["09001"], (1500.0, 0.7))

    def test_null_below_half_coverage(self):
        crosswalk = [("09003", "01001", 0.3), ("09003", "99999", 0.7)]
        self.assertEqual(bi.county_premiums({"01001": 1000.0}, crosswalk)["09003"], (None, 0.3))


if __name__ == "__main__":
    unittest.main()
