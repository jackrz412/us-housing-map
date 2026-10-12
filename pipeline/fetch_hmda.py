"""Download and unzip the HMDA Snapshot national loan-level file into data/raw/.

The zip is ~740 MB and unzips to one ~5 GB CSV, so both stay out of git.

Usage: python3 pipeline/fetch_hmda.py [--force]
Files already in data/raw/ are reused unless --force is given.
"""
import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile

from geo import RAW_DIR

HMDA_YEAR = 2025
# "Snapshot" is the first national release for a year, and the only one for
# the newest year. The later One-Year and Three-Year datasets add resubmissions
# (DATA_SOURCES.md). Pin one dataset type so values don't shift silently.
DATASET = "snapshot"
URL = (f"https://files.ffiec.cfpb.gov/static-data/{DATASET}/{HMDA_YEAR}/"
       f"{HMDA_YEAR}_public_lar_csv.zip")

ZIP_PATH = RAW_DIR / f"{HMDA_YEAR}_public_lar_csv.zip"
CSV_PATH = RAW_DIR / f"{HMDA_YEAR}_public_lar_csv.csv"
SOURCE_PATH = RAW_DIR / f"{HMDA_YEAR}_public_lar.source.json"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(force):
    if ZIP_PATH.exists() and SOURCE_PATH.exists() and not force:
        print(f"skip {ZIP_PATH.name} (already downloaded; --force to refresh)")
        return
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    part = ZIP_PATH.with_suffix(".zip.part")
    print(f"fetch {URL}")
    with urllib.request.urlopen(URL, timeout=600) as resp, part.open("wb") as f:
        last_modified = resp.headers.get("Last-Modified")
        # Stream to disk in chunks; never hold the 740 MB body in memory.
        shutil.copyfileobj(resp, f, length=1 << 20)
    part.replace(ZIP_PATH)  # only a complete download gets the real name
    SOURCE_PATH.write_text(json.dumps({
        "url": URL,
        "dataset": DATASET,
        "last_modified": last_modified,
        "sha256": sha256(ZIP_PATH),
        "bytes": ZIP_PATH.stat().st_size,
    }, indent=2) + "\n")
    print(f"wrote {ZIP_PATH} ({ZIP_PATH.stat().st_size:,} bytes)")


def unzip(force):
    if CSV_PATH.exists() and not force:
        print(f"skip {CSV_PATH.name} (already unzipped)")
        return
    with zipfile.ZipFile(ZIP_PATH) as z:
        [name] = [n for n in z.namelist() if n.endswith(".csv")]
        print(f"unzip {name}")
        with z.open(name) as src, CSV_PATH.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)
    print(f"wrote {CSV_PATH} ({CSV_PATH.stat().st_size:,} bytes)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-download and re-unzip")
    args = parser.parse_args()
    download(args.force)
    unzip(args.force)


if __name__ == "__main__":
    main()
