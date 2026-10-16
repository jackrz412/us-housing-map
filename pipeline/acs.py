"""Read ACS table-based summary files (downloaded by fetch_acs.py).

Each .dat file is pipe-delimited, one row per geography, with a GEO_ID column
followed by <TABLE>_E### (estimate) and <TABLE>_M### (90% margin of error)
columns.
"""
import json
import math

from fetch_acs import ACS_YEAR, raw_path

COUNTY_PREFIX = "0500000US"  # GEO_ID summary level 050 = county
NATION_GEO_ID = "0100000US"


def parse(raw):
    """Estimate or MOE as a number, or None when Census publishes none.

    Census marks unavailable values with large negative codes (-666666666
    "not available", -999999999, -888888888, -222222222 ...). None of the
    quantities we read can legitimately be negative, so any negative is None.
    """
    if raw == "":
        return None
    v = float(raw)
    if v < 0:
        return None
    return int(v) if v.is_integer() and "." not in raw else v


def read_table(table, geo_ids=None, year=ACS_YEAR):
    """Return {fips: {column: value}} for county rows.

    If geo_ids is given, return {geo_id: {column: value}} for exactly those
    GEO_IDs instead (e.g. the national row). `year` is the 5-year vintage's
    end year (2024 = 2020-2024).
    """
    out = {}
    with raw_path(table, year).open() as f:
        header = f.readline().rstrip("\n").split("|")
        for line in f:
            parts = line.rstrip("\n").split("|")
            geo_id = parts[0]
            if geo_ids is not None:
                if geo_id in geo_ids:
                    out[geo_id] = {h: parse(p) for h, p in zip(header[1:], parts[1:])}
            elif geo_id.startswith(COUNTY_PREFIX):
                # GEO_ID ends in the 5-digit state+county FIPS. Slicing keeps it
                # a string, so leading zeros survive.
                out[geo_id[len(COUNTY_PREFIX):]] = {
                    h: parse(p) for h, p in zip(header[1:], parts[1:])}
    return out


def source_info(table, year=ACS_YEAR):
    """Provenance recorded by fetch_acs.py, for meta.json."""
    return json.loads(raw_path(table, year).with_suffix(".source.json").read_text())


def period(year=ACS_YEAR):
    return f"{year - 4}–{year}"


def legend_period(year=ACS_YEAR):
    return f"ACS {year - 4}–{year} 5-year"


# --- Margins of error ---------------------------------------------------------
# ACS estimates are survey-based. Census publishes a 90% MOE with each one, and
# its handbook ("Understanding and Using ACS Data", ch. 8) gives approximation
# formulas for derived estimates. These treat the inputs as independent, which
# they aren't exactly, so the results are approximate.

def moe_sum(*moes):
    """MOE of a sum or difference of estimates."""
    return math.sqrt(sum(m * m for m in moes))


def moe_proportion(p, x, moe_y, moe_x):
    """MOE of p = y / x where y is a subset of x (e.g. a share of households)."""
    radicand = moe_y ** 2 - p ** 2 * moe_x ** 2
    if radicand < 0:
        # Census: when the subtraction goes negative, use the ratio formula.
        radicand = moe_y ** 2 + p ** 2 * moe_x ** 2
    return math.sqrt(radicand) / x


def cv(estimate, moe):
    """Coefficient of variation: standard error / estimate.

    A 90% MOE is 1.645 standard errors. Undefined (None) for a zero estimate.
    """
    if not estimate:
        return None
    return (moe / 1.645) / estimate
