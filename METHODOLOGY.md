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
| Reliability flags | Values shown but flagged in `meta.json` → `flags` (`low_reliability`, `topcoded`, `sd_floored`). Shown as a ⚠ caveat in the tooltip, click panel and table view. | `clean_acs_burden.py`, `clean_delinquency.py`, `site/map.js` |
| Determinism | Re-running the pipeline on the same inputs produces byte-identical files. `run_date` only changes when a layer's data does. | `pipeline/output.py` |
| Update cadence | Checked weekly. A layer updates only when its source file changes upstream (by Last-Modified date). Within a data year that means CFPB releases (every 4–8 months) and any source revisions. A **new data year** (ACS 5-year, HMDA, BPS annual) is not picked up automatically: the refresh opens a GitHub issue and the switch is a reviewed code change, since definitions can change between vintages. | `pipeline/refresh.py`, `refresh.yml` |
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

### Delinquency vs the county's own baseline: `cfpb_delinquency_z`
- **Definition:** z = (latest 90+ day delinquency rate − county's 2017–2019 monthly mean) ÷ max(county's 2017–2019 monthly SD, 0.2). The SD is the sample SD over 36 months.
- **Source:** CFPB Mortgage Performance Trends, county file, % of mortgages 90+ days delinquent. Latest month Dec 2025 (release thru-2025-12, published Aug 2026).
- **Reading it:** z = +2 means this county's delinquency is now two of its own pre-pandemic standard deviations above its own pre-pandemic average. It measures *change relative to the county's normal*, not the level. A county can have a high z at a low rate, or the reverse; the click panel shows the rate and change alongside.
- **Nuances:**
  - **Coverage:** CFPB publishes a county only if it has ≥1,000 mortgages in its sample (the National Mortgage Database, ~5% of mortgages): 507 counties. All others are "Data not available" (DECISIONS 007).
  - **Why 2017–2019, not 2015–2019** (DECISIONS 016). Delinquency was still falling from the foreclosure crisis through 2015–2016 (national 1.6% at end-2015, 1.1% at end-2017, 0.9% at end-2019). With 2015–2019, each county's baseline mean and SD were inflated by that tail: the median county scored z = −0.69 and 186 of 507 were ≤ −1. With 2017–2019, the median is −0.10 (98 counties ≥ +1, 132 ≤ −1). Some decline remains inside 2017–2019 (median −0.14 points/year), so z still leans slightly negative.
  - **Why not 2020 onward:** CARES Act forbearance kept many missed payments from being reported as delinquent, so 2020–2021 understates stress.
  - **SD floor of 0.2 points.** CFPB rounds to 0.1 points, and many counties' baseline SDs are close to that resolution (as low as 0.03). Unfloored, one rounding step could swing z by about 3. The floor caps a single 0.1-point step at 0.5 z, the narrowest legend class. It applies to **223 of 507 counties** (flagged `sd_floored`). For them, z understates how unusual a move is relative to their true (very stable) baseline: it's conservative by design.
  - **Revisions:** each CFPB release revises the full history, so a county's baseline can shift slightly between releases. The pipeline always uses the newest release.
  - `FIPSCode` comes wrapped in literal quotes (`'01003'`), stripped by the pipeline.
  - Distribution (Dec 2025): p5 −2.05, p25 −1.01, median −0.10, p75 0.78, p95 2.24, max 5.60 (Pueblo County, CO).
