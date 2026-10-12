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
