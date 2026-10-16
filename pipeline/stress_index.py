"""Housing stress index (Phase 4): the Burden and Equity scores.

One set of functions computes every component for any vintage; only the input
files differ. clean_index.py runs it on current data (HMDA 2025, ACS 2020-2024,
FIO 2022 premiums), build_benchmarks.py and the 4b backtest on 2019 inputs.

  Burden = 0.5 * NewBuyer + 0.5 * Existing
    NewBuyer = mean(x_PTI, x_D, x_R)      (over the components a county has)
    Existing = x_S                         (O dropped, DECISIONS 023)
  Equity = x_CLTV
  x_i = c_i / b_i  (1.0 = at the benchmark)

b_PTI = 0.28; every other benchmark is the 2019 national value, computed once
and stored in data/processed/benchmarks.json (DECISIONS 020). Definitions and
the PTI loan rules are in SPEC.md (Phase 4) and DECISIONS 020-025.
"""
import duckdb

import acs
from clean_acs_burden import B25091_AT_LEAST_30, MIN_OWNERS, burden_share
from geo import RAW_DIR
from hmda_codes import (APPLICATION_ACTIONS, BASE_FILTERS, CLTV_THRESHOLD, CONVENTIONAL,
                        DENIED, FILTERS, denied_for_dti_sql, dti_over_43_sql, sql_list)

MEMORY_LIMIT = "8GB"  # a ceiling, not an allocation (see clean_hmda.py)

# --- Fixed choices (SPEC Phase 4, DECISIONS 020/025) -----------------------------
B_PTI = 0.28          # housing should take at most 28% of gross income
MIN_N = 30            # loans or applications per county, as in Phase 2
DEFAULT_TERM = 360    # months, used only when loan_term is NA or Exempt
MAX_RATE = 20         # percent; 0 < rate <= 20
MIN_INCOME = 10       # thousands of dollars (HMDA reports income in $000s)
MAX_PTI = 1.0         # a payment above 100% of income isn't a real loan
BURDEN_WEIGHTS = (0.5, 0.5)  # NewBuyer, Existing

# Components each score is built from, in display order.
NEW_BUYER = ["pti", "d", "r"]
EXISTING = ["s"]
EQUITY = ["cltv"]

# PTI loan rules, checked in this order; a loan is counted under the first
# rule it fails (DECISIONS 025). "no_tax_or_premium" is a county-level gap
# (no ACS tax rate or no FIO premium), not a problem with the loan, so it's
# kept out of the >10% loss flag.
RULES = ["payment_feature", "rate", "amount_value", "income", "no_tax_or_premium", "pti_cap"]
LOAN_RULES = [r for r in RULES if r != "no_tax_or_premium"]
LOSS_FLAG_SHARE = 0.10

# USPS codes for the 50 states + DC: the "national" scope for benchmarks.
# Loans with no county code ('NA') still count nationally if their state is in.
STATES_50_DC = [
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "IA", "ID",
    "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC",
    "ND", "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
]


# --- Formulas -------------------------------------------------------------------

def monthly_payment(principal, annual_rate_pct, n_months):
    """Principal and interest on a fully amortizing loan.

    M = L * r(1+r)^n / ((1+r)^n - 1), with r the monthly rate. The SQL in
    LOAN_SQL uses the same expression; the unit tests check both against
    known answers.
    """
    r = annual_rate_pct / 100 / 12
    growth = (1 + r) ** n_months
    return principal * r * growth / (growth - 1)


def scale(value, benchmark):
    """x_i = c_i / b_i, or None if either is missing."""
    if value is None or benchmark is None:
        return None
    return value / benchmark


