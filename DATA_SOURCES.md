# Data Sources

Phase 0 data spike, run 2026-10-12. For each layer I pulled one small sample, confirmed the latest period, and checked county coverage.

**Scope rules (DECISIONS 006–008):**
- **50 states + DC only.** Drop Puerto Rico (`72xxx`) and other territories (state FIPS `60`, `66`, `69`, `78`) from every layer and from the map. The universe is **3,144 counties**.
- **Missing data:** a county with no value for a layer is greyed out and labelled **"Data not available"**. Nothing is estimated.
- **Map:** `@severo_bo/us-atlas-2023` (2023 Census boundaries), which matches every source's FIPS codes.

Counts below exclude Puerto Rico.

## Summary

| Layer | Latest period | Published | Lag | Counties | Status |
|---|---|---|---|---|---|
| Mortgage delinquency (CFPB) | Dec 2025 | Aug 2026 | ~8 months | **507** | ✅ Kept. Other ~2,640 counties show "Data not available" |
| Median mortgage rate (HMDA) | 2025 | Jun 2026 | ~6 months after year end | 2,645–2,752 after 30-loan suppression | ✅ Live (pipeline built in 2a) |
| Building permits (Census BPS) | 2025 annual (Jan–Aug 2026 YTD also available) | May 2026 | ~4.5 months (annual); ~1 month (monthly YTD) | 3,024 | ✅ Live |
| Property tax ratio (ACS 5-yr) | 2020–2024 | Jan 2026 | ~13 months | 3,144 (3,135 with both values) | ✅ Live |
| Median income (ACS 5-yr) | 2020–2024 | Jan 2026 | ~13 months | 3,144 (3,143 with a value) | ✅ Live |

**Resolved 2026-10-12:** keep CFPB at 507 counties, exclude Puerto Rico, switch to a 2023-boundary map. See DECISIONS 006–008.

---

## 1. Mortgage delinquency: CFPB Mortgage Performance Trends

- **Page:** https://www.consumerfinance.gov/data-research/mortgage-performance-trends/download-the-data/
- **Sample file:** `https://files.consumerfinance.gov/data/mortgage-performance/downloads/CountyMortgagesPercent-90-plusDaysLate-thru-2025-12.csv` (458 KB, `Last-Modified: 2026-08-03`)
- **Latest period:** December 2025. The page says the data covers "January 2008–December 2025" and was published August 2026.
- **Update cadence:** data is monthly, but **releases come roughly every 4–8 months** and include revisions to the full history. Recent releases: Jul 2025 (thru Dec 2024), Dec 2025 (thru Mar 2025), Apr 2026 (thru Sep 2025), Aug 2026 (thru Dec 2025). The filename embeds the end month, so the fetcher has to find the newest link on the page. The URL isn't fixed.
- **Shape:** wide. One row per geography, columns `RegionType, State, Name, FIPSCode, 2008-01 … 2025-12`. One `National` row plus county rows.
- **Values:** percent of mortgages 90+ days delinquent, rounded to 0.1. Dec 2025 county range is 0.1–3.6, median 0.9. No blanks in the latest month.
- **Gotchas:**
  - `FIPSCode` is wrapped in literal single quotes (`'01003'`), presumably to keep Excel from dropping the leading zero. Strip them.
  - Uses Connecticut's new planning-region FIPS (`091xx`) since the Dec 2023 update.
  - There is also a 30–89 days file with the same shape.
  - **Fetching:** `pipeline/fetch_cfpb.py` reads the download page and takes the newest `CountyMortgagesPercent-90-plusDaysLate-thru-YYYY-MM.csv` link. Each release revises history, so only the newest is used. CFPB's CDN returns **403 for a bare `Mozilla/5.0` user agent** but accepts curl's, Python's default, or a descriptive one; the fetcher sends `us-housing-map/1.0 (+repo URL)`.
  - **Completeness:** the Dec 2025 release has no blank cells. All 507 counties have every month from 2008-01, and Connecticut's history is already on the planning-region codes.
