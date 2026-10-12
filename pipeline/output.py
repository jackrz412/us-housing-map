"""Shared writers for data/processed/, so every layer is deterministic the same way."""
import datetime
import json

from geo import PROCESSED_DIR


def write_json(path, obj):
    # Sorted keys + fixed separators make the bytes deterministic, so re-running
    # on the same input produces an identical file (SPEC: idempotent pipeline).
    path.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n")


def write_layer(name, values):
    """Write data/processed/<name>.json. Returns True if its bytes changed."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = PROCESSED_DIR / f"{name}.json"
    before = out.read_bytes() if out.exists() else None
    write_json(out, values)
    changed = out.read_bytes() != before
    print(f"wrote {out.name} ({'changed' if changed else 'unchanged'})")
    return changed


def update_meta(entries, changed):
    """Merge {layer: entry} into meta.json.

    run_date is only bumped for layers whose data actually changed. Otherwise a
    no-op re-run would rewrite meta.json with today's date and break the
    "re-running produces identical outputs" rule.
    """
    meta_path = PROCESSED_DIR / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    today = datetime.date.today().isoformat()
    for layer, entry in entries.items():
        old = meta.get(layer, {})
        entry = dict(entry)
        entry["run_date"] = today if changed[layer] or "run_date" not in old else old["run_date"]
        meta[layer] = entry
    write_json(meta_path, meta)
