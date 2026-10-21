"""Figures for the portfolio's housing project page, as SVG, from committed data.

Writes, for each figure, a wide version (for the 736px text column) and a
narrow one (for phones), so text stays at its design size on both:
  regions-{wide,narrow}.svg    Figure 1: owner cost burden vs thin-equity
                               lending by region (reports/regions/regions.json)
  secondary-{wide,narrow}.svg  Figure 2: partial rank correlations from the
                               secondary backtest (reports/backtest/secondary.json)

The SVGs are meant to be inlined in the page: colors and fonts are the site's
CSS tokens (var(--color-text), var(--font-sans), ...), resolved by the page's
tokens.css, so a token change restyles the figures. The page's own stylesheet
animates the marks (classes .fig-bar, .fig-dot, with --i as the stagger index).

Usage: .venv/bin/python pipeline/figures/figures.py [--out DIR ...]
Default output: reports/figures/. Pass --out more than once to also write
into the portfolio (src/assets/housing/).
"""
import argparse
import json
import textwrap
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGIONS = ROOT / "reports" / "regions" / "regions.json"
SECONDARY = ROOT / "reports" / "backtest" / "secondary.json"
DEFAULT_OUT = ROOT / "reports" / "figures"

# Widths in SVG units = CSS pixels at the size the page shows them.
WIDE, NARROW = 736, 358
FONT_SM = 13   # --text-sm: chart labels
FONT_MD = 15   # --text-md: panel titles
AXIS_TITLE_GAP = 38  # DESIGN.md: axisTitleMargin

REGION_ORDER = ["Pacific (CA, OR, WA)", "Mountain", "Northeast", "South Atlantic", "Midwest"]
REGION_LABEL = {"Pacific (CA, OR, WA)": "Pacific", "Mountain": "Mountain", "Northeast": "Northeast",
                "South Atlantic": "South Atlantic", "Midwest": "Midwest"}

# Plain-language row labels for Figure 2 (secondary.json keys).
SECONDARY_LABEL = {
    "burden": "Burden score",
    "pti": "New buyers' payment-to-income",
    "d": "Loans with debt above 43% of income",
    "r": "Applications denied for debt-to-income",
    "s": "Owners paying 30%+ of income on housing",
    "cltv": "Loans above 90% loan-to-value",
    "lower_income": "Lower median income",
}

STYLE = """
  .fig-text { font-family: var(--font-sans); fill: var(--color-text); }
  .fig-muted { font-family: var(--font-sans); fill: var(--color-muted); }
  .fig-title { font-family: var(--font-sans); font-weight: var(--weight-semibold); fill: var(--color-text); }
  .fig-grid { stroke: var(--color-border); stroke-width: 1; }
  .fig-zero { stroke: var(--color-muted); stroke-width: 1.5; }
  .fig-halo { paint-order: stroke; stroke: var(--color-bg); stroke-width: 4px; stroke-linejoin: round; }
"""


def svg(fig_id, width, height, title, desc, body, extra_style=""):
    """An inline-ready SVG: role=img with a title (the caption) and desc (the takeaway).

    fig_id makes the title/desc ids unique: the page inlines several SVGs.
    """
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" '
            f'aria-labelledby="{fig_id}-title {fig_id}-desc">\n'
            f'<title id="{fig_id}-title">{escape(title)}</title>\n'
            f'<desc id="{fig_id}-desc">{escape(desc)}</desc>\n'
            f'<style>{STYLE}{extra_style}</style>\n{body}\n</svg>\n')


def text(x, y, s, cls="fig-text", anchor="start", size=FONT_SM, weight=None, halo=False):
    w = f' font-weight="{weight}"' if weight else ""
    c = f"{cls} fig-halo" if halo else cls
    return (f'<text x="{x:.1f}" y="{y:.1f}" class="{c}" font-size="{size}" '
            f'text-anchor="{anchor}"{w}>{escape(s)}</text>')


def bar(x, y, w, h, color_var, i):
    """A horizontal bar from x, rounded 4px at the data end only (DESIGN.md)."""
    r = min(4, w / 2, h / 2)
    d = (f"M{x:.1f},{y:.1f} H{x + w - r:.1f} A{r},{r} 0 0 1 {x + w:.1f},{y + r:.1f} "
         f"V{y + h - r:.1f} A{r},{r} 0 0 1 {x + w - r:.1f},{y + h:.1f} H{x:.1f} Z")
    return f'<path d="{d}" class="fig-bar" style="fill: var({color_var}); --i: {i}"/>'


# --- Figure 1: regions ----------------------------------------------------------

def regions_data():
    r = json.loads(REGIONS.read_text())["regions"]
    rows = []
    for name in REGION_ORDER:
        m = r[name]["measures"]
        rows.append((REGION_LABEL[name], m["cost_burden"]["median"], m["cltv90"]["median"]))
    return rows


