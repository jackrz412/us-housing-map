#!/usr/bin/env bash
# Assemble the deployable site in _site/: the contents of site/, plus
# data/processed/*.json under _site/data/ and the backtest charts under
# _site/img/backtest/. Used by the Pages workflow and for
# local preview, so both serve exactly the same files.
set -euo pipefail

cd "$(dirname "$0")/.."

rm -rf _site
mkdir -p _site/data
cp -R site/. _site/
cp data/processed/*.json _site/data/
# Backtest charts for methodology.html, from the committed Phase 4b report.
mkdir -p _site/img/backtest
cp reports/backtest/*.png _site/img/backtest/

echo "built _site/ ($(find _site -type f | wc -l | tr -d ' ') files)"