def mean(values):
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def score_county(c, bench):
    """Both scores for one county.

    c: {component: value or None} for pti, d, r, s, cltv.
    bench: {component: benchmark}.
    Returns (burden_row, equity_row): each component, its x, and the score.

    Burden needs both halves: at least one NewBuyer component and S. With only
    one half it would describe new buyers or existing owners, not both, so it's
    left null rather than silently changing meaning. n_components counts the
    Burden inputs present (of 4); validate.py warns below 3.
    """
    x = {k: round4(scale(c[k], bench[k])) for k in NEW_BUYER + EXISTING + EQUITY}
    new_buyer = round4(mean(x[k] for k in NEW_BUYER))
    existing = round4(mean(x[k] for k in EXISTING))
    burden = None
    if new_buyer is not None and existing is not None:
        burden = round4(BURDEN_WEIGHTS[0] * new_buyer + BURDEN_WEIGHTS[1] * existing)
    burden_row = {**{k: c[k] for k in NEW_BUYER + EXISTING},
                  **{f"x_{k}": x[k] for k in NEW_BUYER + EXISTING},
                  "new_buyer": new_buyer, "existing": existing, "burden": burden,
                  "n_components": sum(c[k] is not None for k in NEW_BUYER + EXISTING)}
    equity_row = {"cltv": c["cltv"], "x_cltv": x["cltv"], "equity": x["cltv"]}
    return burden_row, equity_row


def round4(v):
    return None if v is None else round(v, 4)


# --- ACS inputs -------------------------------------------------------------------

def acs_inputs(year):
    """Per county: S (cost burden share, %) and tau (effective property tax rate).

    S reuses the Phase 2b function, so it matches the acs_cost_burden layer
    definition (DECISIONS 014), including its 30-owner suppression. tau =
    median real estate taxes paid / median home value (B25103_E001 /
    B25077_E001); taxes are top-coded at $10,000, so tau is a lower bound in
    those counties. Also returns the national S, for the benchmark.
    """
    b25091 = acs.read_table("b25091", year=year)
    b25103 = acs.read_table("b25103", year=year)
    b25077 = acs.read_table("b25077", year=year)
    s, tau = {}, {}
    for fips, row in b25091.items():
        share, _, denom = burden_share(row, B25091_AT_LEAST_30)
        s[fips] = round(share, 2) if share is not None and denom >= MIN_OWNERS else None
    for fips in set(b25103) | set(b25077):
        taxes = b25103.get(fips, {}).get("B25103_E001")
        value = b25077.get(fips, {}).get("B25077_E001")
        tau[fips] = taxes / value if taxes and value else None
    nation = acs.read_table("b25091", geo_ids={acs.NATION_GEO_ID}, year=year)[acs.NATION_GEO_ID]
    s_national, _, _ = burden_share(nation, B25091_AT_LEAST_30)
    return s, tau, s_national


# --- HMDA inputs ------------------------------------------------------------------

# Per-loan table: one row per qualifying origination, with its PTI or the first
# rule it fails. `src` is a relation (read_csv(...) in production, a small
# table in the tests), and county_inputs(fips, tau, premium) holds the ACS tax
# rate and FIO annual premium per county.
LOAN_SQL = f"""
WITH loans AS (
    SELECT
        county_code AS fips,
        state_code,
        TRY_CAST(interest_rate AS DOUBLE)  AS rate,
        TRY_CAST(loan_amount AS DOUBLE)    AS amount,
        TRY_CAST(property_value AS DOUBLE) AS value,
        TRY_CAST(income AS DOUBLE)         AS income,
        TRY_CAST(loan_term AS DOUBLE)      AS term,
        loan_type = '{CONVENTIONAL}'        AS is_conv,
        TRY_CAST(combined_loan_to_value_ratio AS DOUBLE) AS cltv,
        {dti_over_43_sql()}                 AS dti_over_43,
        -- Payments that don't amortize normally: the formula doesn't describe
        -- them. '1111' (exempt from reporting) stays in, as in DECISIONS 013.
        '1' IN (interest_only_payment, balloon_payment, negative_amortization) AS special
    FROM {{src}}
    WHERE {FILTERS}
),
priced AS (
    SELECT l.*, ci.tau, ci.premium,
           -- n = the loan's own term; 360 only when it's NA or Exempt.
           term IS NULL OR term <= 0           AS term_fallback,
           CASE WHEN term > 0 THEN term ELSE {DEFAULT_TERM} END AS n,
           rate / 100 / 12                      AS r
    FROM loans l LEFT JOIN county_inputs ci USING (fips)
),
checked AS (
    SELECT *,
        CASE
            WHEN COALESCE(special, FALSE)                         THEN 'payment_feature'
            WHEN rate IS NULL OR rate <= 0 OR rate > {MAX_RATE}   THEN 'rate'
            WHEN amount IS NULL OR amount <= 0
                 OR value IS NULL OR value <= 0                   THEN 'amount_value'
            WHEN income IS NULL OR income < {MIN_INCOME}          THEN 'income'
            WHEN tau IS NULL OR premium IS NULL                   THEN 'no_tax_or_premium'
        END AS early_rule
    FROM priced
),
pti AS (
    SELECT *,
        CASE WHEN early_rule IS NULL THEN
            ( amount * r * pow(1 + r, n) / (pow(1 + r, n) - 1)   -- M: principal and interest
            + tau * value / 12                                   -- T: property tax
            + premium / 12 )                                     -- I: insurance
            / (income * 1000 / 12)                               -- monthly income
        END AS pti_raw
    FROM checked
)
SELECT *,
    COALESCE(early_rule, CASE WHEN pti_raw > {MAX_PTI} THEN 'pti_cap' END) AS rule,
    CASE WHEN early_rule IS NULL AND pti_raw <= {MAX_PTI} THEN pti_raw END AS pti
FROM pti
"""

