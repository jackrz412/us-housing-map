"""Download and unzip an HMDA national loan-level file into data/raw/.

Each zip is ~0.8-1 GB and unzips to one 5-7 GB CSV, so both stay out of git.

Usage: python3 pipeline/fetch_hmda.py [--vintage 2025] [--force]
Vintages: 2025 (Snapshot, the current layers), 2019 (One-Year, stress index
backtest and benchmarks), 2018 (Snapshot, backtest robustness).
Files already in data/raw/ are reused unless --force is given.
"""
import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile

from geo import RAW_DIR

STATIC = "https://files.ffiec.cfpb.gov/static-data"

# "Snapshot" is the first national release for a year, and the only one for
# the newest year. The later One-Year dataset adds resubmissions
# (DATA_SOURCES.md). Pin one dataset type per year so values don't shift
# silently. There is no One-Year file for 2018 (DECISIONS 026).
VINTAGES = {
    2025: {"dataset": "snapshot",
           "url": f"{STATIC}/snapshot/2025/2025_public_lar_csv.zip",
           "csv": "2025_public_lar_csv.csv"},
    2019: {"dataset": "one-year",
           "url": f"{STATIC}/one-year/2019/2019_public_lar_one_year_csv.zip",
           "csv": "2019_public_lar_one_year.csv"},
    2018: {"dataset": "snapshot",
           "url": f"{STATIC}/snapshot/2018/2018_public_lar_csv.zip",
           "csv": "2018_public_lar_csv.csv"},
}

# The year the Phase 2 layers use.
HMDA_YEAR = 2025


def files(year):
    """(url, dataset, zip path, csv path, provenance sidecar path) for a vintage."""
    v = VINTAGES[year]
    zip_path = RAW_DIR / v["url"].rsplit("/", 1)[-1]
    csv_path = RAW_DIR / v["csv"]
    source_path = RAW_DIR / f"{year}_public_lar.source.json"
    return v["url"], v["dataset"], zip_path, csv_path, source_path


URL, DATASET, ZIP_PATH, CSV_PATH, SOURCE_PATH = files(HMDA_YEAR)


def dataset_label(year):
    """e.g. 'Snapshot 2025', 'One-Year 2019', for meta.json."""
    return f"{VINTAGES[year]['dataset'].title()} {year}"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(year, force):
    url, dataset, zip_path, _, source_path = files(year)
    if zip_path.exists() and source_path.exists() and not force:
        print(f"skip {zip_path.name} (already downloaded; --force to refresh)")
        return
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    part = zip_path.with_suffix(".zip.part")
    print(f"fetch {url}")
    with urllib.request.urlopen(url, timeout=600) as resp, part.open("wb") as f:
        last_modified = resp.headers.get("Last-Modified")
        # Stream to disk in chunks; never hold the ~1 GB body in memory.
        shutil.copyfileobj(resp, f, length=1 << 20)
    part.replace(zip_path)  # only a complete download gets the real name
    source_path.write_text(json.dumps({
        "url": url,
        "dataset": dataset,
        "last_modified": last_modified,
        "sha256": sha256(zip_path),
        "bytes": zip_path.stat().st_size,
    }, indent=2) + "\n")
    print(f"wrote {zip_path} ({zip_path.stat().st_size:,} bytes)")


def unzip(year, force):
    _, _, zip_path, csv_path, _ = files(year)
    if csv_path.exists() and not force:
        print(f"skip {csv_path.name} (already unzipped)")
        return
    with zipfile.ZipFile(zip_path) as z:
        [name] = [n for n in z.namelist() if n.endswith(".csv")]
        print(f"unzip {name}")
        with z.open(name) as src, csv_path.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)
    print(f"wrote {csv_path} ({csv_path.stat().st_size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vintage", type=int, default=HMDA_YEAR, choices=sorted(VINTAGES))
    parser.add_argument("--force", action="store_true", help="re-download and re-unzip")
    args = parser.parse_args()
    download(args.vintage, args.force)
    unzip(args.vintage, args.force)


if __name__ == "__main__":
    main()
