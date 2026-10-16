"""Compute the stress index benchmarks from 2019 inputs, once.

Writes data/processed/benchmarks.json: {component: benchmark}. b_PTI is fixed
at 0.28; every other benchmark is the 2019 national value (50 states + DC) of
that component, computed with the same functions as the scores
(stress_index.py), from HMDA 2019 One-Year and ACS 2015-2019.

These are held FIXED (DECISIONS 020): this script is not part of the
scheduled refresh, and benchmarks are never recomputed from current data. If
a benchmark ever has to change, the owner decides and it's logged in
DECISIONS.md.

Usage: .venv/bin/python pipeline/build_benchmarks.py
(first: fetch_hmda.py --vintage 2019; fetch_acs.py --year 2019)
"""
import json

import stress_index as si
from fetch_acs import url_for
from fetch_hmda import dataset_label, files
from geo import PROCESSED_DIR, map_counties
from output import write_json

HMDA_YEAR = 2019
ACS_YEAR = 2019
OUT = PROCESSED_DIR / "benchmarks.json"


def main():
    _, _, _, csv_path, source_path = files(HMDA_YEAR)
    shapes = map_counties()
    # National values don't depend on the insurance premium or the tax rate
    # (those only enter PTI, whose benchmark is fixed), so none are loaded.
    none = {k: None for k in si.NEW_BUYER + si.EXISTING + si.EQUITY}
    _, _, report = si.compute(csv_path, ACS_YEAR, premium={}, benchmarks=none, shapes=shapes)
    nat = report["national_values"]

    benchmarks = {"pti": si.B_PTI, "d": nat["d"], "r": nat["r"], "s": nat["s"],
                  "cltv": nat["cltv"]}
    write_json(OUT, benchmarks)
    print(f"wrote {OUT.name}: {benchmarks}")

    # Provenance alongside the layers' entries in meta.json.
    meta_path = PROCESSED_DIR / "meta.json"
    meta = json.loads(meta_path.read_text())
    source = json.loads(source_path.read_text())
    meta["benchmarks"] = {
        "label": "Stress index benchmarks (fixed)",
        "definition": "b_PTI = 0.28 (housing at most 28% of gross income); "
                      "d, r, s, cltv = 2019 national values, 50 states + DC "
                      "(percent). Never recomputed from current data (DECISIONS 020).",
        "hmda_dataset": dataset_label(HMDA_YEAR),
        "hmda_source_url": source["url"],
        "hmda_source_sha256": source["sha256"],
        "acs_period": f"{ACS_YEAR - 4}–{ACS_YEAR}",
        "acs_source_url": url_for("b25091", ACS_YEAR),
        "national_counts": {k: report["national"][k] for k in ("loans", "kept")},
    }
    write_json(meta_path, meta)


if __name__ == "__main__":
    main()
