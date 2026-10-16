"""Backtest the housing stress index on 2019 inputs (Phase 4b), once.

Question: did counties that scored higher on 2019 inputs see delinquency rise
more afterwards? Design: SPEC.md Phase 4 "Backtest (4b)", DECISIONS 022.

  Scores    the same code as the current index (stress_index.compute), on
            HMDA 2019 One-Year, ACS 2015-2019 and FIO 2019 premiums.
  Outcome   per CFPB county: mean 90+ day delinquency rate over 2023-01 to
            2025-12 minus the mean over 2017-01 to 2019-12, percentage points.
            2020-2022 are left out (forbearance). The 8 Connecticut planning
            regions are left out, leaving 499 counties.
  Metrics   Spearman rank correlation of each measure with the outcome; the
            outcome by quintile of the measure (mean change, share of counties
            that rose); 95% percentile bootstrap CIs from 1,000 resamples of
            counties, seed fixed below.
  Baselines each single component, and median household income alone.
  Key test  does Burden beat its best single input? Answered with paired
            bootstrap CIs for rho(Burden) - rho(component), on the counties
            that have both, for every component.
  Robustness HMDA 2018 Snapshot + FIO 2018 premiums (DECISIONS 026); and the
            2019 scores against a 2024-01 to 2025-12 outcome window.

Fixed before the run, never changed after seeing results (SPEC Phase 4):
  - every measure is oriented so that a positive rho means "higher stress,
    bigger rise": income enters as -income ("lower income");
  - each measure is evaluated on the counties that have it (its own n), and
    each paired comparison on the counties that have both;
  - quintiles are by rank of the measure, ties broken by FIPS, sizes as
    equal as possible (the first n % 5 quintiles get one extra county);
  - "rose" means outcome > 0;
  - Q5-Q1 = mean outcome in the top quintile minus the bottom one.

Outputs in reports/backtest/: results.json (every metric) and
county_scores.json (each county's measures and outcomes, for the charts and
for audit). Charts: backtest_charts.py. Not part of the scheduled refresh.

Usage: .venv/bin/python pipeline/backtest.py
(first: fetch_hmda.py --vintage 2019 and 2018; fetch_acs.py --year 2019;
fio_premium_2019/2018.json from build_insurance.py)
"""
import csv
import hashlib
import json
import random
import re
from datetime import date

import acs
import stress_index as si
from fetch_cfpb import RAW_PATH as CFPB_PATH, SOURCE_PATH as CFPB_SOURCE
from fetch_hmda import VINTAGES, dataset_label, files
from geo import PROCESSED_DIR, ROOT
from output import write_json

OUT_DIR = ROOT / "reports" / "backtest"

BASELINE = ("2017-01", "2019-12")
WINDOW = ("2023-01", "2025-12")
ROBUST_WINDOW = ("2024-01", "2025-12")
EXCLUDED_STATES = {"09"}   # Connecticut planning regions (DECISIONS 022)
ACS_YEAR = 2019
N_BOOT = 1000
SEED = 20261016            # fixed so the CIs are reproducible
CI = (2.5, 97.5)

# Measures, in report order: the two scores, the Burden halves, each
# component, and the income baseline. All oriented "higher = more stress".
SCORES = ["burden", "equity"]
HALVES = ["new_buyer"]     # Existing = x_S, the same ranking as s
COMPONENTS = si.NEW_BUYER + si.EXISTING + si.EQUITY
BASELINES = ["lower_income"]
MEASURES = SCORES + HALVES + COMPONENTS + BASELINES
BURDEN_INPUTS = si.NEW_BUYER + si.EXISTING

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


# --- Outcome ----------------------------------------------------------------------

def read_cfpb(path=CFPB_PATH):
    """{fips: {month: rate}} for CFPB counties, Connecticut left out."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        months = [c for c in reader.fieldnames if MONTH_RE.match(c)]
        out = {}
        for row in reader:
            if row["RegionType"] != "County":
                continue
            fips = row["FIPSCode"].strip("'")
            if fips[:2] in EXCLUDED_STATES:
                continue
            out[fips] = {m: float(row[m]) for m in months if row[m].strip() not in ("", "NA")}
    return out


def window_mean(series, start, end):
    """Mean over [start, end], or None if any month in it is missing."""
    months = month_range(start, end)
    if any(m not in series for m in months):
        return None
    return sum(series[m] for m in months) / len(months)


def month_range(start, end):
    y, m = map(int, start.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def outcome(series, window, baseline=BASELINE):
    """Change in the mean 90+ day rate, window minus baseline, percentage points."""
    after, before = window_mean(series, *window), window_mean(series, *baseline)
    return None if after is None or before is None else after - before


# --- Statistics -------------------------------------------------------------------

def ranks(values):
    """1-based ranks, ties given their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else None


