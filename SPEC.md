# US Housing Map — Spec

## Purpose
An interactive county-level map of where US mortgage risk is building. Users pick a metric layer, see it shaded across ~3,100 counties, and click a county to see all of its metrics together. This is the data and visualization foundation for the later AI layer (Projects 2–4).

## Unit of analysis
- One row = one county, identified by its 5-digit **FIPS** code (primary key).
- **Coverage:** the 50 states + DC (3,144 counties). Puerto Rico and other territories are excluded from all data and from the map.
- Counties missing a metric are greyed out for that layer and show **"Data not available"** in the click panel. The page states that missing data is excluded, not estimated.

## Phase 2: where mortgage risk is building

Phase 2 reframes the map around the **double trigger** model of mortgage default: owners default when they *can't* pay (a payment burden they can't carry, or thin equity that rules out selling or refinancing) **and** something goes wrong (a shock such as job loss). The map shows where the first trigger is loaded and where the outcome is already appearing. It doesn't predict defaults; the shock layer (county unemployment) is a Phase 4 candidate.

### Layers by role

| Role | Layer | Source | Definition | Color scale |
|---|---|---|---|---|
| Outcome | Delinquency vs own baseline | CFPB | z-score of the latest 90+ day delinquency rate against the county's 2015–2019 mean and SD (DECISIONS 012) | Diverging, midpoint 0 |
| Burden | Owner cost burden | ACS `B25092_E002` | **Median** selected monthly owner costs as % of household income, owner-occupied units *with a mortgage* | Diverging, midpoint 30% (HUD cost-burdened), extra step at 50% (severely cost-burdened) |
| Burden | High-DTI loans | HMDA | % of 2025 qualifying loans with debt-to-income above 43% | Sequential warm |
| Burden | Property tax burden | ACS | Median real estate taxes paid (`B25103_E001`) ÷ median household income (`B19013_E001`), as % | Sequential warm |
| Equity | High-CLTV loans | HMDA | % of 2025 qualifying loans with combined loan-to-value above 90% | Sequential warm |
| Context (click panel only) | Median household income; median HMDA rate; permits per 1,000 households | ACS `B19013`; HMDA; BPS ÷ ACS `B11001_E001` | as named | Neutral blue |

"Qualifying" HMDA loans are originated, home-purchase, first-lien, principal-residence loans, excluding open-end lines of credit and reverse mortgages (DECISIONS 013).

**Open question for 2b, owner cost burden.** `B25092_E002` is a county *median*, and medians rarely reach the HUD line. In ACS 2020–2024 the county median is 19.6% (10th–90th percentile 17.4–23.3%). Only 23 of 3,140 counties reach 30% and 2 reach 50%. A diverging scale centred on 30% would show ~99% of the map on the cool side. Options for 2b:
- Keep the median and its benchmarks, accepting a mostly-cool layer whose message is "few counties have a typical owner over the line".
- Switch to the *share* of mortgaged owners above 30% from `B25091` (the distribution table), which spreads across counties and keeps the HUD threshold meaningful.

### Color rules
- **Discrete classes** via `d3.scaleThreshold` with **fixed benchmark breaks**, not quantiles, so a class means the same thing in every county and every data year (DECISIONS 011). Each layer's breaks are listed in `meta.json` and shown in the legend.
- **One diverging palette** (blue → neutral grey → red/orange) and **one warm sequential ramp**, used map-wide. Both must be colorblind-safe, and **neighbouring classes must differ in lightness**, not only hue.
- **Same color direction in light and dark mode.**
- The cool end is labelled **"below threshold"**, never "safe".
- Missing data keeps the **grey hatch** and "Data not available".
- Context metrics appear only in the click panel, in neutral blue, never as a map layer.

### Metric rules
- **HMDA suppression:** a metric is null where the county has fewer than 30 *valid* loans for that metric. `Exempt` and `NA` are dropped per field, so each metric has its own valid count. The threshold is configurable (`--min-loans`) and recorded in `meta.json`.
- **Property tax burden:** labelled a "ratio of medians", not the median household's actual tax share.
- **Permits:** labelled as permits, never as "starts".
- **Delinquency z-score:** counties whose baseline SD is near zero are flagged, not shown as extreme (2c).
- Every layer shows its data period (e.g. "HMDA 2025") in the legend.

### Delivery: four PRs, each branched from an up-to-date `main`
| PR | Branch | Scope |
|---|---|---|
| 2a | `phase-2a-hmda` | HMDA pipeline: loan count, median rate, DTI > 43% share, CLTV > 90% share, median loan amount |
| 2b | `phase-2b-acs` | ACS burden layers: owner cost burden, property tax % of income, permits per 1,000 households |
| 2c | `phase-2c-delinquency` | CFPB delinquency z-score against the 2015–2019 baseline |
| 2d | `phase-2d-ui` | Grouped layer switcher, new scales, click panel with context metrics, keyboard access, table view |

## Architecture

```
sources → pipeline/ (Python + DuckDB) → data/processed/*.json → site/ (D3 + TopoJSON) → GitHub Pages
```

- **Pipeline:** one script per source (`fetch_*.py`, `clean_*.py`). Raw files go to `data/raw/` (git-ignored); outputs go to `data/processed/`. ACS scripts use the standard library only; HMDA needs DuckDB (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
- **Output format:** one JSON per metric, shaped `{ "fips": value }` over every map county (`null` = not available), plus `meta.json` (source, dataset, period, run date, and suppression threshold where one applies).
- **Front end:** D3 with a 2023-boundary counties TopoJSON (`@severo_bo/us-atlas-2023`, vendored into `site/`) and the `geoAlbersUsa` projection, which places Alaska and Hawaii as insets.
- **Pipeline must be idempotent:** re-running it produces identical outputs.

## Validation (runs after every pipeline run)
- At least 3,000 counties with a value per county-level layer, except: CFPB delinquency, which only publishes ~500 counties (floor: 450); HMDA metrics after suppression (~2,650–2,750 counties; floor: 2,400). The count is printed every run.
- Every data FIPS has a map shape (anti-join).
- No FIPS outside the 50 states + DC (state FIPS `01`–`56`).
- Values within plausible bounds (e.g. 0–20% for mortgage rates, 0–100% for shares).
- FIPS codes are 5-character strings, zero-padded so codes like `01001` keep their leading zero.

## Phases

| Phase | Scope | Exit criteria |
|---|---|---|
| 0 | Data spike: pull one sample per source, document it in `DATA_SOURCES.md` | Each layer confirmed live with known lag, or relabeled or cut |
| 1 | Median income layer end-to-end (DECISIONS 009) | Live URL with one working choropleth |
| 2 | Mortgage-risk layers by role (see Phase 2 above), shipped as PRs 2a–2d | All outcome, burden and equity layers working with benchmark color scales; layer switcher grouped by role; county click panel with context metrics; every county reachable by keyboard (focus shows the same tooltip and panel as hover/click); a table view lists every county's values for the active layer |
| 3 | GitHub Actions scheduled refresh + validation | Unattended run passes |
| 4 | Housing stress index + backtest. Candidates: county unemployment (BLS LAUS) as the shock trigger; a mortgage demand model | Write-up on the portfolio |

## Out of scope for v1
Total tax burden (state income and sales taxes), AI Q&A, zoom below county level, and time-series animation.