- **Scale:** diverging, midpoint 0; breaks −2, −1, −0.5 | 0.5, 1, 2. The legend ends are labelled "Better than baseline" and "Worse than baseline" (the midpoint is the county's own 2017–2019 average), never "safe". This layer has data for only ~500 counties, so its "Data not available" hatch is drawn fainter than on other layers.

### Delinquency rate and change: `cfpb_delinquency_90`, `cfpb_delinquency_change` (click panel)
- `cfpb_delinquency_90`: the latest month's 90+ day rate, % of mortgages (rounded to 0.1 by CFPB). Median county 0.9%.
- `cfpb_delinquency_change`: latest rate minus the county's 2017–2019 mean, in percentage points (median −0.02; p5–p95 −0.68 to +0.53). Unlike z, it isn't scaled by the county's volatility, so it's the easier number to read in the panel: "0.4 points above its 2017–19 average".

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
- **Scale:** diverging. Neutral class 25–30% contains the US share (28.1%); cool classes <15, 15–20, 20–25; warm classes 30–35, 35–40, ≥40. Because the midpoint is the US share rather than a fixed benchmark, the ends are labelled "Below US share" and "Above US share", never "safe".

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
- **Scale:** sequential warm; breaks 20, 30, 40, 50%.

### Property tax as % of owner income (ratio of medians): `acs_property_tax_income`
- **Definition:** median real estate taxes paid (`B25103_E001`, owner-occupied units) ÷ median household income of owner-occupied households (`B25119_E002`) × 100.
- **Nuances:**
  - **A ratio of medians,** not the median owner's tax share. The median-tax home and the median-income owner are generally different households. Label it that way (SPEC).
  - **Owner-only on both sides** (DECISIONS 015). An earlier version divided by all-household income (`B19013`), which includes renters, who typically earn less. That overstated owners' burden: the owner-only ratio is about 14% lower at the county median (2.12% vs 2.46%; p10–p90 of new ÷ old: 0.76–0.93), and the maximum falls from 12.4% to 7.7%.
  - **Top-coded taxes.** B25103 publishes medians of $10,000 or more as `10001`. For those 17 counties the ratio is a **lower bound**, flagged `topcoded`. Owner income (`B25119`) is top-coded at $250,000+, but no county reaches it (max $228,060).
  - **Missing** in 8 counties, where either median is unpublished (e.g. Culberson County, TX `48109` has no owner-income estimate).
  - Taxes are as reported by respondents and include all property taxes on the home. They're not a statutory rate.
  - Distribution: p25 1.52%, median 2.12%, p75 2.86%, p90 3.70%.
- **Scale:** sequential warm; breaks 1, 1.5, 2, 2.5, 3, 4%.

---

## Equity

### Conventional loans with combined loan-to-value above 90%: `hmda_cltv_over_90`
- **Definition:** share of 2025 qualifying **conventional** loans (`loan_type` 1) with `combined_loan_to_value_ratio` > 90. Suppressed below 30 conventional loans with a valid CLTV.
- **Why conventional only (DECISIONS 019).** Government-backed loans are above 90% CLTV by program design. National shares above 90%, 2025 qualifying loans:

  | Loan type | Loans | CLTV reported | Above 90% |
  |---|---|---|---|
  | Conventional | 1,980,765 | 1,847,889 | 29.7% |
  | FHA | 630,419 | 622,981 | 90.0% |
  | VA | 329,120 | 263,509 | 81.4% |
  | USDA/RHS | 32,502 | 31,780 | 91.9% |
  | All | 2,972,806 | 2,766,159 | 48.9% |

  With every loan type included, a county's share above 90% tracked its government-loan share (correlation 0.76 across counties), so the layer mostly mapped FHA/VA lending. Conventional only, the correlation is 0.22: the layer shows where buyers choosing a standard mortgage put down less than 10%.
- **Nuances:**
  - **CLTV includes all liens** the lender relied on (e.g. piggyback seconds), so it measures the buyer's equity at purchase better than LTV would.
  - **Government lending isn't dropped from the page.** Its share is shown next to this layer in the click panel (`hmda_govt_share`, below), because those loans are thin-equity too.
  - **Conventional loans above 80% LTV usually carry private mortgage insurance,** which protects the lender, not the borrower's equity.
  - **Equity at origination only.** Price changes since purchase aren't reflected.
  - **Fewer counties:** 2,331 (vs 2,645 with all loan types). Rural counties where most purchase loans are FHA/VA/USDA often have fewer than 30 conventional loans.
  - **`NA` is more common for CLTV** than for other fields (133k conventional loans). One in five VA loans has no CLTV, which no longer affects the layer.
  - Extreme values (CLTV up to 560) exist in the raw data; a share-above-threshold is unaffected by them.
  - Distribution: p10 21.8%, median 35.5%, p90 49.2%.
- **Scale:** sequential warm; breaks 20, 30, 40, 50% (the national conventional share, 29.7%, sits at the 30% break). Counties per class: 167, 532, 833, 584, 215.

---

## Context (click panel only)

### Median household income: `income`
- ACS 2020–2024 5-year, `B19013_E001`, in 2024 inflation-adjusted dollars. Missing for De Baca County, NM (`35011`).

### Government-backed share of loans: `hmda_govt_share`
- Share of 2025 qualifying loans that are FHA, VA or USDA/RHS (`loan_type` 2–4). Shown in the click panel under Equity, next to the conventional CLTV layer. Suppressed below 30 loans; 2,752 counties. County p10 19.3%, median 38.2%, p90 56.7%.

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

## Stress index (Phase 4)

Two scores, one per trigger of the double trigger model (DECISIONS 020). Every component is divided by a fixed benchmark, so **1.0 = at the benchmark** and 1.2 = 20% above it. Formulas in `pipeline/stress_index.py`; design in SPEC Phase 4.

| Component | Value | Benchmark | Source (current) |
|---|---|---|---|
| PTI: new-buyer payment ÷ income, county median of per-loan values | ratio | **0.28** (fixed rule of thumb) | HMDA 2025, ACS 2020–2024, FIO 2022 |
| D: loans with DTI above 43% | % of loans | **28.52%** (2019 national) | HMDA 2025 |
| R: applications denied for debt-to-income | % of applications | **4.10%** | HMDA 2025 |
| S: mortgaged owners paying 30%+ of income | % of mortgaged owners | **27.81%** | ACS 2020–2024 |
| CLTV: conventional loans above 90% CLTV | % of conventional loans | **36.03%** | HMDA 2025 |

- **Burden** = 0.5 × mean(x_PTI, x_D, x_R) + 0.5 × x_S. NewBuyer averages the components a county has. Burden is null unless both halves are present. O (non-mortgage debt) was dropped (DECISIONS 023).
- **Equity** = x_CLTV, over conventional loans only (DECISIONS 021).
- **Benchmarks** are the 2019 national values (50 states + DC) from HMDA 2019 One-Year and ACS 2015–2019, computed once by `build_benchmarks.py` and stored in `benchmarks.json`. They're **never recomputed** from current data, so a score means the same thing in every year (DECISIONS 020).

### PTI, per loan
- PTI = (M + T + I) ÷ (income × 1000 / 12), with:
  - M = principal and interest on `loan_amount` at `interest_rate` over the loan's own `loan_term` (360 months when `NA` or `Exempt`);
  - T = the county effective property tax rate (ACS median taxes ÷ median value) × `property_value` ÷ 12;
  - I = the county average homeowners premium per policy ÷ 12.
- **Loan rules** (DECISIONS 025). A loan is counted under the first rule it fails:
  1. interest-only, balloon or negative-amortization (`1111` exempt stays in);
  2. rate not in (0, 20];
  3. loan amount or property value missing or ≤ 0;
  4. income below $10,000;
  5. no county tax rate or premium;
  6. PTI above 1.0.
- The county value is the **median** over the loans that pass, if at least 30 do. Per-rule counts, nationally and per county, are in `index_pti_rules.json`. Counties where the loan-level rules (1–4 and 6) remove more than 10% of their loans are flagged `pti_rules_over_10pct` in `meta.json`.
- **Nuances:**
  - **Small-lender exemptions drive the >10% flag.** Lenders under the 2018 EGRRCPA partial exemption report `Exempt` for the rate, so their loans can't get a PTI. Nationally that's 2.3% of loans, but it's concentrated: in about 550 counties, exempt-rate loans alone are over 10% of loans. In those counties, PTI describes loans from larger lenders.
  - **Insurance (DECISIONS 024).** I is FIO's average premium per policy (HO-3/HO-5 owner policies from the largest insurers, excluding residual markets such as Florida's Citizens and excess & surplus lines). It's converted to counties with HUD's county-to-ZIP crosswalk, weighted by residential addresses, and is null below 50% address coverage. **The current score pairs 2025 loans with 2022 premiums, unadjusted**: FIO has no later data, and premiums rose faster than inflation in 2018–2022, so I is likely understated.
  - **Binned inputs:** loan amount and property value are $10,000-bin midpoints.
  - **Tax rate:** taxes are top-coded at $10,000, so T is a lower bound in the top-coded counties.
  - **Timing:** PTI and D describe this year's buyers. S describes all mortgaged owners in a 5-year window.

