# Decisions

Each entry: the decision, the alternatives, and why. Newest at the bottom.

## 001 — County as the unit of analysis (2026-10-06)
- **Chose:** county (FIPS) grain; counties without data are excluded with a note.
- **Over:** state (too coarse) or metro area (doesn't cover rural areas).
- **Why:** county is the finest grain where most federal housing data is published.

## 002 — Property tax only for "tax burden" in v1 (2026-10-12)
- **Chose:** effective property tax rate from ACS (median taxes ÷ median home value).
- **Over:** a composite of property tax plus state income and sales tax burden.
- **Why:** property tax is the only tax measure published at county level. The composite mixes state-level and county-level data and would need weighting choices that are hard to defend. Revisit after v1.

## 003 — HMDA county median for mortgage rates (2026-10-12)
- **Chose:** median `interest_rate` from HMDA originations, computed per county.
- **Over:** Freddie Mac PMMS, which is a single weekly national number.
- **Why:** HMDA shows real geographic variation in rates.
- **Cost accepted:** about one year of data lag, very large files (handled with DuckDB), and suppression of small-sample counties.

## 004 — D3 + TopoJSON for the map (2026-10-12)
- **Chose:** D3 with `us-atlas` TopoJSON, rendered as SVG.
- **Over:** MapLibre GL, a tile-based map with smooth zoom and pan.
- **Why:** it needs no tile server or API key, the files are small, and it teaches the underlying mechanics of projections, scales, and data joins. A county choropleth doesn't need street-level zoom.

## 005 — Building permits as the proxy for housing starts (2026-10-12)
- **Chose:** Census Building Permits Survey, at county level.
- **Over:** Census New Residential Construction (starts), which is published only nationally and for 4 regions.
- **Why:** permits lead starts closely and exist at county level. Labeled honestly as permits.

## 006 — 50 states + DC only; Puerto Rico excluded (2026-10-12)
- **Chose:** keep only counties in the 50 states and DC (3,144). Drop Puerto Rico (`72xxx`) and other territories from every layer and from the map.
- **Over:** including Puerto Rico's 78 municipios, which ACS and the map file both carry.
- **Why:** the project focuses on US states. `geoAlbersUsa` doesn't draw Puerto Rico anyway, and CFPB and Building Permits don't cover it, so it would be a partial layer.

## 007 — Keep CFPB delinquency at county level despite ~500 counties (2026-10-12)
- **Chose:** keep the layer. The ~2,640 counties CFPB doesn't publish are greyed out and labelled "Data not available".
- **Over:** switching to CFPB's metro/non-metro file (full coverage but not county values), or cutting the layer.
- **Why:** it's the only free county-level delinquency source, and the counties it covers hold most mortgages. CFPB publishes a county only if it has ≥1,000 mortgages in their sample.
- **Cost accepted:** the map is mostly grey outside metro areas. The ≥3,000-county validation rule gets a layer-specific floor of 450.

## 008 — 2023-boundary TopoJSON instead of us-atlas 3.0.1 (2026-10-12)
- **Chose:** `@severo_bo/us-atlas-2023` (2023 Census cartographic boundaries, same layout as `us-atlas`), vendored into the repo.
- **Over:** `us-atlas@3.0.1` (2017 boundaries), or building our own from Census 2025 boundary files now.
- **Why:** `us-atlas` has Connecticut's old counties and a pre-2019 Alaska split, so all of CT would be grey. The 2023 file matches every source's FIPS exactly. Building from the 2025 Census files remains the fallback if the fork goes away or boundaries change.

## 009 — Median income as the Phase 1 layer (2026-10-12)
- **Chose:** build median household income (ACS B19013) end-to-end first.
- **Over:** CFPB delinquency, the original Phase 1 layer.
- **Why:** income covers 3,143 of 3,144 counties, so it tests the full pipeline, validation and map against a complete layer. Delinquency covers ~500 counties and would mostly exercise the "Data not available" path.
- **Note:** the ACS scripts use only the Python standard library. The summary file is 18 MB and needs a filter, not a query. DuckDB comes in with HMDA, where the 737 MB file needs it.

## 010 — Reframe the layers around mortgage risk; rate, permits and income become context (2026-10-12)
- **Chose:** organise the map around the "double trigger" model: outcome (delinquency vs baseline), burden (owner cost burden, high-DTI loans, property tax % of income) and equity (high-CLTV loans). Median HMDA rate, permits per 1,000 households and median income move to the click panel as context.
- **Over:** the v1 set of five independent layers (delinquency, rate, permits, property tax ÷ home value, income).
- **Why:** the v1 layers described housing conditions without a question tying them together. Measured against "where is mortgage risk building", the rate is too flat to map: across 2,719 counties the 2025 median rate has an IQR of 0.135 points (6.49–6.625%). Permits describe supply, not borrower risk. Income is an input to the burden ratios rather than a risk on its own.
- **Cost accepted:** the Phase 1 income choropleth becomes a context metric in 2d. There is no shock layer until Phase 4 (BLS LAUS county unemployment).

## 011 — Benchmark-based color scales instead of quantiles (2026-10-12)
- **Chose:** `d3.scaleThreshold` with fixed breaks tied to benchmarks (e.g. HUD's 30% and 50% cost-burden lines, z = 0) or to round, documented values. One diverging and one warm sequential palette map-wide, distinguishable by lightness.
- **Over:** quantile breaks, as used in Phase 1.
- **Why:** quantiles always fill every class, so a map looks equally alarming whether risk is high everywhere or nowhere, and a class means something different every year. Fixed breaks make a class mean the same thing across counties, layers and data years, which risk layers need.
- **Cost accepted:** a layer can bunch into one or two classes when the data sits far from the benchmark (see the owner cost burden open question in SPEC).

## 012 — Delinquency baseline window: 2015–2019 (2026-10-12)
- **Superseded by 016:** 2015–2019 turned out to be dominated by the post-crisis decline.
- **Chose:** score each county's latest 90+ day delinquency rate as a z-score against that county's own monthly mean and SD over 2015–2019.
- **Over:** a national benchmark (hides structural differences between counties), the full 2008–present history (dominated by the foreclosure crisis), or a window including 2020–2021.
- **Why:** by 2015 the foreclosure-crisis backlog had largely cleared. From 2020, CARES Act forbearance kept many missed payments from being reported as delinquent, so 2020–2021 understates stress. 2015–2019 is the most recent "normal" stretch.
- **Cost accepted:** counties with a very stable baseline have a near-zero SD, which inflates z. These get flagged rather than shown as extreme (2c sets the cutoff). Only the ~500 counties CFPB publishes have the layer (DECISIONS 007).

## 013 — HMDA loan filters and per-metric suppression (2026-10-12)
- **Chose:** 2025 Snapshot loans that are originated, home purchase, first lien and principal residence, excluding open-end lines of credit and reverse mortgages. `Exempt`/`NA` dropped per field. Each metric suppressed below 30 valid loans in the county. Loan count is a true 0 where a county has no reported loans.
- **Over:** dropping a loan entirely when any field is exempt, or one suppression rule based on total loans.
- **Why:** per-field validity keeps every usable value. A loan with an exempt DTI still has a valid rate. Lenders exempt from reporting the open-end or reverse flag (code `1111`, ~113k loans) aren't evidence that a loan *is* open-end or reverse, so those loans stay in.
- **Note:** 99.8% of qualifying loans are in counties that survive suppression. The ~425 suppressed counties are small and rural.

## 014 — Owner cost burden as the share of mortgaged owners at 30%+, with ACS reliability rules (2026-10-12)
- **Chose:** the share of owner-occupied units with a mortgage paying ≥ 30% of income on owner costs (ACS B25091), with ≥ 50% as click-panel context. Suppress below 30 mortgaged owner units with a computed burden. Flag `low_reliability` where the derived CV exceeds 40% or the share is 0.
- **Over:** the county median burden (B25092), as first planned.
- **Why:** the median reaches the HUD 30% line in only 23 of 3,140 counties, so the benchmark scale would be ~99% one color. The share uses the same HUD threshold but varies meaningfully (p10 17.9%, median 24.8%, p90 35.3%; US 28.1%). Suppression mirrors the HMDA 30-observation rule. The CV flag uses the Census MOE approximation formulas.
- **Cost accepted:** the diverging midpoint becomes the US share rather than the 30% line itself. The 30% line is now built into the definition. CV flags miss some outliers (only 3 of the 21 counties above 50% are flagged).
- **Also:** all layer-level nuances are now tracked in `METHODOLOGY.md`, updated in the same PR as any change.

## 015 — Property tax burden uses owner household income (2026-10-12)
- **Chose:** median real estate taxes paid (B25103) ÷ median household income of owner-occupied households (`B25119_E002`).
- **Over:** ÷ median household income of all households (B19013), as first specified for 2b.
- **Why:** property taxes are paid by owners, so the income should be owners' too. All-household income includes renters, who typically earn less, which overstated the burden. The owner-only ratio is ~14% lower at the county median (2.12% vs 2.46%) and its maximum falls from 12.4% to 7.7%.
- **Cost accepted:** one more ACS table. Coverage is unchanged at 3,136 counties: De Baca County, NM gains a value and Culberson County, TX loses one.

## 016 — Delinquency baseline: 2017–2019 with a 0.2-point SD floor (2026-10-12)
- **Chose:** score the latest 90+ day rate against each county's 2017–2019 monthly mean and SD (36 months), with the SD floored at 0.2 percentage points. Counties where the floor applies are flagged `sd_floored`. Also output the latest rate and the percentage-point change from the baseline mean, for the click panel.
- **Over:** 2015–2019 (DECISIONS 012); 2018–2019; a percentage-point change with no z-score.
- **Why:**
  - **The trend problem with 2015–2019.** Delinquency was still falling from the foreclosure crisis through the window (national 1.6% at end-2015 → 0.9% at end-2019). The early years inflate each county's baseline mean and SD, so the median county scored z = −0.69 and 186 of 507 were ≤ −1. The layer would mostly have said "lower than 2015", not "unusual for this county".
  - **Why not shorter.** Shorter windows remove more of the trend but shrink SDs toward CFPB's 0.1-point rounding. 2018–2019 leaves 346 counties with SD < 0.2. 2017–2019 balances the two: median z −0.10, 98 counties ≥ +1, 132 ≤ −1.
  - **The floor.** One 0.1-point rounding step moves z by 0.1 ÷ SD. Below SD 0.2 that exceeds 0.5, the narrowest legend class, so z would reflect rounding rather than change. Flooring rather than flagging keeps every county on the map with a conservative score.
- **Cost accepted:** the floor applies to 223 of 507 counties, so for nearly half the map z understates moves relative to a very stable baseline. A small within-window decline remains (median −0.14 points/year), so z leans slightly negative. Both are documented in METHODOLOGY.md.

## 017 — Phase 2 UI: palettes, legend config, default layer, keyboard model (2026-10-12)
- **Chose:**
  - **Palettes.** One warm sequential ramp (cream → red-brown), sampled at each layer's class count. One diverging palette (blue → grey → red-orange) with lightness matched across arms. Both built in OKLCH and checked with the dataviz validator's color math: lightness is monotonic along each ramp/arm, and the worst adjacent ΔE under simulated protan/deutan is 7.9 (warm, 7 classes) and 12.4 (diverging). The same colors are used in light and dark mode.
  - **Breaks** as proposed in METHODOLOGY.md. Defined with roles, labels and formats in `site/layers.js`.
  - **"Data not available"** is a hatch over the bare surface, not a grey fill, so it can't be confused with the diverging scales' grey neutral class.
  - **Default layer:** owner cost burden.
  - **Keyboard:** native radios for the layer switcher. A roving tabindex on the map (one tab stop; arrow keys move to the nearest county in that direction; Enter opens the panel; Esc closes). A county search box. A sortable, filterable table of all counties for the active layer.
  - **URL:** layer and selected county are kept in the hash (`#layer=…&county=…`) so a view can be shared.
- **Over:** breaks in `meta.json` (as SPEC first said); delinquency as the default layer; making every county a tab stop.
- **Why:** breaks and colors are presentation choices that change with the page, not with the data, so they belong with the site code. `meta.json` stays a description of the data. Delinquency is the outcome layer but covers only 507 counties, so as a default it would open on a mostly hatched map. Owner cost burden covers 3,134 and sits at the centre of the burden framing. 3,144 tab stops would make the map a keyboard trap; a roving tabindex makes it one stop.
- **Cost accepted:** the first warm step (`#ffeccd`) is close to the light page surface; county borders and the legend carry it. Arrow-key navigation follows centroids, so between irregular or island counties it can jump further than expected. The search box covers direct access.

## 018 — Weekly change-driven refresh that commits to main (2026-10-12)
- **Chose:** a weekly GitHub Actions refresh (plus manual runs). `pipeline/refresh.py` compares each upstream file's Last-Modified date with a committed manifest (`data/processed/sources.json`), re-downloads only changed sources, and re-runs only the clean scripts that depend on them. If validation passes and data changed, the bot commits `data/processed/` to `main` and calls the deploy workflow. Newer data years are reported as a GitHub issue, not switched automatically. PRs touching the pipeline rebuild everything from scratch and must match the committed data byte for byte.
- **Over:** opening a PR for each refresh (the site would wait on a manual merge); re-running the full pipeline every week (a 740 MB HMDA download for a file that changes once a year); auto-switching to new vintages.
- **Why:** SPEC's Phase 3 exit criterion is an unattended run, and validation already gates bad data. Nothing is committed or deployed unless every check passes, and a failed scheduled run emails the repo owner. A separate manifest is needed because `meta.json` records one source per layer, while some layers read two (permits: BPS plus ACS households). New vintages can change table layouts or definitions (as B25092 → B25091 showed), so moving to one is a reviewed change.
- **Cost accepted:** bot commits appear on `main`. A refresh push fails if `main` moved during the run (the next run retries). The deploy is called directly because pushes made with the workflow token don't trigger other workflows. The PR rebuild check can fail spuriously if CFPB publishes a release mid-PR.

## 019 — High-CLTV layer: conventional loans only (2026-10-12)
- **Chose:** compute the CLTV > 90% share over conventional loans only (`loan_type` 1), with sequential breaks 20, 30, 40, 50%. Add the government-backed (FHA/VA/USDA) share of loans to the click panel under Equity.
- **Over:** all loan types with breaks 40–80% (as built in 2a/2d); all loan types with the government share as a caveat only.
- **Why:** FHA, VA and USDA loans are above 90% CLTV by program design (90.0%, 81.4%, 91.9% nationally, against 29.7% for conventional). With them included, a county's share tracked its government-loan share (correlation 0.76), so the equity layer mostly mapped where FHA/VA lending is common. Conventional only, the correlation falls to 0.22 and the layer shows thin equity chosen within a standard product. The government share stays one click away so that thin equity isn't hidden. The 30% break sits at the national conventional share; the classes hold 167/532/833/584/215 counties.
- **Cost accepted:** 314 fewer counties have a value (2,331 vs 2,645), mostly rural counties where government lending dominates, and the layer no longer shows the FHA/VA thin-equity risk on the map itself. The validation floor for this layer drops to 2,100.

## 020 — Housing stress index: two benchmark-scaled scores with fixed weights (2026-10-15)
- **Chose:** two scores matching the double trigger model. **Burden** = 0.5 × NewBuyer + 0.5 × Existing, where NewBuyer = mean(x_PTI, x_D, x_R) and Existing = mean(x_S, x_O), or x_S alone if no other-debt source is usable. **Equity** = x_CLTV. Each component is scaled as x_i = c_i / b_i, with b_PTI = 0.28 and every other benchmark the **2019 national value, fixed** and stored in `benchmarks.json`. PTI is computed per loan from HMDA (principal and interest at n = 360, plus property tax from the county effective rate and insurance from FIO), then the county median. Full definitions in SPEC Phase 4.
- **Over:** a single combined index; weights fitted to delinquency (regression or machine learning); z-scores or percentiles against the current cross-section; benchmarks recomputed each year; PTI from county medians (median loan ÷ median income).
- **Why:**
  - **Two scores, not one.** The double trigger theory says burden and equity fail in different ways. Adding them would let a county with thin equity but low burden look as stressed as one with both, which is the case that matters.
  - **Benchmark scaling.** "1.2 = 20% above benchmark" can be read without a statistics background, and components on different scales (a ratio, shares) become comparable.
  - **Fixed 2019 benchmarks.** Benchmarks recomputed from current data would always center the map on "average", like quantile colors (DECISIONS 011), so a score would mean something different every year. 2019 is the last pre-pandemic year and the backtest's baseline year.
  - **Weights chosen, not fitted.** With 499 backtest counties, fitted weights would largely describe that sample. A stated choice can be tested honestly once (4b), and the test result reported whatever it is.
  - **PTI per loan.** A ratio of medians mixes different borrowers (the median loan isn't taken out by the median-income buyer). Per-loan PTI is each buyer's own payment against their own income.
- **Cost accepted:** equal weights are arbitrary, and the backtest may show the scores add little over their best single input. That's a reportable result, not a reason to tune. The scores mix vintages: 2025 loans, 2020–2024 ACS, 2022 insurance. 2019 benchmarks age, and a 2019 "normal" isn't a target.

## 021 — Equity score uses conventional loans only (2026-10-15)
- **Chose:** x_CLTV is the conventional-loan CLTV > 90% share (`loan_type` 1), ÷ its 2019 national conventional value.
- **Over:** all loan types.
- **Why:** the loan-type check in DECISIONS 019 holds in 2019 too. CLTV > 90%: conventional **36.0%**, FHA 92.6%, VA 88.9%, USDA 94.8% (2025: 29.7%, 89.9%, 81.5%, 91.6%). With government loans included, the score would mostly map where FHA/VA lending is common.
- **Cost accepted:** the same as 019: counties dominated by government lending fall below the 30-loan threshold more often, and FHA/VA thin equity isn't in the score. The government share stays in the click panel.

## 022 — Backtest design: 2019 inputs, 2023–2025 vs 2017–2019 outcome, Connecticut excluded (2026-10-15)
- **Chose:**
  - Score each CFPB county from **2019 inputs** with the same code as the current index.
  - Outcome = the county's mean 90+ day delinquency rate over 2023-01 to 2025-12 minus its mean over 2017-01 to 2019-12, in percentage points. 2020–2022 are excluded.
  - Measure with Spearman correlation, quintile means and the share of counties that rose, with 1,000-resample bootstrap CIs. Compare against each single component and median income alone. Check robustness with HMDA 2018 inputs and a 2024–2025 outcome window.
  - **Exclude the 8 Connecticut planning regions** in CFPB's file, leaving 499 counties.
  - Run once; commit the results. Never tune weights or benchmarks afterwards.
- **Over:** a crosswalk from Connecticut's old counties to planning regions; including 2020–2022; a random train/test split.
- **Why:**
  - **2020–2022 excluded:** CARES Act forbearance kept missed payments from being reported as delinquent (DECISIONS 012), so those years understate stress.
  - **Connecticut:** 2019 HMDA and ACS use the old 8 counties, and the planning regions don't nest within them, so a crosswalk would apportion by population for 8 of 507 counties. Alaska's Valdez-Cordova split doesn't affect the set, since CFPB doesn't publish those counties.
  - **Run once:** a test that can be re-run until it passes isn't a test.
  - **Single-input baselines:** an index is only worth its complexity if it beats the best of its parts.
- **Cost accepted:** 499 counties, mostly metropolitan (CFPB's coverage rule, DECISIONS 007), so the result says nothing about rural counties. One outcome window, in a period with its own shocks (rate rises, insurance costs), so a null result doesn't prove the theory wrong, and a positive one doesn't prove it right.

## 023 — Drop O (non-mortgage debt) from the Burden score (2026-10-15)
- **Chose:** Existing = x_S alone. No non-mortgage debt component.
- **Over:** the Urban Institute credit card delinquency rate as O; any of its collections measures.
- **Why:**
  - **Rounding.** The only 2019-era release (`201911-update`, built on 2018 credit data) rounds rates to 2 decimals. Card delinquency takes just **20 distinct values** across 2,945 counties, mostly 0.02–0.07, so x_O would move in steps of about 25% of its benchmark and rank counties mostly by rounding.
  - **A structural break.** From 2022 the credit bureaus stopped reporting most medical collections: the median county's share with medical debt in collections fell from 0.19 to 0.04, and with any debt in collections from 0.32 to 0.23. That's a change in reporting, not in stress, and against a fixed 2019 benchmark it would read as improvement. Student loans also changed from "in default" to "delinquent or in default".
  - Urban still reports Connecticut by its old counties in 2025.
- **Cost accepted:** **non-mortgage debt enters the score only through D and R**, i.e. through new buyers' debt-to-income ratios and denials. Existing owners' card, auto and student debt isn't measured. Listed as a limitation (SPEC Phase 4).

## 024 — Insurance premiums: HUD crosswalk run once, locally; county tables committed (2026-10-15)
- **Chose:** convert FIO ZIP premiums to counties with the HUD USPS crosswalk via a HUD API token kept in a git-ignored `.env` on this Mac. Run once per FIO year used, and **commit the county-level premium tables** to `data/processed/`. Use the **Q4 2019** crosswalk for the 2019 premiums (2019 county codes, as in the backtest inputs) and a **recent** crosswalk for 2022 (current county codes, matching the map). The county premium is the residential-address-weighted mean of its ZIPs' premiums, renormalized over the ZIPs FIO publishes, and null below 50% coverage.
- **Over:** storing the token as a GitHub Actions secret and converting on every refresh; the public Census 2010 ZCTA housing-unit weights; one crosswalk for both years.
- **Why:** FIO data is a one-off release (2018–2022, nothing newer), so there's nothing for a scheduled job to refresh. Committing the result keeps the token off GitHub and the refresh free of a dependency on a login-gated service. HUD's crosswalk reflects USPS addresses at the time, and using the crosswalk from the same period as the premiums keeps each year's county codes consistent with its other inputs.
- **Cost accepted:** the county tables can only be rebuilt on a machine with the token. Their provenance (crosswalk year and quarter, retrieval date, input file hash) is recorded in `meta.json` so they can be audited.

## 025 — PTI loan rules and loan term (2026-10-15)
- **Chose:**
  - **n = each loan's own `loan_term`** (months), falling back to **360 only when it's `NA` or `Exempt`**; the fallbacks are counted.
  - **Exclude interest-only, balloon and negative-amortization loans** (flag = `1`; `1111` exempt stays in, as in DECISIONS 013). The amortization formula doesn't describe their payments.
  - **Keep a loan only if** `0 < interest_rate ≤ 20`, `loan_amount > 0` and `property_value > 0`, `income ≥ 10` ($10,000), and the computed **PTI ≤ 1.0**. Also, the county must have a tax rate and an insurance premium, since T and I need them.
  - Report the loans removed by each rule, nationally and per county, and **flag counties that lose more than 10%** of their loans.
  - The amortization unit test includes a 15-year case.
- **Over:** n = 360 for every loan; validity bounds of `rate > 0` and `income > 0` only; trimming by percentiles.
- **Why:**
  - **Loan term.** 15-year loans have much higher payments than a 30-year formula gives (3.6% of qualifying 2019 loans and 2.3% of 2025 loans have a 180-month term), so a fixed 360 would understate PTI where they're common.
  - **The bounds.** 2019 has interest rates up to 5,625% and incomes of $0 or less, which are reporting errors. An income below $10,000 for a home buyer is almost always a placeholder or a misreported unit, and a payment above 100% of income isn't a real loan.
  - **Per-rule counts and the flag** keep the rules auditable and show where they bite.
- **Cost accepted:** the rules are judgment calls. The PTI ≤ 1.0 cap trims the extreme tail, so PTI medians lean very slightly low where such loans cluster. Counties without an insurance premium or tax rate get no PTI, and so a NewBuyer half of only D and R.

## 026 — 2018 robustness inputs: HMDA Snapshot, alongside 2019 One-Year (2026-10-15)
- **Chose:** the 4b robustness run uses the **2018 Snapshot** HMDA file; the main backtest uses the **2019 One-Year** file.
- **Over:** dropping the 2018 check; switching 2019 to Snapshot so both match.
- **Why:** FFIEC publishes no 2018 One-Year file (404 at every path tried; the Data Browser serves 2018 from the Three-Year dataset). One-Year is the more complete view of 2019, and the difference between the two dataset types is resubmitted records only.
- **Cost accepted:** the two runs differ slightly in dataset type as well as year. Recorded in `meta.json` and in the 4b report.

## 027 — ACS 2015–2019 from the Census prototype table-based files (2026-10-15)
- **Chose:** read 2019 ACS tables from `summary_file/2019/prototype/5YRData/acsdt5y2019-{table}.dat` with the existing reader.
- **Over:** parsing the official sequence-based summary files; the Census API (needs a key).
- **Why:** table-based files exist from 2021 onward only, and 2019 is published in that format only as a "prototype". A **spot-check against the official sequence-based 2019 release** (run 2026-10-15) compared every county in 10 states (AL, AK, CA, CT, DE, DC, FL, NY, TX, VT): **563 counties, all six tables** (B11001, B19013, B25077, B25091, B25103, B25119), **45,040 cells (every estimate and MOE), 0 mismatches**. 99 cells are unavailable in both, each file using its own missing-value code.
- **Cost accepted:** a check of 10 states, not all 51. The headers are identical to 2024, so a format error elsewhere would also have shown up in these states.

## 028 — Backtest analysis choices, fixed before the run (2026-10-16)
- **Chose:**
  - Every measure is oriented so a **positive rho means "higher stress, bigger rise"**; median income enters as −income ("lower income").
  - Each measure is evaluated on **the counties that have it**; each Burden-vs-input comparison on the counties that have both.
  - **"Does Burden beat its best single input?"** is answered with a **paired bootstrap CI of rho(Burden) − rho(component) for every Burden input** (PTI, D, R, S), not just for whichever looks best afterwards. Burden "beats" an input only if that CI is above 0.
  - Quintiles by rank of the measure, ties broken by FIPS; the first n mod 5 quintiles get one extra county. "Rose" = outcome > 0. Q5−Q1 = top-quintile mean change minus bottom, with its own bootstrap CI.
  - Percentile bootstrap, 1,000 resamples of counties, seed 20261016; one random stream in a fixed order.
  - Robustness: HMDA 2018 runs with the **2018 FIO premiums** (Q4 2018 crosswalk) and the same ACS 2015–2019.
- **Over:** evaluating all measures on one common sample (it would drop counties from every measure to match the sparsest); comparing Burden only against the best-looking input (choosing the comparison after seeing the results).
- **Why:** SPEC Phase 4 fixed the metrics but not these details, and each one could be bent after seeing the results. Committing them with the code, before the 2019 county scores exist, keeps the test honest.
- **Cost accepted:** measures with different n aren't on exactly the same counties; the paired comparisons are the like-for-like test.

## 029 — One pre-specified secondary backtest outcome: the 2023–2025 level, controlling for the 2017–2019 level (2026-10-16)
- **Chose** (the owner's specification, logged before any of it is computed):
  - **Outcome:** each county's mean 90+ day delinquency **level**, 2023-01 to 2025-12 (a level, not a change).
  - **Test:** Spearman **partial** correlation between the 2019 Burden score and that level, controlling for the county's 2017-01 to 2019-12 mean level. Rank all three variables (ties averaged), regress the outcome ranks and the Burden ranks each on the baseline ranks (OLS with an intercept), and correlate the two sets of residuals.
  - **CI:** 95% percentile bootstrap, 1,000 resamples of counties, seed 20261016 (as in DECISIONS 028); each resample is re-ranked.
  - **Baselines:** the same test for each single component (PTI, D, R, S, CLTV; Equity = x_CLTV ranks identically to CLTV) and for median income, entered as −income ("lower income") so a positive value means the expected direction, as in DECISIONS 028.
  - **Same 499 counties and the same 2019 scores** (`reports/backtest/county_scores.json`, from the primary run). No other changes.
  - **Reported whatever its sign.** The primary change-score result stays the headline of BACKTEST.md; this one is labelled a pre-specified secondary analysis added after the primary result.
- **Over:** a second change score; adding further secondary outcomes or robustness runs for it.
- **Why:** the primary outcome turned out to be dominated by regression to the mean: delinquency fell in 92% of counties and the change tracks the 2017–2019 level (ρ = −0.77), so any measure correlated with that level gets a negative ρ. Controlling for the baseline asks whether Burden ranks counties' later levels beyond what their earlier levels already explain.
- **Cost accepted:** it was chosen after the primary result was seen. Fixing exactly one test, in writing, before computing it limits but doesn't remove that; the report says so.
