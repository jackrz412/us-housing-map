"""Download ACS 5-year table-based summary files into data/raw/.

Uses the bulk summary files on www2.census.gov rather than api.census.gov,
because the API now requires a key and these files don't (DATA_SOURCES.md).

Usage: python3 pipeline/fetch_acs.py [--year 2024] [--force]
Years: 2024 (2020-2024, the current layers) and 2019 (2015-2019, the stress
index backtest and benchmarks).
Files already in data/raw/ are reused unless --force is given.
"""
import argparse
import hashlib
import json
import urllib.request

from geo import RAW_DIR

# Latest published 5-year vintage (2020-2024). Bump when 2021-2025 is released.
ACS_YEAR = 2024
TABLES = [
    "b19013",  # median household income
    "b25091",  # mortgage status by owner costs as % of household income (distribution)
    "b25103",  # median real estate taxes paid, by mortgage status
    "b11001",  # households (total)
    "b25119",  # median household income by tenure (owner / renter)
    "b25077",  # median home value (stress index: effective property tax rate)
]

URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/{year}"
    "/table-based-SF/data/5YRData/acsdt5y{year}-{table}.dat"
)
# Table-based files start with the 2021 vintage. Census published 2015-2019
# in the same format only as a "prototype" (DECISIONS 027, which records the
# spot-check against the official sequence-based release).
PROTOTYPE_URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/{year}"
    "/prototype/5YRData/acsdt5y{year}-{table}.dat"
)
PROTOTYPE_YEARS = {2019}


def url_for(table, year=ACS_YEAR):
    return (PROTOTYPE_URL if year in PROTOTYPE_YEARS else URL).format(year=year, table=table)


def raw_path(table, year=ACS_YEAR):
    return RAW_DIR / f"acsdt5y{year}-{table}.dat"


def fetch(table, year=ACS_YEAR, force=False):
    dest = raw_path(table, year)
    # The sidecar records where the file came from, for meta.json.
    sidecar = dest.with_suffix(".source.json")
    if dest.exists() and sidecar.exists() and not force:
        print(f"skip {dest.name} (already downloaded; --force to refresh)")
        return

    url = url_for(table, year)
    print(f"fetch {url}")
    with urllib.request.urlopen(url, timeout=300) as resp:
        body = resp.read()
        last_modified = resp.headers.get("Last-Modified")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    sidecar.write_text(json.dumps({
        "url": url,
        "last_modified": last_modified,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }, indent=2) + "\n")
    print(f"wrote {dest} ({len(body):,} bytes)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=ACS_YEAR)
    parser.add_argument("--force", action="store_true", help="re-download files")
    args = parser.parse_args()
    for table in TABLES:
        fetch(table, year=args.year, force=args.force)


if __name__ == "__main__":
    main()