- **Coverage:** **507 counties** across 50 states (no Puerto Rico in this file). CFPB only publishes a county "if there are at least 1,000 mortgages in our sample" (their sample is the NMDB, roughly 5% of mortgages). That covers most of the population but only about 16% of counties.
- **Decision (DECISIONS 007):** keep the layer at county level. The other ~2,640 counties show "Data not available". The spec's ≥3,000 validation rule can't apply to this layer, so it needs its own floor (e.g. ≥450, to catch a broken download without failing on normal release-to-release changes).

## 2. HMDA loan-level data (FFIEC)

- **Data Browser API (small samples):** `https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?years=2025&counties=01001&actions_taken=1&loan_purposes=1`. It answers with a redirect to a pre-built file on `files.ffiec.cfpb.gov`, so use `curl -L`. Responses are gzip-encoded (`--compressed`).
- **Full national file (used by the pipeline):** `https://files.ffiec.cfpb.gov/static-data/snapshot/2025/2025_public_lar_csv.zip`. 737 MB zipped (`Last-Modified: 2026-06-23`), one 5.1 GB CSV with 99 columns.
- **Latest period:** **2025** (Snapshot dataset). 2026 data won't appear until about mid-2027. The API rejects `years=2026`.
- **Dataset types:** 2025 is currently served as the **Snapshot**. 2024 is served from the **One-Year** dataset, a later re-cut that includes resubmissions. The pipeline pins Snapshot and records it in `meta.json` (`"dataset": "Snapshot 2025"`).
- **Coded values (from the full 2025 file, home-purchase first liens):**
  - `occupancy_type`: 1 principal residence (3.0M), 2 second home (93k), 3 investment (347k).
  - `open_end_line_of_credit`: 1 open-end (21k), 2 not (3.3M), 1111 exempt (113k). `reverse_mortgage`: 1 reverse (1.6k), 2 not, 1111 exempt (113k).
  - `debt_to_income_ratio`: bins `<20%`, `20%-<30%`, `30%-<36%`; whole numbers `36`–`49`; bins `50%-60%`, `>60%`; plus `NA`, `Exempt`. "Above 43%" = `44`–`49`, `50%-60%`, `>60%`.
  - `interest_rate` and `combined_loan_to_value_ratio`: numeric strings, or `NA`/`Exempt`. Extremes exist (rates of 0% and 20%, CLTV up to 560). Medians and over-threshold shares are robust to them, so no trimming.
  - `county_code`: 5-digit string (new CT planning regions), or `NA` (5,261 qualifying loans, dropped).
- **Pipeline results (2025, qualifying loans as defined in DECISIONS 013):** 2,988,847 loans, of which 16,041 are in territories or have county `NA` and are dropped. Counties surviving the 30-valid-loan suppression: rate 2,719, DTI 2,718, CLTV 2,645 (2,331 once limited to conventional loans, DECISIONS 019), loan amount 2,752 (of 3,144). Those counties hold 99.8% of the loans.

| Metric (county) | min | p25 | median | p75 | max |
|---|---|---|---|---|---|
| Median rate (%) | 5.5 | 6.49 | 6.5 | 6.625 | 9.785 |
| Loans with DTI > 43% (%) | 7.9 | 28.2 | 33.3 | 39.0 | 62.3 |
| Loans with CLTV > 90% (%) | 0.8 | 49.5 | 58.8 | 66.7 | 93.5 |
| Median loan amount ($) | 95,000 | 175,000 | 225,000 | 295,000 | 1,115,000 |

- **Performance:** one DuckDB pass over the 5.1 GB CSV takes ~4 s warm and ~40 s cold on a 10-core Mac, with an 8 GB memory cap.

## 3. Building permits: Census Building Permits Survey

