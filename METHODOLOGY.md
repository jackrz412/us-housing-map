# Methodology

How every number on the map is defined and computed, and what it can't tell you. This is the place for **nuances**: anything a careful reader would need in order not to misread a layer. Each entry says where it's enforced (code, `meta.json`, or "UI, 2d") so it can be checked.

- **Why each choice was made:** `DECISIONS.md`.
- **What each source looks like, and its release timing:** `DATA_SOURCES.md`.
- **This file:** what the resulting number means.

Update it in the same PR as any change to a definition, filter, threshold or caveat.

---

## Rules that apply to every layer

| Rule | Detail | Enforced in |
|---|---|---|
| County universe | The 3,144 counties and county-equivalents of the 50 states + DC, as drawn by the vendored 2023-boundary map. Puerto Rico and other territories are excluded (DECISIONS 006). | `pipeline/geo.py`, `validate.py` |
| FIPS | 5-character, zero-padded strings, never numbers (`"01001"`). | all `clean_*.py`, `validate.py` |
| Connecticut | The 9 planning regions (`09110`–`09190`) that replaced its 8 counties as county-equivalents in 2022. All sources use them. | map file (DECISIONS 008) |
| Missing data | `null` in the layer file; grey hatch and "Data not available" on the map. **Never estimated, interpolated or zero-filled.** A true zero (e.g. 0 permits reported) is `0`, not `null`. | `clean_*.py`, UI |
| Small samples | Suppressed to `null` below 30 observations: 30 valid loans for HMDA metrics; 30 mortgaged owner households for ACS cost-burden shares. | `clean_hmda.py`, `clean_acs_burden.py` |
| Reliability flags | Values shown but flagged in `meta.json` → `flags` (e.g. `low_reliability`, `topcoded`). The click panel should show the caveat (UI, 2d). | `clean_acs_burden.py`, `validate.py` |
| Determinism | Re-running the pipeline on the same inputs produces byte-identical files. `run_date` only changes when a layer's data does. | `pipeline/output.py` |
| Not a prediction | Layers show conditions associated with mortgage risk (the double trigger: burden or thin equity, plus a shock). They don't forecast defaults for any county. | UI copy, 2d |

### Periods don't line up

Layers come from different time windows. Comparing them in the click panel compares **different periods**:

| Source | Period | What it describes |
|---|---|---|
| ACS 5-year | 2020–2024, pooled | The stock of *all* current owners/households, averaged over five years |
| HMDA Snapshot | 2025 | *New* home-purchase loans originated in 2025 |
| Building Permits Survey | 2025 | Units permitted in 2025 |
| CFPB delinquency | latest month (Dec 2025 as of Aug 2026 release) | Existing mortgages, monthly |

This matters most when ACS and HMDA are read together. ACS burden includes owners who bought or refinanced at 2020–2021's ~3% rates. HMDA DTI describes 2025 buyers at ~6.5%. A county can show low owner cost burden (ACS) and high new-buyer DTI (HMDA) at the same time, and both are correct.

### ACS margins of error

ACS figures are survey estimates with 90% margins of error. For derived values (sums, shares), MOEs are approximated with the Census Bureau's formulas (*Understanding and Using ACS Data*, ch. 8). Those treat inputs as independent, so they're approximate. The coefficient of variation (CV) is standard error ÷ estimate, where SE = MOE / 1.645. A CV above 40% is flagged `low_reliability`, the common "low reliability" band.

---

## Outcome

