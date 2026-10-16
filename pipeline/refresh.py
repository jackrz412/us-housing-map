"""Refresh every layer whose upstream source has changed (Phase 3).

For each source, HEAD-request its files and compare their Last-Modified dates
with data/processed/sources.json (committed alongside the data). Only changed
sources are re-downloaded, and only the clean_*.py scripts that read them are
re-run, so the 740 MB HMDA file isn't fetched every week.

Also checks whether a newer data year has been published (ACS, HMDA, BPS).
That is reported, never switched to automatically: a new vintage can change
table layouts or definitions, so moving to it is a reviewed code change.

Usage:
  python3 pipeline/refresh.py --check     # report what changed, change nothing
  python3 pipeline/refresh.py             # refresh changed sources
  python3 pipeline/refresh.py --force     # rebuild every layer from fresh downloads
Options: --summary FILE (append a Markdown report, e.g. $GITHUB_STEP_SUMMARY),
         --vintages FILE (write new-vintage notices, one per line)

Run validate.py afterwards; this script doesn't validate.
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import fetch_acs
import fetch_bps
import fetch_cfpb
import fetch_hmda
from geo import PROCESSED_DIR
from output import write_json

PIPELINE = Path(__file__).resolve().parent
MANIFEST = PROCESSED_DIR / "sources.json"
HEADERS = fetch_cfpb.HEADERS  # descriptive user agent, accepted by every source


def acs_urls(year=fetch_acs.ACS_YEAR):
    return [fetch_acs.URL.format(year=year, table=t) for t in fetch_acs.TABLES]


def hmda_url(year=fetch_hmda.HMDA_YEAR):
    return (f"https://files.ffiec.cfpb.gov/static-data/{fetch_hmda.DATASET}/{year}/"
            f"{year}_public_lar_csv.zip")


def bps_url(year=fetch_bps.BPS_YEAR):
    return f"https://www2.census.gov/econ/bps/County/co{year}a.txt"


# Each source: the files that define it (resolved at run time; CFPB's URL
# changes with every release) and the fetch script that downloads them.
SOURCES = {
    "acs": {"urls": acs_urls, "fetch": "fetch_acs.py"},
    "hmda": {"urls": lambda: [hmda_url()], "fetch": "fetch_hmda.py"},
    "bps": {"urls": lambda: [bps_url()], "fetch": "fetch_bps.py"},
    "cfpb": {"urls": lambda: [fetch_cfpb.FILE_URL.format(period=fetch_cfpb.newest_period())],
             "fetch": "fetch_cfpb.py"},
}

# Each clean script and the sources it reads. A script re-runs when any of
# its sources changed.
CLEANS = {
    "clean_income.py": ["acs"],
    "clean_acs_burden.py": ["acs"],
    "clean_permits.py": ["acs", "bps"],
    "clean_hmda.py": ["hmda"],
    "clean_delinquency.py": ["cfpb"],
    # The stress index (Phase 4a) reads HMDA and ACS, plus two committed
    # inputs that the refresh never rebuilds: the fixed 2019 benchmarks and
    # the FIO county premiums (DECISIONS 020, 024).
    "clean_index.py": ["hmda", "acs"],
}

# Next-vintage probes: if one of these exists, a newer data year is out.
VINTAGE_PROBES = {
    f"ACS {fetch_acs.ACS_YEAR - 3}–{fetch_acs.ACS_YEAR + 1} 5-year":
        lambda: acs_urls(fetch_acs.ACS_YEAR + 1)[0],
    f"HMDA {fetch_hmda.HMDA_YEAR + 1} Snapshot": lambda: hmda_url(fetch_hmda.HMDA_YEAR + 1),
    f"Building Permits {fetch_bps.BPS_YEAR + 1} annual": lambda: bps_url(fetch_bps.BPS_YEAR + 1),
}


def head(url):
    """Return the Last-Modified header, or None if the file doesn't exist (404)."""
    req = urllib.request.Request(url, method="HEAD", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.headers.get("Last-Modified") or r.headers.get("ETag") or "present"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def remote_state():
    """{source: {url: last_modified}} for every source, from HEAD requests."""
    state = {}
    for name, src in SOURCES.items():
        state[name] = {}
        for url in src["urls"]():
            lm = head(url)
            if lm is None:
                raise SystemExit(f"{name}: expected file is missing upstream: {url}")
            state[name][url] = lm
    return state


def run(script, *args):
    print(f"\n$ {script} {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, str(PIPELINE / script), *args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only; change nothing")
    parser.add_argument("--force", action="store_true", help="treat every source as changed")
    parser.add_argument("--summary", type=Path, help="append a Markdown report to this file")
    parser.add_argument("--vintages", type=Path, help="write new-vintage notices to this file")
    args = parser.parse_args()

    recorded = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    current = remote_state()
    changed = [s for s in SOURCES if args.force or recorded.get(s) != current[s]]
    cleans = [c for c, deps in CLEANS.items() if set(deps) & set(changed)]
    # A clean script needs all of its sources on disk, changed or not.
    fetches = sorted({d for c in cleans for d in CLEANS[c]})

    vintages = [f"{label} appears to be published: {url()}"
                for label, url in VINTAGE_PROBES.items() if head(url()) is not None]

    lines = ["## Data refresh", ""]
    for s in SOURCES:
        status = "changed" if s in changed else "unchanged"
        lines.append(f"- **{s}**: {status}")
        if s in changed:
            for url, lm in current[s].items():
                was = (recorded.get(s) or {}).get(url, "not recorded")
                lines.append(f"  - `{url.rsplit('/', 1)[-1]}`: {was} → {lm}")
    lines += ["", f"Re-running: {', '.join(cleans) or 'nothing'}"]
    if vintages:
        lines += ["", "### Newer data available (not switched automatically)"]
        lines += [f"- {v}" for v in vintages]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.summary:
        with args.summary.open("a") as f:
            f.write(report)
    if args.vintages and vintages:
        args.vintages.write_text("\n".join(vintages) + "\n")

    if args.check or not cleans:
        return

    for s in fetches:
        # --force on the changed ones; the others are only fetched if missing.
        run(SOURCES[s]["fetch"], *(["--force"] if s in changed else []))
    for c in cleans:
        run(c)

    # Record the new upstream state only after every clean succeeded.
    write_json(MANIFEST, {s: current[s] for s in SOURCES})
    print(f"\nwrote {MANIFEST.name}")


if __name__ == "__main__":
    main()
