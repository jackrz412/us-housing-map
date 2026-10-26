"""Convert Treasury FIO ZIP-level homeowners premiums to counties, once, locally.

Writes data/processed/fio_premium_<year>.json: {county fips: average annual
premium per policy, USD} for each premium year, plus coverage and provenance
in meta.json. These tables are COMMITTED and read by the stress index; this
script is not part of the scheduled refresh (DECISIONS 024).

Why local only: HUD's ZIP-county crosswalk now needs an API token. The token
lives in a git-ignored .env file on this machine (HUD_TOKEN=...), never in
GitHub Actions. FIO's data is a one-off release (2018-2022), so there's
nothing for a scheduled job to update.

County premium = the mean of its ZIPs' premiums, weighted by the share of the
county's residential addresses in each ZIP (HUD county-to-ZIP file,
res_ratio), renormalized over the ZIPs FIO publishes. Null when those ZIPs
hold less than half of the county's residential addresses.

Usage: .venv/bin/python pipeline/build_insurance.py
"""
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import acs
from fetch_acs import ACS_YEAR
from geo import PROCESSED_DIR, RAW_DIR, ROOT
from output import write_json

FIO_URL = ("https://home.treasury.gov/system/files/311/Supporting_Underlying_Metrics_and_"
           "Disclaimer_for_Analyses_of_US_Homeowners_Insurance_Markets_2018-2022.xlsx")
FIO_PATH = RAW_DIR / "fio_homeowners_2018_2022.xlsx"
FIO_SHEET = 3  # "Supporting Underlying Metrics"
HUD_API = "https://www.huduser.gov/hudapi/public/usps"
HUD_COUNTY_ZIP = 7  # API type 7 = county-ZIP: the share of a county's addresses in each ZIP

# Premium year -> HUD crosswalk (year, quarter). Each premium year uses a
# crosswalk whose county codes match the other inputs it's combined with:
# Q4 of 2018/2019 for the backtest (old Connecticut counties, as in HMDA and
# ACS 2019), and a recent one for 2022, which the current index pairs with
# 2025 loans on today's map (Connecticut planning regions).
CROSSWALKS = {2018: (2018, 4), 2019: (2019, 4), 2022: (2026, 2)}
MIN_COVERAGE = 0.5
USER_AGENT = "us-housing-map/1.0 (+https://github.com/jackrz412/us-housing-map)"


def read_env():
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    if not env.get("HUD_TOKEN"):
        raise SystemExit("HUD_TOKEN missing: add HUD_TOKEN=... to .env (git-ignored). "
                         "Free token: https://www.huduser.gov/portal/dataset/uspszip-api.html")
    return env


