// Layer configuration: what each metric is, which role it plays, and how it's
// colored. map.js reads this; nothing here is computed from the data.
//
// Breaks are fixed benchmarks, not quantiles (DECISIONS 011): a class means the
// same thing in every county and every data year. Definitions and the reasons
// for each break are in METHODOLOGY.md.

// --- Palettes ------------------------------------------------------------------
// Built in OKLCH so equal steps look equal. Checked with the dataviz validator's
// color math: lightness changes monotonically along each ramp/arm, and every
// adjacent pair stays distinguishable under simulated protanopia and
// deuteranopia (worst adjacent ΔE ×100: warm 7.9, diverging 12.4). The same
// colors are used in light and dark mode, so color direction never flips.
//
// Warm sequential: one ramp (light cream -> dark red-brown), sampled at each
// layer's class count so lightness steps stay even.
const WARM = {
  5: ["#ffeccd", "#feaf4c", "#de7802", "#af4c0d", "#6b372a"],
  6: ["#ffeccd", "#febc68", "#f08c0b", "#cc6605", "#a24717", "#6b372a"],
  7: ["#ffeccd", "#ffc479", "#f79b2c", "#de7802", "#c05a04", "#9a431d", "#6b372a"],
};
// Diverging: blue arm, grey neutral, red-orange arm, lightness matched across
// arms so neither side looks more important.
const DIVERGING = ["#215da5", "#528ed9", "#9bc1f1", "#e6e5e0", "#ecac9b", "#d76549", "#a03317"];
// Bivariate (Burden × Equity), 3×3, index = equity class * 3 + burden class
// (each class 0 = below 0.9, 1 = 0.9–1.1, 2 = above 1.1). Built in OKLab:
// lightness falls by the same step for each class up on either score, so
// darker = more loaded; Burden adds orange (hue 50°) and Equity adds blue
// (265°), which stay apart on the blue–yellow axis that colorblind viewers
// keep. Checked with the dataviz validator's math over all 36 pairs: worst
// ΔE ×100 16.2 in normal vision (floor 15) and 14.5 under simulated
// protanopia/deuteranopia (target 8).
const BIVARIATE = [
  "#e8e8e8", "#e8ab89", "#de6907",
  "#a0baf2", "#a4849a", "#9c4946",
  "#5b89f6", "#6759a1", "#602753",
];

// --- Formats -------------------------------------------------------------------
const fmt = {
  pct1: (v) => `${v.toFixed(1)}%`,
  pct2: (v) => `${v.toFixed(2)}%`,
  z: (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)} SD`,
  pts: (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)} pts`,
  rate: (v) => `${v.toFixed(3).replace(/0$/, "")}%`,
  usd: (v) => `$${Math.round(v).toLocaleString("en-US")}`,
  count: (v) => Math.round(v).toLocaleString("en-US"),
  per1000: (v) => v.toFixed(1),
  ratio: (v) => `${v.toFixed(2)}×`,
  pti: (v) => `${(100 * v).toFixed(1)}%`,
};

// Short legend tick labels.
const tick = {
  pct: (v) => `${v}%`,
  z: (v) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : "0"),
  ratio: (v) => `${v}`,
};

// Stress index scores (Phase 4): x = value ÷ its fixed 2019 benchmark, so
// 1.0 = the benchmark. Breaks are roughly symmetric on a ratio scale
// (1/1.5 ≈ 0.67, 1/1.25 = 0.8, 1/1.1 ≈ 0.9), with 0.9–1.1 as "near
// benchmark" (DECISIONS 031). The bivariate view uses the same 0.9 / 1.1.
const INDEX_BREAKS = [0.67, 0.8, 0.9, 1.1, 1.25, 1.5];
const BIVARIATE_BREAKS = [0.9, 1.1];
const BIVARIATE_LEVELS = ["below", "near", "above"];
const bivariateClass = (v) => BIVARIATE_BREAKS.filter((b) => v >= b).length;

