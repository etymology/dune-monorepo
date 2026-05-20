"""One-shot migration: enforce the natural-axis offset policy on existing data.

Rewrites the live V/U recipe files in place (off-axis components zeroed,
on-axis quantised to 0.1 mm, empty offsets dropped) and normalises the stored
template drafts that back the GCode Generation page.  Uses the same policy
functions as the generator so the result matches future regenerations.

Run from the repo root:  python scripts/migrate_offset_natural_axis.py
"""

from __future__ import annotations

import json
import os

from dune_winder.recipes.offset_axis_policy import (
    enforce_offset_dict,
    enforce_offset_natural_axis,
)
from dune_winder.recipes.v_template_gcode import OFFSET_NATURAL_AXIS as V_AXIS
from dune_winder.recipes.u_template_gcode import OFFSET_NATURAL_AXIS as U_AXIS

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GC_FILES = {
    "V": os.path.join(_ROOT, "dune_winder", "gc_files", "V-layer.gc"),
    "U": os.path.join(_ROOT, "dune_winder", "gc_files", "U-layer.gc"),
}
DRAFT_FILES = {
    "V": (
        os.path.join(_ROOT, "dune_winder", "cache", "TemplateRecipe", "V_Draft.json"),
        V_AXIS,
    ),
    "U": (
        os.path.join(_ROOT, "dune_winder", "cache", "TemplateRecipe", "U_Draft.json"),
        U_AXIS,
    ),
}


def _migrate_gc(layer, path):
    if not os.path.isfile(path):
        print(f"  [skip] {path} (missing)")
        return
    with open(path, "r", encoding="utf-8", newline="") as handle:
        content = handle.read()
    # The offset regex never spans newlines, so normalising the whole file as a
    # single string leaves every newline and unaffected character untouched.
    (normalized,) = enforce_offset_natural_axis([content], layer=layer)
    if normalized == content:
        print(f"  [ok]   {path} (already compliant)")
        return
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(normalized)
    print(f"  [done] {path}")


def _migrate_draft(path, axis_by_id):
    if not os.path.isfile(path):
        print(f"  [skip] {path} (missing)")
        return
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    offsets = data.get("offsets")
    if not isinstance(offsets, dict):
        print(f"  [skip] {path} (no offsets)")
        return
    changed = False
    for offset_id, value in list(offsets.items()):
        natural_axis = axis_by_id.get(offset_id, "x")
        normalized = enforce_offset_dict(value, natural_axis)
        if normalized != value:
            offsets[offset_id] = normalized
            changed = True
    if not changed:
        print(f"  [ok]   {path} (already compliant)")
        return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    os.replace(tmp, path)
    print(f"  [done] {path}")


def main():
    print("Recipe files:")
    for layer, path in GC_FILES.items():
        _migrate_gc(layer, path)
    print("Template drafts:")
    for _layer, (path, axis_by_id) in DRAFT_FILES.items():
        _migrate_draft(path, axis_by_id)


if __name__ == "__main__":
    main()
