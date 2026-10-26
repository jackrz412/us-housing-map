// Mortgage county map: layer switcher, choropleth, tooltip, county
// panel, keyboard navigation and table view. Layer definitions, breaks and
// colors live in layers.js.
//
// Pipeline: TopoJSON (shapes) + data/<file>.json ({fips: value}, or
// {fips: {field: value}} for the index files; layers.js) ->
// projection -> path generator -> one <path> per county, colored by a
// threshold scale that changes with the selected layer.

const MAP_URL = "geo/counties-10m.json";
// scripts/build_site.sh copies data/processed/ to ./data/ next to this page.
const DATA_DIR = "data/";

// Fixed drawing size. The SVG scales to its container through viewBox, so
// these are coordinate units, not screen pixels.
const WIDTH = 975;
const HEIGHT = 610;

// 50 states + DC only (DECISIONS 006). Territories have state FIPS above 56.
const inScope = (id) => +id.slice(0, 2) <= 56;

const LAYER_BY_ID = new Map(MAP_LAYERS.map((l) => [l.id, l]));
// Every map layer and panel row by id, with where its value comes from. A
// panel row marked `layer: true` is the map layer of the same id.
const SPECS = new Map(MAP_LAYERS.map((l) => [l.id, l]));
for (const row of PANEL.flatMap((s) => s.rows)) if (!SPECS.has(row.id)) SPECS.set(row.id, row);
// The file a value is read from (a pair layer reads its first member's file
// for meta.json: both index files share one period).
const fileOf = (id) => {
  const spec = SPECS.get(id);
  return spec?.pair ? fileOf(spec.pair[0]) : spec?.file ?? id;
};
// Every file the page needs: the map layers plus the panel's context metrics.
const DATA_FILES = [...new Set([...SPECS.values()].filter((s) => !s.pair).map((s) => fileOf(s.id)))];

Promise.all([
  d3.json(MAP_URL),
  d3.json(`${DATA_DIR}meta.json`),
  ...DATA_FILES.map((file) => d3.json(`${DATA_DIR}${file}.json`)),
])
  .then(([topo, meta, ...files]) => {
    const data = Object.fromEntries(DATA_FILES.map((file, i) => [file, files[i]]));
    init(topo, meta, data);
  })
  .catch((err) => {
    console.error(err);
    const msg = document.createElement("p");
    msg.className = "error";
    msg.textContent = "The map data couldn't be loaded.";
    document.getElementById("map").replaceChildren(msg);
  });