// --- Map layers, grouped by role --------------------------------------------------
// `title`, `unit`, `panelName` and panel `name` may mark glossary terms as [[key|shown text]] (GLOSSARY
// below); the page shows those as small definition tooltips. Use plainText()
// wherever the text is needed without them.
// `name` is the short switcher label. `panelName` is used in the click panel
// and table, where each value sits next to a number: it says what the value
// is a share (or ratio) of, so "34%" can't be misread.
// Order here is the order in the layer switcher.
//
// Data: a layer or panel row reads data/<id>.json ({fips: value}) unless it
// names a `file` and `field`, for files with one object per county
// ({fips: {field: value}}, e.g. burden.json). `flags` lists which of the
// file's per-county caveats (meta.json -> flags) apply to it.
const ROLES = [
  { id: "outcome", label: "Outcome" },
  { id: "burden", label: "Burden" },
  { id: "equity", label: "Equity" },
  { id: "index", label: "Index" },
];

const MAP_LAYERS = [
  {
    id: "cfpb_delinquency_z",
    role: "outcome",
    name: "Delinquency vs baseline",
    panelName: "[[delinquency|Delinquency]] vs own 2017–2019 average",
    title: "[[delinquency|90+ day mortgage delinquency]] compared with each county's 2017–2019 normal",
    scale: "diverging",
    breaks: [-2, -1, -0.5, 0.5, 1, 2],
    tick: tick.z,
    unit: "[[sd|Standard deviations]] from the county's 2017–2019 average",
    neutral: "−0.5 to +0.5: near baseline",
    // Midpoint is the county's own 2017–2019 baseline (z = 0). Higher
    // delinquency is worse, so the ends say which way is better.
    ends: ["Better than baseline", "Worse than baseline"],
    format: fmt.z,
  },
  {
    id: "acs_cost_burden",
    role: "burden",
    name: "Owner cost burden",
    panelName: "Mortgaged owners [[cost_burden|paying 30%+]]",
    title: "Share of mortgaged owners [[cost_burden|paying 30% or more of income on housing]]",
    scale: "diverging",
    // Neutral class 25–30% contains the US share (28.1%).
    breaks: [15, 20, 25, 30, 35, 40],
    tick: tick.pct,
    unit: "% of owners with a mortgage",
    neutral: "25–30%: around the US share",
    // Midpoint is the US share (28.1%), not a fixed benchmark.
    ends: ["Below US share", "Above US share"],
    format: fmt.pct1,
  },
  {
    id: "hmda_dti_over_43",
    role: "burden",
    name: "High-DTI loans",
    panelName: "2025 loans with [[dti|DTI]] above [[qm|43%]]",
    title: "Share of 2025 home-purchase loans with [[dti|debt-to-income]] above 43%",
    scale: "sequential",
    breaks: [20, 30, 40, 50],
    tick: tick.pct,
    unit: "% of loans",
    format: fmt.pct1,
  },
  {
    id: "acs_property_tax_income",
    role: "burden",
    name: "Property tax burden",
    panelName: "Median property tax as % of owner income ([[ratio_of_medians|ratio of medians]])",
    title: "Median property tax as a share of median owner income ([[ratio_of_medians|ratio of medians]])",
    scale: "sequential",
    breaks: [1, 1.5, 2, 2.5, 3, 4],
    tick: tick.pct,
    unit: "% of owner household income",
    format: fmt.pct2,
  },
  {
    id: "hmda_cltv_over_90",
    role: "equity",
    name: "High-CLTV loans",
    panelName: "2025 [[conventional|conventional]] loans with [[cltv|CLTV]] above 90%",
    title: "Share of 2025 [[conventional|conventional]] purchase loans with [[cltv|combined loan-to-value (CLTV)]] above 90%",
    scale: "sequential",
    // Conventional loans only (DECISIONS 019). 30% is about the national share.
    breaks: [20, 30, 40, 50],
    tick: tick.pct,
    unit: "% of conventional loans (excludes FHA, VA, USDA)",
    format: fmt.pct1,
  },
  {
    id: "index_burden",
    role: "index",
    file: "burden", field: "burden",
    flags: ["fewer_than_3_components"],
    name: "Burden score",
    panelName: "[[burden_score|Burden score]] (1.0 = [[benchmark|2019 benchmark]])",
    title: "[[burden_score|Burden score]]: [[pti|payment burden]], [[dti|high-DTI lending]], [[dti_denials|DTI denials]] and [[cost_burden|owner cost burden]] vs 2019",
    scale: "diverging",
    breaks: INDEX_BREAKS,
    tick: tick.ratio,
    unit: "× the [[benchmark|2019 national benchmark]]",
    neutral: "0.9–1.1: near benchmark",
    ends: ["Below benchmark", "Above benchmark"],
    format: fmt.ratio,
  },
  {
    id: "index_equity",
    role: "index",
    file: "equity", field: "equity",
    name: "Equity score",
    panelName: "[[equity_score|Equity score]] (1.0 = [[benchmark|2019 benchmark]])",
    title: "[[equity_score|Equity score]]: share of [[conventional|conventional]] loans above 90% [[cltv|CLTV]] vs 2019",
    scale: "diverging",
    breaks: INDEX_BREAKS,
    tick: tick.ratio,
    unit: "× the [[benchmark|2019 national benchmark]]",
    neutral: "0.9–1.1: near benchmark",
    ends: ["Below benchmark", "Above benchmark"],
    format: fmt.ratio,
  },
  {
    id: "index_bivariate",
    role: "index",
    // Two values per county; map.js reads both and colors by BIVARIATE.
    pair: ["index_burden", "index_equity"],
    name: "Burden × Equity",
    panelName: "Burden × Equity",
    title: "[[burden_score|Burden]] and [[equity_score|Equity scores]] together: where both are above the [[benchmark|2019 benchmark]]",
    scale: "bivariate",
    unit: "Scores × the 2019 national benchmark",
    format: ([b, e]) => `Burden ${fmt.ratio(b)} · Equity ${fmt.ratio(e)}`,
    describe: ([b, e]) => {
      const [i, j] = [bivariateClass(b), bivariateClass(e)];
      if (i === 2 && j === 2) return "Both above benchmark: heavy burden and thin equity";
      return `Burden ${BIVARIATE_LEVELS[i]} · Equity ${BIVARIATE_LEVELS[j]} benchmark`;
    },
    // Table sort: by combined class, then Burden.
    sortValue: ([b, e]) => 10 * (bivariateClass(b) + bivariateClass(e)) + b,
  },
];

