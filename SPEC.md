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
| Equity | High-CLTV loans | HMDA | % of 2025 qualifying **conventional** loans with combined loan-to-value above 90% (DECISIONS 019) | Sequential warm |
| Context (click panel only) | Latest 90+ day delinquency rate and change vs 2017–2019 (pp); median household income (all households); median HMDA rate; permits per 1,000 households; severe cost burden (≥ 50%); loan count; median loan amount; government-backed (FHA/VA/USDA) share of loans | CFPB; ACS `B19013`; HMDA; BPS ÷ ACS `B11001_E001`; ACS `B25091` | as named | Neutral blue |

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

## Phase 4: housing stress index

Two scores, one per trigger of the double trigger model (DECISIONS 020): **Burden** (can owners keep paying?) and **Equity** (could they sell or refinance their way out?). Both are built from transparent, benchmark-scaled components, and a backtest (4b) checks whether they add anything over their inputs. The shock trigger stays out of the index; county unemployment (BLS LAUS) is a later candidate.

### Benchmark scaling
Every component is divided by a benchmark: **x_i = c_i / b_i**, so 1.0 means "at the benchmark" and 1.2 means 20% above it.
- **b_PTI = 0.28**: the traditional rule that housing should take at most 28% of gross income.
- **Every other benchmark = the 2019 national value, held fixed.** Benchmarks are computed once from 2019 inputs, stored in `data/processed/benchmarks.json`, and **never recomputed from current data**, so a score means the same thing in every year.

### Burden score
```
NewBuyer = mean(x_PTI, x_D, x_R)
Existing = x_S                   (O dropped: DECISIONS 023)
Burden   = 0.5 * NewBuyer + 0.5 * Existing
```

| Component | Definition | Source | Minimum n |
|---|---|---|---|
| **PTI** new-buyer payment-to-income | County **median of per-loan** PTI = (M + T + I) ÷ (income × 1000 / 12). M = L·r(1+r)^n / ((1+r)^n − 1), with L = `loan_amount`, r = `interest_rate`/100/12, n = the loan's own `loan_term` in months (360 when it is `NA` or `Exempt`). T = τ·V/12, with τ = the county effective property tax rate (ACS median taxes ÷ median value) and V = `property_value`. I = the county average homeowners premium ÷ 12 (FIO, via the committed county premium tables). HMDA `income` is in thousands. | HMDA, ACS, FIO | 30 valid loans |
| **D** high-DTI share | Share of qualifying loans with DTI above 43% (the Phase 2a measure) | HMDA | 30 valid loans |
| **R** DTI denial rate | Home-purchase applications denied with debt-to-income (code 1) as any of `denial_reason_1`–`_4`, ÷ all home-purchase applications (`action_taken` 1 originated, 2 approved not accepted, 3 denied) | HMDA | 30 applications |
| **S** owner cost burden | Share of mortgaged owners paying 30%+ of income on owner costs (the Phase 2b measure) | ACS `B25091` | 30 mortgaged owner units |
| ~~**O** non-mortgage debt stress~~ | **Dropped** (DECISIONS 023). Non-mortgage debt enters only through D and R, i.e. for new buyers. | n/a | n/a |

- **Loans:** the Phase 2a filters (originated, home purchase, first lien, principal residence, not open-end or reverse; DECISIONS 013). R uses the same filters except `action_taken`.
- **PTI loan rules (DECISIONS 025).** A loan counts toward PTI only if **all** of these hold, checked in this order:
  1. not interest-only, balloon or negative-amortization (`interest_only_payment`, `balloon_payment`, `negative_amortization` ≠ `1`; `1111` exempt stays in, as in DECISIONS 013);
  2. `0 < interest_rate ≤ 20`;
  3. `loan_amount > 0` and `property_value > 0`;
  4. `income ≥ 10` ($10,000);
  5. the county has a tax rate and an insurance premium;
  6. computed **PTI ≤ 1.0**.
- The pipeline reports the loans removed by each rule, nationally and per county, and **flags counties that lose more than 10%** of their loans. It counts the loans whose `loan_term` fell back to 360.
- **One function, two vintages:** the same code computes the current scores (4a) and the 2019 scores (4b). Only the input files differ.

### Equity score
**x_CLTV = the high-CLTV share ÷ its 2019 national value**, over **conventional loans only** (DECISIONS 019, 021: in both 2019 and 2025, most FHA, VA and USDA loans are above 90% CLTV by program design).

### Combining
The weights (equal within each half, 0.5/0.5 across halves) are a **transparent choice, not fitted**. The backtest tests whether they add value; they are never tuned on its results.

### Data vintages

| Input | Current (4a) | Backtest (4b) | Robustness (4b) |
|---|---|---|---|
| HMDA | 2025 Snapshot | **2019 One-Year** | 2018 Snapshot (no 2018 One-Year file) |
| ACS 5-year | 2020–2024 | 2015–2019 (Census prototype table-based files; spot-checked, DECISIONS 027) | same |
| FIO insurance | 2022 premiums, recent HUD crosswalk (latest FIO year; no later release) | 2019 premiums, Q4 2019 HUD crosswalk | 2018 premiums |
| Other debt | not used (DECISIONS 023) | not used | not used |