function init(topo, meta, data) {
  // --- TopoJSON -> GeoJSON ---------------------------------------------------
  // TopoJSON stores each border once, as a shared "arc", and polygons refer to
  // arcs by index. That's why the file is small. D3 draws GeoJSON, so
  // topojson.feature() rebuilds each county's polygon from its arcs.
  const counties = topojson.feature(topo, topo.objects.counties).features
    .filter((f) => inScope(f.id));
  const states = topojson.feature(topo, topo.objects.states).features
    .filter((f) => inScope(f.id));
  // The same counties still in TopoJSON form, for topojson.merge() (render()).
  const countyGeoms = topo.objects.counties.geometries.filter((g) => inScope(g.id));
  const stateName = new Map(states.map((s) => [s.id, s.properties.name]));
  const countyById = new Map(counties.map((f) => [f.id, f]));
  const placeName = (f) => `${f.properties.name}, ${stateName.get(f.id.slice(0, 2)) ?? ""}`;

  // topojson.mesh() returns only the arcs that pass the filter, as one line.
  // `a !== b` keeps arcs shared by two different shapes (interior borders)
  // and skips coastlines (where a === b).
  const countyBorders = topojson.mesh(topo, topo.objects.counties,
    (a, b) => a !== b && inScope(a.id) && inScope(b.id));
  const stateBorders = topojson.mesh(topo, topo.objects.states,
    (a, b) => a !== b && inScope(a.id) && inScope(b.id));

  // --- Projection --------------------------------------------------------------
  // A projection maps [longitude, latitude] to [x, y]. geoAlbersUsa is a
  // composite of three Albers conic equal-area projections: the lower 48,
  // plus Alaska and Hawaii scaled and moved into insets. Equal-area keeps each
  // county's on-screen size proportional to its real area, so no region looks
  // more important because the projection inflated it. fitExtent() picks the
  // scale and translation that fit all states inside the given box. The box
  // is inset by FIT_PAD on each side: with no inset the western Aleutians
  // land exactly on x = 0 and their outlines are cut off by the SVG edge.
  const FIT_PAD = 10;
  const projection = d3.geoAlbersUsa()
    .fitExtent([[FIT_PAD, FIT_PAD], [WIDTH - FIT_PAD, HEIGHT - FIT_PAD]],
      { type: "FeatureCollection", features: states });

  // --- Path generator ---------------------------------------------------------
  // geoPath(projection) turns a GeoJSON feature into an SVG path string. For
  // each vertex it calls the projection, adds points where a straight screen
  // line would misrepresent a curved edge (adaptive resampling), and clips
  // anything outside the projection's regions.
  const path = d3.geoPath(projection);

  // Projected centroid of each county, for arrow-key navigation (below).
  const centroid = new Map(counties.map((f) => [f.id, path.centroid(f)]));

  // --- Color scales -------------------------------------------------------------
  // One d3.scaleThreshold per map layer. A threshold scale takes explicit break
  // points: values below breaks[0] get color 0, values in [b0, b1) get color 1,
  // and so on, so N breaks -> N+1 colors. Breaks here are fixed benchmarks
  // (layers.js, DECISIONS 011), not quantiles of the data, so a color keeps
  // its meaning across counties, layers and data years.
  // The bivariate layer has no threshold scale: colorOf() picks its cell.
  const scales = new Map(MAP_LAYERS.filter((l) => l.scale !== "bivariate").map((l) => {
    const n = l.breaks.length + 1;
    const range = l.scale === "diverging" ? DIVERGING : WARM[n];
    if (!range || range.length !== n) throw new Error(`no ${n}-class palette for ${l.id}`);
    return [l.id, d3.scaleThreshold().domain(l.breaks).range(range)];
  }));

  const colorOf = (layer, v) => (layer.scale === "bivariate"
    ? BIVARIATE[3 * bivariateClass(v[1]) + bivariateClass(v[0])]
    : scales.get(layer.id)(v));
  const metaOf = (id) => meta[fileOf(id)];

  // Per-county caveats from meta.json, as {file: {flag: Set(fips)}}. A row
  // that reads one field of a file shows only the flags it lists (layers.js);
  // a pair layer shows its members' flags.
  const flags = Object.fromEntries(DATA_FILES.map((file) => [file,
    Object.fromEntries(Object.entries(meta[file]?.flags ?? {}).map(([k, v]) => [k, new Set(v)]))]));
  const flagsFor = (id, fips) => {
    const spec = SPECS.get(id) ?? {};
    if (spec.pair) return spec.pair.flatMap((p) => flagsFor(p, fips));
    const allowed = spec.flags ?? (spec.field ? [] : null);
    return Object.entries(flags[fileOf(id)] ?? {})
      .filter(([k, set]) => (!allowed || allowed.includes(k)) && set.has(fips))
      .map(([k]) => FLAG_TEXT[k] ?? k);  // may hold [[term]] markup
  };

  // A county's value for a layer or panel row: a number, [burden, equity]
  // for the pair layer, or null when the source doesn't publish it.
  const valueOf = (id, fips) => {
    const spec = SPECS.get(id) ?? {};
    if (spec.pair) {
      const vs = spec.pair.map((p) => valueOf(p, fips));
      return vs.includes(null) ? null : vs;
    }
    const v = data[fileOf(id)]?.[fips];
    return (spec.field ? v?.[spec.field] : v) ?? null;
  };
  // A component's x (value ÷ 2019 benchmark), from the same file.
  const xOf = (id, fips) => data[fileOf(id)]?.[fips]?.[SPECS.get(id).x] ?? null;

  // --- Page state ---------------------------------------------------------------
  const hash = new URLSearchParams(location.hash.slice(1));
  const state = {
    layer: LAYER_BY_ID.has(hash.get("layer")) ? hash.get("layer") : DEFAULT_LAYER,
    selected: countyById.has(hash.get("county")) ? hash.get("county") : null,
    focused: null,
    sort: { key: "value", dir: -1 },
  };
  const writeHash = () => {
    const p = new URLSearchParams({ layer: state.layer });
    if (state.selected) p.set("county", state.selected);
    history.replaceState(null, "", `#${p}`);
  };

  document.getElementById("methodology-link").href = METHODOLOGY_URL;

  // --- Layer switcher -------------------------------------------------------------
  // One radio group (name="layer"), visually split by role. Native radios give
  // keyboard support for free: Tab into the group, arrow keys to change layer.
  const switcher = document.getElementById("switcher");
  for (const role of ROLES) {
    const group = document.createElement("div");
    group.className = "role";
    const label = document.createElement("span");
    label.className = "role-label";
    label.textContent = role.label;
    const options = document.createElement("div");
    options.className = "role-options";
    for (const layer of MAP_LAYERS.filter((l) => l.role === role.id)) {
      const pill = document.createElement("label");
      pill.className = "pill";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "layer";
      input.value = layer.id;
      input.checked = layer.id === state.layer;
      input.setAttribute("aria-label", `${role.label}: ${layer.name}`);
      input.addEventListener("change", () => setLayer(layer.id));
      const text = document.createElement("span");
      text.textContent = layer.name;
      pill.append(input, text);
      options.append(pill);
    }
    group.append(label, options);
    switcher.append(group);
  }

  // --- SVG ----------------------------------------------------------------------
  const mapCard = document.getElementById("map-card");
  const svg = d3.select("#map").append("svg")
    .attr("class", "map")
    .attr("viewBox", [0, 0, WIDTH, HEIGHT])
    .attr("aria-label", "County map. Tab to enter, arrow keys to move between counties, Enter to open details.");

  // Diagonal hatch for "Data not available": a 0.75-wide stripe every 4 units.
  // The tile is 8x8 with two stripes rather than 4x4 with one, so the browser
  // repeats a quarter as many tiles to fill the map. (The legend swatch in
  // index.html has its own small copy.)
  const naHatch = svg.append("defs").append("pattern")
    .attr("id", "na-hatch")
    .attr("patternUnits", "userSpaceOnUse")
    .attr("width", 8).attr("height", 8)
    .attr("patternTransform", "rotate(45)")
    .call((p) => p.append("rect").attr("width", 8).attr("height", 8).style("fill", "var(--na-fill)"))
    .call((p) => p.selectAll(".stripe").data([0, 4]).join("rect")
      .attr("x", (x) => x).attr("width", 0.75).attr("height", 8)
      .style("fill", "var(--na-line)"));

  // --- Data join ----------------------------------------------------------------
  // selectAll(...).data(array, key) pairs each county feature with a <path>.
  // On first draw every county is in the "enter" set and .join("path") creates
  // one path per county. The key function (f => f.id) pairs by FIPS code, so
  // when a layer switch re-colors the paths, each path stays bound to the same
  // county. Switching layers doesn't rebuild the paths; it only re-runs the
  // fill (see render()), which is the cheap part.
  //
  // The *data* join (shapes <-> values) is the lookup data[layer][f.id]. FIPS
  // are strings in both files, so "01001" matches "01001". A county with null,
  // or no key at all, is left transparent so the hatch underneath shows.
  //
  // The hatch is one shape, not a fill on each county: every pattern fill is
  // painted separately, and delinquency alone has ~2,640 missing counties,
  // which made scrolling and zooming choppy. render() merges the missing
  // counties into one outline (naArea) per layer and hatches that once.
  //
  // Keyboard access uses a "roving tabindex": exactly one county path has
  // tabindex=0 (the one Tab lands on); the rest have -1, so Tab enters and
  // leaves the map in one step instead of visiting 3,144 counties.
  // Everything that pans and zooms lives in one group; d3.zoom moves it.
  const viewport = svg.append("g").attr("class", "viewport");

  const naArea = viewport.append("path").attr("class", "na-area");

  const countyPaths = viewport.append("g").attr("class", "counties")
    .selectAll("path")
    .data(counties, (f) => f.id)
    .join("path")
      .attr("d", path)
      .attr("role", "button")
      .attr("tabindex", -1);

  viewport.append("path").attr("class", "county-borders").attr("d", path(countyBorders));
  viewport.append("path").attr("class", "state-borders").attr("d", path(stateBorders));
  const selectedHalo = viewport.append("path").attr("class", "selected-outline-halo");
  const selectedOutline = viewport.append("path").attr("class", "selected-outline");
  const hoverOutline = viewport.append("path").attr("class", "hover-outline");

  // --- Zoom and pan -----------------------------------------------------------------
  // d3.zoom tracks a transform {k, x, y}: k is the scale factor, (x, y) the
  // translation. A point p in map coordinates is drawn at k·p + (x, y). On
  // every gesture d3 updates the transform and calls zoomed(), which writes it
  // onto the viewport group as transform="translate(x,y) scale(k)". The paths
  // themselves never change; only the group's transform does.
  //
  // Strokes are drawn in the group's coordinate system, so a scale of k would
  // also multiply every border's width by k (a 1px state line becomes 8px at
  // 8x). vector-effect: non-scaling-stroke (index.html CSS) tells the browser
  // to apply the transform to the geometry but not to the stroke width, so
  // borders and outlines stay the same thickness on screen at any zoom.
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const zoom = d3.zoom()
    .scaleExtent([1, 8])
    // extent = the viewport; translateExtent = the area the viewport may show.
    // Making them equal means you can't pan past the map's edges, and at 1x
    // there's nothing to pan.
    .extent([[0, 0], [WIDTH, HEIGHT]])
    .translateExtent([[0, 0], [WIDTH, HEIGHT]])
    // A mouse that moves more than 4px between down and up is a drag: d3
    // swallows the click that follows, so panning never selects a county.
    .clickDistance(4)
    // Which input starts a zoom gesture:
    // - wheel only with Ctrl/Cmd held (trackpad pinch sends ctrlKey too), so
    //   plain scrolling always scrolls the page;
    // - touch only with two or more fingers, so one finger scrolls the page;
    // - mouse with the primary button (not Ctrl-click, which is a right-click
    //   on macOS).
    .filter((event) => {
      if (event.type === "wheel") return event.ctrlKey || event.metaKey;
      if (event.type.startsWith("touch")) return event.touches.length >= 2;
      return !event.button && !event.ctrlKey;
    })
    // d3's default speeds up only for ctrlKey; treat Cmd the same.
    .wheelDelta((event) => -event.deltaY * (event.deltaMode === 1 ? 0.05 : event.deltaMode ? 1 : 0.002) * 10)
    .on("zoom", zoomed)
    .on("end", zoomEnded);

  svg.call(zoom)
    // Double-click would both select a county and zoom; keep it to selecting.
    .on("dblclick.zoom", null);

  function zoomed({ transform }) {
    viewport.attr("transform", transform);
    // A pointer tooltip would now point at the wrong place, so hide it; a
    // keyboard-focused county keeps its tooltip, re-anchored to where it moved.
    const focused = document.activeElement;
    if (focused?.closest?.(".counties")) showTipAtElement(d3.select(focused).datum());
    else hideTip();
  }

  // The hatch pattern is in the group's coordinates too, so it grows with the
  // zoom; scaling it by 1/k keeps it the same size on screen. This runs once
  // when a gesture ends, not on every frame: changing the pattern makes the
  // browser rebuild it and repaint the whole hatched area, which on delinquency
  // is most of the map. During a pinch the stripes scale with the map, then
  // snap back.
  function zoomEnded({ transform }) {
    naHatch.attr("patternTransform", `scale(${1 / transform.k}) rotate(45)`);
  }

  const animate = (sel) => (reduceMotion ? sel : sel.transition().duration(250));
  document.getElementById("zoom-in").addEventListener("click", () => animate(svg).call(zoom.scaleBy, 1.5));
  document.getElementById("zoom-out").addEventListener("click", () => animate(svg).call(zoom.scaleBy, 1 / 1.5));
  document.getElementById("zoom-reset").addEventListener("click", () => animate(svg).call(zoom.transform, d3.zoomIdentity));

  // When zoomed in, keep the keyboard-focused or searched-for county on
  // screen by panning to it (the scale stays the same).
  function ensureVisible(fips) {
    const t = d3.zoomTransform(svg.node());
    if (t.k === 1) return;
    const [x, y] = t.apply(centroid.get(fips));
    const margin = 40;
    if (x < margin || x > WIDTH - margin || y < margin || y > HEIGHT - margin) {
      animate(svg).call(zoom.translateTo, ...centroid.get(fips));
    }
  }

  const pathById = new Map();
  countyPaths.each(function (f) { pathById.set(f.id, this); });

  // Start the roving tabindex on the selected county, or a central one.
  setRoving(state.selected ?? "20109");

  function setRoving(fips) {
    if (state.focused && pathById.has(state.focused)) pathById.get(state.focused).setAttribute("tabindex", -1);
    state.focused = fips;
    pathById.get(fips)?.setAttribute("tabindex", 0);
  }

  // --- Tooltip ------------------------------------------------------------------
  const tip = document.getElementById("tooltip");
  // The tooltip's size is measured once each time its content changes, not on
  // every pointer move: reading a size right after moving an element forces
  // the browser to redo layout on the spot. Moves are batched to at most one
  // per frame with requestAnimationFrame.
  let tipOn = false;
  let tipSize = [0, 0];
  let tipAt = null;
  let tipFrame = 0;

  function showTip(f, x, y) {
    const layer = LAYER_BY_ID.get(state.layer);
    const v = valueOf(layer.id, f.id);
    const value = document.createElement("div");
    value.className = v == null ? "value na" : "value";
    value.textContent = v == null ? "Data not available" : layer.format(v);
    const where = document.createElement("div");
    where.className = "where";
    where.textContent = placeName(f);
    const parts = [value, where];
    if (v != null && layer.describe) {
      const kind = document.createElement("div");
      kind.className = "where";
      kind.textContent = layer.describe(v);
      parts.push(kind);
    }
    for (const text of v == null ? [] : flagsFor(layer.id, f.id)) {
      const flag = document.createElement("div");
      flag.className = "flag";
      flag.textContent = plainText(text);
      parts.push(flag);
    }
    tip.replaceChildren(...parts);
    tip.classList.add("on");
    tipOn = true;
    const { width, height } = tip.getBoundingClientRect();
    tipSize = [width, height];
    hoverOutline.attr("d", path(f));
    placeTip(x, y);
  }

  function placeTip(x, y) {
    tipAt = [x, y];
    if (!tipFrame) tipFrame = requestAnimationFrame(moveTip);
  }

  function moveTip() {
    tipFrame = 0;
    // Sit below-right of the point, flipped to stay inside the window.
    const [x, y] = tipAt;
    const [width, height] = tipSize;
    const pad = 14;
    let left = x + pad;
    let top = y + pad;
    if (left + width > window.innerWidth - 8) left = x - width - pad;
    if (top + height > window.innerHeight - 8) top = y - height - pad;
    // transform, not left/top: moving with a transform needs no layout.
    tip.style.transform = `translate(${Math.max(8, left)}px, ${Math.max(8, top)}px)`;
  }

  function hideTip() {
    // Called on every zoom frame; skip the DOM writes when already hidden.
    if (!tipOn) return;
    tipOn = false;
    tip.classList.remove("on");
    hoverOutline.attr("d", null);
  }

  // Keyboard focus has no pointer position, so anchor the tooltip to the
  // county's on-screen box.
  function showTipAtElement(f) {
    const r = pathById.get(f.id).getBoundingClientRect();
    showTip(f, r.left + r.width / 2, r.top + r.height / 2);
  }

  countyPaths
    .on("pointerenter", (event, f) => showTip(f, event.clientX, event.clientY))
    .on("pointermove", (event) => placeTip(event.clientX, event.clientY))
    .on("pointerleave", () => { if (document.activeElement?.closest?.(".counties") == null) hideTip(); })
    .on("click", (event, f) => { setRoving(f.id); select(f.id); showTip(f, event.clientX, event.clientY); })
    .on("focus", (event, f) => { setRoving(f.id); ensureVisible(f.id); showTipAtElement(f); })
    .on("blur", hideTip)
    .on("keydown", (event, f) => {
      const dir = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] }[event.key];
      if (dir) {
        event.preventDefault();
        const next = neighbourInDirection(f.id, dir);
        if (next) pathById.get(next).focus();
      } else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select(f.id);
      } else if (event.key === "Escape") {
        hideTip();
        select(null);
      }
    });

  // --- Arrow-key navigation -------------------------------------------------------
  // Spatial navigation: from the current county's centroid, look for counties
  // whose centroid lies roughly in the arrow's direction (within ±60° of it),
  // and pick the one that minimises distance along the arrow plus twice the
  // sideways offset. The penalty favours the county straight ahead over one
  // that is closer but off to the side.
  function neighbourInDirection(fips, [dx, dy]) {
    const [x0, y0] = centroid.get(fips);
    let best = null;
    let bestScore = Infinity;
    for (const [id, [x, y]] of centroid) {
      if (id === fips || Number.isNaN(x)) continue;
      const along = (x - x0) * dx + (y - y0) * dy;
      const across = Math.abs((x - x0) * dy - (y - y0) * dx);
      if (along <= 0 || across > along * 1.73) continue;
      const score = along + 2 * across;
      if (score < bestScore) { bestScore = score; best = id; }
    }
    return best;
  }

  // --- County search ---------------------------------------------------------------
  const search = document.getElementById("county-search");
  const byPlace = new Map(counties.map((f) => [placeName(f).toLowerCase(), f.id]));
  document.getElementById("county-list").replaceChildren(
    ...[...counties].sort((a, b) => d3.ascending(placeName(a), placeName(b))).map((f) => {
      const o = document.createElement("option");
      o.value = placeName(f);
      return o;
    }));
  search.addEventListener("change", () => {
    const fips = byPlace.get(search.value.trim().toLowerCase());
    if (fips) goToCounty(fips);
  });

  // Select a county and move keyboard focus to it on the map.
  function goToCounty(fips) {
    select(fips);
    setRoving(fips);
    ensureVisible(fips);
    const el = pathById.get(fips);
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.focus({ preventScroll: true });
  }

  // --- Panel --------------------------------------------------------------------
  const panel = document.getElementById("panel");

  function select(fips) {
    state.selected = fips;
    const f = fips ? countyById.get(fips) : null;
    selectedHalo.attr("d", f ? path(f) : null);
    selectedOutline.attr("d", f ? path(f) : null);
    renderPanel();
    writeHash();
  }

  function renderPanel() {
    // The panel is about to be rebuilt; don't leave a card for a removed term.
    if (termOpen && panel.contains(termOpen)) hideTermTip();
    const fips = state.selected;
    if (!fips) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "Select a county (click, tap, search or use the keyboard) to see all of its measures together.";
      panel.replaceChildren(empty);
      return;
    }
    const f = countyById.get(fips);
    const close = document.createElement("button");
    close.className = "panel-close";
    close.type = "button";
    close.textContent = "Close";
    close.addEventListener("click", () => {
      select(null);
      pathById.get(fips)?.focus();
    });
    const h2 = document.createElement("h2");
    h2.textContent = f.properties.name;
    const place = document.createElement("p");
    place.className = "place";
    place.textContent = `${stateName.get(fips.slice(0, 2))} · FIPS ${fips}`;
    const parts = [close, h2, place];

    for (const section of PANEL) {
      const h3 = document.createElement("h3");
      h3.textContent = section.label;
      const dl = document.createElement("dl");
      for (const row of section.rows) {
        const layer = row.layer ? LAYER_BY_ID.get(row.id) : null;
        const name = layer ? layer.panelName : row.name;
        // The pair layer's two numbers are the rows above it; it shows which
        // cell of the grid the county is in instead.
        const format = layer ? layer.describe ?? layer.format : row.format;
        const v = valueOf(row.id, fips);
        const x = row.x && v != null ? xOf(row.id, fips) : null;

        const div = document.createElement("div");
        div.className = `row${row.id === state.layer ? " active" : ""}`;
        const chip = document.createElement("span");
        chip.className = "chip";
        // Only map layers get a color chip; context metrics stay neutral.
        if (layer && v != null) {
          chip.classList.add("filled");
          chip.style.background = colorOf(layer, v);
        }
        const dt = document.createElement("dt");
        setTermText(dt, name);
        const dd = document.createElement("dd");
        // Components show their x as a glossary term, so "1.53×" explains itself.
        setTermText(dd, v == null ? "Data not available"
          : x == null ? format(v) : `${format(v)} · [[x|${fmt.ratio(x)}]]`);
        if (v == null) dd.className = "na";
        else if (layer?.describe) dd.className = "text";
        div.append(chip, dt, dd);
        for (const text of v == null ? [] : flagsFor(row.id, fips)) {
          const flag = document.createElement("span");
          flag.className = "flag";
          setTermText(flag, text);
          div.append(flag);
        }
        dl.append(div);
      }
      parts.push(h3, dl);
    }
    panel.replaceChildren(...parts);
  }

  // --- Legend ---------------------------------------------------------------------
  // The bivariate key's grid, built once: top row = high Equity.
  document.getElementById("bk-grid").replaceChildren(...[2, 1, 0].flatMap((j) => [0, 1, 2].map((i) => {
    const cell = document.createElement("span");
    cell.style.background = BIVARIATE[3 * j + i];
    return cell;
  })));

  function renderLegend(layer) {
    const bivariate = layer.scale === "bivariate";
    document.getElementById("ramp").hidden = bivariate;
    document.getElementById("bivariate-key").hidden = !bivariate;
    if (bivariate) {
      setTermText(document.getElementById("legend-unit"),
        markPeriods([layer.unit, metaOf(layer.id)?.legend_period].filter(Boolean).join(" · ")));
      return;
    }
    const scale = scales.get(layer.id);
    const colors = scale.range();
    const n = colors.length;
    const swatches = document.getElementById("swatches");
    swatches.style.gridTemplateColumns = `repeat(${n}, 1fr)`;
    swatches.replaceChildren(...colors.map((c) => {
      const s = document.createElement("span");
      s.style.background = c;
      return s;
    }));
    // Each break sits on the boundary between two swatches.
    document.getElementById("ticks").replaceChildren(...layer.breaks.map((b, i) => {
      const s = document.createElement("span");
      s.style.left = `${((i + 1) / n) * 100}%`;
      s.textContent = layer.tick(b);
      return s;
    }));
    // Diverging layers say what their midpoint is (layers.js `ends`: the
    // county's own baseline, or the US share); sequential layers just run low
    // to high.
    const [lo, hi] = (layer.ends ?? ["Lower", "Higher"]).map((t, i) => (i ? `${t} ▶` : `◀ ${t}`));
    const ends = document.getElementById("ends");
    ends.replaceChildren(...[lo, hi].map((t) => {
      const s = document.createElement("span");
      s.textContent = t;
      return s;
    }));
    // SPEC: every layer shows its data period in the legend.
    const bits = [layer.unit, metaOf(layer.id)?.legend_period];
    if (layer.neutral) bits.push(`grey = ${layer.neutral}`);
    setTermText(document.getElementById("legend-unit"), markPeriods(bits.filter(Boolean).join(" · ")));
  }

  // --- Glossary terms ----------------------------------------------------------------
  // Layer titles and legend captions mark terms as [[key|text]] (layers.js
  // GLOSSARY). Each becomes an inline role="button" span (a real <button> can't
  // wrap across lines) with a dotted underline that opens a small
  // definition: on hover or keyboard focus, and on tap/click (which keeps it
  // open until a tap elsewhere, Esc, or scrolling).
  const termTip = document.getElementById("term-tip");
  let termOpen = null;     // the button whose definition is showing
  let termPinned = false;  // opened by a click/tap rather than hover/focus

  function setTermText(el, text) {
    const parts = [];
    let last = 0;
    for (const m of text.matchAll(TERM_MARKUP)) {
      parts.push(text.slice(last, m.index));
      const btn = document.createElement("span");
      btn.className = "term";
      btn.setAttribute("role", "button");
      btn.tabIndex = 0;
      btn.dataset.term = m[1];
      btn.textContent = m[2];
      parts.push(btn);
      last = m.index + m[0].length;
    }
    parts.push(text.slice(last));
    el.replaceChildren(...parts);
  }

  function showTermTip(btn) {
    const entry = GLOSSARY[btn.dataset.term];
    if (!entry) return;
    if (termOpen !== btn) {
      termOpen?.removeAttribute("aria-describedby");
      const term = document.createElement("div");
      term.className = "tt-term";
      term.textContent = entry.term;
      const def = document.createElement("div");
      def.textContent = entry.def;
      const ex = document.createElement("div");
      ex.className = "tt-example";
      const label = document.createElement("span");
      label.textContent = "Example: ";
      ex.append(label, entry.example);
      termTip.replaceChildren(term, def, ex);
      termOpen = btn;
      btn.setAttribute("aria-describedby", "term-tip");
    }
    termTip.hidden = false;
    // Below the term, left-aligned with it; above it if there's no room
    // below; always inside the window.
    const r = btn.getBoundingClientRect();
    const { width, height } = termTip.getBoundingClientRect();
    const left = Math.min(Math.max(8, r.left), window.innerWidth - width - 8);
    let top = r.bottom + 6;
    if (top + height > window.innerHeight - 8) top = Math.max(8, r.top - height - 6);
    termTip.style.transform = `translate(${Math.max(8, left)}px, ${top}px)`;
  }

  function hideTermTip() {
    if (!termOpen) return;
    termOpen.removeAttribute("aria-describedby");
    termOpen = null;
    termPinned = false;
    termTip.hidden = true;
  }

  // Delegated, so it covers terms in text that's re-rendered on every layer
  // change. The card ignores the pointer (CSS), so it never blocks the term
  // or map under it.
  document.addEventListener("pointerover", (event) => {
    if (event.pointerType !== "mouse" || termPinned) return;
    const btn = event.target.closest?.(".term");
    if (btn) showTermTip(btn);
  });
  document.addEventListener("pointerout", (event) => {
    if (event.pointerType !== "mouse" || termPinned) return;
    if (event.target.closest?.(".term") && document.activeElement !== event.target.closest(".term")) hideTermTip();
  });
  document.addEventListener("focusin", (event) => {
    const btn = event.target.closest?.(".term");
    if (btn && !termPinned) showTermTip(btn);
  });
  document.addEventListener("focusout", (event) => {
    if (event.target.closest?.(".term") && !termPinned) hideTermTip();
  });
  function toggleTerm(btn) {
    if (termPinned && termOpen === btn) { hideTermTip(); return; }
    showTermTip(btn);
    termPinned = true;
  }
  document.addEventListener("click", (event) => {
    const btn = event.target.closest?.(".term");
    if (btn) toggleTerm(btn);
    else hideTermTip();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && termOpen) hideTermTip();
    // Enter and Space, as a native button would.
    const btn = event.target.closest?.(".term");
    if (btn && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      toggleTerm(btn);
    }
  });
  // position: fixed would leave it behind as the page, or the panel, scrolls.
  document.addEventListener("scroll", hideTermTip, { capture: true, passive: true });
  window.addEventListener("resize", hideTermTip);

  // --- Table view -------------------------------------------------------------------
  const tableView = document.getElementById("table-view");
  const tableFilter = document.getElementById("table-filter");
  tableView.addEventListener("toggle", () => { if (tableView.open) renderTable(); });
  tableFilter.addEventListener("input", renderTable);
  document.querySelectorAll("th button[data-sort]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.sort;
      state.sort = state.sort.key === key
        ? { key, dir: -state.sort.dir }
        : { key, dir: key === "value" ? -1 : 1 };
      renderTable();
    });
  });

  function renderTable() {
    if (!tableView.open) return;
    const layer = LAYER_BY_ID.get(state.layer);
    const q = tableFilter.value.trim().toLowerCase();
    let rows = counties.map((f) => {
      const value = valueOf(layer.id, f.id);
      return {
        fips: f.id,
        name: f.properties.name,
        state: stateName.get(f.id.slice(0, 2)),
        value,
        // What the Value column sorts by: the number, or for the pair layer
        // its combined class, then Burden (layers.js sortValue).
        sortValue: value == null || !layer.sortValue ? value : layer.sortValue(value),
      };
    });
    if (q) rows = rows.filter((r) => `${r.name}, ${r.state}`.toLowerCase().includes(q));
    const { key, dir } = state.sort;
    rows.sort((a, b) => {
      // Missing values always sort last, whichever direction.
      if (key === "value" && (a.value == null) !== (b.value == null)) return a.value == null ? 1 : -1;
      const k = key === "value" ? "sortValue" : key;
      return dir * d3.ascending(a[k], b[k]) || d3.ascending(a.name, b.name);
    });

    document.getElementById("value-header").textContent = plainText(layer.panelName);
    document.querySelectorAll("thead th").forEach((th) => {
      const k = th.querySelector("button")?.dataset.sort;
      th.setAttribute("aria-sort", k === key ? (dir > 0 ? "ascending" : "descending") : "none");
    });
    document.getElementById("table-caption").textContent =
      `${plainText(layer.title)}, ${metaOf(layer.id)?.legend_period ?? ""}, by county`;
    const withData = rows.filter((r) => r.value != null).length;
    document.getElementById("table-count").textContent =
      `${rows.length.toLocaleString("en-US")} counties shown, ${withData.toLocaleString("en-US")} with data`;

    const body = document.getElementById("table-body");
    body.replaceChildren(...rows.map((r) => {
      const tr = document.createElement("tr");
      const name = document.createElement("td");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = r.name;
      btn.addEventListener("click", () => goToCounty(r.fips));
      name.append(btn);
      const st = document.createElement("td");
      st.textContent = r.state;
      const val = document.createElement("td");
      val.className = r.value == null ? "num na" : "num";
      val.textContent = r.value == null ? "Data not available" : layer.format(r.value);
      const notes = document.createElement("td");
      notes.textContent = r.value == null ? ""
        : [layer.describe?.(r.value), ...flagsFor(layer.id, r.fips).map(plainText)].filter(Boolean).join("; ");
      tr.append(name, st, val, notes);
      return tr;
    }));
  }

  // --- Render a layer ---------------------------------------------------------------
  function setLayer(id) {
    state.layer = id;
    render();
    writeHash();
  }

  function render() {
    const layer = LAYER_BY_ID.get(state.layer);
    // Re-color the existing paths; the join from first draw still holds.
    // Missing counties are "transparent" rather than "none": a transparent
    // fill still counts as painted, so they keep hover, click and focus.
    countyPaths
      .style("fill", (f) => {
        const v = valueOf(layer.id, f.id);
        return v == null ? "transparent" : colorOf(layer, v);
      })
      .attr("aria-label", (f) => {
        const v = valueOf(layer.id, f.id);
        return `${placeName(f)}: ${v == null ? "Data not available" : layer.format(v)}`;
      });

    // topojson.merge() joins the missing counties into one multipolygon,
    // dropping the borders they share, so the hatch is a single shape.
    const missing = countyGeoms.filter((g) => valueOf(layer.id, g.id) == null);
    naArea.attr("d", missing.length ? path(topojson.merge(topo, missing)) : null);

    // Delinquency has data for only ~500 counties, so at full contrast the
    // hatch would dominate the map. A quieter hatch (index.html CSS, applied
    // to both the map and its legend swatch) lets the counties with data lead.
    mapCard.classList.toggle("na-quiet", layer.id === "cfpb_delinquency_z");

    setTermText(document.getElementById("layer-title"), layer.title);
    const ids = Object.keys(data[fileOf(layer.id)] ?? {});
    const withData = ids.filter((f) => valueOf(layer.id, f) != null).length;
    document.getElementById("layer-sub").textContent =
      `${metaOf(layer.id)?.legend_period ?? ""} · data for ${withData.toLocaleString("en-US")} of ${ids.length.toLocaleString("en-US")} counties`;
    renderLegend(layer);
    renderPanel();
    renderTable();
    hideTip();
    hideTermTip();
  }

  // Sources line, from meta.json. The index layers' period lists several sources
  // ("HMDA 2025 · ACS … · FIO 2022"), so split on " · " before dropping repeats.
  const periods = [...new Set(DATA_FILES.flatMap((file) =>
    (meta[file]?.legend_period ?? "").split(" · ")).filter(Boolean))];
  const processed = d3.max(DATA_FILES, (file) => meta[file]?.run_date);
  document.getElementById("sources").textContent =
    `Sources: ${periods.join("; ")} (CFPB Mortgage Performance Trends, Census ACS, FFIEC HMDA, Census Building Permits Survey, Treasury Federal Insurance Office). Processed ${processed}.`;

  render();
  if (state.selected) select(state.selected);
}
