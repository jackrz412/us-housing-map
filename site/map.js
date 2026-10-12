// County choropleth of median household income.
//
// Pipeline: TopoJSON (shapes) + income.json ({fips: value}) -> projection ->
// path generator -> one <path> per county, colored by a threshold scale.

const MAP_URL = "geo/counties-10m.json";
// The page reads the pipeline's output directly. Locally, serve the repo root
// (python3 -m http.server) and open /site/.
const DATA_URL = "../data/processed/income.json";
const META_URL = "../data/processed/meta.json";

// Fixed drawing size. The SVG scales to its container through viewBox, so
// these are coordinate units, not screen pixels. 975x610 is the aspect ratio
// geoAlbersUsa was designed around.
const WIDTH = 975;
const HEIGHT = 610;

// 50 states + DC only (DECISIONS 006). Territories have state FIPS above 56.
const inScope = (id) => +id.slice(0, 2) <= 56;

const fmtMoney = d3.format("$,.0f");
const fmtK = (v) => `$${Math.round(v / 1000)}k`;

Promise.all([d3.json(MAP_URL), d3.json(DATA_URL), d3.json(META_URL)])
  .then(([topo, income, meta]) => draw(topo, income, meta.income))
  .catch((err) => {
    console.error(err);
    const msg = document.createElement("p");
    msg.className = "error";
    msg.textContent = "The map data couldn't be loaded.";
    document.getElementById("map").replaceChildren(msg);
  });

