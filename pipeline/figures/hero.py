"""Hero image for the portfolio's housing project page: the live map, Burden score layer.

A Playwright screenshot (Firefox) of the map card on the published site, about
1600px wide, saved as JPEG. Dev-only: needs `pip install -r requirements-dev.txt`
and `python -m playwright install firefox`; not part of the pipeline or CI.

Usage: .venv/bin/python pipeline/figures/hero.py [--out DIR ...] [--url URL]
Default output: reports/figures/hero-burden.jpg.
"""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "reports" / "figures"
URL = "https://jackrz412.github.io/us-housing-map/#layer=index_burden"
NAME = "hero-burden.jpg"

# The map card is ~1,050 CSS px wide at a 1,440px viewport; 1.5x pixel density
# gives an image about 1,600px wide that stays sharp on high-density screens.
VIEWPORT = {"width": 1440, "height": 1100}
SCALE = 1.5


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, action="append", help=f"output dir (default {DEFAULT_OUT})")
    parser.add_argument("--url", default=URL)
    args = parser.parse_args()
    outs = args.out or [DEFAULT_OUT]

    with sync_playwright() as p:
        browser = p.firefox.launch()
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=SCALE,
                                color_scheme="light", reduced_motion="reduce")
        page.goto(args.url, wait_until="networkidle")
        # Ready when every county is drawn and the Burden layer's title is up.
        page.wait_for_function("document.querySelectorAll('.counties path').length > 3000")
        page.wait_for_function("document.getElementById('layer-title').textContent.includes('Burden')")
        page.evaluate("document.fonts.ready")
        card = page.locator("#map-card")
        for out in outs:
            out.mkdir(parents=True, exist_ok=True)
            card.screenshot(path=str(out / NAME), type="jpeg", quality=85)
            print(f"wrote {out / NAME}")
        browser.close()


if __name__ == "__main__":
    main()
