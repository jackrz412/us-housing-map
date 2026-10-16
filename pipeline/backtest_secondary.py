"""The one pre-specified secondary backtest analysis (DECISIONS 029), once.

Outcome: each county's mean 90+ day delinquency level, 2023-01 to 2025-12.
Test: Spearman partial correlation of each 2019 measure with that level,
controlling for the county's 2017-01 to 2019-12 mean level, with a 95%
percentile bootstrap CI (1,000 resamples, seed 20261016; each resample is
re-ranked). Measures: Burden, each single component, and lower median income.
Positive = the expected direction ("higher stress, higher later level than
the earlier level alone predicts").

Inputs: the primary run's 2019 scores (reports/backtest/county_scores.json)
and the CFPB file, so nothing else changes. Output:
reports/backtest/secondary.json.

Usage: .venv/bin/python pipeline/backtest_secondary.py   (after backtest.py)
"""
import json
import random
from datetime import date

from backtest import (BASELINE, N_BOOT, OUT_DIR, SEED, WINDOW, bootstrap_ci,
                      partial_spearman, read_cfpb, window_mean)
from fetch_cfpb import SOURCE_PATH as CFPB_SOURCE
from output import write_json

MEASURES = ["burden", "pti", "d", "r", "s", "cltv", "lower_income"]


def evaluate(scores, level, baseline, seed=SEED):
    """{measure: {n, partial_rho, partial_rho_ci}}; one seeded stream, fixed order."""
    rng = random.Random(seed)
    out = {}
    for name in MEASURES:
        rows = [(scores[f][f"{name}_2019"], level[f], baseline[f]) for f in sorted(scores)
                if scores[f][f"{name}_2019"] is not None
                and level.get(f) is not None and baseline.get(f) is not None]

        def stat(s):
            return partial_spearman([r[0] for r in s], [r[1] for r in s], [r[2] for r in s])
        out[name] = {"n": len(rows), "partial_rho": stat(rows),
                     "partial_rho_ci": bootstrap_ci(rows, stat, rng)}
    return out


def main():
    scores = json.loads((OUT_DIR / "county_scores.json").read_text())
    series = read_cfpb()
    if sorted(series) != sorted(scores):
        raise SystemExit("CFPB counties differ from the primary run's")
    level = {f: window_mean(series[f], *WINDOW) for f in scores}
    baseline = {f: window_mean(series[f], *BASELINE) for f in scores}
    result = evaluate(scores, level, baseline)
    write_json(OUT_DIR / "secondary.json", {
        "decision": "DECISIONS 029",
        "run_date": date.today().isoformat(),
        "outcome": f"mean 90+ day delinquency level, {WINDOW[0]} to {WINDOW[1]}",
        "control": f"mean level, {BASELINE[0]} to {BASELINE[1]}",
        "n_boot": N_BOOT, "seed": SEED,
        "cfpb_sha256": json.loads(CFPB_SOURCE.read_text())["sha256"],
        "measures": result,
    })
    for name, v in result.items():
        print(f"  {name:13s} n={v['n']:3d}  partial rho={v['partial_rho']:+.3f}  "
              f"[{v['partial_rho_ci'][0]:+.3f}, {v['partial_rho_ci'][1]:+.3f}]")


if __name__ == "__main__":
    main()