### Delinquency vs the county's own baseline (planned, 2c)
- **Definition:** z-score = (latest 90+ day delinquency rate − county's 2015–2019 monthly mean) ÷ county's 2015–2019 monthly SD.
- **Source:** CFPB Mortgage Performance Trends, county file, 90+ days delinquent.
- **Nuances:**
  - **Coverage:** CFPB publishes a county only if it has ≥1,000 mortgages in its sample (the National Mortgage Database, ~5% of mortgages), about 500 counties. All others are "Data not available" (DECISIONS 007).
  - **Baseline window:** 2015–2019 avoids the foreclosure-crisis backlog and the 2020–2021 forbearance period, when missed payments often weren't reported as delinquent (DECISIONS 012).
  - **Near-zero baseline SD** inflates z. These counties are flagged, not shown as extreme. The cutoff is set in 2c.
  - **Revisions:** each CFPB release revises the full history, so a county's baseline can shift slightly between releases.
  - Values are rounded to 0.1 percentage points in the source, which limits precision for low-delinquency counties.
  - `FIPSCode` comes wrapped in literal quotes (`'01003'`) and must be stripped.
- **Proposed scale (2d):** diverging, midpoint 0; breaks −2, −1, −0.5 | 0.5, 1, 2.

---

## Burden

### Mortgaged owners paying 30%+ of income on housing: `acs_cost_burden`
- **Definition:** share of owner-occupied units *with a mortgage* whose selected monthly owner costs are 30% or more of household income.
- **Source:** ACS 2020–2024 5-year, table **B25091**. Numerator `_E008`–`_E011` (30–34.9%, 35–39.9%, 40–49.9%, 50%+). Denominator `_E002` (units with a mortgage) − `_E012` ("not computed").
- **Why the share, not the median:** the county *median* burden (`B25092_E002`) reaches 30% in only 23 of 3,140 counties, so a 30% benchmark would barely register. The share spreads across counties: p10 17.9%, median 24.8%, p90 35.3% (DECISIONS 014).
- **Nuances:**
  - **"≥ 30%" vs HUD's "> 30%".** ACS bins start at exactly 30.0%, so a household at exactly 30% counts as burdened. This is the Census convention and the standard way B25091 is used. The difference is negligible.
  - **"Not computed"** units (zero or negative household income) are excluded from the denominator, not counted as burdened.
  - **Owner costs** include mortgage payments, property taxes, insurance, utilities, fuel, and condo/HOA and mobile-home fees. They are not just the mortgage payment.
  - **All mortgaged owners, not new buyers.** Includes owners on low-rate pandemic-era loans (see "Periods don't line up").
  - **Suppressed** where fewer than 30 mortgaged owner units have a computed burden (10 counties).
  - **Flagged `low_reliability`** where CV > 40%, or where the share is 0%, since a zero has no CV and only occurs in small counties (95 counties). The flag doesn't catch every outlier. Of the 21 counties above 50%, only 3 are flagged, e.g. Edwards County, TX (84%, 75 households). Zavala County, TX (68.3%, 757 households) is above 50% and not flagged.
  - **US benchmark:** 28.1% of mortgaged owners nationally (same table and vintage), recorded as `us_value` in `meta.json`.
- **Proposed scale (2d):** diverging. Neutral class 25–30% contains the US share (28.1%); cool classes <15, 15–20, 20–25; warm classes 30–35, 35–40, ≥40. The cool end is labelled "below threshold", never "safe".

### Mortgaged owners paying 50%+ of income: `acs_cost_burden_severe` (click-panel context)
- As above, numerator `_E011` only (HUD "severely cost-burdened").
- Many more counties are flagged `low_reliability` (356), because small shares in small counties have large relative error. Show it in the panel with the flag, not as a map layer.

### Loans with debt-to-income above 43%: `hmda_dti_over_43`
- **Definition:** share of 2025 qualifying loans whose `debt_to_income_ratio` is above 43%.
- **Source:** HMDA 2025 Snapshot. "Qualifying" = originated, home purchase, first lien, principal residence, excluding open-end lines of credit and reverse mortgages (DECISIONS 013).
- **Nuances:**
  - **Bin mapping.** DTI is reported as bins below 36% (`<20%`, `20%-<30%`, `30%-<36%`), whole numbers 36–49, and bins `50%-60%`, `>60%`. Above 43% = `44`–`49`, `50%-60%`, `>60%`. `43` itself is **not** above 43.
  - **`Exempt` and `NA`** are excluded from both numerator and denominator. Any unexpected new code is treated as invalid, not as "not above 43".
  - **43% is a historical benchmark,** not a current rule. It was the general Qualified Mortgage DTI cap until the 2021 price-based QM definition replaced it. FHA and VA routinely allow higher DTIs.
  - **Strongly tied to loan type.** Nationally, 59% of FHA and 52% of VA qualifying loans are above 43% DTI, against 29% of conventional loans. A high county share partly reflects a high share of government-backed lending.
  - DTI is the lender's own calculation at origination, so methods vary somewhat between lenders.
  - **Suppressed** below 30 valid DTI values (2,718 counties kept).
- **Proposed scale (2d):** sequential warm; breaks 20, 30, 40, 50%.

### Property tax as % of income (ratio of medians): `acs_property_tax_income`
- **Definition:** median real estate taxes paid (`B25103_E001`, all owner-occupied units) ÷ median household income (`B19013_E001`, all households) × 100.
- **Nuances:**
  - **A ratio of medians,** not the median household's tax share. Label it that way (SPEC).
  - **Mismatched universes.** Taxes are for owner-occupied units, but income is for all households, including renters, who typically earn less. This tends to *overstate* owners' tax burden, most where renters are a large share. The owner-only alternative is `B25119_E002` (median income of owner-occupied households); not used, per the 2b spec.
  - **Top-coded.** B25103 publishes medians of $10,000 or more as `10001`. For those 17 counties the ratio is a **lower bound**, flagged `topcoded`.
  - Taxes are as reported by respondents and include all property taxes on the home. They're not a statutory rate.
- **Proposed scale (2d):** sequential warm; breaks 1, 2, 3, 4, 5%.

---

## Equity

### Loans with combined loan-to-value above 90%: `hmda_cltv_over_90`
- **Definition:** share of 2025 qualifying loans with `combined_loan_to_value_ratio` > 90.
- **Nuances:**
  - **CLTV includes all liens** the lender relied on (e.g. piggyback seconds), so it measures the buyer's equity at purchase better than LTV would.
  - **Mostly a loan-type signal.** Nationally, 90% of FHA, 82% of VA and 92% of USDA loans are above 90% CLTV, against 30% of conventional loans. These programs are designed for low down payments. The layer largely shows where low-down-payment government lending is concentrated, which *is* thin equity, but readers should know the driver. Consider showing FHA/VA share in the click panel (2d).
  - **Equity at origination only.** Price changes since purchase aren't reflected.
  - **`NA` is more common for CLTV** than for other fields (141k loans), so CLTV has the fewest surviving counties (2,645).
  - Extreme values (CLTV up to 560) exist in the raw data; a share-above-threshold is unaffected by them.
- **Proposed scale (2d):** sequential warm; breaks 40, 50, 60, 70, 80%.

---

## Context (click panel only)

### Median household income: `income`
- ACS 2020–2024 5-year, `B19013_E001`, in 2024 inflation-adjusted dollars. Missing for De Baca County, NM (`35011`).

### Median mortgage rate: `hmda_rate`
- Median `interest_rate` of 2025 qualifying loans. The note rate, not APR (excludes points and fees).
- **Context only, not a map layer:** across counties it barely varies. The IQR is 0.135 points (6.49–6.625%) (DECISIONS 010).
- Differences mostly reflect product mix: FHA (6.25%) and VA (6.125%) medians run below conventional (6.5%).
- Rates of 0% (e.g. housing-agency programs) and up to 20% exist; the median is robust to them.

### Qualifying loans: `hmda_loans`
- Count of 2025 qualifying loans. A county with no reported loans is a true `0` (8 counties), because HMDA covers every lender required to report. Lenders below HMDA's reporting thresholds aren't included, so this undercounts in some rural areas.

### Median loan amount: `hmda_loan_amount`
- Median `loan_amount`. HMDA reports the midpoint of a $10,000 band, so values end in 5,000.

### Housing units permitted per 1,000 households: `permits_per_1000_hh`
- Units authorized by building permits in 2025 (Census BPS annual county file, all structure sizes) ÷ ACS 2020–2024 households (`B11001_E001`) × 1,000.
- **Nuances:**
  - **Permits, not starts or completions.** Some permitted units are never built (SPEC: never labelled "starts").
  - **Includes Census imputation** for places that didn't report. The reported-only columns undercount.
  - **"Balance of State" rows dropped.** Permits not assigned to a county (county code `000`: ME, MI, MT, NM, OR) aren't counted anywhere. New Mexico's 2,752 such units make its county values understate activity.
  - **120 counties are `null`,** not zero. They have no permit-issuing places in the survey, so their permits are unknown. 248 counties reported a true 0.
  - **Period mismatch:** 2025 permits over 2020–2024 households.
  - **Volatile in small counties.** A single subdivision can dominate (max 141.6, Jasper County, SC).

---

## Change log
| Date | PR | Change |
|---|---|---|
| 2026-10-12 | 2b | Sheet created. Owner cost burden switched from the B25092 median to the B25091 share at ≥30% (DECISIONS 014). |