- **Directory:** https://www2.census.gov/econ/bps/County/
- **Sample file:** `https://www2.census.gov/econ/bps/County/co2025a.txt` (annual 2025, posted 2026-05-14, 367 KB)
- **Latest period:** **2025 annual.** Monthly county files also exist through **August 2026**: `co2608c.txt` (that month) and `co2608y.txt` (year to date). Naming is `coYYMMc` / `coYYMMy`, and `coYYYYa` for annual.
- **Shape:** CSV with a **2-line header plus a blank line** (skip 3 lines). Columns: `Date, State FIPS, County FIPS, Region, Division, Name`, then Bldgs/Units/Value for 1-unit, 2-units, 3–4 units, 5+ units. The first 12 numeric columns are estimates that include imputation for non-reporting places. The second 12 (`… rep`) are reported only.
- **Metric:** total units = `1-unit Units + 2-units Units + 3-4 Units + 5+ Units` from the imputed (first) block. 2025 total: 1,431,616 units. Median county is 62 units, max 31,651. **248 counties reported 0.**
- **Coverage:** 3,024 counties, 50 states + DC (no Puerto Rico in this file). The other 120 counties are outside the permit-issuing universe and show "Data not available". New CT planning-region FIPS.
- **"Balance of State" rows:** the file has 5 rows with county code `000` (`23000` Maine Unorganized Territory, `26000` Michigan, `30000` Montana, `35000` New Mexico, `41000` Oregon). These are permits not assigned to any county (2,752 units in New Mexico). They aren't counties and must be dropped.
- **Gotchas:** State and county FIPS are separate columns. Concatenate them as strings to keep zero padding. `Name` is right-padded with spaces.
- **Suggestion:** a raw unit count mostly tracks population. Consider units per 1,000 households (ACS B11001) as the shaded value. Spec decision, not done here.

## 4 & 5. Property tax ratio and median income: Census ACS 5-year

- **Latest period:** **2020–2024 ACS 5-year** (the API catalog lists vintage 2024 as the newest `acs/acs5`). The B19013 summary file has `Last-Modified: 2026-01-29`, so this vintage landed in late January 2026. The 2021–2025 release is expected around December 2026. It isn't published yet (the 2025 summary-file URL returns 404).
- **⚠️ The Census API now requires a key.** Keyless calls to `api.census.gov/data/…` redirect to `missing_key.html`. Two routes:
  - **Get a free key** (https://api.census.gov/data/key_signup.html). Store it as a GitHub Actions secret in Phase 3.
  - **Use the table-based summary files (what I used, no key):**
    `https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-{b19013,b25103,b25077}.dat`
    These are pipe-delimited, one file per table, about 15–18 MB each, covering all geographies. Filter rows where `GEO_ID` starts with `0500000US` (counties). FIPS = the last 5 characters.
- **Columns used:** `B19013_E001` (median household income), `B25103_E001` (median real estate taxes paid, all owner-occupied units), `B25077_E001` (median home value). `_M001` holds margins of error.
- **Sample (Autauga County AL, 01001):** income $72,481 · taxes $627 · home value $207,200 → tax ratio 0.30%.
- **Coverage:** 3,222 county rows, of which 78 are Puerto Rico municipios (`72xxx`) and are dropped, leaving **3,144** (50 states + DC). Missing values are the sentinel **`-666666666`** and become "Data not available":
  - income: `35011` (De Baca NM)
  - taxes: `02068`, `02164`, `13239`, `15005`, `28055`, `48261`, `48301`
  - home value: `15005`, `48105`, `48137`, `48261`, `48301`
  - That leaves 3,135 counties with a computable tax ratio and 3,143 with income.
- **Distributions:** income $16,314–$181,765 (median $65,346). Tax ratio 0.07%–3.56% (median 0.79%).
- **Gotchas:**
  - **B25103 is top-coded at $10,000** and stored as `10001`. 17 counties hit it, so their ratio is a lower bound. Flag them in the click panel or note it in the legend.

## Geography join: map file

**Decision (DECISIONS 008):** use `@severo_bo/us-atlas-2023` in place of `us-atlas@3.0.1`.

| | `us-atlas@3.0.1` | `@severo_bo/us-atlas-2023@4.0.0` |
|---|---|---|
| Boundaries | 2017 | 2023 Census cartographic boundaries |
| Connecticut | old 8 counties (`09001`–`09015`) | 9 planning regions (`09110`–`09190`) ✅ |
| Alaska | `02261` Valdez-Cordova (split in 2019) | `02063` / `02066` ✅ |
| ACS counties with no shape | 11 | **0** |
| CFPB counties with no shape | 8 | **0** |
| BPS counties with no shape | 10 | **0** (after dropping Balance of State rows) |

- **Source:** https://github.com/severo/us-atlas-2023. ISC license, same build recipe and file layout as `us-atlas` (`counties-10m.json` with `counties` / `states` / `nation` objects, plus `counties-albers-10m.json` pre-projected to `geoAlbersUsa` at 975×610). So D3 code written for `us-atlas` works unchanged. Each county has `id` (5-digit FIPS string) and `properties.name`.
- **Territories:** the file has 3,233 counties. 78 are Puerto Rico and 11 are other territories (`60`, `66`, `69`, `78`). Filter to state FIPS ≤ `56` to get exactly the 3,144 that match ACS.
- **Risk:** it's a one-person fork with a single release (Sep 2024), not the official `topojson/us-atlas`. **Vendor the file into `site/`** (don't hotlink the CDN) so the site doesn't depend on it staying published.
- **Fallback / future refresh:** Census publishes 2025 boundaries (`https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_5m.zip`, posted 2026-04-23, 3 MB). It can be turned into the same TopoJSON with the `us-atlas` recipe (`shapefile` → `topojson-server` → `topojson-simplify`). I don't know of any county changes between 2023 and 2025, so the fork is enough for now.

