#!/usr/bin/env bash
# Assemble the deployable site in _site/: the contents of site/ plus
# data/processed/*.json under _site/data/. Used by the Pages workflow and for
# local preview, so both serve exactly the same files.
set -euo pipefail

cd "$(dirname "$0")/.."

rm -rf _site
mkdir -p _site/data
cp -R site/. _site/
cp data/processed/*.json _site/data/

echo "built _site/ ($(find _site -type f | wc -l | tr -d ' ') files)"