### Limitations
- **Non-mortgage debt enters only through D and R**, i.e. through new buyers' debt-to-income. Existing owners' card, auto and student debt isn't in the score (DECISIONS 023).
- The weights are a stated choice, not an estimate. The 4b backtest tests them once and they aren't tuned afterwards.
- A score of 1.0 means "at the 2019 national level", not "safe".

### A description, not a forecast: what the backtest showed
The index describes where housing costs, borrowing and thin equity are **loaded now**, relative to 2019. **It is not shown to predict defaults, delinquency or foreclosures**, and the map doesn't present it that way (DECISIONS 030). Full results: `BACKTEST.md`.

- **The test (DECISIONS 022, 028).** The scores were computed on 2019 inputs with the same code, for the 499 counties CFPB publishes (Connecticut excluded). They were compared with each county's change in 90+ day delinquency from 2017–2019 to 2023–2025. It was run once, with the analysis fixed in advance.
- **The result.** Higher 2019 Burden went with a *larger fall* in delinquency (Spearman ρ = −0.16, 95% CI −0.24 to −0.07). The result held with 2018 inputs and a 2024–2025 window. Burden didn't beat its own inputs, and lower median income alone did about as well.
- **Why the sign is negative: regression to the mean.** Delinquency fell in 92% of these counties, and how far it fell depends mostly on where it started (ρ = −0.77 between the 2017–2019 level and the change). Counties that started high fell the most. Burden, S and low income are all higher where 2017–2019 delinquency was higher, so a change score pulls them negative whether or not they carry a signal.
- **The secondary test (DECISIONS 029)**, specified after the primary result and before it was computed, asks: among counties starting at the same 2017–2019 level, did higher-scoring ones end 2023–2025 higher? It ranks the 2023–2025 level and computes a partial correlation, controlling for the 2017–2019 level. **For Burden, the answer is no detectable relationship** (partial ρ = +0.006, CI −0.08 to +0.09). D, R and CLTV (the Equity score) point the expected way (+0.13, +0.23, +0.34), while PTI and S point the other way and cancel them inside Burden. Lower income alone scores +0.27.
- **Why this period can't really test the theory.** The index measures the first trigger of a double-trigger default: a household that is stretched or has thin equity. Default usually also needs **a shock** (a job loss, or a price fall that wipes out equity). 2019–2025 mostly lacked one:
  - **unemployment** was low apart from a brief 2020 spike;
  - **CARES Act forbearance** let borrowers pause payments without being reported delinquent (which is why 2020–2022 is excluded);
  - **home prices rose** sharply, so even thin-equity owners could usually sell or refinance rather than default.
  With no shock, loaded counties had little reason to diverge, so a null result here doesn't show the index is wrong. A positive result wouldn't have proved it right either.