FIO premiums are converted to counties **once, locally** (the HUD token is in a git-ignored `.env`, never in GitHub Actions), and the resulting county premium tables are committed under `data/processed/` (DECISIONS 024). The scheduled refresh reads those tables and never calls HUD.

### Backtest (4b)
- **Outcome**, per CFPB county: mean 90+ day delinquency rate over 2023-01 to 2025-12 minus the mean over 2017-01 to 2019-12, in percentage points. 2020–2022 are excluded (forbearance). The 8 Connecticut planning regions are excluded (2019 inputs use the old counties), leaving **499 counties** (DECISIONS 022).
- **Metrics:** Spearman rank correlation of score and outcome; the outcome by score quintile (mean change, and share of counties that rose); 95% bootstrap confidence intervals (1,000 resamples of counties).
- **Baselines:** the same metrics for each single component, and for median income alone. The key question: **does Burden beat its best single input?**
- **Robustness:** HMDA 2018 inputs; outcome window 2024–2025.
- **Report:** a results table, a score-vs-outcome scatter and quintile bars (PNG), and a plain-language summary of what the evidence does and doesn't support.
- Run once; results committed. **Not** part of the scheduled refresh. Weights and benchmarks are never changed after seeing the results; any change is decided by the owner and logged in DECISIONS with the reason.

### Map integration (4c)
- A new **Index** layer group with the Burden and Equity scores: diverging scale with midpoint 1.0 = benchmark; legend "Below benchmark / Above benchmark".
- A **bivariate view**, Burden × Equity, as a 3×3 colorblind-safe grid with a square legend; the high-high corner reads "both triggers loaded".
- Click panel: an **Index** section with both scores and every component, each showing its value and its x_i.
- Table view and keyboard access cover the new layers.

### Validation (4a)
- Anti-join against the map; bounds: county PTI between 0.05 and 1.5, scores between 0.2 and 5; county counts per component; a **warning** where a county's score rests on fewer than 3 components.

### Unit tests (4a)
Known answers, including: amortization ($300,000 at 6.5% over 30 years ≈ $1,896.20 a month, plus a 15-year case); benchmark scaling; the DTI-bin mapping; denial-reason matching; the PTI loan rules.

### Delivery: five PRs, each branched from an up-to-date `main`
| PR | Branch | Scope |
|---|---|---|
| 4.0 | `phase-4-spike` | Data spike (DATA_SOURCES.md) and this design. **Stop for review.** |
| 4a | `phase-4a-index` | Index pipeline on current data, unit tests, `burden.json`, `equity.json`, `benchmarks.json`, validation, scheduled refresh |
| 4b | `phase-4b-backtest` | Backtest on 2019 inputs, baselines, robustness, report. **Stop for review.** |
| 4c | `phase-4c-map` | Index layers, bivariate view, panel, table, keyboard. Starts only after 4b is approved. |
| 4d | `phase-4d-writeup` | Methodology page on the site with formulas, vintages, backtest results and limitations; linked from the map intro |

### Decisions from the 4.0 review (2026-10-15)
1. **O dropped**; Existing = x_S (DECISIONS 023).
2. **Insurance crosswalk:** HUD token used locally only; county premium tables computed once and committed; Q4 2019 crosswalk for 2019 premiums, a recent one for 2022 (DECISIONS 024).
3. **PTI loan rules:** as listed under Burden score, with per-rule counts and a >10% county flag (DECISIONS 025).
4. **Loan term:** each loan's own `loan_term`, 360 when missing or exempt; interest-only, balloon and negative-amortization loans excluded; a 15-year amortization unit test (DECISIONS 025).
5. **2018 robustness:** HMDA 2018 Snapshot alongside 2019 One-Year (DECISIONS 026).
6. **ACS 2019 prototype files accepted** after a spot-check: 563 counties in 10 states, 45,040 cells, all six tables, 0 mismatches (DECISIONS 027).

### Limitations (carried into the 4d write-up)
- **Non-mortgage debt enters only through D and R**, i.e. only for new buyers. Existing owners' card, auto and student debt isn't in the score (DECISIONS 023).
- **The current score pairs 2025 loans with 2022 insurance premiums, unadjusted.** FIO has no later data, and premiums rose faster than inflation in 2018–2022, so I is likely understated for 2025 buyers.
- Insurance is the average premium per policy for HO-3/HO-5 policies from the largest insurers. It excludes residual-market plans (e.g. Florida's Citizens) and excess & surplus lines.
- The backtest covers 499 mostly metropolitan counties (CFPB's coverage rule).
- The outcome skips 2020–2022 (the forbearance gap).
- Timing: the new-buyer half describes recent buyers, while the outcome is delinquency across all existing mortgages.
- The weights are a choice, not an estimate.

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
- At least 3,000 counties with a value per county-level layer, except: CFPB delinquency, which only publishes ~500 counties (floor: 450); HMDA metrics after suppression (~2,650–2,750 counties; floor: 2,400), except the conventional-only CLTV share (~2,330; floor: 2,100). The count is printed every run.
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
| 4 | Housing stress index (Burden and Equity scores) + backtest + map integration + write-up, shipped as PRs 4.0–4d (see Phase 4 above). County unemployment (BLS LAUS) stays a later shock-trigger candidate | Backtest results reviewed; Index layers live; methodology page on the site, linked from the map |

## Out of scope for v1
Total tax burden (state income and sales taxes), AI Q&A, zoom below county level, and time-series animation.
