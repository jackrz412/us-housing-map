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
};

// Short legend tick labels.
const tick = {
  pct: (v) => `${v}%`,
  z: (v) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : "0"),
};

// --- Map layers, grouped by role --------------------------------------------------
// Order here is the order in the layer switcher.
const ROLES = [
  { id: "outcome", label: "Outcome" },
  { id: "burden", label: "Burden" },
  { id: "equity", label: "Equity" },
];

const MAP_LAYERS = [
  {
    id: "cfpb_delinquency_z",
    role: "outcome",
    name: "Delinquency vs baseline",
    title: "90+ day mortgage delinquency compared with each county's 2017–2019 normal",
    scale: "diverging",
    breaks: [-2, -1, -0.5, 0.5, 1, 2],
    tick: tick.z,
    unit: "Standard deviations from the county's 2017–2019 average",
    neutral: "−0.5 to +0.5: near baseline",
    format: fmt.z,
  },
  {
    id: "acs_cost_burden",
    role: "burden",
    name: "Owner cost burden",
    title: "Share of mortgaged owners paying 30% or more of income on housing",
    scale: "diverging",
    // Neutral class 25–30% contains the US share (28.1%).
    breaks: [15, 20, 25, 30, 35, 40],
    tick: tick.pct,
    unit: "% of owners with a mortgage",
    neutral: "25–30%: around the US share",
    format: fmt.pct1,
  },
  {
    id: "hmda_dti_over_43",
    role: "burden",
    name: "High-DTI loans",
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
    title: "Share of 2025 home-purchase loans with combined loan-to-value above 90%",
    scale: "sequential",
    breaks: [40, 50, 60, 70, 80],
    tick: tick.pct,
    unit: "% of loans",
    format: fmt.pct1,
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
      { id: "cfpb_delinquency_90", name: "90+ days delinquent", format: fmt.pct1 },
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
    rows: [{ id: "hmda_cltv_over_90", layer: true }],
  },
  {
    role: "context", label: "Context",
    rows: [
      { id: "income", name: "Median household income", format: fmt.usd },
      { id: "hmda_rate", name: "Median mortgage rate (2025 loans)", format: fmt.rate },
      { id: "hmda_loan_amount", name: "Median loan amount", format: fmt.usd },
      { id: "hmda_loans", name: "Home-purchase loans (2025)", format: fmt.count },
      { id: "permits_per_1000_hh", name: "Units permitted per 1,000 households (2025)", format: fmt.per1000 },
    ],
  },
];

// Wording for per-county caveats recorded in meta.json -> flags.
const FLAG_TEXT = {
  low_reliability: "Low reliability: small survey sample",
  topcoded: "Lower bound: taxes top-coded at $10,000+",
  sd_floored: "Very stable baseline: SD floored at 0.2 pts, so this is conservative",
};

const METHODOLOGY_URL = "https://github.com/jackrz412/us-housing-map/blob/main/METHODOLOGY.md";
