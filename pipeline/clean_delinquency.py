"""Build the CFPB delinquency layers (Phase 2c).

Outputs in data/processed/, each {fips: value} over every in-scope map county
(null where CFPB doesn't publish the county, ~2,640 of 3,144):
  cfpb_delinquency_z.json       map layer: latest 90+ day rate as a z-score
                                against the county's own 2017-2019 baseline
  cfpb_delinquency_change.json  click panel: latest rate minus baseline mean,
                                percentage points
  cfpb_delinquency_90.json      click panel: latest 90+ day rate, %

See DECISIONS 016 and METHODOLOGY.md.

Usage: python3 pipeline/clean_delinquency.py   (run fetch_cfpb.py first)
"""
import csv
import json
import re
import statistics

from fetch_cfpb import RAW_PATH, SOURCE_PATH
from geo import map_counties
from output import update_meta, write_layer

# Baseline: the county's own "normal" before the pandemic (DECISIONS 016).
# 2015-2016 are excluded because delinquency was still falling from the
# foreclosure crisis (national 1.6% -> 1.1% over 2015-2017); including them
# inflates both the baseline mean and SD, and pushes most counties' z negative.
# 2020 onward is excluded because forbearance kept missed payments from
# being reported as delinquent.
BASELINE_START = "2017-01"
BASELINE_END = "2019-12"

# CFPB rounds rates to 0.1 percentage points. With a tiny baseline SD, one
# rounding step would swing z wildly (the lowest 2017-2019 SD is 0.03, where
# one step = 3 z). Flooring
# the SD at 0.2 caps a single 0.1-point step at 0.5 z, the width of the
# narrowest legend class. Counties where the floor applies are flagged.
SD_FLOOR = 0.2

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def read_rows():
    with RAW_PATH.open(newline="") as f:
        reader = csv.DictReader(f)
        months = [c for c in reader.fieldnames if MONTH_RE.match(c)]
        rows = [r for r in reader if r["RegionType"] == "County"]
    return months, rows


def build():
    shapes = map_counties()
    months, rows = read_rows()
    latest = months[-1]
    baseline = [m for m in months if BASELINE_START <= m <= BASELINE_END]
    if len(baseline) != 36:
        raise SystemExit(f"expected 36 baseline months, found {len(baseline)}")

    layers = {"cfpb_delinquency_z": {}, "cfpb_delinquency_change": {},
              "cfpb_delinquency_90": {}}
    floored = []
    found = {}
    for r in rows:
        # FIPSCode comes wrapped in literal single quotes ('01003'), presumably
        # so Excel keeps the leading zero. Strip them; keep it a string.
        fips = r["FIPSCode"].strip().strip("'")
        values = [float(r[m]) for m in baseline]
        mean = statistics.mean(values)
        # Sample SD (n - 1): the 36 months are a sample of the county's normal.
        sd = statistics.stdev(values)
        if sd < SD_FLOOR:
            floored.append(fips)
            sd = SD_FLOOR
        rate = float(r[latest])
        found[fips] = (rate, rate - mean, (rate - mean) / sd)

    off_map = sorted(set(found) - set(shapes))
    if off_map:
        print(f"dropped {len(off_map)} CFPB counties not on the map: {off_map}")

    for fips in sorted(shapes):
        rate, change, z = found.get(fips, (None, None, None))
        layers["cfpb_delinquency_90"][fips] = rate
        layers["cfpb_delinquency_change"][fips] = None if change is None else round(change, 2)
        layers["cfpb_delinquency_z"][fips] = None if z is None else round(z, 2)

    floored = sorted(f for f in floored if f in shapes)
    kept = sum(v is not None for v in layers["cfpb_delinquency_z"].values())
    print(f"latest month {latest}; {kept} of {len(shapes):,} counties; "
          f"SD floored for {len(floored)}")
    return layers, latest, floored


def meta_entries(latest, floored):
    src = json.loads(SOURCE_PATH.read_text())
    year, month = latest.split("-")
    month_name = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(month) - 1]
    common = {
        "source": "Consumer Financial Protection Bureau, Mortgage Performance Trends "
                  "(National Mortgage Database), county 90+ days delinquent",
        "period": f"{month_name} {year}",
        "legend_period": f"CFPB {month_name} {year}",
        "release": f"thru-{src['period']}",
        "source_url": src["url"],
        "source_last_modified": src["last_modified"],
        "source_sha256": src["sha256"],
        "coverage_note": "CFPB publishes only counties with at least 1,000 mortgages "
                         "in its sample (DECISIONS 007)",
    }
    baseline = {"baseline": f"{BASELINE_START} to {BASELINE_END}", "sd_floor": SD_FLOOR}
    return {
        "cfpb_delinquency_z": {
            **common, **baseline,
            "label": "Mortgage delinquency vs the county's own 2017–2019 baseline",
            "unit": "standard deviations",
            "definition": "(latest 90+ day delinquency rate − county's 2017–2019 monthly "
                          "mean) ÷ county's 2017–2019 monthly SD, with the SD floored "
                          f"at {SD_FLOOR} percentage points",
            "flags": {"sd_floored": floored} if floored else {},
        },
        "cfpb_delinquency_change": {
            **common, **baseline,
            "label": "Change in 90+ day delinquency vs 2017–2019 average",
            "unit": "percentage points",
            "definition": "latest 90+ day delinquency rate minus the county's "
                          "2017–2019 monthly mean",
        },
        "cfpb_delinquency_90": {
            **common,
            "label": "Mortgages 90+ days delinquent",
            "unit": "% of mortgages",
            "definition": "share of mortgages 90 or more days delinquent in the latest "
                          "month (CFPB rounds to 0.1 points)",
        },
    }


def main():
    layers, latest, floored = build()
    changed = {name: write_layer(name, values) for name, values in layers.items()}
    update_meta(meta_entries(latest, floored), changed)


if __name__ == "__main__":
    main()
