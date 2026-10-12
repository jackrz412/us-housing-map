"""Download the Census Building Permits Survey annual county file into data/raw/.

Usage: python3 pipeline/fetch_bps.py [--force]
"""
import argparse
import hashlib
import json
import urllib.request

from geo import RAW_DIR

BPS_YEAR = 2025
# Annual county file: coYYYYa.txt. Monthly (coYYMMc) and year-to-date
# (coYYMMy) files also exist; the annual file is final for the year.
URL = f"https://www2.census.gov/econ/bps/County/co{BPS_YEAR}a.txt"
RAW_PATH = RAW_DIR / f"co{BPS_YEAR}a.txt"
SOURCE_PATH = RAW_PATH.with_suffix(".source.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download")
    args = parser.parse_args()
    if RAW_PATH.exists() and SOURCE_PATH.exists() and not args.force:
        print(f"skip {RAW_PATH.name} (already downloaded; --force to refresh)")
        return
    print(f"fetch {URL}")
    with urllib.request.urlopen(URL, timeout=120) as resp:
        body = resp.read()
        last_modified = resp.headers.get("Last-Modified")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(body)
    SOURCE_PATH.write_text(json.dumps({
        "url": URL,
        "last_modified": last_modified,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }, indent=2) + "\n")
    print(f"wrote {RAW_PATH} ({len(body):,} bytes)")


if __name__ == "__main__":
    main()
