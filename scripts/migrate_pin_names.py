"""Rename legacy pin-name keys ("A234") to canonical form ("UA234") inside
JSON files persisted under config/, data/, calibration/, etc.

The legacy format keyed pin maps as ``{"A234": ...}``, with the layer
implied by the filename (e.g. ``U_Calibration.json``). The new canonical
form is ``{layer}{side}{number}`` like ``UA234``, layer-explicit so a single
combined file can hold both U and V.

Usage::

    python scripts/migrate_pin_names.py PATH_TO_FILE [--layer U|V] [--write]

Without ``--write`` the script prints a unified diff. With ``--write`` it
overwrites the file in-place. The layer hint is required when the source
JSON does not name the layer; if the JSON has a top-level ``"layer"`` field
or the filename matches ``{LAYER}_*.json``, the hint is optional.

This is a one-shot: it does NOT understand the snapshot-based
``pin_calibrations.json`` format introduced in Phase C — that file already
uses canonical keys.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any

LEGACY_PIN_KEY_RE = re.compile(r"^([AB])(\d+)$")
CANONICAL_PIN_KEY_RE = re.compile(r"^([UV])([AB])(\d+)$")
LAYER_FROM_FILENAME_RE = re.compile(r"^(?P<layer>[UV])_.+\.json$", re.IGNORECASE)


def infer_layer(path: Path, doc: dict[str, Any], explicit: str | None) -> str:
    if explicit is not None:
        return explicit.upper()
    layer = doc.get("layer")
    if isinstance(layer, str) and layer.upper() in {"U", "V"}:
        return layer.upper()
    m = LAYER_FROM_FILENAME_RE.match(path.name)
    if m:
        return m.group("layer").upper()
    raise ValueError(
        f"could not infer layer for {path}: pass --layer U|V "
        f"or ensure a top-level 'layer' field"
    )


def to_canonical(layer: str, key: str) -> str:
    """Return the canonical key, or the input if already canonical or unrelated."""
    if CANONICAL_PIN_KEY_RE.match(key):
        return key
    m = LEGACY_PIN_KEY_RE.match(key)
    if not m:
        return key
    return f"{layer}{m.group(1)}{m.group(2)}"


def rewrite_pin_keys(node: Any, layer: str) -> Any:
    """Recursively rewrite pin-shaped keys throughout the document.

    Touches dict keys only (values are walked but not transformed). A key is
    rewritten only when it matches the legacy ``[AB]\\d+`` pattern; canonical
    keys and unrelated strings are passed through unchanged.
    """
    if isinstance(node, dict):
        return {
            to_canonical(layer, k): rewrite_pin_keys(v, layer) for k, v in node.items()
        }
    if isinstance(node, list):
        return [rewrite_pin_keys(item, layer) for item in node]
    return node


def migrate_file(path: Path, layer_hint: str | None, write: bool) -> int:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        sys.stderr.write(f"{path}: top level is not a JSON object; skipping (no-op)\n")
        return 0
    layer = infer_layer(path, doc, layer_hint)
    rewritten = rewrite_pin_keys(doc, layer)
    if rewritten == doc:
        sys.stderr.write(f"{path}: no legacy pin keys found, nothing to do\n")
        return 0
    new_text = json.dumps(rewritten, indent=2) + "\n"
    if write:
        path.write_text(new_text, encoding="utf-8")
        sys.stderr.write(f"{path}: rewrote (layer {layer})\n")
    else:
        diff = difflib.unified_diff(
            raw.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path) + " (migrated)",
        )
        sys.stdout.writelines(diff)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--layer",
        choices=["U", "V", "u", "v"],
        default=None,
        help="Explicit layer hint; required when the file lacks a top-level 'layer' "
        "field and does not match the {LAYER}_*.json filename pattern.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply changes in-place (default: print unified diff).",
    )
    args = parser.parse_args(argv)

    changed_any = False
    for path in args.paths:
        if migrate_file(path, args.layer, args.write):
            changed_any = True

    return 0 if (args.write or not changed_any) else 1


if __name__ == "__main__":
    raise SystemExit(main())
