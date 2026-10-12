"""Build data/processed/permits_per_1000_hh.json (click-panel context).

New residential units permitted in 2025 (Census Building Permits Survey) per
1,000 households (ACS 2020-2024 5-year, B11001). Permits, never "starts".

Usage: python3 pipeline/clean_permits.py   (run fetch_bps.py and fetch_acs.py first)
"""
import csv
import json

from acs import period as acs_period, read_table
from fetch_bps import BPS_YEAR, RAW_PATH, SOURCE_PATH
from geo import map_counties
from output import update_meta, write_layer

LAYER = "permits_per_1000_hh"

# The file has two header lines and a blank line before the data.
HEADER_LINES = 3
# Units columns in the first (imputed) block: 1-unit, 2-units, 3-4 units, 5+.
# The first block includes Census's imputation for places that didn't report;
# the second ("rep") block is reported-only and undercounts.
UNIT_COLUMNS = [7, 10, 13, 16]
# County code 000 is a "Balance of State" or "Unorganized Territory" row:
# permits not assigned to any county. Not a county, so dropped.
BALANCE_OF_STATE = "000"


def read_permits():
    """Return {fips: total units permitted}."""
    units = {}
    with RAW_PATH.open(newline="") as f:
        for _ in range(HEADER_LINES):
            next(f)
        for row in csv.reader(f):
            if len(row) <= max(UNIT_COLUMNS) or row[2] == BALANCE_OF_STATE:
                continue
            # State and county FIPS are separate columns; concatenating the
            # strings keeps the zero padding.
            units[row[1] + row[2]] = sum(int(row[c]) for c in UNIT_COLUMNS)
    return units


def build():
    shapes = map_counties()
    permits = read_permits()
    households = read_table("b11001")

    off_map = sorted(set(permits) - set(shapes))
    if off_map:
        print(f"dropped {len(off_map)} BPS counties not on the map: {off_map[:8]}")

    values = {}
    for fips in sorted(shapes):
        hh = households.get(fips, {}).get("B11001_E001")
        # A county absent from BPS isn't a county with zero permits: it has no
        # permit-issuing places in the survey, so the count is unknown.
        if fips not in permits or not hh:
            values[fips] = None
        else:
            values[fips] = round(1000 * permits[fips] / hh, 1)
    kept = sum(v is not None for v in values.values())
    print(f"{LAYER}: {kept:,} of {len(values):,} counties with a value "
          f"({sum(v == 0 for v in values.values()):,} reported zero permits)")
    return values


def meta_entry():
    bps = json.loads(SOURCE_PATH.read_text())
    return {
        "label": "Housing units permitted per 1,000 households",
        "unit": "units per 1,000 households",
        "source": "US Census Bureau, Building Permits Survey (annual county file) and "
                  "American Community Survey 5-year estimates, table B11001",
        "definition": f"New residential units authorized by building permits in {BPS_YEAR} "
                      f"(all structure sizes, including imputation) per 1,000 households "
                      f"(ACS {acs_period()})",
        "period": f"permits {BPS_YEAR}; households {acs_period()}",
        "legend_period": f"BPS {BPS_YEAR}",
        "source_url": bps["url"],
        "source_last_modified": bps["last_modified"],
        "source_sha256": bps["sha256"],
    }


def main():
    changed = write_layer(LAYER, build())
    update_meta({LAYER: meta_entry()}, {LAYER: changed})


if __name__ == "__main__":
    main()