def fetch_fio():
    if not FIO_PATH.exists():
        req = urllib.request.Request(FIO_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as r:
            FIO_PATH.write_bytes(r.read())
    return hashlib.sha256(FIO_PATH.read_bytes()).hexdigest()


def read_xlsx(path, sheet=1):
    """Rows of one worksheet as [{header: value}], with the standard library.

    An .xlsx is a zip of XML files: cells are in xl/worksheets/sheetN.xml, and
    text cells point into a shared string table. Reading it this way avoids
    adding a spreadsheet dependency for a few one-off files.
    """
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        shared = ["".join(t.text or "" for t in si.iter(f"{ns}t"))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{ns}si")]

    def cell_value(c):
        v = c.find(f"{ns}v")
        if v is None:
            inline = c.find(f"{ns}is")
            return "".join(t.text or "" for t in inline.iter(f"{ns}t")) if inline is not None else ""
        return shared[int(v.text)] if c.get("t") == "s" else v.text

    rows = []
    with z.open(f"xl/worksheets/sheet{sheet}.xml") as f:
        for _, el in ET.iterparse(f):
            if el.tag == f"{ns}row":
                rows.append({re.match(r"[A-Z]+", c.get("r")).group(0): cell_value(c)
                             for c in el.findall(f"{ns}c")})
                el.clear()
    col = {letter: name.strip() for letter, name in rows[0].items()}
    return [{col[k]: v for k, v in r.items() if k in col} for r in rows[1:]]


def read_fio():
    """{year: {zip: premium per policy}} from the FIO workbook.

    ZIPs are stored as numbers, so New England ZIPs lost their leading zero;
    zero-pad.
    """
    out = {}
    for r in read_xlsx(FIO_PATH, FIO_SHEET):
        zip_code, year, premium = r.get("ZIP Code", ""), r.get("Year", ""), r.get("Premiums Per Policy", "")
        if zip_code and year and premium:
            out.setdefault(int(year), {})[zip_code.zfill(5)] = float(premium)
    return out


def hud_get(token, params):
    url = f"{HUD_API}?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            time.sleep(30 * (attempt + 1))  # rate-limited: back off


def api_row(item):
    """(county, zip, res_ratio) from one HUD API result or downloaded-file row.
    For the county-ZIP type the county is in "county" and the ZIP in "geoid"."""
    return str(item["county"]).zfill(5), str(item["geoid"]).zfill(5), float(item["res_ratio"])


def fetch_crosswalk(token, year, quarter, counties):
    """[(county, zip, res_ratio)] for one HUD quarter, and a hash of the input.

    Three routes, cheapest first:
      1. a file downloaded from huduser.gov while logged in, saved as
         data/raw/COUNTY-ZIP_<MM><YYYY>.xlsx (e.g. COUNTY-ZIP_122019.xlsx), with
         the same columns as the API;
      2. the API with query=All (one request; HUD supports it from 2021 Q1);
      3. the API one county at a time (older quarters; ~3,200 requests,
         cached per county so an interrupted run resumes).
    """
    xlsx = RAW_DIR / f"COUNTY-ZIP_{quarter * 3:02d}{year}.xlsx"
    if xlsx.exists():
        rows = [api_row(r) for r in read_xlsx(xlsx) if r.get("county")]
        return rows, hashlib.sha256(xlsx.read_bytes()).hexdigest(), xlsx.name

    cache = RAW_DIR / f"hud_county_zip_{year}q{quarter}"
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    if (year, quarter) >= (2021, 1):
        path = cache / "All.json"
        if not path.exists():
            path.write_text(json.dumps(hud_get(token, {"type": HUD_COUNTY_ZIP, "query": "All",
                                                       "year": year, "quarter": quarter})))
        rows += [api_row(item) for item in json.loads(path.read_text())["data"]["results"]]
    else:
        for i, county in enumerate(sorted(counties), 1):
            path = cache / f"{county}.json"
            if not path.exists():
                path.write_text(json.dumps(hud_get(token, {"type": HUD_COUNTY_ZIP, "query": county,
                                                           "year": year, "quarter": quarter})))
                time.sleep(0.5)  # be polite to HUD's API
            if i % 250 == 0:
                print(f"  {year} Q{quarter}: {i:,} of {len(counties):,} counties")
            rows += [api_row(item) for item in json.loads(path.read_text())["data"]["results"]]
    digest = hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()
    return rows, digest, f"HUD USPS API type {HUD_COUNTY_ZIP}"


def county_premiums(premium_by_zip, crosswalk):
    """{county: (premium, coverage)} using residential-address weights."""
    acc = {}
    for county, zip_code, w in crosswalk:
        a = acc.setdefault(county, [0.0, 0.0, 0.0])  # covered weight, weighted sum, total weight
        a[2] += w
        p = premium_by_zip.get(zip_code)
        if p is not None and w > 0:
            a[0] += w
            a[1] += w * p
    out = {}
    for county, (covered, total_p, total_w) in sorted(acc.items()):
        coverage = covered / total_w if total_w else 0.0
        premium = round(total_p / covered, 2) if covered and coverage >= MIN_COVERAGE else None
        out[county] = (premium, round(coverage, 4))
    return out


def main():
    token = read_env()["HUD_TOKEN"]
    fio_sha = fetch_fio()
    fio = read_fio()
    meta_path = PROCESSED_DIR / "meta.json"
    meta = json.loads(meta_path.read_text())
    for year, (cw_year, cw_quarter) in CROSSWALKS.items():
        # County list for per-county API calls: that vintage's ACS counties
        # (old Connecticut in 2018/2019, planning regions now).
        acs_year = 2019 if cw_year < 2022 else ACS_YEAR
        counties = [c for c in acs.read_table("b25077", year=acs_year) if int(c[:2]) <= 56]
        crosswalk, cw_sha, cw_source = fetch_crosswalk(token, cw_year, cw_quarter, counties)
        result = county_premiums(fio[year], crosswalk)
        # Keep only real counties of that vintage. A few HUD rows carry just a state code
        # (e.g. "48", or Pacific territories like "64"), which zero-pads to a bogus "00048".
        valid = set(counties)
        dropped = sorted(set(result) - valid)
        if dropped:
            print(f"  {year}: dropped {len(dropped)} codes not in the county list: {dropped}")
        values = {c: p for c, (p, _) in result.items() if c in valid}
        name = f"fio_premium_{year}"
        write_json(PROCESSED_DIR / f"{name}.json", values)
        kept = sum(v is not None for v in values.values())
        print(f"{name}: {kept:,} of {len(values):,} counties with a premium "
              f"(crosswalk {cw_year} Q{cw_quarter}, {len(crosswalk):,} county-ZIP rows)")
        meta[name] = {
            "label": f"Average homeowners premium per policy, {year}",
            "unit": "USD per year",
            "source": "US Treasury Federal Insurance Office, Supporting Underlying Metrics "
                      "for Analyses of U.S. Homeowners Insurance Markets 2018-2022",
            "source_url": FIO_URL,
            "source_sha256": fio_sha,
            "crosswalk": f"HUD USPS county-ZIP crosswalk {cw_year} Q{cw_quarter}, res_ratio "
                         f"({cw_source})",
            "crosswalk_sha256": cw_sha,
            "min_coverage": MIN_COVERAGE,
            "coverage_below_min": sorted(c for c, p in values.items() if p is None),
        }
    write_json(meta_path, meta)


if __name__ == "__main__":
    main()