## Reproducing the samples

Samples were pulled to a scratch directory, not into `data/raw/`. Nothing is committed. Every URL above works without auth except the Census API.

---

# Phase 4.0 spike: housing stress index sources

Run 2026-10-14/15 for the index and backtest in SPEC Phase 4. Samples only; no pipeline code. The HMDA 2019 file was downloaded into `data/raw/` (git-ignored) because 4b needs it; everything else went to a scratch directory.

## Summary

| # | Source | Needed for | Verdict |
|---|---|---|---|
| 1 | HMDA 2019 One-Year | PTI, D, R, CLTV as of 2019 | ✅ Every field present with the same codes as 2025. Needs validity bounds for `interest_rate` and `income` (below). 2018 has no One-Year file at the usual path. |
| 2 | ACS 2015–2019 5-year | S, effective tax rate as of 2019 | ✅ Table-based files exist, but only under the Census **prototype** folder. Same headers as 2024. |
| 3 | Treasury FIO homeowners insurance | I (insurance in PTI) | ✅ Usable, 2018–2022 only, nothing newer. ⚠️ The HUD crosswalk now needs a registered token. Coverage estimated with a public Census substitute. |
| 4 | Urban Institute "Debt in America" | O (non-mortgage debt) | ⚠️ A 2019-era release exists (2018 credit data), but its rates are rounded to 2 decimals, and the measures that would vary most changed definition after 2022. **Recommendation: leave O out; Existing = x_S.** |
| 5 | BLS LAUS county unemployment | report only | ✅ Monthly through Aug 2026. Bulk files need a contact email in the request; the keyless API is too rate-limited for 3,144 counties. |
| 6 | 2019 geography | backtest | Connecticut's 8 old counties and Alaska's Valdez-Cordova (`02261`). **8 of the 507 CFPB counties are affected** (all Connecticut). |
| 7 | HMDA 2019 size and time | planning | 985 MB zip, 6.8 GB CSV. Download ~2 min, unzip 20 s, one DuckDB pass ~5 s warm. |

## 1. HMDA 2019 (One-Year dataset)

- **File (pin this):** `https://files.ffiec.cfpb.gov/static-data/one-year/2019/2019_public_lar_one_year_csv.zip`
  - 985,323,790 bytes, `Last-Modified: Wed, 15 Oct 2025 05:29:18 GMT`, sha256 `4fb470ecebfcd2d78fd4c529e382a0c58d32d5865afa5e51efc80daf3e709033`.
  - Unzips to `2019_public_lar_one_year.csv`, 6,837,866,739 bytes, 99 columns (same column set as 2025).
  - The Snapshot 2019 file also exists (`snapshot/2019/2019_public_lar_csv.zip`, 980 MB). One-Year includes resubmissions, so it's the better "final" view of 2019. Record `"dataset": "One-Year 2019"` in `meta.json`.
- **2018 (for the 4b robustness check):** there is **no One-Year file** at `one-year/2018/…` (404 for every name tried). The Data Browser serves 2018 from the Three-Year dataset. The **Snapshot** exists: `snapshot/2018/2018_public_lar_csv.zip` (823,719,647 bytes, `Last-Modified: 2025-11-21`). Using it means the 2018 run is Snapshot while 2019 is One-Year; the difference is resubmitted records only.
- **Fields checked** (2019 vs 2025, Phase 2a loan filters, home purchase): `income`, `property_value`, `loan_amount`, `interest_rate`, `loan_type`, `debt_to_income_ratio`, `combined_loan_to_value_ratio`, `denial_reason_1`–`_4`, `county_code`. All present, same names, same codes.