# Applications for R: same filters, any decision (originated, approved not
# accepted, denied).
APPS_SQL = f"""
SELECT county_code AS fips, state_code,
       action_taken = '{DENIED}' AND {denied_for_dti_sql()} AS dti_denial
FROM {{src}}
WHERE action_taken IN ({sql_list(APPLICATION_ACTIONS)}) AND {BASE_FILTERS}
"""

NATIONAL_SCOPE = f"""
    CASE WHEN regexp_full_match(fips, '[0-9]{{5}}') THEN CAST(left(fips, 2) AS INTEGER) <= 56
         ELSE state_code IN ({sql_list(STATES_50_DC)}) END
"""

# County aggregates. GROUPING SETS adds national rows (grouped by in_scope);
# the one with in_scope = TRUE is the 50 states + DC total. County codes are
# 5 digits or 'NA', so 'national' can't collide with one. Shares are exact
# integer ratios (count / count), not float averages, so they don't depend on
# the order DuckDB sums rows in.
AGG_SQL = f"""
WITH l AS (SELECT *, {NATIONAL_SCOPE} AS in_scope FROM ({LOAN_SQL})),
a AS (SELECT *, {NATIONAL_SCOPE} AS in_scope FROM ({APPS_SQL})),
loan_agg AS (
    SELECT CASE WHEN GROUPING(fips) = 1 THEN 'national' ELSE fips END AS key, in_scope,
        count(*)                                             AS n_loans,
        {', '.join(f"count(*) FILTER (WHERE rule = '{r}') AS n_{r}" for r in RULES)},
        count(pti)                                           AS n_pti,
        count(*) FILTER (WHERE pti IS NOT NULL AND term_fallback) AS n_term_fallback,
        median(pti)                                          AS pti,
        count(dti_over_43)                                   AS n_d,
        count(*) FILTER (WHERE dti_over_43)                  AS k_d,
        count(cltv) FILTER (WHERE is_conv)                   AS n_cltv,
        count(*) FILTER (WHERE is_conv AND cltv > {CLTV_THRESHOLD}) AS k_cltv
    FROM l GROUP BY GROUPING SETS ((fips, in_scope), (in_scope))
),
app_agg AS (
    SELECT CASE WHEN GROUPING(fips) = 1 THEN 'national' ELSE fips END AS key, in_scope,
        count(*) AS n_r, count(*) FILTER (WHERE dti_denial) AS k_r
    FROM a GROUP BY GROUPING SETS ((fips, in_scope), (in_scope))
)
-- National rows get the key 'national' rather than a NULL fips: NULL never
-- equals NULL in a join, so the loan and application totals wouldn't meet.
SELECT * FROM loan_agg FULL JOIN app_agg USING (key, in_scope)
"""