PANELS = [
    ("Mortgaged owners paying 30%+ of income", "--chart-payment"),
    ("2025 conventional loans above 90% loan-to-value", "--chart-equity"),
]
SCALE_MAX = 50  # percent; both panels share one 0-50% scale, so lengths compare


def pct(v):
    """Whole percent, rounding halves up like the page copy (38.5 -> 39%).

    Python's own formatting rounds halves to even (38.5 -> 38), which would
    disagree with the text.
    """
    return f"{Decimal(str(v)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)}%"


# Average glyph width of 15px semibold Plex Sans, for wrapping titles without a
# text-measuring dependency (slightly generous, so lines never overrun).
TITLE_CHAR_W = 8.4


def panel(x0, y0, width, title, color_var, values, labels_left, label_w, stagger0,
          title_x=None):
    """One bar panel: title (wrapped to fit), rows of bars with value labels, faint 10% gridlines."""
    row_h, bar_h = 34, 16
    tx = x0 + (label_w if labels_left else 0) if title_x is None else title_x
    lines = textwrap.wrap(title, int((x0 + width - tx) / TITLE_CHAR_W), break_on_hyphens=False)
    out = [text(tx, y0 + FONT_MD + i * 20, line, "fig-title", size=FONT_MD) for i, line in enumerate(lines)]
    top = y0 + FONT_MD + 20 * (len(lines) - 1) + 16
    bx = x0 + (label_w if labels_left else 0)
    bw = width - (label_w if labels_left else 0) - 44  # room for the value label
    scale = lambda v: bw * v / SCALE_MAX  # noqa: E731
    bottom = top + row_h * len(values)
    for t in range(0, SCALE_MAX + 1, 10):
        gx = bx + scale(t)
        out.append(f'<line x1="{gx:.1f}" y1="{top - 4}" x2="{gx:.1f}" y2="{bottom}" class="fig-grid"/>')
        if t % 20 == 0:
            out.append(text(gx, bottom + 16, f"{t}%", "fig-muted", "middle"))
    for i, (label, v) in enumerate(values):
        y = top + i * row_h
        if labels_left:
            out.append(text(x0 + label_w - 12, y + row_h / 2 + 4.5, label, anchor="end"))
        out.append(bar(bx, y + (row_h - bar_h) / 2, scale(v), bar_h, color_var, stagger0 + i))
        out.append(text(bx + scale(v) + 6, y + row_h / 2 + 4.5, pct(v), halo=True))
    return "\n".join(out), bottom + 16


def regions_svg(width):
    rows = regions_data()
    title = "Different regions are stretched in different ways."
    desc = ("Bar chart by region. The Pacific coast has the highest share of mortgaged owners "
            f"paying 30% or more of income ({pct(rows[0][1])}) and the lowest share of 2025 "
            f"conventional loans above 90% loan-to-value ({pct(rows[0][2])}). The Midwest is the "
            f"reverse: {pct(rows[4][1])} and {pct(rows[4][2])}. Mountain, Northeast and South "
            "Atlantic sit in between on both.")
    parts = []
    if width >= 600:
        # Side by side; region names once, at the left.
        label_w, gap = 112, 28
        pw = (width - label_w - gap) / 2
        a, ha = panel(0, 0, label_w + pw, PANELS[0][0], PANELS[0][1],
                      [(r[0], r[1]) for r in rows], True, label_w, 0)
        b, hb = panel(label_w + pw + gap, 0, pw, PANELS[1][0], PANELS[1][1],
                      [(r[0], r[2]) for r in rows], False, 0, len(rows))
        # The second panel has no labels of its own; it shares the first's rows.
        parts, height = [a, b], max(ha, hb) + 8
    else:
        # Stacked, each panel with its own region labels.
        label_w = 112
        a, ha = panel(0, 0, width, PANELS[0][0], PANELS[0][1], [(r[0], r[1]) for r in rows],
                      True, label_w, 0, title_x=0)
        b, hb = panel(0, ha + 24, width, PANELS[1][0], PANELS[1][1], [(r[0], r[2]) for r in rows],
                      True, label_w, len(rows), title_x=0)
        parts, height = [a, b], hb + 8
    return svg(f"regions-{'wide' if width >= 600 else 'narrow'}", width, round(height), title, desc,
               "\n".join(parts))


# --- Figure 2: secondary backtest ------------------------------------------------

def secondary_data():
    m = json.loads(SECONDARY.read_text())["measures"]
    rows = [(k, SECONDARY_LABEL[k], v["partial_rho"], *v["partial_rho_ci"]) for k, v in m.items()]
    return sorted(rows, key=lambda r: r[2], reverse=True)


X_MIN, X_MAX = -0.3, 0.5