| Field | 2019 | 2025 | Note for 4a |
|---|---|---|---|
| Qualifying originations | 3,857,134 | 2,988,847 | |
| Applications for R (`action_taken` 1, 2, 3) | 4,554,867 | 3,624,067 | |
| Denied (3) with debt-to-income (code `1`) in any `denial_reason` | 190,305 (34.6% of denials) | 197,161 (39.2%) | |
| `loan_type` | 1–4 | 1–4 | same codes |
| `debt_to_income_ratio` | same bins and whole numbers 36–49, `NA`, `Exempt` | same | the Phase 2a DTI mapping works unchanged |
| `income` (thousands of $) | `NA` 33,998; ≤ 0: 5,756; median 81; max 139,000 | `NA` 25,559; ≤ 0: 5,879; median 113 | drop `NA` and ≤ 0 |
| `interest_rate` (%) | `Exempt` 100,934, `NA` 1,415; ≤ 0: 1,280; median 4.125; **max 5,625** | ≤ 0: 982; median 6.49; max 20 | needs a validity bound (proposed 0 < rate ≤ 20) |
| `property_value` ($) | `Exempt` 101,002, `NA` 28,536; median 265,000; max 2,147,483,647 | median 385,000 | reported as the **midpoint of a $10,000 bin** (always ends in 5000) |
| `loan_amount` ($) | never missing; median 235,000 | median 325,000 | also $10,000-bin midpoints |
| `combined_loan_to_value_ratio` | `NA` 143,243, `Exempt` 100,966 | similar | over-90 shares are robust to the extreme values (max 13.4 million) |
| `denial_reason_1` | 1–9, `10` = not applicable, `1111` = exempt | same | also filled for `action_taken` 7 (preapproval request denied); R counts only 3 |
| `county_code` | old CT `09001`–`09015`, `02261`; `NA` 265,280 rows (all actions) | CT planning regions, `02063`/`02066` | see 6 |

- **CLTV by loan type** (share of loans with CLTV > 90%): 2019 conventional **36.0%**, FHA 92.6%, VA 88.9%, USDA 94.8%. 2025: 29.7%, 89.9%, 81.5%, 91.6%. Government loans are above 90% by program design in both years, so the Equity score uses **conventional loans only** (DECISIONS 019, 021).
- **Binning:** `loan_amount` and `property_value` are $10,000-bin midpoints, so per-loan PTI has rounding error of up to ±$5,000 on each. That's ±2% on a $250,000 loan, and it averages out in a county median.
- **Loan term:** PTI uses n = 360 for every loan, as specified. HMDA also has `loan_term`. A 15-year loan has a higher payment than the formula gives, so PTI understates those loans. Not changed; flagged for review.

## 2. ACS 2015–2019 5-year

- **The regular table-based path doesn't exist for 2019 or 2020** (404). Table-based summary files start with the 2021 vintage.
- **Census published 2019 as a prototype:** `https://www2.census.gov/programs-surveys/acs/summary_file/2019/prototype/5YRData/acsdt5y2019-{table}.dat` (1,137 tables, `Last-Modified: 2021-01-06`).
  - Same pipe-delimited layout, same `GEO_ID` format, and **byte-identical headers** to the 2024 files for `b25091`, `b25103`, `b25119`, `b19013`, `b11001`. `b25077` (median value, for the effective tax rate) is there too. So `pipeline/acs.py` reads them unchanged with a different URL and year.
  - 3,220 county rows; 3,142 in the 50 states + DC (old Connecticut and `02261`, see 6).
  - Example: Autauga County AL (`01001`) median taxes $467 (2024: $627).
  - ⚠️ "Prototype" is Census's label for the format, not a different survey. I haven't checked values against the official sequence-based 2019 release; 4b should spot-check a few counties before relying on it.
- **Effective tax rate:** τ = `B25103_E001` ÷ `B25077_E001` (median taxes ÷ median value), both available for 2019 and 2024. Same caveat as Phase 2b: taxes are top-coded at $10,000.

## 3. Treasury FIO homeowners insurance (ZIP level, 2018–2022)

