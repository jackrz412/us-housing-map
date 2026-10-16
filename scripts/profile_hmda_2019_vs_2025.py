"""Phase 4.0 spike (DATA_SOURCES.md, Phase 4.0 §1): compare HMDA 2019 One-Year with 2025 Snapshot.

Checks that the fields the stress index needs exist in both years with the
same codes, and times one DuckDB pass over each file. Not part of the pipeline.

Usage (from the repo root): .venv/bin/python scripts/profile_hmda_2019_vs_2025.py
"""
import sys
import time

import duckdb

FILES = {
    2019: "data/raw/2019_public_lar_one_year.csv",
    2025: "data/raw/2025_public_lar_csv.csv",
}
NEEDED = [
    "activity_year", "county_code", "action_taken", "loan_purpose", "lien_status",
    "occupancy_type", "open_end_line_of_credit", "reverse_mortgage", "loan_type",
    "loan_amount", "interest_rate", "property_value", "income",
    "debt_to_income_ratio", "combined_loan_to_value_ratio",
    "denial_reason_1", "denial_reason_2", "denial_reason_3", "denial_reason_4",
]
# Phase 2a loan filters, minus action_taken (applications need 1, 2 and 3).
BASE = """
    loan_purpose = '1' AND lien_status = '1' AND occupancy_type = '1'
    AND open_end_line_of_credit IS DISTINCT FROM '1'
    AND reverse_mortgage IS DISTINCT FROM '1'
"""

con = duckdb.connect()
con.execute("SET memory_limit = '8GB'")


def q(sql):
    return con.execute(sql).fetchall()


for year, path in FILES.items():
    print(f"\n===== {year}: {path}")
    src = f"read_csv('{path}', all_varchar = true, header = true)"
    cols = [r[0] for r in q(f"DESCRIBE SELECT * FROM {src} LIMIT 0")]
    missing = [c for c in NEEDED if c not in cols]
    print(f"columns: {len(cols)}; missing needed: {missing or 'none'}")

    t = time.time()
    con.execute(f"CREATE OR REPLACE TABLE l AS SELECT {', '.join(NEEDED)} FROM {src} WHERE {BASE}")
    print(f"one pass (filter + load {len(NEEDED)} cols): {time.time() - t:.1f} s")
    print("rows by action_taken:", q("SELECT action_taken, count(*) FROM l GROUP BY 1 ORDER BY 1"))

    o = "FROM l WHERE action_taken = '1'"
    n = q(f"SELECT count(*) {o}")[0][0]
    print(f"originated qualifying loans: {n:,}")
    for c in ["loan_type", "debt_to_income_ratio"]:
        print(f"{c}:", q(f"SELECT {c}, count(*) {o} GROUP BY 1 ORDER BY 2 DESC LIMIT 25"))
    # Non-numeric values in numeric fields (NA, Exempt, anything unexpected).
    for c in ["income", "property_value", "interest_rate", "loan_amount", "combined_loan_to_value_ratio"]:
        bad = q(f"SELECT {c}, count(*) {o} AND TRY_CAST({c} AS DOUBLE) IS NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
        st = q(f"""SELECT min(v), quantile_cont(v, 0.01), median(v), quantile_cont(v, 0.99), max(v),
                   count(*) FILTER (WHERE v <= 0)
                   FROM (SELECT TRY_CAST({c} AS DOUBLE) v {o}) WHERE v IS NOT NULL""")[0]
        print(f"{c}: non-numeric {bad}; min/p1/median/p99/max {st[:5]}; <=0: {st[5]}")
    # property_value is reported as the midpoint of a $10,000 bin.
    print("property_value last 4 digits (top 3):",
          q(f"SELECT right(property_value, 4), count(*) {o} AND property_value <> 'NA' GROUP BY 1 ORDER BY 2 DESC LIMIT 3"))
    print("loan_amount last 4 digits (top 3):",
          q(f"SELECT right(loan_amount, 4), count(*) {o} GROUP BY 1 ORDER BY 2 DESC LIMIT 3"))
    print("denial_reason_1 (denied apps):",
          q("SELECT denial_reason_1, count(*) FROM l WHERE action_taken = '3' GROUP BY 1 ORDER BY 1"))
    print("denial_reason_2 codes:",
          q("SELECT denial_reason_2, count(*) FROM l WHERE action_taken = '3' GROUP BY 1 ORDER BY 1"))
    print("DTI (code 1) in any denial_reason:",
          q("""SELECT count(*) FROM l WHERE action_taken = '3'
               AND '1' IN (denial_reason_1, denial_reason_2, denial_reason_3, denial_reason_4)"""))
    print("denial_reason_1 on non-denied rows:",
          q("SELECT denial_reason_1, count(*) FROM l WHERE action_taken <> '3' GROUP BY 1 ORDER BY 2 DESC LIMIT 3"))
    print("county codes: CT", q("""SELECT count(DISTINCT county_code), min(county_code), max(county_code)
                                  FROM l WHERE county_code LIKE '09%'"""),
          "| AK 02261/02063/02066:", q("""SELECT county_code, count(*) FROM l
                                          WHERE county_code IN ('02261','02063','02066') GROUP BY 1 ORDER BY 1"""),
          "| NA:", q("SELECT count(*) FROM l WHERE county_code = 'NA'"))
    print("distinct county codes:", q("SELECT count(DISTINCT county_code) FROM l"))
    sys.stdout.flush()