function draw(topo, income, meta) {
  document.getElementById("period").textContent =
    `Census American Community Survey, ${meta.period} 5-year estimates. Hover or tap a county for its value.`;
  // SPEC: every layer shows its data period in the legend.
  document.getElementById("legend-title").textContent =
    `${meta.label} · ${meta.legend_period}`;
  document.getElementById("source").textContent =
    `Source: ${meta.source}, ${meta.period}. Processed ${meta.run_date}.`;

  // --- TopoJSON -> GeoJSON ---------------------------------------------------
  // TopoJSON stores each border once, as a shared "arc", and polygons refer to
  // arcs by index. That's why the file is small. D3 draws GeoJSON, so
  // topojson.feature() rebuilds each county's polygon from its arcs.
  const counties = topojson.feature(topo, topo.objects.counties).features
    .filter((f) => inScope(f.id));
  const states = topojson.feature(topo, topo.objects.states).features
    .filter((f) => inScope(f.id));
  const stateName = new Map(states.map((s) => [s.id, s.properties.name]));

  // topojson.mesh() returns only the arcs that pass the filter, as one line.
  // `a !== b` keeps arcs shared by two different shapes, i.e. interior borders,
  // and skips coastlines (where a === b). Drawing borders as one mesh instead
  // of stroking every county avoids drawing each shared edge twice.
  const countyBorders = topojson.mesh(topo, topo.objects.counties,
    (a, b) => a !== b && inScope(a.id) && inScope(b.id));
  const stateBorders = topojson.mesh(topo, topo.objects.states,
    (a, b) => a !== b && inScope(a.id) && inScope(b.id));

  // --- Projection --------------------------------------------------------------
  // A projection maps [longitude, latitude] on the sphere to [x, y] on screen.
  // geoAlbersUsa is a *composite* projection: three Albers conic equal-area
  // projections stitched together, one for the lower 48 and one each for
  // Alaska and Hawaii, which are scaled and moved into insets bottom-left.
  // Equal-area matters for a choropleth: a county's size on screen stays
  // proportional to its real area, so no region looks more important just
  // because the projection inflated it (Mercator would blow up Alaska).
  // Points outside those three regions project to null, which is one reason
  // territories are filtered out above rather than left to vanish silently.
  // fitSize() picks the scale and translation that fit all states in the box.
  const projection = d3.geoAlbersUsa()
    .fitSize([WIDTH, HEIGHT], { type: "FeatureCollection", features: states });

  // --- Path generator ---------------------------------------------------------
  // geoPath(projection) is a function: give it a GeoJSON feature and it returns
  // an SVG path string ("M x,y L x,y ... Z"). For each vertex it calls the
  // projection, adds intermediate points where a straight screen line would
  // misrepresent the curved edge (adaptive resampling), and clips anything
  // outside the projection's regions.
  const path = d3.geoPath(projection);

  // --- Color scale ------------------------------------------------------------
  // A scale maps a data value (domain) to a visual value (range), here a color.
  // Income is right-skewed: most counties sit around $50k–80k and a few reach
  // $180k. A linear scale would spend most of its colors on those few rich
  // counties and wash everything else into the same pale blue.
  //
  // scaleThreshold instead takes explicit break points: values below
  // thresholds[0] get color 0, values in [t0, t1) get color 1, and so on.
  // N thresholds -> N+1 colors. The breaks are the 1/7, 2/7, ... 6/7 quantiles
  // of the data, so each of the 7 classes holds about the same number of
  // counties and the whole ramp gets used. They're rounded to the nearest
  // $1,000 so the legend reads cleanly. 7 classes is the readable limit:
  // past that, neighbouring shades are hard to tell apart.
  const values = Object.values(income).filter((v) => v != null).sort(d3.ascending);
  const CLASSES = 7;
  const thresholds = [...new Set(
    d3.range(1, CLASSES).map((i) => Math.round(d3.quantileSorted(values, i / CLASSES) / 1000) * 1000)
  )];
  // The range is CSS variables, not hex, so the ramp can flip in dark mode
  // without redrawing. Each color is a step of one hue, light -> dark.
  const color = d3.scaleThreshold()
    .domain(thresholds)
    .range(d3.range(thresholds.length + 1).map((i) => `var(--seq-${i})`));

  drawLegend(thresholds, color);

  // --- SVG ----------------------------------------------------------------------
  const svg = d3.select("#map").append("svg")
    .attr("class", "map")
    .attr("viewBox", [0, 0, WIDTH, HEIGHT])
    .attr("role", "img")
    .attr("aria-label", `Choropleth map of ${meta.label.toLowerCase()} by US county, ${meta.legend_period}.`);

  // Diagonal hatch for "Data not available". The legend swatch reuses it.
  svg.append("defs").append("pattern")
    .attr("id", "na-hatch")
    .attr("patternUnits", "userSpaceOnUse")
    .attr("width", 4).attr("height", 4)
    .attr("patternTransform", "rotate(45)")
    .call((p) => p.append("rect").attr("width", 4).attr("height", 4).style("fill", "var(--na-fill)"))
    .call((p) => p.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 4)
      .style("stroke", "var(--na-line)").style("stroke-width", 1.5));

  // --- Data join ----------------------------------------------------------------
  // selectAll(...).data(array) pairs each array element with a DOM element.
  // There are no <path>s yet, so every county is in the "enter" set, and
  // .join("path") creates one <path> per county. Each path keeps its feature
  // as its bound datum (d), which later callbacks receive.
  //
  // The key function (f => f.id) makes the pairing by FIPS code rather than by
  // position. It doesn't matter on first draw, but when Phase 2 swaps layers
  // and re-joins, each path stays matched to the same county.
  //
  // The *data* join (shapes <-> income values) is the lookup income[f.id].
  // FIPS are strings in both files, so "01001" matches "01001"; if either
  // side had been parsed as a number, Alabama's leading zero would be lost and
  // the lookup would miss. A county with null, or no key at all, gets the hatch.
  const valueOf = (f) => income[f.id] ?? null;
  const fillFor = (f) => {
    const v = valueOf(f);
    return v == null ? "url(#na-hatch)" : color(v);
  };

  const countyPaths = svg.append("g").attr("class", "counties")
    .selectAll("path")
    .data(counties, (f) => f.id)
    .join("path")
      .attr("d", path)
      // style(), not attr(): the fill attribute doesn't resolve var(--seq-n).
      .style("fill", fillFor);

  svg.append("path").attr("class", "county-borders").attr("d", path(countyBorders));
  svg.append("path").attr("class", "state-borders").attr("d", path(stateBorders));
  const outline = svg.append("path").attr("class", "hover-outline");

  // --- Tooltip ------------------------------------------------------------------
  const tip = document.getElementById("tooltip");

  function show(event, f) {
    const v = valueOf(f);
    const value = document.createElement("div");
    value.className = v == null ? "value na" : "value";
    value.textContent = v == null ? "Data not available" : fmtMoney(v);
    const place = document.createElement("div");
    place.className = "place";
    place.textContent = `${f.properties.name}, ${stateName.get(f.id.slice(0, 2)) ?? ""}`;
    tip.replaceChildren(value, place);
    tip.classList.add("on");
    outline.attr("d", path(f));
    move(event);
  }

  function move(event) {
    // Sit below-right of the pointer, flipped to stay inside the window.
    const pad = 14;
    const { width, height } = tip.getBoundingClientRect();
    let x = event.clientX + pad;
    let y = event.clientY + pad;
    if (x + width > window.innerWidth - 8) x = event.clientX - width - pad;
    if (y + height > window.innerHeight - 8) y = event.clientY - height - pad;
    tip.style.left = `${Math.max(8, x)}px`;
    tip.style.top = `${Math.max(8, y)}px`;
  }

  function hide() {
    tip.classList.remove("on");
    outline.attr("d", null);
  }

  countyPaths
    .on("pointerenter", show)
    .on("pointermove", move)
    .on("pointerleave", hide)
    // Touch has no hover, so a tap shows the tooltip.
    .on("pointerdown", show);
  // Tapping off the map hides it again on touch screens.
  document.addEventListener("pointerdown", (e) => {
    if (!e.target.closest(".counties")) hide();
  });
}

function drawLegend(thresholds, color) {
  // One swatch per class, in scale order.
  const swatches = document.getElementById("swatches");
  swatches.replaceChildren(...color.range().map((c) => {
    const s = document.createElement("span");
    s.style.background = c;
    return s;
  }));
  // Each threshold sits on the boundary between two swatches.
  const n = color.range().length;
  const ticks = document.getElementById("ticks");
  ticks.replaceChildren(...thresholds.map((t, i) => {
    const s = document.createElement("span");
    s.style.left = `${((i + 1) / n) * 100}%`;
    s.textContent = fmtK(t);
    return s;
  }));
}
