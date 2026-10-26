"""Build the housing stress index on current data (Phase 4a).

Inputs: HMDA 2025 Snapshot, ACS 2020-2024, FIO 2022 county premiums
(data/processed/fio_premium_2022.json, committed; build_insurance.py) and the
fixed 2019 benchmarks (data/processed/benchmarks.json; build_benchmarks.py).

Outputs in data/processed/, each {fips: {...}} over every map county:
  burden.json          pti, d, r, s, each x_*, new_buyer, existing, burden,
                       n_components (Burden inputs present, of 4)
  equity.json          cltv, x_cltv, equity
  index_pti_rules.json loans removed by each PTI rule, nationally and per
                       county, and the counties losing more than 10%
Formulas: stress_index.py; definitions: SPEC.md Phase 4.

Usage: .venv/bin/python pipeline/clean_index.py
(run fetch_hmda.py and fetch_acs.py first; needs duckdb)
"""
import json

import stress_index as si
from acs import legend_period, period, source_info
from fetch_acs import ACS_YEAR
from fetch_hmda import CSV_PATH, HMDA_YEAR, SOURCE_PATH, dataset_label
from geo import PROCESSED_DIR, map_counties
from output import update_meta, write_layer

FIO_YEAR = 2022  # latest FIO year; no later release (DATA_SOURCES.md, Phase 4.0 §3)


def load(name):
    return json.loads((PROCESSED_DIR / f"{name}.json").read_text())


def main():
    shapes = map_counties()
    benchmarks = load("benchmarks")
    premium = load(f"fio_premium_{FIO_YEAR}")
    burden, equity, report = si.compute(CSV_PATH, ACS_YEAR, premium, benchmarks, shapes)

    report.pop("national_values")  # only used for 2019 benchmarks
    report.pop("national_shares")  # same: the benchmarks' metadata
    changed = {
        "burden": write_layer("burden", burden),
        "equity": write_layer("equity", equity),
        "index_pti_rules": write_layer("index_pti_rules", report),
    }

    hmda = json.loads(SOURCE_PATH.read_text())
    fio_meta = json.loads((PROCESSED_DIR / "meta.json").read_text())[f"fio_premium_{FIO_YEAR}"]
    common = {
        "source": "Housing stress index (Phase 4): FFIEC HMDA, Census ACS, Treasury FIO",
        "period": f"HMDA {HMDA_YEAR}; ACS {period()}; FIO {FIO_YEAR}",
        "legend_period": f"HMDA {HMDA_YEAR} · {legend_period()} · FIO {FIO_YEAR}",
        "source_url": hmda["url"],
        "hmda_dataset": dataset_label(HMDA_YEAR),
        "hmda_source_sha256": hmda["sha256"],
        "acs_source_url": source_info("b25091")["url"],
        "fio_source_sha256": fio_meta["source_sha256"],
        "fio_crosswalk": fio_meta["crosswalk"],
        "benchmarks": benchmarks,
        "min_n": si.MIN_N,
    }
    update_meta({
        "burden": {**common, "label": "Burden score", "unit": "× benchmark",
                   "definition": "0.5 × mean(x_PTI, x_D, x_R) + 0.5 × x_S; x = value ÷ "
                                 "benchmark (SPEC Phase 4, DECISIONS 020, 023)",
                   "flags": {"pti_rules_over_10pct": [f for f in report["flagged_over_10pct"]
                                                      if burden[f]["pti"] is not None],
                             "fewer_than_3_components": sorted(
                                 f for f, row in burden.items()
                                 if row["burden"] is not None and row["n_components"] < 3)}},
        "equity": {**common, "label": "Equity score", "unit": "× benchmark",
                   "definition": "x_CLTV: conventional-loan CLTV > 90% share ÷ its 2019 "
                                 "national value (DECISIONS 021)"},
        "index_pti_rules": {**common, "label": "PTI loan rules: loans removed per rule",
                            "unit": "loans",
                            "definition": "Loans counted under the first PTI rule they "
                                          "fail (DECISIONS 025)"},
    }, changed)

    n = report["national"]
    print(f"\nPTI rules, national: {n['loans']:,} loans, {n['kept']:,} kept; "
          + ", ".join(f"{r} {n[r]:,}" for r in si.RULES)
          + f"; loan_term fallback to 360 among kept: {n['term_fallback']:,}")
    print(f"counties losing > 10% of loans to loan-level rules: {len(report['flagged_over_10pct'])}")
    for name, rows, keys in (("burden", burden, si.NEW_BUYER + si.EXISTING + ["burden"]),
                             ("equity", equity, ["cltv", "equity"])):
        counts = {k: sum(r[k] is not None for r in rows.values()) for k in keys}
        print(f"{name}: counties with a value: {counts}")


if __name__ == "__main__":
    main()
