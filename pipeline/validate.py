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


def main():
    shapes = map_counties()
    print(f"map universe: {len(shapes):,} counties (50 states + DC)")
    meta_path = PROCESSED_DIR / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    r = Report()
    for name, rules in LAYERS.items():
        validate_layer(name, rules, shapes, meta, r)

    print(f"\n{'FAILED' if r.failures else 'OK'}: {r.failures} failure(s)")
    sys.exit(1 if r.failures else 0)


if __name__ == "__main__":
    main()
