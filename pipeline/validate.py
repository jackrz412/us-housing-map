"""Validate data/processed/ after a pipeline run (SPEC: Validation).

Exits non-zero if any check fails, so a scheduled run can stop before deploying
bad data.

Usage: python3 pipeline/validate.py
"""
import json
import re
import sys

from geo import MAX_STATE_FIPS, PROCESSED_DIR, map_counties

# Per-layer rules. min_counties counts non-null values. Add a layer here as
# each one is built; CFPB delinquency will get min_counties=450 (DECISIONS 007).
#
# HMDA metrics are suppressed below 30 valid loans per county, which leaves
# ~2,650-2,750 counties (2025 Snapshot). Their floor of 2,400 sits ~10% under
# that: a normal year passes, a broken filter or truncated download doesn't.
HMDA_FLOOR = 2400
# The CLTV share counts conventional loans only (DECISIONS 019), so fewer
# counties reach 30 valid loans (~2,330); same ~10% margin.
HMDA_CONV_FLOOR = 2100
LAYERS = {
    "income": {"min_counties": 3000, "min": 5_000, "max": 500_000},
    "hmda_loans": {"min_counties": 3000, "min": 0, "max": 500_000},
    "hmda_rate": {"min_counties": HMDA_FLOOR, "min": 0, "max": 20},
    "hmda_dti_over_43": {"min_counties": HMDA_FLOOR, "min": 0, "max": 100},
    "hmda_cltv_over_90": {"min_counties": HMDA_CONV_FLOOR, "min": 0, "max": 100},
    "hmda_govt_share": {"min_counties": HMDA_FLOOR, "min": 0, "max": 100},
    "hmda_loan_amount": {"min_counties": HMDA_FLOOR, "min": 10_000, "max": 5_000_000},
    "acs_cost_burden": {"min_counties": 3000, "min": 0, "max": 100},
    "acs_cost_burden_severe": {"min_counties": 3000, "min": 0, "max": 100},
    "acs_property_tax_income": {"min_counties": 3000, "min": 0, "max": 20},
    # BPS covers ~3,020 counties (those with permit-issuing places), so the
    # standard 3,000 floor would leave almost no margin.
    "permits_per_1000_hh": {"min_counties": 2900, "min": 0, "max": 500},
    # CFPB publishes only ~500 counties (DECISIONS 007).
    "cfpb_delinquency_90": {"min_counties": 450, "min": 0, "max": 20},
    "cfpb_delinquency_change": {"min_counties": 450, "min": -10, "max": 10},
    # With the SD floored at 0.2 points, |z| > 20 would need a 4-point move.
    "cfpb_delinquency_z": {"min_counties": 450, "min": -20, "max": 20},
}
META_FIELDS = ["label", "source", "period", "legend_period", "source_url", "run_date"]

FIPS_RE = re.compile(r"^\d{5}$")


