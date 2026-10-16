"""Phase 4.0 (DECISIONS 027) spot-check: ACS 2019 5-year prototype table-based files vs the official
sequence-based release, for every county in a set of states, every cell
(estimate and MOE) of every table the index uses.

Official layout: per state and sequence, a zip holding e<...>.txt (estimates)
and m<...>.txt (MOEs). Each row: FILEID, FILETYPE, STUSAB, CHARITER, SEQUENCE,
LOGRECNO, then the sequence's cells. A table occupies `cells` columns starting
at 1-based position `start`. g<...>.csv maps LOGRECNO to GEOID.
"""
import csv
import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

# The prototype files, as downloaded by: pipeline/fetch_acs.py --year 2019
PROTO = Path(__file__).resolve().parent.parent / "data" / "raw"
BASE = "https://www2.census.gov/programs-surveys/acs/summary_file/2019/data/5_year_seq_by_state"
TABLES = {  # table: (sequence, start position, cells)
    "B11001": ("0035", 7, 9), "B19013": ("0058", 177, 1), "B25077": ("0114", 246, 1),
    "B25091": ("0115", 108, 23), "B25103": ("0116", 199, 3), "B25119": ("0117", 221, 3),
}
STATES = {"Alabama": "al", "Alaska": "ak", "California": "ca", "Connecticut": "ct",
          "Delaware": "de", "DistrictOfColumbia": "dc", "Florida": "fl", "NewYork": "ny",
          "Texas": "tx", "Vermont": "vt"}


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def num(s):
    """Official files leave unavailable cells empty or '.'; the prototype uses
    large negative codes. Both mean 'no value', so compare them as None."""
    s = s.strip()
    if s in ("", "."):
        return None
    v = float(s)
    return None if v < 0 else v


def proto(table):
    out = {}
    with open(PROTO / f"acsdt5y2019-{table.lower()}.dat") as f:
        hdr = f.readline().rstrip("\n").split("|")
        for line in f:
            p = line.rstrip("\n").split("|")
            if p[0].startswith("0500000US"):
                out[p[0][9:]] = dict(zip(hdr[1:], p[1:]))
    return out, hdr[1:]


def main():
    protos = {t: proto(t) for t in TABLES}
    counties = cells = mismatches = 0
    missing_both = 0
    examples = []
    for state, ab in STATES.items():
        d = f"{BASE}/{state}/All_Geographies_Not_Tracts_Block_Groups"
        geo = {}
        for row in csv.reader(io.StringIO(get(f"{d}/g20195{ab}.csv").decode("latin-1"))):
            if row[2] == "050":  # SUMLEVEL county
                gid = next(c for c in row if re.fullmatch(r"05000US\d{5}", c))
                geo[row[4]] = gid[-5:]
        n_state = len(geo)
        for table, (seq, start, ncell) in TABLES.items():
            z = zipfile.ZipFile(io.BytesIO(get(f"{d}/20195{ab}{seq}000.zip")))
            rows = {}
            for kind in ("e", "m"):
                name = f"{kind}20195{ab}{seq}000.txt"
                for r in csv.reader(io.TextIOWrapper(z.open(name), "latin-1")):
                    if r[5] in geo:
                        rows.setdefault(geo[r[5]], {})[kind] = r[start - 1:start - 1 + ncell]
            pdata, pcols = protos[table]
            for fips, ev in rows.items():
                for i in range(ncell):
                    for kind, col in (("e", f"{table}_E{i + 1:03d}"), ("m", f"{table}_M{i + 1:03d}")):
                        o = num(ev[kind][i])
                        p = num(pdata[fips][col])
                        cells += 1
                        if o is None and p is None:
                            missing_both += 1
                        elif o != p:
                            mismatches += 1
                            if len(examples) < 15:
                                examples.append((fips, col, ev[kind][i], pdata[fips][col]))
        counties += n_state
        print(f"{state}: {n_state} counties checked")
        sys.stdout.flush()
    print(f"\ncounties: {counties}; cells compared: {cells:,}; both unavailable: {missing_both}; mismatches: {mismatches}")
    for e in examples:
        print("  mismatch", e)


if __name__ == "__main__":
    main()
