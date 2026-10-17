"""Charts for the Phase 4b backtest report, from reports/backtest/*.json.

  scatter_burden.png   each county's 2019 Burden score vs its delinquency change
  quintiles_burden.png mean delinquency change by Burden quintile
  rho_by_measure.png   Spearman rho with its 95% CI, every measure (main run)

Reads only backtest.py's outputs, so the charts can't change a number.
Needs matplotlib (requirements-report.txt), which the scheduled refresh doesn't.

Usage: .venv/bin/python pipeline/backtest_charts.py
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from backtest import MEASURES, OUT_DIR  # noqa: E402

# Light chart surface and one series hue (the dataviz reference palette).
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
SERIES = "#2a78d6"

LABELS = {
    "burden": "Burden score",
    "equity": "Equity score (= CLTV share)",
    "new_buyer": "NewBuyer half",
    "pti": "PTI (payment ÷ income)",
    "d": "D: DTI over 43%",
    "r": "R: denied for DTI",
    "s": "S: owners at 30%+ cost burden",
    "cltv": "CLTV over 90% (conventional)",
    "lower_income": "Lower median income",
}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 10, "text.color": TEXT, "axes.labelcolor": TEXT_2,
    "xtick.color": TEXT_2, "ytick.color": TEXT_2, "axes.edgecolor": GRID,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def fmt_ci(ci):
    return f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"


def subtitle(ax, text):
    ax.text(0, 1.02, text, transform=ax.transAxes, color=TEXT_2, fontsize=9, va="bottom")


def scatter(scores, main):
    pts = [(c["burden_2019"], c["outcome"]) for c in scores.values()
           if c["burden_2019"] is not None and c["outcome"] is not None]
    m = main["measures"]["burden"]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    ax.axhline(0, color=TEXT_2, linewidth=1, zorder=1)
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=22, color=SERIES, alpha=0.7,
               edgecolors=SURFACE, linewidths=1, zorder=2)
    ax.set_xlabel("Burden score, 2019 inputs (1.0 = 2019 national benchmark)")
    ax.set_ylabel("Change in 90+ day delinquency, pp\n(2023–2025 mean minus 2017–2019)")
    ax.set_title("Burden score (2019) vs later change in delinquency", pad=22)
    subtitle(ax, f"{m['n']} CFPB counties · Spearman ρ = {m['rho']:+.2f}, "
                 f"95% CI {fmt_ci(m['rho_ci'])}")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "scatter_burden.png", dpi=160)
    plt.close(fig)


def quintile_bars(main):
    m = main["measures"]["burden"]
    q = m["quintiles"]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    xs = range(1, 6)
    vals = [g["mean_change"] for g in q]
    ax.bar(xs, vals, width=0.45, color=SERIES, zorder=2)
    ax.axhline(0, color=TEXT_2, linewidth=1, zorder=3)
    span = max(abs(v) for v in vals) or 1
    for x, g in zip(xs, q):
        v = g["mean_change"]
        ax.text(x, v + (0.04 if v >= 0 else -0.04) * span, f"{v:+.2f}",
                ha="center", va="bottom" if v >= 0 else "top", color=TEXT, fontsize=9)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"Q{g['quintile']}\n{g['measure_min']:.2f}–{g['measure_max']:.2f}\n"
                        f"{g['share_rose']:.0%} rose" for g in q], color=TEXT_2)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Mean change in 90+ day delinquency, pp")
    ax.set_title("Delinquency change by Burden quintile (2019 inputs)", pad=22)
    subtitle(ax, f"Q1 = lowest Burden. Q5 − Q1 = {m['q5_minus_q1']:+.2f} pp, "
                 f"95% CI {fmt_ci(m['q5_minus_q1_ci'])}")
    ax.set_ylim(min(0, min(vals)) - 0.15 * span, max(0, max(vals)) + 0.2 * span)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "quintiles_burden.png", dpi=160)
    plt.close(fig)


def rho_by_measure(main):
    names = [n for n in MEASURES if "rho" in main["measures"][n]]
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(names) + 1.4))
    ax.axvline(0, color=TEXT_2, linewidth=1, zorder=1)
    for i, n in enumerate(reversed(names)):
        m = main["measures"][n]
        ax.plot(m["rho_ci"], [i, i], color=SERIES, linewidth=2, solid_capstyle="round", zorder=2)
        ax.scatter([m["rho"]], [i], s=40, color=SERIES, edgecolors=SURFACE, linewidths=2, zorder=3)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([f"{LABELS[n]}  (n={main['measures'][n]['n']})" for n in reversed(names)])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Spearman ρ with the change in delinquency\n(positive = higher measure, bigger rise)")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    # Title and subtitle on the figure's left edge: the long tick labels would
    # push an axes-anchored title off the right side.
    fig.text(0.02, 0.97, "Each measure's rank correlation with the outcome", fontsize=12,
             fontweight="bold", va="top", color=TEXT)
    fig.text(0.02, 0.925, "2019 inputs, 2023–2025 vs 2017–2019 · dots = ρ, lines = 95% "
             "bootstrap CI", fontsize=9, va="top", color=TEXT_2)
    fig.savefig(OUT_DIR / "rho_by_measure.png", dpi=160)
    plt.close(fig)


def main():
    results = json.loads((OUT_DIR / "results.json").read_text())
    scores = json.loads((OUT_DIR / "county_scores.json").read_text())
    main_run = results["runs"]["main"]
    scatter(scores, main_run)
    quintile_bars(main_run)
    rho_by_measure(main_run)
    print("wrote", ", ".join(p.name for p in sorted(OUT_DIR.glob("*.png"))))


if __name__ == "__main__":
    main()