class Report:
    def __init__(self):
        self.failures = 0

    def check(self, ok, msg, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {msg}" + (f": {detail}" if detail and not ok else ""))
        if not ok:
            self.failures += 1

    def info(self, msg):
        print(f"  info  {msg}")


def sample(items, n=10):
    items = sorted(items)
    return ", ".join(map(str, items[:n])) + (f" … (+{len(items) - n})" if len(items) > n else "")


def validate_layer(name, rules, shapes, meta, r):
    print(f"\n[{name}]")
    path = PROCESSED_DIR / f"{name}.json"
    if not path.exists():
        r.check(False, f"{path.name} exists")
        return
    data = json.loads(path.read_text())
    r.check(isinstance(data, dict), "file is a {fips: value} object")
    if not isinstance(data, dict):
        return

    keys = set(data)
    bad_fips = [k for k in keys if not FIPS_RE.match(k)]
    r.check(not bad_fips, "FIPS are 5-digit zero-padded strings", sample(bad_fips))

    out_of_scope = [k for k in keys if FIPS_RE.match(k) and int(k[:2]) > MAX_STATE_FIPS]
    r.check(not out_of_scope, "no FIPS outside 50 states + DC", sample(out_of_scope))

    # Anti-join: data FIPS that have no shape in the map. These would be
    # silently invisible on the page, which is the bug this check exists for.
    no_shape = keys - set(shapes)
    r.check(not no_shape, "every data FIPS has a map shape (anti-join)", sample(no_shape))

    # The reverse direction is allowed (those counties render grey), but report it.
    no_data = set(shapes) - {k for k, v in data.items() if v is not None}
    r.info(f"{len(no_data)} map counties show 'Data not available': {sample(no_data)}")

    values = {k: v for k, v in data.items() if v is not None}
    wrong_type = [k for k, v in values.items()
                  if isinstance(v, bool) or not isinstance(v, (int, float))]
    r.check(not wrong_type, "values are numbers or null", sample(wrong_type))

    # Reports the surviving count every run, so a slow drift is visible
    # before it trips the floor.
    r.check(len(values) >= rules["min_counties"],
            f"{len(values):,} counties with a value (floor {rules['min_counties']:,})")

    numeric = {k: v for k, v in values.items() if k not in wrong_type}
    out_of_bounds = [f"{k}={v}" for k, v in numeric.items()
                     if not rules["min"] <= v <= rules["max"]]
    r.check(not out_of_bounds,
            f"values within plausible bounds {rules['min']:,}–{rules['max']:,}",
            sample(out_of_bounds))

    entry = meta.get(name, {})
    missing = [f for f in META_FIELDS if not entry.get(f)]
    r.check(not missing, "meta.json entry complete", f"missing {missing}")

    # Per-county flags in meta.json (e.g. low_reliability, topcoded) must point
    # at counties that are on the map and have a value to qualify.
    for flag, fips_list in entry.get("flags", {}).items():
        stray = [f for f in fips_list if f not in values]
        r.check(not stray, f"flag '{flag}' ({len(fips_list)}) only on counties with a value",
                sample(stray))


# --- Stress index (Phase 4) ---------------------------------------------------------
# burden.json and equity.json hold an object per county, not a single number.
# Bounds from SPEC Phase 4: county PTI 0.05-1.5, scores 0.2-5. Floors sit ~10%
# under the current counts (burden ~2,860, PTI ~2,650, equity = the CLTV layer).
INDEX_LAYERS = {
    "burden": {
        "fields": ["pti", "d", "r", "s", "x_pti", "x_d", "x_r", "x_s",
                   "new_buyer", "existing", "burden", "n_components"],
        "score": "burden", "min_counties": 2500,
        "component_floors": {"pti": 2300, "d": HMDA_FLOOR, "r": HMDA_FLOOR, "s": 3000},
        "bounds": {"pti": (0.05, 1.5), "burden": (0.2, 5)},
    },
    "equity": {
        "fields": ["cltv", "x_cltv", "equity"],
        "score": "equity", "min_counties": HMDA_CONV_FLOOR,
        "component_floors": {"cltv": HMDA_CONV_FLOOR},
        # Reported, not failed: a handful of counties have almost no high-CLTV
        # conventional loans (0.6-7%), which is real, and puts x_CLTV below 0.2.
        # Owner to decide whether the 0.2 floor should apply to Equity.
        "warn_bounds": {"equity": (0.2, 5)},
    },
}
MIN_COMPONENTS = 3


def validate_index(name, rules, shapes, meta, r):
    print(f"\n[{name}]")
    path = PROCESSED_DIR / f"{name}.json"
    if not path.exists():
        r.check(False, f"{path.name} exists")
        return
    data = json.loads(path.read_text())
    no_shape = set(data) - set(shapes)
    r.check(not no_shape, "every data FIPS has a map shape (anti-join)", sample(no_shape))
    r.check(set(shapes) <= set(data), "every map county has a row", sample(set(shapes) - set(data)))
    bad_rows = [f for f, row in data.items()
                if not isinstance(row, dict) or set(row) != set(rules["fields"])]
    r.check(not bad_rows, f"rows have exactly the fields {rules['fields']}", sample(bad_rows))
    if bad_rows:
        return

    scored = [f for f, row in data.items() if row[rules["score"]] is not None]
    r.check(len(scored) >= rules["min_counties"],
            f"{len(scored):,} counties with a {rules['score']} score (floor {rules['min_counties']:,})")
    for field, floor in rules["component_floors"].items():
        n = sum(row[field] is not None for row in data.values())
        r.check(n >= floor, f"{n:,} counties with {field} (floor {floor:,})")

    def out_of(field, lo, hi):
        return [f"{f}={row[field]}" for f, row in data.items()
                if row[field] is not None and not lo <= row[field] <= hi]

    for field, (lo, hi) in rules.get("bounds", {}).items():
        bad = out_of(field, lo, hi)
        r.check(not bad, f"{field} within {lo}–{hi}", sample(bad))
    for field, (lo, hi) in rules.get("warn_bounds", {}).items():
        bad = out_of(field, lo, hi)
        if bad:
            r.info(f"WARNING {len(bad)} counties with {field} outside {lo}–{hi}: {sample(bad)}")

    if "n_components" in rules["fields"]:
        thin = [f for f in scored if data[f]["n_components"] < MIN_COMPONENTS]
        if thin:
            r.info(f"WARNING {len(thin)} counties' {rules['score']} rests on fewer than "
                   f"{MIN_COMPONENTS} components: {sample(thin)}")

    entry = meta.get(name, {})
    missing = [f for f in META_FIELDS if not entry.get(f)]
    r.check(not missing, "meta.json entry complete", f"missing {missing}")


def validate_benchmarks(r):
    print("\n[benchmarks]")
    path = PROCESSED_DIR / "benchmarks.json"
    if not path.exists():
        r.check(False, "benchmarks.json exists")
        return
    b = json.loads(path.read_text())
    r.check(set(b) == {"pti", "d", "r", "s", "cltv"}, "one benchmark per component", str(sorted(b)))
    r.check(b.get("pti") == 0.28, "b_PTI = 0.28 (fixed)", str(b.get("pti")))
    r.check(all(isinstance(v, (int, float)) and 0 < v < 100 for v in b.values()),
            "benchmarks are positive percentages or ratios", str(b))


# --- Insurance premiums (DECISIONS 024) ---------------------------------------------
# Built once, locally, so the refresh never rewrites them, but a rebuild could still
# let a bad code through (e.g. "00048" from a HUD row with only a state code). 2022
# uses today's counties, so it gets the map anti-join. 2018/2019 use 2019 codes for
# the backtest, so they may also hold the counties that existed then but are off
# today's map: Connecticut's 8 old counties and Alaska's Valdez-Cordova (split 2019).
PREMIUM_YEARS = (2018, 2019, 2022)
PREMIUM_MAP_YEAR = 2022
COUNTIES_2019_ONLY = {"02261", "09001", "09003", "09005", "09007", "09009", "09011",
                      "09013", "09015"}


def validate_premiums(shapes, meta, r):
    for year in PREMIUM_YEARS:
        name = f"fio_premium_{year}"
        print(f"\n[{name}]")
        path = PROCESSED_DIR / f"{name}.json"
        if not path.exists():
            r.check(False, f"{path.name} exists")
            continue
        data = json.loads(path.read_text())
        allowed = set(shapes) | (COUNTIES_2019_ONLY if year != PREMIUM_MAP_YEAR else set())
        unknown = set(data) - allowed
        r.check(not unknown, "every FIPS is a county of its vintage (anti-join)", sample(unknown))
        if year == PREMIUM_MAP_YEAR:
            r.check(set(shapes) <= set(data), "every map county has a row",
                    sample(set(shapes) - set(data)))

        # The meta list must name exactly the counties left null for low coverage.
        listed = set(meta.get(name, {}).get("coverage_below_min", []))
        nulls = {k for k, v in data.items() if v is None}
        r.check(listed == nulls, f"coverage_below_min ({len(listed)}) matches the null counties",
                f"listed only: {sample(listed - nulls)}; null only: {sample(nulls - listed)}")


def main():
    shapes = map_counties()
    print(f"map universe: {len(shapes):,} counties (50 states + DC)")
    meta_path = PROCESSED_DIR / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    r = Report()
    for name, rules in LAYERS.items():
        validate_layer(name, rules, shapes, meta, r)
    validate_benchmarks(r)
    validate_premiums(shapes, meta, r)
    for name, rules in INDEX_LAYERS.items():
        validate_index(name, rules, shapes, meta, r)

    print(f"\n{'FAILED' if r.failures else 'OK'}: {r.failures} failure(s)")
    sys.exit(1 if r.failures else 0)


if __name__ == "__main__":
    main()
