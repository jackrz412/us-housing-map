"""Download the newest CFPB county 90+ day delinquency file into data/raw/.

CFPB publishes every 4-8 months, and each release has a new filename ending in
its last month (…-thru-2025-12.csv). There's no stable "latest" URL, so this
reads the download page and takes the newest county file it links to. Each
release revises the full history, so only the newest file is used.

Usage: python3 pipeline/fetch_cfpb.py [--force]
"""
import argparse
import hashlib
import json
import re
import urllib.request

from geo import RAW_DIR

PAGE_URL = ("https://www.consumerfinance.gov/data-research/"
            "mortgage-performance-trends/download-the-data/")
FILE_URL = ("https://files.consumerfinance.gov/data/mortgage-performance/downloads/"
            "CountyMortgagesPercent-90-plusDaysLate-thru-{period}.csv")
LINK_RE = re.compile(r"CountyMortgagesPercent-90-plusDaysLate-thru-(\d{4}-\d{2})\.csv")

# CFPB's CDN rejects some generic browser user agents (a bare "Mozilla/5.0"
# gets 403) but accepts an honest, descriptive one.
HEADERS = {"User-Agent": "us-housing-map/1.0 (+https://github.com/jackrz412/us-housing-map)"}

RAW_PATH = RAW_DIR / "cfpb_county_90plus.csv"
SOURCE_PATH = RAW_DIR / "cfpb_county_90plus.source.json"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as r:
        return r.read(), r.headers.get("Last-Modified")


def newest_period():
    html, _ = get(PAGE_URL)
    periods = sorted(set(LINK_RE.findall(html.decode("utf-8", "replace"))))
    if not periods:
        raise SystemExit(f"no county 90+ file links found on {PAGE_URL}")
    return periods[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download")
    args = parser.parse_args()

    period = newest_period()
    if RAW_PATH.exists() and SOURCE_PATH.exists() and not args.force:
        have = json.loads(SOURCE_PATH.read_text())["period"]
        if have == period:
            print(f"skip {RAW_PATH.name} (already have the thru-{period} release)")
            return
        print(f"newer release found: thru-{period} (have thru-{have})")

    url = FILE_URL.format(period=period)
    print(f"fetch {url}")
    body, last_modified = get(url)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(body)
    SOURCE_PATH.write_text(json.dumps({
        "url": url,
        "period": period,
        "last_modified": last_modified,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }, indent=2) + "\n")
    print(f"wrote {RAW_PATH} ({len(body):,} bytes)")


if __name__ == "__main__":
    main()