def spearman(xs, ys):
    """Spearman's rho: Pearson correlation of the ranks (ties averaged)."""
    return pearson(ranks(xs), ranks(ys))


def quintiles(pairs):
    """Outcome by quintile of the measure.

    pairs: [(fips, measure, outcome)]. Sorted by measure, ties by FIPS; the
    first len % 5 quintiles get one extra county.
    """
    ordered = sorted(pairs, key=lambda p: (p[1], p[0]))
    n, out, start = len(ordered), [], 0
    for q in range(5):
        size = n // 5 + (1 if q < n % 5 else 0)
        group = ordered[start:start + size]
        start += size
        ys = [p[2] for p in group]
        out.append({"quintile": q + 1, "n": len(group),
                    "measure_min": group[0][1], "measure_max": group[-1][1],
                    "mean_change": sum(ys) / len(ys),
                    "share_rose": sum(y > 0 for y in ys) / len(ys)})
    return out


def q5_minus_q1(pairs):
    q = quintiles(pairs)
    return q[4]["mean_change"] - q[0]["mean_change"]


def percentile(sorted_values, p):
    """Linear-interpolation percentile of an already sorted list."""
    k = (len(sorted_values) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def bootstrap_ci(rows, stat, rng, n_boot=N_BOOT):
    """95% percentile CI of stat(rows) over n_boot resamples of the rows."""
    n = len(rows)
    draws = []
    for _ in range(n_boot):
        v = stat([rows[rng.randrange(n)] for _ in range(n)])
        if v is not None:
            draws.append(v)
    draws.sort()
    return [percentile(draws, CI[0]), percentile(draws, CI[1])]


# --- Evaluation -------------------------------------------------------------------

def evaluate(measures, outcomes, seed=SEED):
    """Every metric for one run.

    measures: {name: {fips: value or None}}; outcomes: {fips: value or None}.
    One random.Random(seed) drives every bootstrap, in a fixed order.
    """
    rng = random.Random(seed)
    result = {"measures": {}, "burden_vs_inputs": {}}
    for name in MEASURES:
        pairs = [(f, v, outcomes[f]) for f, v in sorted(measures[name].items())
                 if v is not None and outcomes.get(f) is not None]
        if len(pairs) < 5:
            result["measures"][name] = {"n": len(pairs)}
            continue
        rho = spearman([p[1] for p in pairs], [p[2] for p in pairs])
        result["measures"][name] = {
            "n": len(pairs),
            "rho": rho,
            "rho_ci": bootstrap_ci(pairs, lambda s: spearman([p[1] for p in s],
                                                            [p[2] for p in s]), rng),
            "quintiles": quintiles(pairs),
            "q5_minus_q1": q5_minus_q1(pairs),
            "q5_minus_q1_ci": bootstrap_ci(pairs, q5_minus_q1, rng),
        }

    burden = measures["burden"]
    for name in BURDEN_INPUTS:
        rows = [(burden[f], measures[name][f], outcomes[f]) for f in sorted(burden)
                if burden[f] is not None and measures[name].get(f) is not None
                and outcomes.get(f) is not None]

        def diff(s):
            y = [r[2] for r in s]
            a, b = spearman([r[0] for r in s], y), spearman([r[1] for r in s], y)
            return None if a is None or b is None else a - b
        if len(rows) < 5:
            result["burden_vs_inputs"][name] = {"n": len(rows)}
            continue
        result["burden_vs_inputs"][name] = {"n": len(rows), "rho_diff": diff(rows),
                                            "rho_diff_ci": bootstrap_ci(rows, diff, rng)}
    return result


def measures_from(burden, equity, income):
    """{measure: {fips: value}} from compute()'s rows and ACS median income."""
    m = {name: {} for name in MEASURES}
    for f, row in burden.items():
        m["burden"][f] = row["burden"]
        m["new_buyer"][f] = row["new_buyer"]
        for k in BURDEN_INPUTS:
            m[k][f] = row[k]
        m["equity"][f] = equity[f]["equity"]
        m["cltv"][f] = equity[f]["cltv"]
        m["lower_income"][f] = None if income.get(f) is None else -income[f]
    return m


# --- Runs -------------------------------------------------------------------------

def score(hmda_year, fio_year, counties, benchmarks):
    """compute() on one vintage, over the backtest counties."""
    _, _, _, csv_path, _ = files(hmda_year)
    premium = json.loads((PROCESSED_DIR / f"fio_premium_{fio_year}.json").read_text())
    burden, equity, report = si.compute(csv_path, ACS_YEAR, premium, benchmarks, counties,
                                        renames=VINTAGES[hmda_year].get("renames"))
    return burden, equity, report


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    series = read_cfpb()
    counties = sorted(series)
    benchmarks = json.loads((PROCESSED_DIR / "benchmarks.json").read_text())
    income = {f: row.get("B19013_E001")
              for f, row in acs.read_table("b19013", year=ACS_YEAR).items()}
    outcomes = {name: {f: outcome(series[f], w) for f in counties}
                for name, w in (("main", WINDOW), ("window_2024_2025", ROBUST_WINDOW))}

    vintages = {}
    for key, hmda_year, fio_year in (("2019", 2019, 2019), ("2018", 2018, 2018)):
        burden, equity, report = score(hmda_year, fio_year, counties, benchmarks)
        vintages[key] = {"measures": measures_from(burden, equity, income), "report": report,
                         "hmda_year": hmda_year, "fio_year": fio_year}
        print(f"scored HMDA {hmda_year}: {sum(r['burden'] is not None for r in burden.values())}"
              f" of {len(counties)} counties with a Burden score")

    runs = {
        "main": ("2019", "main"),
        "hmda_2018": ("2018", "main"),
        "window_2024_2025": ("2019", "window_2024_2025"),
    }
    results = {}
    for name, (vintage, window) in runs.items():
        results[name] = {"inputs": {"hmda": dataset_label(vintages[vintage]["hmda_year"]),
                                    "fio_premiums": vintages[vintage]["fio_year"],
                                    "acs": f"{ACS_YEAR - 4}-{ACS_YEAR}",
                                    "outcome_window": list(WINDOW if window == "main"
                                                           else ROBUST_WINDOW),
                                    "baseline": list(BASELINE)},
                         **evaluate(vintages[vintage]["measures"], outcomes[window])}

    cfpb = json.loads(CFPB_SOURCE.read_text())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(OUT_DIR / "results.json", {
        "run_date": date.today().isoformat(),
        "counties": len(counties),
        "n_boot": N_BOOT, "seed": SEED, "ci": list(CI),
        "benchmarks": benchmarks,
        "sources": {
            "cfpb": {"url": cfpb["url"], "sha256": cfpb["sha256"]},
            **{f"hmda_{v['hmda_year']}": {
                "dataset": dataset_label(v["hmda_year"]),
                "sha256": json.loads(files(v["hmda_year"])[4].read_text())["sha256"]}
               for v in vintages.values()},
            **{f"fio_premium_{y}": {"sha256": sha256(PROCESSED_DIR / f"fio_premium_{y}.json")}
               for y in (2019, 2018)},
            "acs": acs.source_info("b25091", year=ACS_YEAR)["url"],
        },
        "pti_rules": {k: {"national": v["report"]["national"],
                          "flagged_over_10pct": v["report"]["flagged_over_10pct"]}
                      for k, v in vintages.items()},
        "runs": results,
    })
    write_json(OUT_DIR / "county_scores.json", {
        f: {"outcome": outcomes["main"][f], "outcome_2024_2025": outcomes["window_2024_2025"][f],
            **{f"{k}_2019": vintages["2019"]["measures"][k][f] for k in MEASURES},
            **{f"{k}_2018": vintages["2018"]["measures"][k][f] for k in MEASURES}}
        for f in counties})

    for name, r in results.items():
        print(f"\n[{name}]")
        for m, v in r["measures"].items():
            print(f"  {m:13s} n={v['n']:3d}  rho={v['rho']:+.3f}  "
                  f"[{v['rho_ci'][0]:+.3f}, {v['rho_ci'][1]:+.3f}]  "
                  f"Q5-Q1={v['q5_minus_q1']:+.3f}")
        for m, v in r["burden_vs_inputs"].items():
            print(f"  burden - {m:5s} n={v['n']:3d}  diff={v['rho_diff']:+.3f}  "
                  f"[{v['rho_diff_ci'][0]:+.3f}, {v['rho_diff_ci'][1]:+.3f}]")


if __name__ == "__main__":
    main()
