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
| Outcome | Delinquency vs own baseline | CFPB | z-score of the latest 90+ day delinquency rate against the county's 2017–2019 monthly mean and SD, SD floored at 0.2 points (DECISIONS 016) | Diverging, midpoint 0 |
| Burden | Owner cost burden | ACS `B25091` | **Share** of owner-occupied units *with a mortgage* paying ≥ 30% of household income on owner costs (HUD cost-burdened line) | Diverging around the US share (28.1%); see METHODOLOGY.md for proposed breaks |
| Burden | High-DTI loans | HMDA | % of 2025 qualifying loans with debt-to-income above 43% | Sequential warm |
| Burden | Property tax burden | ACS | Median real estate taxes paid (`B25103_E001`) ÷ median household income of owner-occupied households (`B25119_E002`), as % | Sequential warm |
| Equity | High-CLTV loans | HMDA | % of 2025 qualifying loans with combined loan-to-value above 90% | Sequential warm |
| Context (click panel only) | Latest 90+ day delinquency rate and change vs 2017–2019 (pp); median household income (all households); median HMDA rate; permits per 1,000 households; severe cost burden (≥ 50%); loan count; median loan amount | CFPB; ACS `B19013`; HMDA; BPS ÷ ACS `B11001_E001`; ACS `B25091` | as named | Neutral blue |

"Qualifying" HMDA loans are originated, home-purchase, first-lien, principal-residence loans, excluding open-end lines of credit and reverse mortgages (DECISIONS 013).

**Owner cost burden uses the share, not the median (DECISIONS 014).** The county median (`B25092_E002`) reaches 30% in only 23 of 3,140 counties. The share at ≥ 30% (`B25091`) spreads from 17.9% to 35.3% (p10–p90). The share at ≥ 50% (severely cost-burdened) goes in the click panel as context.

Definitions, caveats and proposed legend breaks for every layer are in **`METHODOLOGY.md`**.

### Color rules
- **Discrete classes** via `d3.scaleThreshold` with **fixed benchmark breaks**, not quantiles, so a class means the same thing in every county and every data year (DECISIONS 011). Each layer's breaks, palette and role live in `site/layers.js` (presentation config, versioned with the page) and are shown in the legend (DECISIONS 017).
- **One diverging palette** (blue → neutral grey → red/orange) and **one warm sequential ramp**, used map-wide. Both must be colorblind-safe, and **neighbouring classes must differ in lightness**, not only hue.
- **Same color direction in light and dark mode.**
- Diverging legends name their midpoint: delinquency runs **"Better than baseline" to "Worse than baseline"** (z = 0 is the county's own 2017–2019 average), and owner cost burden **"Below US share" to "Above US share"**. Never "safe". Sequential layers run "Lower" to "Higher".
- In the click panel and table, each metric's label says what it is a share (or ratio) of, e.g. "Mortgaged owners paying 30%+", "2025 loans with DTI above 43%". The short layer names are for the switcher only.
- Missing data keeps the **grey hatch** and "Data not available".
- Context metrics appear only in the click panel, in neutral blue, never as a map layer.

### Metric rules
- **ACS share suppression and reliability:** cost-burden shares are null below 30 mortgaged owner units with a computed burden, and flagged `low_reliability` in `meta.json` where the CV exceeds 40% or the share is 0.
- **HMDA suppression:** a metric is null where the county has fewer than 30 *valid* loans for that metric. `Exempt` and `NA` are dropped per field, so each metric has its own valid count. The threshold is configurable (`--min-loans`) and recorded in `meta.json`.
- **Property tax burden:** labelled a "ratio of medians", not the median household's actual tax share. Top-coded counties (taxes ≥ $10,000) are flagged `topcoded`; their ratio is a lower bound.
- **Permits:** labelled as permits, never as "starts".
- **Delinquency z-score:** the baseline SD is floored at 0.2 percentage points, so a single 0.1-point rounding step can't move z by more than 0.5. Counties where the floor applies are flagged `sd_floored`. The latest rate and its percentage-point change from the baseline mean go in the click panel.
- Every layer shows its data period (e.g. "HMDA 2025") in the legend.

### Delivery: four PRs, each branched from an up-to-date `main`
| PR | Branch | Scope |
|---|---|---|
| 2a | `phase-2a-hmda` | HMDA pipeline: loan count, median rate, DTI > 43% share, CLTV > 90% share, median loan amount |
| 2b | `phase-2b-acs` | ACS burden layers: owner cost burden share (B25091), property tax % of income, permits per 1,000 households; `METHODOLOGY.md` |
| 2c | `phase-2c-delinquency` | CFPB delinquency z-score against the 2017–2019 baseline, plus latest rate and pp change for the click panel |
| 2d | `phase-2d-ui` | Grouped layer switcher, new scales, click panel with context metrics, keyboard access, table view |

## Architecture

```
sources → pipeline/ (Python + DuckDB) → data/processed/*.json → site/ (D3 + TopoJSON) → GitHub Pages
```

- **Pipeline:** one script per source (`fetch_*.py`, `clean_*.py`). Raw files go to `data/raw/` (git-ignored); outputs go to `data/processed/`. ACS scripts use the standard library only; HMDA needs DuckDB (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`).
- **Output format:** one JSON per metric, shaped `{ "fips": value }` over every map county (`null` = not available), plus `meta.json` (source, dataset, period, run date, and suppression threshold where one applies).
- **Front end:** D3 with a 2023-boundary counties TopoJSON (`@severo_bo/us-atlas-2023`, vendored into `site/`) and the `geoAlbersUsa` projection, which places Alaska and Hawaii as insets.
- **Pipeline must be idempotent:** re-running it produces identical outputs.
- **Refresh (Phase 3):** `.github/workflows/refresh.yml` runs weekly (Mondays 13:17 UTC) and on demand. `pipeline/refresh.py` HEAD-requests every source file, compares Last-Modified dates with the committed manifest `data/processed/sources.json`, re-downloads only what changed, and re-runs only the `clean_*.py` scripts that read it. If validation passes and data changed, the bot commits `data/processed/` to `main` and calls `deploy.yml`. Newer data years (ACS, HMDA, BPS) are reported as a GitHub issue and switched manually (DECISIONS 018).
- **PR check:** PRs touching `pipeline/` rebuild every layer from fresh downloads on Linux and must reproduce the committed data byte for byte.

## Validation (runs after every pipeline run, and gates every refresh commit and deploy)
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
