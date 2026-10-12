"""Build data/processed/income.json from the raw ACS B19013 summary file.

Output shape: {"01001": 72481, ..., "35011": null}, one key per in-scope county
in the map. null means ACS published no estimate; the site shows those counties
as "Data not available". Nothing is estimated or filled in.

Also writes this layer's entry in data/processed/meta.json.

Usage: python3 pipeline/clean_income.py   (run fetch_acs.py first)
"""
import json

from fetch_acs import ACS_YEAR, raw_path
from geo import map_counties
from output import update_meta, write_layer

LAYER = "income"
TABLE = "b19013"
COLUMN = "B19013_E001"  # estimate; B19013_M001 is the margin of error
COUNTY_PREFIX = "0500000US"  # GEO_ID summary level 050 = county
SENTINEL = "-666666666"  # Census code for "estimate not available"


def read_counties(path):
    """Yield (fips, raw value string) for every county row in a summary file."""
    with path.open() as f:
        header = f.readline().rstrip("\n").split("|")
        col = header.index(COLUMN)
        for line in f:
            parts = line.rstrip("\n").split("|")
            geo_id = parts[0]
            if geo_id.startswith(COUNTY_PREFIX):
                # GEO_ID ends in the 5-digit state+county FIPS. Slicing keeps it
                # a string, so leading zeros survive.
                yield geo_id[len(COUNTY_PREFIX):], parts[col]


def parse_value(raw):
    if raw == SENTINEL or raw == "":
        return None
    return int(raw)


def build():
    shapes = map_counties()
    acs = dict(read_counties(raw_path(TABLE)))

    # Keep only counties the map can draw. That drops Puerto Rico (its shapes
    # are filtered out of the universe) and any FIPS the map doesn't know.
    dropped = sorted(set(acs) - set(shapes))
    no_row = sorted(set(shapes) - set(acs))
    income = {fips: parse_value(acs[fips]) for fips in sorted(shapes) if fips in acs}
    # A map county with no ACS row at all is also "not available".
    for fips in no_row:
        income[fips] = None
    income = dict(sorted(income.items()))

    nulls = sorted(f for f, v in income.items() if v is None)
    print(f"{len(income)} counties, {len(nulls)} null: {nulls}")
    print(f"dropped {len(dropped)} ACS rows not on the map "
          f"(first few: {dropped[:5]})")
    if no_row:
        print(f"WARNING: {len(no_row)} map counties had no ACS row: {no_row}")
    return income


def meta_entry():
    source = json.loads(raw_path(TABLE).with_suffix(".source.json").read_text())
    return {
        "label": "Median household income",
        "unit": "USD",
        "source": "US Census Bureau, American Community Survey 5-year estimates, "
                  "table B19013",
        "period": f"{ACS_YEAR - 4}–{ACS_YEAR}",
        "legend_period": f"ACS {ACS_YEAR - 4}–{ACS_YEAR} 5-year",
        "source_url": source["url"],
        "source_last_modified": source["last_modified"],
        "source_sha256": source["sha256"],
    }


def main():
    changed = write_layer(LAYER, build())
    update_meta({LAYER: meta_entry()}, {LAYER: changed})


if __name__ == "__main__":
    main()