const DEFAULT_LAYER = "acs_cost_burden";

// --- Click panel ------------------------------------------------------------------
// Every metric the panel shows, by section. `layer: true` rows are map layers
// (shown with their color chip); the rest are context, shown without color.
const PANEL = [
  {
    role: "outcome", label: "Outcome",
    rows: [
      { id: "cfpb_delinquency_z", layer: true },
      { id: "cfpb_delinquency_90", name: "Mortgages [[delinquency|90+ days delinquent]]", format: fmt.pct1 },
      { id: "cfpb_delinquency_change", name: "Change vs 2017–2019 average ([[pp|points]])", format: fmt.pts },
    ],
  },
  {
    role: "burden", label: "Burden",
    rows: [
      { id: "acs_cost_burden", layer: true },
      { id: "acs_cost_burden_severe", name: "Mortgaged owners [[cost_burden|paying 50%+]]", format: fmt.pct1 },
      { id: "hmda_dti_over_43", layer: true },
      { id: "acs_property_tax_income", layer: true },
    ],
  },
  {
    role: "equity", label: "Equity",
    rows: [
      { id: "hmda_cltv_over_90", layer: true },
      // Excluded from the layer because they're above 90% by design; shown
      // here so that thin equity isn't hidden.
      { id: "hmda_govt_share", name: "2025 loans that are [[govt|FHA, VA or USDA]]", format: fmt.pct1 },
    ],
  },
  {
    // Each component shows its value and its x (value ÷ 2019 benchmark).
    role: "index", label: "Index",
    rows: [
      { id: "index_burden", layer: true },
      { id: "index_pti", file: "burden", field: "pti", x: "x_pti", flags: ["pti_rules_over_10pct"],
        name: "[[pti|PTI]]: median [[pi|payment]] on 2025 loans, % of income", format: fmt.pti },
      { id: "index_d", file: "burden", field: "d", x: "x_d",
        name: "D: 2025 loans with [[dti|DTI]] above [[qm|43%]]", format: fmt.pct1 },
      { id: "index_r", file: "burden", field: "r", x: "x_r",
        name: "R: applications [[dti_denials|denied for DTI]]", format: fmt.pct1 },
      { id: "index_s", file: "burden", field: "s", x: "x_s",
        name: "S: mortgaged owners [[cost_burden|paying 30%+]]", format: fmt.pct1 },
      { id: "index_equity", layer: true },
      { id: "index_cltv", file: "equity", field: "cltv", x: "x_cltv",
        name: "[[cltv|CLTV]]: [[conventional|conventional]] loans above 90%", format: fmt.pct1 },
      { id: "index_bivariate", layer: true },
    ],
  },
  {
    role: "context", label: "Context",
    rows: [
      { id: "income", name: "[[median|Median]] household income", format: fmt.usd },
      { id: "hmda_rate", name: "Median rate on 2025 loans", format: fmt.rate },
      { id: "hmda_loan_amount", name: "Median amount of 2025 loans", format: fmt.usd },
      { id: "hmda_loans", name: "2025 home-purchase loans", format: fmt.count },
      { id: "permits_per_1000_hh", name: "2025 units permitted per 1,000 households", format: fmt.per1000 },
    ],
  },
];

