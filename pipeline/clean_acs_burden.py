"""Build the ACS burden layers (Phase 2b).

Outputs in data/processed/, each {fips: value} over every in-scope map county:
  acs_cost_burden.json         % of owners with a mortgage paying >= 30% of
                               household income on owner costs (B25091)
  acs_cost_burden_severe.json  same, >= 50% (click-panel context)
  acs_property_tax_income.json median real estate taxes paid / median
                               household income, % (B25103 / B19013)

Per-county reliability flags (high CV, top-coded taxes) go in meta.json.
See METHODOLOGY.md for definitions and caveats.

Usage: python3 pipeline/clean_acs_burden.py   (run fetch_acs.py first)
"""
from acs import (NATION_GEO_ID, cv, legend_period, moe_proportion, moe_sum,
                 period, read_table, source_info)
from geo import map_counties
from output import update_meta, write_layer

# Suppress a share when fewer than this many mortgaged owner households have a
# computed burden. Same threshold as HMDA's valid-loan rule, for the same
# reason: a share of a handful of households is mostly noise.
MIN_OWNERS = 30

# Flag (don't suppress) estimates whose coefficient of variation exceeds this.
# 40% is the common "low reliability" cutoff (e.g. Esri's ACS reliability
# bands: <=12% high, 12-40% medium, >40% low).
LOW_RELIABILITY_CV = 0.40

# B25103 is top-coded: medians of $10,000 or more are published as 10001.
TAX_TOPCODE = 10001

# B25091 columns for owner-occupied units *with a mortgage* (table shell,
# ACS 2024 5-year). Costs are binned by % of household income.
B25091_TOTAL = 2               # housing units with a mortgage
B25091_NOT_COMPUTED = 12       # zero or negative household income
B25091_AT_LEAST_30 = [8, 9, 10, 11]  # 30-34.9, 35-39.9, 40-49.9, 50+
B25091_AT_LEAST_50 = [11]


def e(row, table, n):
    return row[f"{table}_E{n:03d}"]


def m(row, table, n):
    return row[f"{table}_M{n:03d}"]


def burden_share(row, bins):
    """(share %, cv, denominator) for one county's B25091 row, or Nones.

    Denominator: mortgaged owners minus "not computed" (no income to divide
    by). HUD calls a household cost-burdened above 30% of income; ACS bins
    start at exactly 30.0%, so this is ">= 30%", Census's own convention.
    """
    t = "B25091"
    if any(e(row, t, n) is None for n in [B25091_TOTAL, B25091_NOT_COMPUTED, *bins]):
        return None, None, None
    x = e(row, t, B25091_TOTAL) - e(row, t, B25091_NOT_COMPUTED)
    if x <= 0:
        return None, None, x
    y = sum(e(row, t, n) for n in bins)
    p = y / x
    moe_x = moe_sum(m(row, t, B25091_TOTAL), m(row, t, B25091_NOT_COMPUTED))
    moe_y = moe_sum(*(m(row, t, n) for n in bins))
    return p * 100, cv(p, moe_proportion(p, x, moe_y, moe_x)), x


def build():
    shapes = map_counties()
    b25091 = read_table("b25091")
    b25103 = read_table("b25103")
    b19013 = read_table("b19013")

    layers = {"acs_cost_burden": {}, "acs_cost_burden_severe": {},
              "acs_property_tax_income": {}}
    flags = {name: {} for name in layers}

    for fips in sorted(shapes):
        row = b25091.get(fips)
        for name, bins in [("acs_cost_burden", B25091_AT_LEAST_30),
                           ("acs_cost_burden_severe", B25091_AT_LEAST_50)]:
            share, share_cv, denom = burden_share(row, bins) if row else (None, None, None)
            if share is None or denom < MIN_OWNERS:
                layers[name][fips] = None
                continue
            layers[name][fips] = round(share, 1)
            # A zero share has no CV (it divides by the estimate). Zeros only
            # occur in small counties, where "none of ~50 sampled-up households"
            # is weak evidence, so they're flagged as low reliability too.
            if share_cv is None or share_cv > LOW_RELIABILITY_CV:
                flags[name].setdefault("low_reliability", []).append(fips)

        # Property tax burden: a ratio of two medians from different universes
        # (taxes: owner-occupied units; income: all households). See
        # METHODOLOGY.md. It is not any household's actual tax share.
        tax = b25103.get(fips, {}).get("B25103_E001")
        income = b19013.get(fips, {}).get("B19013_E001")
        if tax is None or not income:
            layers["acs_property_tax_income"][fips] = None
        else:
            layers["acs_property_tax_income"][fips] = round(100 * tax / income, 2)
            if tax == TAX_TOPCODE:
                # True median taxes are >= $10,000, so the ratio is a lower bound.
                flags["acs_property_tax_income"].setdefault("topcoded", []).append(fips)

    nation = burden_share(read_table("b25091", {NATION_GEO_ID})[NATION_GEO_ID],
                          B25091_AT_LEAST_30)[0]
    for name, values in layers.items():
        kept = sum(v is not None for v in values.values())
        print(f"{name}: {kept:,} of {len(values):,} counties with a value; "
              f"flags {({k: len(v) for k, v in flags[name].items()})}")
    print(f"US share of mortgaged owners at >= 30%: {nation:.1f}%")
    return layers, flags, round(nation, 1)


def meta_entries(flags, us_share):
    common = {
        "unit": "%",
        "period": period(),
        "legend_period": legend_period(),
    }

    def src(table):
        s = source_info(table)
        return {"source_url": s["url"], "source_last_modified": s["last_modified"],
                "source_sha256": s["sha256"]}

    burden_common = {
        **common, **src("b25091"),
        "source": "US Census Bureau, American Community Survey 5-year estimates, table B25091",
        "min_owner_households": MIN_OWNERS,
        "low_reliability_cv": LOW_RELIABILITY_CV,
    }
    return {
        "acs_cost_burden": {
            **burden_common,
            "label": "Mortgaged owners paying 30%+ of income on housing",
            "definition": "Share of owner-occupied units with a mortgage whose selected "
                          "monthly owner costs are 30% or more of household income "
                          "(excludes 'not computed')",
            "us_value": us_share,
            "flags": flags["acs_cost_burden"],
        },
        "acs_cost_burden_severe": {
            **burden_common,
            "label": "Mortgaged owners paying 50%+ of income on housing",
            "definition": "As acs_cost_burden, at 50% or more of household income",
            "flags": flags["acs_cost_burden_severe"],
        },
        "acs_property_tax_income": {
            **common, **src("b25103"),
            "label": "Property tax as % of income (ratio of medians)",
            "source": "US Census Bureau, American Community Survey 5-year estimates, "
                      "tables B25103 and B19013",
            "definition": "Median real estate taxes paid (owner-occupied units, B25103) "
                          "divided by median household income (all households, B19013)",
            "flags": flags["acs_property_tax_income"],
        },
    }


def main():
    layers, flags, us_share = build()
    changed = {name: write_layer(name, values) for name, values in layers.items()}
    update_meta(meta_entries(flags, us_share), changed)


if __name__ == "__main__":
    main()
