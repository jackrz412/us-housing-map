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


class ApiRow(unittest.TestCase):
    def test_county_zip_fields(self):
        # Shape of a real type-7 result: the ZIP is in "geoid".
        item = {"county": "01001", "geoid": "36003", "city": "AUTAUGAVILLE", "state": "AL",
                "res_ratio": 0.0355, "bus_ratio": 0.0185, "oth_ratio": 0.0397, "tot_ratio": 0.0346}
        self.assertEqual(bi.api_row(item), ("01001", "36003", 0.0355))

    def test_pads_codes(self):
        self.assertEqual(bi.api_row({"county": 1001, "geoid": 501, "res_ratio": 0}),
                         ("01001", "00501", 0.0))


if __name__ == "__main__":
    unittest.main()