def connect():
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute(f"SET temp_directory = '{RAW_DIR / 'duckdb_tmp'}'")
    con.execute("SET preserve_insertion_order = false")
    return con


def load_county_inputs(con, tau, premium):
    """county_inputs(fips, tau, premium) for the counties that have both."""
    con.execute("CREATE OR REPLACE TABLE county_inputs (fips VARCHAR, tau DOUBLE, premium DOUBLE)")
    rows = [(f, tau[f], premium[f]) for f in sorted(tau)
            if tau[f] is not None and premium.get(f) is not None]
    if rows:
        con.executemany("INSERT INTO county_inputs VALUES (?, ?, ?)", rows)


def hmda_aggregates(con, src):
    """Run AGG_SQL over `src`. Returns ({fips: row}, national_row)."""
    # str.replace, not str.format: the SQL has literal braces (a regex {5}).
    cur = con.execute(AGG_SQL.replace("{src}", src))
    cols = [d[0] for d in cur.description]
    counties, national = {}, None
    for values in cur.fetchall():
        row = dict(zip(cols, values))
        if not row["in_scope"]:
            continue
        if row["key"] == "national":
            national = row
        else:
            counties[row["key"]] = row
    return counties, national


def share(k, n, min_n=MIN_N):
    """k / n as a percent (2 decimals), or None below min_n."""
    if not n or n < min_n:
        return None
    return round(100 * k / n, 2)


def hmda_components(row, min_n=MIN_N):
    """PTI (ratio), D, R and CLTV (percent) for one county's aggregates."""
    if row is None:
        return {"pti": None, "d": None, "r": None, "cltv": None}
    return {
        "pti": round(row["pti"], 4) if row["n_pti"] and row["n_pti"] >= min_n else None,
        "d": share(row["k_d"], row["n_d"], min_n),
        "r": share(row["k_r"], row["n_r"], min_n),
        "cltv": share(row["k_cltv"], row["n_cltv"], min_n),
    }


def rule_report(counties, national, shapes):
    """Loans removed by each PTI rule, nationally and per map county (DECISIONS 025).

    A county is flagged when the loan-level rules (everything except the
    county-level no_tax_or_premium) remove more than 10% of its loans. Only
    counties with at least MIN_N loans are flagged: below that the county
    gets no PTI anyway, and with 3 loans one bad record is 33%.
    """
    def counts(row):
        c = {"loans": row["n_loans"] or 0, "kept": row["n_pti"] or 0,
             "term_fallback": row["n_term_fallback"] or 0}
        c.update({r: row[f"n_{r}"] or 0 for r in RULES})
        return c

    per_county = {f: counts(counties[f]) for f in sorted(shapes) if f in counties
                  and counties[f]["n_loans"]}
    flagged = sorted(
        f for f, c in per_county.items()
        if c["loans"] >= MIN_N and sum(c[r] for r in LOAN_RULES) > LOSS_FLAG_SHARE * c["loans"])
    return {"national": counts(national), "counties": per_county,
            "flagged_over_10pct": flagged}


def compute(csv_path, acs_year, premium, benchmarks, shapes):
    """Every component and both scores for one vintage.

    Returns (burden, equity, report): burden and equity are {fips: row} over
    every map county; report has the PTI rule counts and the national values
    (which build_benchmarks.py turns into benchmarks for 2019).
    """
    s, tau, s_national = acs_inputs(acs_year)
    con = connect()
    load_county_inputs(con, tau, premium)
    counties, national = hmda_aggregates(con, f"read_csv('{csv_path}', header = true, all_varchar = true)")

    burden, equity = {}, {}
    for fips in sorted(shapes):
        c = hmda_components(counties.get(fips))
        c["s"] = s.get(fips)
        burden[fips], equity[fips] = score_county(c, benchmarks)

    nat = hmda_components(national, min_n=1)
    nat["s"] = round(s_national, 2)
    report = rule_report(counties, national, shapes)
    report["national_values"] = nat
    return burden, equity, report
