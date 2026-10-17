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
    panelName: "Delinquency vs own 2017–2019 average",
    title: "90+ day mortgage delinquency compared with each county's 2017–2019 normal",
    scale: "diverging",
    breaks: [-2, -1, -0.5, 0.5, 1, 2],
    tick: tick.z,
    unit: "Standard deviations from the county's 2017–2019 average",
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
    panelName: "Mortgaged owners paying 30%+",
    title: "Share of mortgaged owners paying 30% or more of income on housing",
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
    panelName: "2025 loans with DTI above 43%",
    title: "Share of 2025 home-purchase loans with debt-to-income above 43%",
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
    panelName: "Median property tax as % of owner income",
    title: "Median property tax as a share of median owner income (ratio of medians)",
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
    panelName: "2025 conventional loans with CLTV above 90%",
    title: "Share of 2025 conventional purchase loans with combined LTV above 90%",
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
    panelName: "Burden score (1.0 = 2019 benchmark)",
    title: "Burden score: payment burden, high-DTI lending, DTI denials and owner cost burden vs 2019",
    scale: "diverging",
    breaks: INDEX_BREAKS,
    tick: tick.ratio,
    unit: "× the 2019 national benchmark",
    neutral: "0.9–1.1: near benchmark",
    ends: ["Below benchmark", "Above benchmark"],
    format: fmt.ratio,
  },
  {
    id: "index_equity",
    role: "index",
    file: "equity", field: "equity",
    name: "Equity score",
    panelName: "Equity score (1.0 = 2019 benchmark)",
    title: "Equity score: share of conventional loans above 90% CLTV vs 2019",
    scale: "diverging",
    breaks: INDEX_BREAKS,
    tick: tick.ratio,
    unit: "× the 2019 national benchmark",
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
    title: "Burden and Equity scores together: where both are above the 2019 benchmark",
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
      { id: "cfpb_delinquency_90", name: "Mortgages 90+ days delinquent", format: fmt.pct1 },
      { id: "cfpb_delinquency_change", name: "Change vs 2017–2019 average", format: fmt.pts },
    ],
  },
  {
    role: "burden", label: "Burden",
    rows: [
      { id: "acs_cost_burden", layer: true },
      { id: "acs_cost_burden_severe", name: "Mortgaged owners paying 50%+", format: fmt.pct1 },
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
      { id: "hmda_govt_share", name: "2025 loans that are FHA, VA or USDA", format: fmt.pct1 },
    ],
  },
  {
    // Each component shows its value and its x (value ÷ 2019 benchmark).
    role: "index", label: "Index",
    rows: [
      { id: "index_burden", layer: true },
      { id: "index_pti", file: "burden", field: "pti", x: "x_pti", flags: ["pti_rules_over_10pct"],
        name: "PTI: median payment on 2025 loans, % of income", format: fmt.pti },
      { id: "index_d", file: "burden", field: "d", x: "x_d",
        name: "D: 2025 loans with DTI above 43%", format: fmt.pct1 },
      { id: "index_r", file: "burden", field: "r", x: "x_r",
        name: "R: applications denied for DTI", format: fmt.pct1 },
      { id: "index_s", file: "burden", field: "s", x: "x_s",
        name: "S: mortgaged owners paying 30%+", format: fmt.pct1 },
      { id: "index_equity", layer: true },
      { id: "index_cltv", file: "equity", field: "cltv", x: "x_cltv",
        name: "CLTV: conventional loans above 90%", format: fmt.pct1 },
      { id: "index_bivariate", layer: true },
    ],
  },
  {
    role: "context", label: "Context",
    rows: [
      { id: "income", name: "Median household income", format: fmt.usd },
      { id: "hmda_rate", name: "Median rate on 2025 loans", format: fmt.rate },
      { id: "hmda_loan_amount", name: "Median amount of 2025 loans", format: fmt.usd },
      { id: "hmda_loans", name: "2025 home-purchase loans", format: fmt.count },
      { id: "permits_per_1000_hh", name: "2025 units permitted per 1,000 households", format: fmt.per1000 },
    ],
  },
];

// Wording for per-county caveats recorded in meta.json -> flags.
const FLAG_TEXT = {
  low_reliability: "Low reliability: small survey sample",
  topcoded: "Lower bound: taxes top-coded at $10,000+",
  sd_floored: "Very stable baseline: SD floored at 0.2 pts, so this is conservative",
  fewer_than_3_components: "Rests on fewer than 3 of its 4 inputs",
  pti_rules_over_10pct: "Over 10% of this county's loans fail the PTI loan rules",
};

const METHODOLOGY_URL = "https://github.com/jackrz412/us-housing-map/blob/main/METHODOLOGY.md";