- **File:** `https://home.treasury.gov/system/files/311/Supporting_Underlying_Metrics_and_Disclaimer_for_Analyses_of_US_Homeowners_Insurance_Markets_2018-2022.xlsx`
  - 14,892,818 bytes, `Last-Modified: 2026-08-19` (re-uploaded; the release is dated January 16, 2025, with the report *Analyses of U.S. Homeowners Insurance Markets, 2018–2022*).
  - Three sheets: *Disclaimer & Background*, *Metric Definitions*, *Supporting Underlying Metrics* (131,941 rows; the last 3,975 are blank).
- **Fields:** `ZIP Code`, `Year`, `Policy Decile Grouping` (1–10), `Claim Frequency`, `Claim Severity`, `Loss Ratio`, **`Premiums Per Policy`** (written premium ÷ policies in force at year end), `Nonrenewal Rate`, `Nonpayment Cancellation Rate`, `Other than Nonpayment Cancellation Rate`.
  - **No coverage amount or insured value**, and **no policy count** (only the decile group). So premium per $1,000 of coverage can't be computed; I is the average premium per policy.
- **Scope:** HO-3 and HO-5 owner-occupied policies from the largest insurers (about 80% of premiums nationally). It **excludes residual-market plans** (e.g. Florida's Citizens) and excess & surplus lines. Published only for ZIPs with at least 10 insurers and 50 policies (22% of ZIPs dropped).
- **Shape:** the **same 25,593 ZIPs in every year** 2018–2022. ZIPs are stored as numbers, so New England ZIPs lost their leading zero (11,410 rows with 4 digits); zero-pad to 5.
- **Values:** premium per policy, ZIP level: 2019 median $1,469 (p1 $819, p99 $5,841); 2022 median $1,551. No zero or negative values.
- **After 2022:** **no later release exists.** The disclaimer says the underlying NAIC data call doesn't include 2023 or 2024, and I found no newer FIO or NAIC ZIP-level release (searched Oct 2026). The current index would combine 2025 loans with 2022 premiums.
- **Crosswalk:** ⚠️ **HUD's ZIP–county crosswalk is no longer downloadable anonymously.** The bulk `.xlsx` files return an AWS WAF browser challenge (HTTP 202, empty body), and the API returns 401 without a token. A token is free with a HUD User account.
  - **Proposed weighting:** a county's premium = the mean of its ZIPs' premiums, weighted by the **share of the county's residential addresses in each ZIP** (HUD `COUNTY_ZIP` file, `res_ratio`), renormalized over the ZIPs FIO publishes. Null below 50% coverage.
  - **Coverage estimate (public substitute):** the Census 2010 ZCTA-to-county relationship file, weighting by housing units (`COHUPCT`). 25,518 of 25,593 FIO ZIPs match a ZCTA.

| Counties (50 states + DC) | any coverage | ≥ 25% of housing units | ≥ 50% | ≥ 80% |
|---|---|---|---|---|
| All 3,143 (2010 geography) | 3,093 | 3,046 | **2,992** | 2,736 |
| Backtest set (499 CFPB counties outside CT) | 499 | n/a | **493** | 482 |

  - Identical in 2019 and 2022, since the ZIP set doesn't change. Counties with no coverage are mostly in Florida (15), Alaska (14), Nebraska (6), North Dakota (6) and Montana (5).
  - **For 4a, either:** register for a HUD token (store it as a GitHub Actions secret), or use the Census housing-unit weights, which are public but describe 2010 ZCTAs.

## 4. Non-mortgage debt: Urban Institute "Debt in America"

- **Downloading:** `datacatalog.urban.org` returns 403 to scripts. The interactive map's own files are open: `https://apps.urban.org/features/debt-interactive-map/data/{release}/{file}.csv`.
- **Releases found** (folder names, from the map's script and the Internet Archive): `201911-update`, `20210323update`, `20220501-update`, `20230914-update`, `20240715-update`, `20251023-update` (current).
- **2019-era version:** `201911-update` (`Overall_Delinquent_Debt_county.csv`, `Auto_loan_county.csv`, `Medical_Debt_county.csv`, `Student_loan_county.csv`). Its technical appendix (Dec 17, 2019) says it uses **2018** credit-bureau data (2% sample). Still served directly. The next release (Mar 2021) is mid-forbearance.
- **Current version:** `20251023-update` (`county_overall.csv` etc.), August 2025 credit data, 4% sample.

| Measure | Definition stable 2018 → 2025? | 2019 release: counties, distinct values | 2025 release: counties | Median 2018 → 2025 |
|---|---|---|---|---|
| Credit card delinquency rate (60+ days) | ✅ same | 2,945, **20 values** | 2,982 | 0.04 → 0.055 |
| Auto/retail loan delinquency rate (60+ days) | ✅ same | 2,945, **20 values** | 2,856 | 0.03 → 0.053 |
| Share with any debt in collections | ❌ medical collections were mostly removed from credit reports in 2022–23 | 2,945, 62 values | 3,071 | 0.32 → 0.23 |
| Share with medical debt in collections | ❌ same reason; 7 states report none in 2025 | 2,945, 55 values | 3,071 | 0.19 → 0.04 |
| Student loans | ❌ "in default" (2018) vs "60+ days delinquent or in default" (2025) | 2,945 | 2,128 | n/a |

- **Problems for O:**
  - **Rounding:** the 2019 release rounds rates to 2 decimals. Card delinquency takes only 20 distinct values across 2,945 counties, mostly 0.02–0.07, so x_O would move in steps of about 25% of the benchmark.
  - **Comparability:** the collections measures fell because reporting rules changed, not because stress fell. Against a fixed 2019 benchmark they'd show a false improvement.
  - **Geography:** even the 2025 release reports Connecticut by its **old 8 counties**; the map has the 9 planning regions.
  - **Timing:** the "2019" release is 2018 data.
- **Recommendation: leave O out of the index** and use Existing = x_S, as the design allows. If you want it anyway, the credit card delinquency rate is the only defensible candidate (stable definition), with the rounding and Connecticut caveats.

## 5. BLS LAUS county unemployment (report only)

- **Series:** `LAUCN{5-digit FIPS}0000000003` = unemployment rate, not seasonally adjusted, monthly. Latest: **August 2026** (preliminary). Example: `LAUCN010010000000003` (Autauga AL) = 3.2%.
- **Bulk files** (`download.bls.gov/pub/time.series/la/la.data.64.County`, `www.bls.gov/lau/laucntyYY.xlsx`): 403 unless the request's User-Agent includes a contact email (BLS policy). Not tested with an email.
- **API:** v1 needs no key, but allows 25 requests a day of up to 25 series, too few for 3,144 counties. v2 needs a free key (500 requests a day, 50 series each: about 63 requests for every county).
- Not part of the index. A Phase 4+ shock layer would need either a BLS key or an email in the User-Agent.

## 6. Geography for 2019

| Code set | HMDA 2019 | ACS 2015–2019 | Urban (both releases) | Map / CFPB |
|---|---|---|---|---|
| Connecticut | 8 counties `09001`–`09015` | same | same (still in 2025) | 9 planning regions `09110`–`09190` |
| Alaska Valdez-Cordova | `02261` | `02261` | `02261` (2019) / split (2025) | `02063` / `02066` |

- Apart from these, every 2019 HMDA and ACS county code matches a map county (checked by anti-join).
- **In the backtest set:** 8 of the 507 CFPB counties are Connecticut planning regions (`09110`, `09120`, `09130`, `09140`, `09160`, `09170`, `09180`, `09190`). The Alaska counties aren't in CFPB's file.
- **Proposal:** exclude those 8 from the backtest, leaving **499 counties**. The planning regions don't nest within the old counties, so a crosswalk would mean apportioning by population for little gain.

## 7. HMDA 2019 on this Mac

| Step | Time | Disk |
|---|---|---|
| Download (985 MB) | 123 s | 0.99 GB zip |
| Unzip | 20 s | 6.84 GB CSV |
| One DuckDB pass (filter + 19 columns) | 5.0 s (2025 file: 4.0 s) | in memory, under the 8 GB cap |

- Total **7.8 GB** for the zip plus CSV (the zip can be deleted after unzipping). With 2018 for robustness, about 7 GB more. 50 GB was free.
- The 5 s pass ran with the file still in the OS cache, right after unzipping. Phase 0 measured about 40 s for a cold read of the 2025 file.
