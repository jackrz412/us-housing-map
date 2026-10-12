"""The county universe: which FIPS codes the map can draw.

Every layer is filtered to this set, and validation checks against it, so the
data and the map can never disagree about what a "county" is.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_FILE = ROOT / "site" / "geo" / "counties-10m.json"
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

# 50 states + DC have state FIPS 01-56. Puerto Rico (72) and the other
# territories (60, 66, 69, 78) are all higher (DECISIONS 006).
MAX_STATE_FIPS = 56


def in_scope(fips):
    return int(fips[:2]) <= MAX_STATE_FIPS


def map_counties():
    """Return {fips: county name} for every in-scope county shape in the map."""
    topo = json.loads(MAP_FILE.read_text())
    return {
        g["id"]: g["properties"]["name"]
        for g in topo["objects"]["counties"]["geometries"]
        if in_scope(g["id"])
    }
