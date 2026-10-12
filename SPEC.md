# US Housing Map — Spec

## Purpose
An interactive county-level map of US housing conditions. Users pick a metric layer, see it shaded across ~3,100 counties, and click a county to see all of its metrics together. This is the data and visualization foundation for the later AI layer (Projects 2–4).

## Unit of analysis
- One row = one county, identified by its 5-digit **FIPS** code (primary key).
- **Coverage:** the 50 states + DC (3,144 counties). Puerto Rico and other territories are excluded from all data and from the map.
- Counties missing a metric are greyed out for that layer and show **"Data not available"** in the click panel. The page states that missing data is excluded, not estimated.

## Metric layers (v1)

| Layer | Source | Definition | Frequency |
|---|---|---|---|
| Mortgage delinquency | CFPB Mortgage Performance Trends | % of mortgages 90+ days delinquent | Monthly |
| Median mortgage rate | HMDA loan-level data (FFIEC) | Median `interest_rate` of originated, first-lien, home-purchase loans in the county | Annual |
| Building permits | Census Building Permits Survey | New residential units permitted (proxy for housing starts) | Annual |
| Property tax rate | Census ACS 5-year | Median real estate taxes paid (B25103) ÷ median home value (B25077) | Annual |
| Median income | Census ACS 5-year | Median household income (B19013) | Annual |

### Metric rules
- **HMDA rate:** suppress a county if it has fewer than 30 qualifying loans, because small samples give noisy medians. The threshold is configurable.
- **Property tax:** label it as the "ratio of medians," not the median household's actual rate.
- **Permits:** labeled as permits, never as "starts."
- Every layer shows its data period (e.g. "HMDA 2025") in the legend.

## Architecture

```
sources → pipeline/ (Python + DuckDB) → data/processed/*.json → site/ (D3 + TopoJSON) → GitHub Pages
```

- **Pipeline:** one script per source (`fetch_*.py`, `clean_*.py`). Raw files go to `data/raw/` (git-ignored); outputs go to `data/processed/`.
- **Output format:** one JSON per metric, shaped `{ "fips": value }`, plus `meta.json` (source, period, run date).
- **Front end:** D3 with a 2023-boundary counties TopoJSON (`@severo_bo/us-atlas-2023`, vendored into `site/`) and the `geoAlbersUsa` projection, which places Alaska and Hawaii as insets.
- **Pipeline must be idempotent:** re-running it produces identical outputs.

## Validation (runs after every pipeline run)
- At least 3,000 counties present per county-level layer, except CFPB delinquency, which only publishes ~500 counties (floor: 450).
- No FIPS outside the 50 states + DC (state FIPS `01`–`56`).
- Rates within plausible bounds (e.g. 0–20% for mortgage rates and delinquency).
- FIPS codes are 5-character strings, zero-padded so codes like `01001` keep their leading zero.

## Phases

| Phase | Scope | Exit criteria |
|---|---|---|
| 0 | Data spike: pull one sample per source, document it in `DATA_SOURCES.md` | Each layer confirmed live with known lag, or relabeled or cut |
| 1 | Median income layer end-to-end (DECISIONS 009) | Live URL with one working choropleth |
| 2 | Remaining layers, layer switcher, county click panel, keyboard access, table view | All 5 layers working; every county reachable by keyboard (focus shows the same tooltip and panel as hover/click); a table view lists every county's values for the active layer |
| 3 | GitHub Actions scheduled refresh + validation | Unattended run passes |
| 4 | Housing stress index + backtest | Write-up on the portfolio |

## Out of scope for v1
Total tax burden (state income and sales taxes), AI Q&A, zoom below county level, and time-series animation.