// Wording for per-county caveats recorded in meta.json -> flags. May mark
// glossary terms, shown as tooltips in the click panel.
const FLAG_TEXT = {
  low_reliability: "[[low_reliability|Low reliability]]: small survey sample",
  topcoded: "Lower bound: taxes [[topcoded|top-coded]] at $10,000+",
  sd_floored: "Very stable baseline: [[sd|SD]] floored at 0.2 pts, so this is conservative",
  fewer_than_3_components: "Rests on fewer than 3 of its 4 inputs",
  pti_rules_over_10pct: "Over 10% of this county's loans fail the PTI loan rules",
};

const METHODOLOGY_URL = "https://github.com/jackrz412/us-housing-map/blob/main/METHODOLOGY.md";

// --- Glossary ----------------------------------------------------------------------
// Definitions behind the [[key|text]] terms in layer titles and units. Each is
// a one- or two-sentence functional definition plus a worked example; the
// numbers in examples are illustrative, except benchmarks, which are the real
// 2019 values (METHODOLOGY.md, Stress index).
const GLOSSARY = {
  delinquency: {
    term: "90+ day delinquency",
    def: "A mortgage is 90+ days delinquent when the borrower is three or more monthly payments behind. The rate is the share of mortgages in that state.",
    example: "12 of 1,000 mortgages 90+ days late → 12 ÷ 1,000 = 1.2%",
  },
  sd: {
    term: "Standard deviations (SD)",
    def: "How unusual the latest rate is for this county, measured in its own typical month-to-month swing during 2017–2019. 0 = its 2017–2019 average.",
    example: "Average 1.0%, SD 0.2 pts, latest 1.4% → (1.4 − 1.0) ÷ 0.2 = +2 SD",
  },
  cost_burden: {
    term: "Owner cost burden",
    def: "Monthly owner costs (mortgage, property tax, insurance, utilities, HOA fees) as a share of household income. 30% or more counts as cost-burdened; 50% or more, severely.",
    example: "$2,100 costs ÷ $6,000 monthly income = 35% → cost-burdened",
  },
  dti: {
    term: "Debt-to-income ratio (DTI)",
    def: "All monthly debt payments, the new mortgage plus car, student loan and card payments, divided by gross monthly income, as the lender calculated it. 43% was the long-standing Qualified Mortgage cap.",
    example: "$2,500 mortgage + $650 other debts on $7,000 income → 3,150 ÷ 7,000 = 45%, above 43%",
  },
  ratio_of_medians: {
    term: "Ratio of medians",
    def: "The county's median property tax divided by its median owner income. The two medians usually belong to different households, so it isn't any one owner's share.",
    example: "$3,000 median tax ÷ $90,000 median income = 3.3%",
  },
  conventional: {
    term: "Conventional loan",
    def: "A mortgage that isn't insured or guaranteed by a government program (FHA, VA or USDA). Those programs allow small down payments by design, so they're left out.",
    example: "100 purchase loans: 70 conventional, 30 FHA or VA → only the 70 are counted",
  },
  cltv: {
    term: "Loan-to-value (LTV) and combined LTV (CLTV)",
    def: "LTV is the mortgage divided by the home's value; 100% minus LTV is the buyer's equity. CLTV adds any second mortgage or home-equity loan. Above 90% means under 10% equity.",
    example: "$340,000 first + $25,000 second on a $400,000 home → LTV 85%, CLTV 365 ÷ 400 = 91%",
  },
  pti: {
    term: "Payment-to-income (PTI)",
    def: "A new buyer's monthly principal, interest, property tax and insurance divided by their gross monthly income. The county value is the median across 2025 loans; the benchmark is 28%.",
    example: "$1,900 loan payment + $350 tax + $150 insurance on $8,000 income → 2,400 ÷ 8,000 = 30%",
  },
  dti_denials: {
    term: "DTI denials",
    def: "The share of home-purchase applications that lenders decided on and denied, citing debt-to-income as a reason.",
    example: "45 of 1,000 decided applications denied for DTI → 4.5% (2019 benchmark 4.10%)",
  },
  benchmark: {
    term: "2019 national benchmark",
    def: "Each input's 2019 US value, fixed for good. A county's value is divided by it, so 1.0 = the 2019 national level and 1.2 = 20% above it.",
    example: "High-DTI benchmark 28.52%; a county at 34.2% → 34.2 ÷ 28.52 = 1.20×",
  },
  burden_score: {
    term: "Burden score",
    def: "Half new-buyer strain (the average of payment-to-income, high-DTI share and DTI denials), half existing owners' cost burden. Each input is first divided by its 2019 benchmark.",
    example: "New-buyer inputs 1.3×, 1.1×, 1.0× → 1.13; owners 0.95× → 0.5 × 1.13 + 0.5 × 0.95 = 1.04",
  },
  equity_score: {
    term: "Equity score",
    def: "The share of conventional loans above 90% CLTV, divided by the 2019 national share (36.03%). Higher means more recent buyers with thin equity.",
    example: "45% of loans above 90% CLTV → 45 ÷ 36.03 = 1.25×",
  },
  pp: {
    term: "Percentage points (pts)",
    def: "The plain difference between two percentages. It isn't the same as a percent change.",
    example: "1.0% → 1.5% is 1.5 − 1.0 = +0.5 pts, but a (1.5 − 1.0) ÷ 1.0 = 50% increase",
  },
  median: {
    term: "Median",
    def: "The middle value once all values are sorted: half are above it, half below. Unlike an average, a few very large values don't pull it up.",
    example: "$40k, $55k, $60k, $70k, $400k → median $60k (average $125k)",
  },
  govt: {
    term: "Government-backed loans (FHA, VA, USDA)",
    def: "Mortgages insured or guaranteed by the Federal Housing Administration, Veterans Affairs or the Department of Agriculture. They allow 0–3.5% down, so most start above 90% CLTV.",
    example: "FHA: $400,000 home, 3.5% down → $386,000 loan, 96.5% LTV",
  },
  qm: {
    term: "43% DTI (old Qualified Mortgage cap)",
    def: "Until 2021, a loan generally needed DTI of 43% or less to count as a Qualified Mortgage, which gives lenders legal protection. The rule is now price-based, and FHA and VA often go higher, so 43% is a historical yardstick.",
    example: "$3,000 debts ÷ $7,000 income = 42.9%, under; $3,050 ÷ $7,000 = 43.6%, over",
  },
  pi: {
    term: "Principal and interest (P&I)",
    def: "The fixed monthly loan payment: interest on the balance plus enough principal to pay the loan off over its term. PTI adds property tax and insurance on top.",
    example: "$300,000 at 6.5% over 30 years → $1,896 a month",
  },
  x: {
    term: "x: value ÷ benchmark",
    def: "Each index input divided by its fixed 2019 national value, so 1.00× is the 2019 level. The Burden and Equity scores are built from these.",
    example: "R: 5.1% ÷ 4.10% = 1.24×",
  },
  low_reliability: {
    term: "Low reliability",
    def: "The Census survey reached few households here, so the margin of error is large next to the estimate (coefficient of variation above 40%). The value is shown, but read it loosely.",
    example: "20% ± 15 pts → error 15 ÷ 1.645 = 9.1; 9.1 ÷ 20 = 46%, above 40%",
  },
  topcoded: {
    term: "Top-coded",
    def: "The Census reports any median property tax of $10,000 or more as \"$10,000+\", so the true value is higher and the ratio is a minimum.",
    example: "$10,000+ tax ÷ $95,000 income → at least 10.5%",
  },
  acs5: {
    term: "ACS 5-year estimate",
    def: "The Census American Community Survey pools five years of responses so that small counties have enough households. The value describes the whole period, not its last year.",
    example: "2020–2024 5-year: answers from 2020 through 2024 combined, centered on 2022",
  },
};

// Glossary markup: [[key|shown text]]. ACS periods in legend captions get
// their term from markPeriods().
const TERM_MARKUP = /\[\[(\w+)\|([^\]]+)\]\]/g;
const plainText = (s) => s.replace(TERM_MARKUP, "$2");
const markPeriods = (s) => s.replace(/ACS \d{4}–\d{4} 5-year/g, "[[acs5|$&]]");
