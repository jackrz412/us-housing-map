"""Build the county HMDA layers from the 2025 Snapshot loan-level CSV.

Outputs in data/processed/, each {fips: value} over every in-scope map county:
  hmda_loans.json        number of qualifying loans (0 if none reported)
  hmda_rate.json         median interest_rate, %
  hmda_dti_over_43.json  % of loans with debt-to-income above 43%
  hmda_cltv_over_90.json % of conventional loans with combined loan-to-value above 90%
  hmda_govt_share.json   % of loans that are FHA, VA or USDA/RHS
  hmda_loan_amount.json  median loan_amount, USD
A metric is null where the county has fewer than --min-loans valid values.

Usage: .venv/bin/python pipeline/clean_hmda.py [--min-loans 30]
(run fetch_hmda.py first; needs duckdb, see requirements.txt)
"""
import argparse
import json

import duckdb

from fetch_hmda import CSV_PATH, DATASET, HMDA_YEAR, SOURCE_PATH
from geo import RAW_DIR, map_counties
from hmda_codes import (CLTV_THRESHOLD, CONVENTIONAL, FILTERS, GOVERNMENT,
                        dti_over_43_sql, sql_list)
from output import update_meta, write_layer

# Why DuckDB and not pandas: the CSV is ~5 GB with 99 columns and ~11M rows.
# pandas.read_csv materialises the whole table in RAM before you can filter
# it, and with string columns stored as Python objects that's several times
# the file size, far more than this 16 GB machine has. DuckDB instead:
#   - streams the file in chunks and parses only the ~12 columns the query
#     uses (projection pushdown), applying the WHERE filter as it reads;
#   - keeps one small hash-table entry per county for the GROUP BY, so memory
#     scales with the ~3,200 output rows, not the 11M input rows;
#   - spills to temp_directory instead of crashing if it ever hits the cap;
#   - runs the scan on every core.
# The memory_limit is a ceiling, not an allocation: this query uses far less.
MEMORY_LIMIT = "8GB"

# Loan filters, DTI codes and loan types live in hmda_codes.py, shared with
# the stress index (Phase 4) so both use the same definitions. The CLTV layer
# counts conventional loans only (DECISIONS 019); the government share is
# output separately so that side isn't hidden.


# One pass over the file computes every metric per county. Each metric uses
# its own valid count: TRY_CAST turns 'NA' and 'Exempt' into NULL, and
# aggregates (count, median) skip NULLs, so a loan with an exempt DTI still
# counts toward the rate median if its rate was reported.
QUERY = f"""
WITH loans AS (
    SELECT
        county_code AS fips,
        TRY_CAST(interest_rate AS DOUBLE) AS rate,
        TRY_CAST(combined_loan_to_value_ratio AS DOUBLE) AS cltv,
        TRY_CAST(loan_amount AS DOUBLE) AS amount,
        CASE WHEN loan_type IN ('{CONVENTIONAL}', {sql_list(GOVERNMENT)})
             THEN loan_type IN ({sql_list(GOVERNMENT)}) END AS is_govt,
        loan_type = '{CONVENTIONAL}' AS is_conv,
        {dti_over_43_sql()} AS dti_over_43
    FROM read_csv(?, header = true, all_varchar = true)
    WHERE {FILTERS}
)
SELECT
    fips,
    count(*)                         AS n_loans,
    count(rate)                      AS n_rate,
    median(rate)                     AS median_rate,
    count(dti_over_43)               AS n_dti,
    avg(dti_over_43::INTEGER) * 100  AS pct_dti_over_43,
    count(cltv) FILTER (WHERE is_conv)                      AS n_cltv,
    avg((cltv > {CLTV_THRESHOLD})::INTEGER) FILTER (WHERE is_conv) * 100 AS pct_cltv_over_90,
    count(is_govt)                   AS n_govt,
    avg(is_govt::INTEGER) * 100      AS pct_govt,
    count(amount)                    AS n_amount,
    median(amount)                   AS median_amount
FROM loans
GROUP BY fips
ORDER BY fips
"""

