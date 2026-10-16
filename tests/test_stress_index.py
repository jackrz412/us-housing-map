"""Unit tests for the stress index (SPEC Phase 4, 4a), with known answers.

The SQL tests run the pipeline's own query text (stress_index.LOAN_SQL,
APPS_SQL, AGG_SQL) on small hand-built tables, so they test the code that
runs on the real files, not a copy of it.

Usage: .venv/bin/python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import duckdb  # noqa: E402

import stress_index as si  # noqa: E402
from hmda_codes import denied_for_dti_sql, dti_over_43_sql  # noqa: E402

COLUMNS = [
    "action_taken", "loan_purpose", "lien_status", "occupancy_type",
    "open_end_line_of_credit", "reverse_mortgage", "county_code", "state_code",
    "interest_rate", "loan_amount", "property_value", "income", "loan_term", "loan_type",
    "combined_loan_to_value_ratio", "debt_to_income_ratio", "interest_only_payment",
    "balloon_payment", "negative_amortization",
    "denial_reason_1", "denial_reason_2", "denial_reason_3", "denial_reason_4",
]

# A valid qualifying conventional loan. Tests override single fields.
BASE_LOAN = {
    "action_taken": "1", "loan_purpose": "1", "lien_status": "1", "occupancy_type": "1",
    "open_end_line_of_credit": "2", "reverse_mortgage": "2", "county_code": "01001",
    "state_code": "AL", "interest_rate": "6.5", "loan_amount": "300000",
    "property_value": "400000", "income": "120", "loan_term": "360", "loan_type": "1",
    "combined_loan_to_value_ratio": "75", "debt_to_income_ratio": "30%-<36%",
    "interest_only_payment": "2", "balloon_payment": "2", "negative_amortization": "2",
    "denial_reason_1": "10", "denial_reason_2": None, "denial_reason_3": None,
    "denial_reason_4": None,
}

# County inputs for 01001: 1% effective tax rate, $1,200/year insurance.
TAU, PREMIUM = 0.01, 1200.0


def make_con(loans):
    """In-memory DuckDB with a `src` table of loans (all text, like the CSV)."""
    con = duckdb.connect()
    con.execute(f"CREATE TABLE src ({', '.join(f'{c} VARCHAR' for c in COLUMNS)})")
    con.executemany(f"INSERT INTO src VALUES ({', '.join('?' * len(COLUMNS))})",
                    [[{**BASE_LOAN, **loan}[c] for c in COLUMNS] for loan in loans])
    si.load_county_inputs(con, {"01001": TAU, "01003": TAU}, {"01001": PREMIUM})
    return con


def loan_rows(loans):
    con = make_con(loans)
    cur = con.execute(si.LOAN_SQL.replace("{src}", "src"))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class Amortization(unittest.TestCase):
    def test_30_year(self):
        # $300,000 at 6.5% over 30 years: the standard answer is $1,896.20.
        self.assertAlmostEqual(si.monthly_payment(300_000, 6.5, 360), 1896.20, places=2)

    def test_15_year(self):
        # Same loan over 15 years: $2,613.32.
        self.assertAlmostEqual(si.monthly_payment(300_000, 6.5, 180), 2613.32, places=2)

    def test_sql_matches_python(self):
        # PTI from the SQL = (M + T + I) / monthly income, with M from the
        # Python formula: 1896.20 + 0.01 * 400,000 / 12 + 1,200 / 12, over
        # $120,000 / 12.
        expected = (si.monthly_payment(300_000, 6.5, 360) + TAU * 400_000 / 12 + PREMIUM / 12) / 10_000
        [row] = loan_rows([{}])
        self.assertIsNone(row["rule"])
        self.assertAlmostEqual(row["pti"], expected, places=10)
        self.assertAlmostEqual(row["pti"], 0.232954, places=6)

    def test_sql_uses_loan_term(self):
        [row] = loan_rows([{"loan_term": "180"}])
        expected = (si.monthly_payment(300_000, 6.5, 180) + TAU * 400_000 / 12 + PREMIUM / 12) / 10_000
        self.assertAlmostEqual(row["pti"], expected, places=10)
        self.assertFalse(row["term_fallback"])

    def test_term_fallback(self):
        for term in ("Exempt", "NA"):
            [row] = loan_rows([{"loan_term": term}])
            self.assertTrue(row["term_fallback"], term)
            self.assertEqual(row["n"], 360)


class BenchmarkScaling(unittest.TestCase):
    def test_scale(self):
        self.assertEqual(si.scale(0.28, si.B_PTI), 1.0)
        self.assertAlmostEqual(si.scale(0.35, si.B_PTI), 1.25)
        self.assertAlmostEqual(si.scale(30.0, 25.0), 1.2)
        self.assertIsNone(si.scale(None, 25.0))
        self.assertIsNone(si.scale(30.0, None))

    def test_score_county(self):
        bench = {"pti": 0.28, "d": 25.0, "r": 4.0, "s": 20.0, "cltv": 40.0}
        c = {"pti": 0.35, "d": 25.0, "r": 6.0, "s": 30.0, "cltv": 20.0}
        burden, equity = si.score_county(c, bench)
        # x: pti 1.25, d 1.0, r 1.5 -> NewBuyer 1.25; S 1.5 -> Existing 1.5.
        self.assertEqual(burden["x_pti"], 1.25)
        self.assertEqual(burden["new_buyer"], 1.25)
        self.assertEqual(burden["existing"], 1.5)
        self.assertEqual(burden["burden"], 1.375)
        self.assertEqual(burden["n_components"], 4)
        self.assertEqual(equity["equity"], 0.5)

    def test_new_buyer_averages_present_components(self):
        bench = {"pti": 0.28, "d": 25.0, "r": 4.0, "s": 20.0, "cltv": 40.0}
        c = {"pti": None, "d": 50.0, "r": None, "s": 20.0, "cltv": None}
        burden, equity = si.score_county(c, bench)
        self.assertEqual(burden["new_buyer"], 2.0)
        self.assertEqual(burden["burden"], 1.5)
        self.assertEqual(burden["n_components"], 2)
        self.assertIsNone(equity["equity"])

    def test_burden_needs_both_halves(self):
        bench = {"pti": 0.28, "d": 25.0, "r": 4.0, "s": 20.0, "cltv": 40.0}
        no_s = {"pti": 0.28, "d": 25.0, "r": 4.0, "s": None, "cltv": 40.0}
        self.assertIsNone(si.score_county(no_s, bench)[0]["burden"])
        no_new = {"pti": None, "d": None, "r": None, "s": 20.0, "cltv": 40.0}
        self.assertIsNone(si.score_county(no_new, bench)[0]["burden"])


class DtiBins(unittest.TestCase):
    def test_mapping(self):
        cases = {
            "<20%": False, "20%-<30%": False, "30%-<36%": False, "36": False, "43": False,
            "44": True, "49": True, "50%-60%": True, ">60%": True,
            "NA": None, "Exempt": None, "99": None,  # unknown codes are invalid, not "not over"
        }
        con = duckdb.connect()
        for code, expected in cases.items():
            got = con.execute(f"SELECT {dti_over_43_sql('c')} FROM (SELECT ? AS c)", [code]).fetchone()[0]
            self.assertEqual(got, expected, code)


class DenialReasons(unittest.TestCase):
    def test_matching(self):
        cases = [
            (("1", None, None, None), True),     # DTI as the first reason
            (("3", "7", "1", None), True),       # DTI as the third reason
            (("3", "7", None, None), False),
            (("10", None, None, None), False),   # 10 = not applicable
            (("1111", None, None, None), False), # exempt
            ((None, None, None, None), False),   # empty, not NULL
        ]
        con = duckdb.connect()
        sql = (f"SELECT {denied_for_dti_sql()} FROM (SELECT ? AS denial_reason_1, "
               "? AS denial_reason_2, ? AS denial_reason_3, ? AS denial_reason_4)")
        for reasons, expected in cases:
            self.assertIs(con.execute(sql, list(reasons)).fetchone()[0], expected, reasons)

    def test_r_counts_denials_only(self):
        # R: DTI denials / applications (actions 1, 2, 3). An origination with a
        # stray DTI reason code doesn't count as a denial; withdrawn (4) and
        # preapproval-denied (7) aren't applications.
        loans = ([{}] * 6
                 + [{"action_taken": "2"}] * 2
                 + [{"action_taken": "3", "denial_reason_1": "1"}] * 3
                 + [{"action_taken": "3", "denial_reason_2": "1", "denial_reason_1": "4"}]
                 + [{"action_taken": "3", "denial_reason_1": "4"}] * 2
                 + [{"action_taken": "1", "denial_reason_1": "1"}]
                 + [{"action_taken": "4"}, {"action_taken": "7", "denial_reason_1": "1"}])
        con = make_con(loans)
        counties, national = si.hmda_aggregates(con, "src")
        row = counties["01001"]
        self.assertEqual(row["n_r"], 15)   # 7 originated + 2 approved + 6 denied
        self.assertEqual(row["k_r"], 4)
        self.assertEqual(si.share(row["k_r"], row["n_r"], min_n=1), round(100 * 4 / 15, 2))


class PtiRules(unittest.TestCase):
    def test_each_rule(self):
        cases = [
            ({"interest_only_payment": "1"}, "payment_feature"),
            ({"balloon_payment": "1"}, "payment_feature"),
            ({"negative_amortization": "1"}, "payment_feature"),
            ({"interest_only_payment": "1111"}, None),       # exempt stays in
            ({"interest_rate": "0"}, "rate"),
            ({"interest_rate": "20"}, None),                  # 20 is allowed
            ({"interest_rate": "20.01"}, "rate"),
            ({"interest_rate": "Exempt"}, "rate"),
            ({"loan_amount": "0"}, "amount_value"),
            ({"property_value": "NA"}, "amount_value"),
            ({"income": "9"}, "income"),
            ({"income": "10", "loan_amount": "100000", "property_value": "120000"}, None),
            ({"income": "-5"}, "income"),
            ({"income": "NA"}, "income"),
            ({"county_code": "01003"}, "no_tax_or_premium"),  # tax rate, no premium
            ({"income": "20"}, "pti_cap"),                    # PTI ~1.4
            # The first failing rule wins: interest-only and a bad rate.
            ({"interest_only_payment": "1", "interest_rate": "0"}, "payment_feature"),
        ]
        rows = loan_rows([override for override, _ in cases])
        # Row order isn't guaranteed (preserve_insertion_order is off in the
        # pipeline), so compare the multiset of outcomes.
        got = sorted((r["rule"] or "") for r in rows)
        want = sorted((e or "") for _, e in cases)
        self.assertEqual(got, want)
        for r in rows:
            if r["rule"] is None:
                self.assertIsNotNone(r["pti"])
                self.assertLessEqual(r["pti"], si.MAX_PTI)
            else:
                self.assertIsNone(r["pti"])

    def test_pti_cap_boundary(self):
        # Income chosen so PTI is just above and just below 1.0.
        monthly = si.monthly_payment(300_000, 6.5, 360) + TAU * 400_000 / 12 + PREMIUM / 12
        just_below = monthly * 12 / 1000 / 0.999   # income ($000s) giving PTI 0.999
        just_above = monthly * 12 / 1000 / 1.001
        rows = loan_rows([{"income": f"{just_below:.6f}"}, {"income": f"{just_above:.6f}"}])
        self.assertEqual(sorted((r["rule"] or "") for r in rows), ["", "pti_cap"])

    def test_report_counts_and_flag(self):
        # 40 loans in 01001: 35 fine, 5 with a bad rate (12.5% > 10%) -> flagged.
        # 01003 has loans but no premium: counted, not flagged.
        loans = [{}] * 35 + [{"interest_rate": "0"}] * 5 + [{"county_code": "01003"}] * 40
        con = make_con(loans)
        counties, national = si.hmda_aggregates(con, "src")
        report = si.rule_report(counties, national, {"01001": "", "01003": ""})
        a = report["counties"]["01001"]
        self.assertEqual((a["loans"], a["kept"], a["rate"]), (40, 35, 5))
        self.assertEqual(report["counties"]["01003"]["no_tax_or_premium"], 40)
        self.assertEqual(report["flagged_over_10pct"], ["01001"])
        self.assertEqual(report["national"]["loans"], 80)

    def test_min_n(self):
        # 29 valid loans: no PTI; 30: PTI.
        for n, has_pti in ((29, False), (30, True)):
            con = make_con([{}] * n)
            counties, _ = si.hmda_aggregates(con, "src")
            self.assertEqual(si.hmda_components(counties["01001"])["pti"] is not None, has_pti, n)


class NationalScope(unittest.TestCase):
    def test_territories_and_na(self):
        loans = ([{}] * 2
                 + [{"county_code": "72001", "state_code": "PR"}]
                 + [{"county_code": "NA", "state_code": "TX"}]      # no county, in scope
                 + [{"county_code": "NA", "state_code": "PR"}])     # no county, out of scope
        con = make_con(loans)
        counties, national = si.hmda_aggregates(con, "src")
        self.assertEqual(national["n_loans"], 3)
        self.assertNotIn("72001", counties)


if __name__ == "__main__":
    unittest.main()