def secondary_svg(width):
    rows = secondary_data()
    by = {r[0]: r for r in rows}
    title = ("Partial rank correlation with 2023–2025 delinquency, controlling for each county's "
             "2017–2019 level. Bars are 95% bootstrap intervals.")
    desc = (f"Dot plot of seven measures. Loans above 90% loan-to-value have the strongest positive "
            f"association ({by['cltv'][2]:+.2f}), followed by lower median income "
            f"({by['lower_income'][2]:+.2f}) and applications denied for debt-to-income "
            f"({by['r'][2]:+.2f}). The Burden score is about zero ({by['burden'][2]:+.2f}), and "
            f"new buyers' payment-to-income ({by['pti'][2]:+.2f}) and owners paying 30%+ of income "
            f"({by['s'][2]:+.2f}) are negative.")
    wide = width >= 600
    label_w = 300 if wide else 0
    row_h = 36 if wide else 52
    # Phones: labels sit above each row, so the plot spans the width, with room at the left
    # for the value label of the most negative row.
    pad_l = 0 if wide else 44
    pad_r = 16
    plot_x, plot_w = label_w + pad_l, width - label_w - pad_l - pad_r
    sx = lambda v: plot_x + plot_w * (v - X_MIN) / (X_MAX - X_MIN)  # noqa: E731
    top = 8
    bottom = top + row_h * len(rows)
    out = []
    # Faint gridlines, then the zero line on top of them. On phones they're drawn per row,
    # over the dot band only, so they never run through a row label.
    spans = ([(top - 4, bottom)] if wide else
             [(top + i * row_h + 20, top + i * row_h + row_h) for i in range(len(rows))])
    for y1, y2 in spans:
        for t in (-0.2, -0.1, 0.1, 0.2, 0.3, 0.4):
            out.append(f'<line x1="{sx(t):.1f}" y1="{y1}" x2="{sx(t):.1f}" y2="{y2}" class="fig-grid"/>')
        out.append(f'<line x1="{sx(0):.1f}" y1="{y1}" x2="{sx(0):.1f}" y2="{y2}" class="fig-zero"/>')
    for t in (-0.2, 0, 0.2, 0.4):
        out.append(text(sx(t), bottom + 16, f"{t:+.1f}" if t else "0", "fig-muted", "middle"))
    out.append(text(plot_x + plot_w / 2, bottom + AXIS_TITLE_GAP,
                    "Partial rank correlation (positive = higher measure, higher later delinquency)"
                    if wide else "Partial rank correlation", "fig-muted", "middle"))
    for i, (key, label, rho, lo, hi) in enumerate(rows):
        emph = key == "burden"
        color = "--color-accent" if emph else "--color-text"
        weight = "600" if emph else None
        if wide:
            cy = top + i * row_h + row_h / 2
            out.append(text(label_w - 16, cy + 4.5, label, anchor="end", weight=weight,
                            cls="fig-title" if emph else "fig-text"))
        else:
            ly = top + i * row_h + 14
            cy = ly + 18
            out.append(text(0, ly, label, weight=weight, cls="fig-title" if emph else "fig-text"))
        out.append(f'<line x1="{sx(lo):.1f}" y1="{cy:.1f}" x2="{sx(hi):.1f}" y2="{cy:.1f}" '
                   f'class="fig-ci" style="stroke: var({color}); --i: {i}" stroke-width="{3 if emph else 2}" '
                   'stroke-linecap="round"/>')
        out.append(f'<circle cx="{sx(rho):.1f}" cy="{cy:.1f}" r="8" class="fig-dot" '
                   f'style="fill: var({color}); stroke: var(--color-bg); --i: {i}" stroke-width="2"/>')
        # Value label past the interval's far end, on the side away from zero.
        if rho >= 0:
            out.append(text(sx(hi) + 8, cy + 4.5, f"{rho:+.2f}", weight=weight, halo=True))
        else:
            out.append(text(sx(lo) - 8, cy + 4.5, f"{rho:+.2f}", anchor="end", weight=weight, halo=True))
    height = bottom + AXIS_TITLE_GAP + 8
    return svg(f"secondary-{'wide' if wide else 'narrow'}", width, round(height), title, desc,
               "\n".join(out))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, action="append",
                        help=f"output directory (repeatable; default {DEFAULT_OUT})")
    args = parser.parse_args()
    outs = args.out or [DEFAULT_OUT]
    figures = {
        "regions-wide.svg": regions_svg(WIDE), "regions-narrow.svg": regions_svg(NARROW),
        "secondary-wide.svg": secondary_svg(WIDE), "secondary-narrow.svg": secondary_svg(NARROW),
    }
    for out in outs:
        out.mkdir(parents=True, exist_ok=True)
        for name, body in figures.items():
            (out / name).write_text(body)
        print(f"wrote {len(figures)} figures to {out}")


if __name__ == "__main__":
    main()