# name -> (valid-count column, value column, rounding, meta)
METRICS = {
    "hmda_rate": ("n_rate", "median_rate", 3, {
        "label": "Median mortgage rate", "unit": "%",
        "definition": "Median interest_rate of qualifying loans"}),
    "hmda_dti_over_43": ("n_dti", "pct_dti_over_43", 1, {
        "label": "Loans with debt-to-income above 43%", "unit": "% of loans",
        "definition": "Share of qualifying loans with debt_to_income_ratio above 43% "
                      "(reported values 44-49, '50%-60%', '>60%')"}),
    "hmda_cltv_over_90": ("n_cltv", "pct_cltv_over_90", 1, {
        "label": "Conventional loans with combined loan-to-value above 90%",
        "unit": "% of conventional loans",
        "definition": f"Share of qualifying conventional loans (loan_type 1) with "
                      f"combined_loan_to_value_ratio above {CLTV_THRESHOLD}"}),
    "hmda_govt_share": ("n_govt", "pct_govt", 1, {
        "label": "Government-backed loans", "unit": "% of loans",
        "definition": "Share of qualifying loans that are FHA, VA or USDA/RHS "
                      "(loan_type 2, 3 or 4)"}),
    "hmda_loan_amount": ("n_amount", "median_amount", 0, {
        "label": "Median loan amount", "unit": "USD",
        "definition": "Median loan_amount of qualifying loans (HMDA reports the "
                      "midpoint of a $10,000 band)"}),
}


def run_query():
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"SET temp_directory = '{RAW_DIR / 'duckdb_tmp'}'")
    # Row order inside the scan doesn't matter (the result is ORDER BY fips),
    # and dropping it lets DuckDB use less memory.
    con.execute("SET preserve_insertion_order = false")
    cur = con.execute(QUERY, [str(CSV_PATH)])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def build(rows, min_loans):
    shapes = map_counties()
    by_fips = {r["fips"]: r for r in rows}

    off_map = {f: r["n_loans"] for f, r in by_fips.items() if f not in shapes}
    print(f"{sum(r['n_loans'] for r in rows):,} qualifying loans in {len(rows):,} county codes")
    print(f"dropped {sum(off_map.values()):,} loans in {len(off_map)} codes not on the map "
          f"(territories, 'NA'): {sorted(off_map)[:8]}")

    layers = {"hmda_loans": {}}
    layers.update({name: {} for name in METRICS})
    for fips in sorted(shapes):
        r = by_fips.get(fips)
        # HMDA covers every reporting lender, so a county missing from the
        # file had zero reported qualifying loans. That's a real 0 for the
        # count, but every other metric is unavailable there.
        layers["hmda_loans"][fips] = r["n_loans"] if r else 0
        for name, (n_col, v_col, digits, _) in METRICS.items():
            if r is None or r[n_col] < min_loans:
                layers[name][fips] = None  # suppressed: too few valid loans
            else:
                v = round(float(r[v_col]), digits)
                layers[name][fips] = int(v) if digits == 0 else v
    return layers


def meta_entries(min_loans):
    source = json.loads(SOURCE_PATH.read_text())
    common = {
        "source": "FFIEC Home Mortgage Disclosure Act (HMDA) loan-level data",
        "dataset": f"{DATASET.capitalize()} {HMDA_YEAR}",
        "period": str(HMDA_YEAR),
        "legend_period": f"HMDA {HMDA_YEAR}",
        "filters": "originated, home purchase, first lien, principal residence; "
                   "excludes open-end lines of credit and reverse mortgages",
        "source_url": source["url"],
        "source_last_modified": source["last_modified"],
        "source_sha256": source["sha256"],
    }
    entries = {"hmda_loans": {**common, "label": "Qualifying home-purchase loans",
                              "unit": "loans"}}
    for name, (*_, meta) in METRICS.items():
        entries[name] = {**common, **meta, "min_valid_loans": min_loans}
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--min-loans", type=int, default=30,
                        help="suppress a metric where a county has fewer valid loans (default 30)")
    args = parser.parse_args()

    layers = build(run_query(), args.min_loans)
    changed = {name: write_layer(name, values) for name, values in layers.items()}
    update_meta(meta_entries(args.min_loans), changed)

    for name, values in layers.items():
        kept = sum(v is not None for v in values.values())
        print(f"{name}: {kept:,} of {len(values):,} counties with a value")


if __name__ == "__main__":
    main()
