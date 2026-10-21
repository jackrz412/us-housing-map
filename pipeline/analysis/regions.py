"""Regional and coastal-metro comparison of current conditions (descriptive only).

For each area: the weighted median of county values for owner cost burden
(share of mortgaged owners paying 30%+), new-buyer PTI, the high-CLTV share
(conventional loans), property tax % of owner income, and the Burden and
Equity scores. Inputs are the same processed files the map uses, so the
numbers describe the live layers.

Method:
  - weight = total households (ACS B11001_E001, same 5-year vintage as the
    ACS layers), except owner cost burden, which is weighted by mortgaged
    owner households with a computed burden (B25091: units with a mortgage
    minus "not computed", the share's own denominator), since it is a share
    of mortgaged owners;
  - weighted median = the first county value, in sorted order, at which the
    cumulative weight reaches half the total weight of counties with a value;
  - a county without a value for a measure is left out of that measure (the
    output records the share of households covered);
  - metros are the county containing the principal city (New York: all five
    boroughs), not the full metro area.

Not a test and not used by the index or the map.

Usage: .venv/bin/python pipeline/analysis/regions.py
Writes reports/regions/regions.json and reports/regions/regions.md.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acs import legend_period, read_table, source_info  # noqa: E402
from clean_acs_burden import B25091_NOT_COMPUTED, B25091_TOTAL  # noqa: E402
from geo import PROCESSED_DIR, ROOT  # noqa: E402

OUT_DIR = ROOT / "reports" / "regions"

STATE_FIPS = {
    "AZ": "04", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MO": "29", "MT": "30", "NE": "31",
    "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
}
# Northeast and Midwest are the Census regions; South Atlantic the Census division.
REGIONS = {
    "Pacific (CA, OR, WA)": "CA OR WA",
    "Mountain": "CO UT NV AZ ID MT WY NM",
    "Northeast": "CT ME MA NH RI VT NJ NY PA",
    "South Atlantic": "DE MD DC VA WV NC SC GA FL",
    "Midwest": "IL IN MI OH WI IA KS MN MO NE ND SD",
}
POOLED = {
    "Pacific + Mountain": ["Pacific (CA, OR, WA)", "Mountain"],
    "Northeast + South Atlantic": ["Northeast", "South Atlantic"],
}
METROS = {
    "Los Angeles (LA Co.)": ["06037"],
    "San Francisco (SF Co.)": ["06075"],
    "Seattle (King Co.)": ["53033"],
    "Denver (Denver Co.)": ["08031"],
    "New York (5 boroughs)": ["36005", "36047", "36061", "36081", "36085"],
    "Boston (Suffolk Co.)": ["25025"],
    "Washington DC": ["11001"],
}

# (key, column label, format)
MEASURES = [
    ("cost_burden", "Owners paying 30%+", lambda v: f"{v:.1f}%"),
    ("pti", "New-buyer PTI", lambda v: f"{100 * v:.1f}%"),
    ("cltv90", "Conventional loans >90% CLTV", lambda v: f"{v:.1f}%"),
    ("prop_tax", "Property tax % of income", lambda v: f"{v:.2f}%"),
    ("burden", "Burden", lambda v: f"{v:.2f}"),
    ("equity", "Equity", lambda v: f"{v:.2f}"),
]
SOURCE_FILES = ["acs_cost_burden", "burden", "hmda_cltv_over_90",
                "acs_property_tax_income", "equity"]


def load(name):
    return json.loads((PROCESSED_DIR / f"{name}.json").read_text())


def field(rows, key):
    return {f: r[key] for f, r in rows.items() if r.get(key) is not None}


def measures():
    burden, equity = load("burden"), load("equity")
    clean = lambda d: {f: v for f, v in d.items() if v is not None}  # noqa: E731
    return {
        "cost_burden": clean(load("acs_cost_burden")),
        "pti": field(burden, "pti"),
        "cltv90": clean(load("hmda_cltv_over_90")),
        "prop_tax": clean(load("acs_property_tax_income")),
        "burden": field(burden, "burden"),
        "equity": field(equity, "equity"),
    }


def weighted_median(values, weights):
    """values, weights: {fips: number}. Returns (median, counties, weight used)."""
    pts = sorted((values[f], weights[f]) for f in values if f in weights)
    if not pts:
        return None, 0, 0
    total = sum(w for _, w in pts)
    cum = 0
    for v, w in pts:
        cum += w
        if cum >= total / 2:
            return v, len(pts), total


def mortgaged_owners():
    """{fips: mortgaged owner households with a computed burden} (B25091).

    The denominator of the owner cost burden share, so the share's weighted
    median describes mortgaged owners, not all households.
    """
    out = {}
    for f, row in read_table("b25091").items():
        total = row.get(f"B25091_E{B25091_TOTAL:03d}")
        not_computed = row.get(f"B25091_E{B25091_NOT_COMPUTED:03d}")
        if total is not None and not_computed is not None and total - not_computed > 0:
            out[f] = total - not_computed
    return out


# Measures weighted by something other than households.
WEIGHTS = {"cost_burden": "mortgaged_owners"}


def summarise(fips, data, weights):
    hh_all = weights["households"]
    fips = [f for f in fips if f in hh_all]
    out = {"counties": len(fips), "households": sum(hh_all[f] for f in fips), "measures": {}}
    for key, _, _ in MEASURES:
        w_all = weights[WEIGHTS.get(key, "households")]
        w = {f: w_all[f] for f in fips if f in w_all}
        total = sum(w.values())
        v, n, used = weighted_median({f: data[key][f] for f in fips if f in data[key]}, w)
        # Coverage is measured in the measure's own weight (households, or
        # mortgaged owners for cost burden).
        out["measures"][key] = {"median": v, "counties": n, "weight": WEIGHTS.get(key, "households"),
                                "coverage": used / total if total else 0}
    return out


def markdown(results, meta):
    head = "| Area | " + " | ".join(label for _, label, _ in MEASURES) + " |"
    lines = [
        "# Regional comparison (descriptive)",
        "",
        f"Generated by `pipeline/analysis/regions.py` from inputs processed through {meta['run_date']}. Do not edit by hand.",
        "",
        "Weighted medians of county values (weights: "
        f"{meta['household_period']} total households; owner cost burden is weighted by "
        "mortgaged owner households, its own denominator). Inputs: the map's processed "
        "files (sources and periods in `regions.json` → `inputs`). Burden and Equity: "
        "1.0 = the 2019 national benchmark; a higher Equity score means more buyers "
        "with thin equity. Metros are principal-city counties only.",
        "",
        head,
        "|" + "---|" * (len(MEASURES) + 1),
    ]
    for group in ["regions", "pooled", "metros"]:
        for name, r in results[group].items():
            cells = [fmt(r["measures"][k]["median"]) if r["measures"][k]["median"] is not None
                     else "–" for k, _, fmt in MEASURES]
            label = f"*{name}*" if group == "pooled" else name
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "Coverage below 98% of each measure's weight (counties without a value are left out):", ""]
    gaps = [f"- {name}, {label}: {r['measures'][k]['coverage']:.1%}"
            for group in ["regions", "pooled", "metros"] for name, r in results[group].items()
            for k, label, _ in MEASURES if r['measures'][k]['coverage'] < 0.98]
    lines += gaps or ["- none"]
    return "\n".join(lines) + "\n"


def main():
    data = measures()
    households = {f: r["B11001_E001"] for f, r in read_table("b11001").items()
                  if r.get("B11001_E001")}
    weights = {"households": households, "mortgaged_owners": mortgaged_owners()}
    by_state = {}
    for f in households:
        by_state.setdefault(f[:2], []).append(f)
    region_fips = {name: [f for st in states.split() for f in by_state.get(STATE_FIPS[st], [])]
                   for name, states in REGIONS.items()}
    results = {
        "regions": {n: summarise(f, data, weights) for n, f in region_fips.items()},
        "pooled": {n: summarise(sum((region_fips[r] for r in rs), []), data, weights)
                   for n, rs in POOLED.items()},
        "metros": {n: summarise(f, data, weights) for n, f in METROS.items()},
    }
    meta_all = load("meta")
    meta = {
        "run_date": max(meta_all[f]["run_date"] for f in SOURCE_FILES),
        "household_period": legend_period(),
        "household_source": source_info("b11001")["url"],
        "inputs": {f: {"legend_period": meta_all[f].get("legend_period"),
                       "run_date": meta_all[f].get("run_date")} for f in SOURCE_FILES},
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "regions.json").write_text(json.dumps(
        {"meta": meta, "method": __doc__.split("Not a test")[0].strip(), **results},
        indent=2, sort_keys=True) + "\n")
    (OUT_DIR / "regions.md").write_text(markdown(results, meta))
    print((OUT_DIR / "regions.md").read_text())


if __name__ == "__main__":
    main()
