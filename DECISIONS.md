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