- **Why not test on the 2007–2010 crisis instead?** The index needs loan-level fields that HMDA only started collecting in **2018**: debt-to-income ratio, combined LTV, interest rate, loan term and property value (Regulation C changes, effective with 2018 data). Pre-2018 HMDA has loan amount and income but none of these, so PTI, D, R and CLTV can't be computed for a crisis-era test.
- **What that leaves.** The components are real, measured conditions: payments relative to income, debt-to-income lending, DTI denials, cost-burdened owners and high-CLTV lending, each compared with 2019. The map shows where they're high. It doesn't say where defaults will happen.

### On the map (4c)
- **Burden score** and **Equity score** layers: diverging, midpoint 1.0 = benchmark, breaks 0.67, 0.8, 0.9, 1.1, 1.25, 1.5 (roughly symmetric on a ratio scale; 0.9–1.1 grey = near benchmark). Legend: "Below benchmark / Above benchmark" (DECISIONS 031).
- **Burden × Equity**: each score in three classes (below 0.9, 0.9–1.1, 1.1 and above), shown as a 3×3 grid; the top-right cell is "both above benchmark: heavy burden and thin equity". A county needs both scores to appear. Colors: `site/layers.js` `BIVARIATE` (checked for colorblind separation).
- **Click panel**: an Index section with both scores, then each component with its value and its x (value ÷ benchmark), e.g. "43.8% · 1.53×". Flags: Burden on fewer than 3 of 4 inputs; PTI where the loan rules remove over 10% of loans.

---

## Change log
| Date | PR | Change |
|---|---|---|
| 2026-10-12 | 2b | Sheet created. Owner cost burden switched from the B25092 median to the B25091 share at ≥30% (DECISIONS 014). |
| 2026-10-12 | 2b | Property tax burden divides by owner household income (B25119) instead of all-household income (B19013) (DECISIONS 015). |
| 2026-10-12 | 2c | Delinquency baseline 2017–2019 with a 0.2-point SD floor, instead of 2015–2019 (DECISIONS 016). Latest rate and pp change added for the click panel. |
| 2026-10-12 | 2d | Legend breaks adopted as proposed and implemented in `site/layers.js`. Per-county flags (`low_reliability`, `topcoded`, `sd_floored`) shown in the tooltip, click panel and table (DECISIONS 017). |
| 2026-10-12 | 3 | Weekly refresh: layers update when their source changes; new data years are switched by hand (DECISIONS 018). |
| 2026-10-12 | 2f | Delinquency legend ends renamed "Better than baseline" / "Worse than baseline"; click-panel and table labels name what each value is a share of; fainter "Data not available" hatch on the delinquency layer. |
| 2026-10-12 | 2g | High-CLTV layer limited to conventional loans; breaks 40–80% → 20, 30, 40, 50%; government-backed loan share added to the click panel (DECISIONS 019). |
| 2026-10-16 | 4a | Stress index: Burden and Equity scores, fixed 2019 benchmarks, PTI loan rules (DECISIONS 020–025). |
| 2026-10-16 | 4b/4c | Stress index section: the backtest, regression to the mean, the missing shock in 2019–2025 and why pre-2018 HMDA can't support a crisis-period test; the index is described, not presented as a forecast (DECISIONS 029–031). Index layers, bivariate view and panel section added to the map. |
| 2026-10-16 | 4d | Index methodology page on the site (`site/methodology.html`): formulas, vintages, backtest results and limitations, linked from the map intro and notes. |
