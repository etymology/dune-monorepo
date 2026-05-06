"""Convert legacy per-layer ``{LAYER}_Calibration.json`` files into the new
snapshot-based ``pin_calibrations.json`` format introduced in Phase C of
the UV layer rewrite.

Legacy shape (one file per layer)::

    {
      "layer": "U",
      "zFront": 145, "zBack": 275,
      "offset": {"x": 0, "y": 0, "z": 0},
      "locations": {"A1": {"x": ..., "y": ..., "z": ...}, ...}
    }

New shape (single file across both layers, append-only snapshots)::

    {
      "machine_id": "...",
      "snapshots": [
        {
          "taken_at": "<mtime ISO 8601>",
          "calibration_camera_id": "<id>",
          "operator": null,
          "notes": "Imported from legacy U_Calibration.json",
          "pins": [
            {"pin": {"layer": "U", "side": "A", "number": 1},
             "xyz": {"x": ..., "y": ..., "z": ...}},
            ...
          ]
        }
      ]
    }

The script subtracts the top-level ``offset`` field from every pin's XYZ
so the new file holds raw camera-space coordinates with no offsets baked
in. Per the new spec, more elaborate offsets (camera wire offset, arm
correction) live in the separate machine-calibration file.

Usage::

    python scripts/convert_legacy_pin_calibration.py \
      --legacy-u config/APA/U_Calibration.json \
      --legacy-v config/APA/V_Calibration.json \
      --machine-id apa-stand-01 \
      --camera-id default \
      --out config/APA/pin_calibrations.json [--write]

Either ``--legacy-u`` or ``--legacy-v`` may be omitted. The script
imports each legacy file as one snapshot, timestamped at the file's
modification time, with a "Imported from legacy {LAYER}_Calibration.json"
note. Without ``--write`` the resulting JSON is printed to stdout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Iterator


def _legacy_pin_iter(
    layer: str, locations: dict[str, dict[str, float]]
) -> Iterator[dict]:
    """Yield {"pin": {layer, side, number}, "xyz": {x, y, z}} entries."""
    for raw_key, xyz in locations.items():
        side, number_str = _split_legacy_key(raw_key)
        if side is None:
            sys.stderr.write(
                f"warning: skipping unrecognised pin key {raw_key!r} in layer {layer}\n"
            )
            continue
        try:
            number = int(number_str)
        except ValueError:
            sys.stderr.write(
                f"warning: skipping pin key {raw_key!r}: number {number_str!r} is not an integer\n"
            )
            continue
        yield {
            "pin": {"layer": layer, "side": side, "number": number},
            "xyz": {"x": float(xyz["x"]), "y": float(xyz["y"]), "z": float(xyz["z"])},
        }


def _split_legacy_key(key: str) -> tuple[str | None, str]:
    """Return (side, number_str) for a legacy "A234" or canonical "UA234" key."""
    if not key:
        return None, ""
    if key[0] in ("U", "V"):
        if len(key) >= 3 and key[1] in ("A", "B"):
            return key[1], key[2:]
        return None, ""
    if key[0] in ("A", "B"):
        return key[0], key[1:]
    return None, ""


def _subtract_offset(
    xyz: dict[str, float], offset: dict[str, float]
) -> dict[str, float]:
    return {
        "x": xyz["x"] - offset["x"],
        "y": xyz["y"] - offset["y"],
        "z": xyz["z"] - offset["z"],
    }


def _legacy_to_snapshot(
    legacy_path: Path,
    legacy: dict,
    *,
    layer_hint: str | None,
    camera_id: str,
) -> dict:
    layer = (legacy.get("layer") or layer_hint or "").upper()
    if layer not in ("U", "V"):
        raise ValueError(
            f"{legacy_path}: cannot infer layer (got {legacy.get('layer')!r}); "
            f"pass --legacy-u / --legacy-v explicitly"
        )

    offset = legacy.get("offset") or {"x": 0.0, "y": 0.0, "z": 0.0}
    raw_locations = legacy.get("locations") or {}
    pins_iter = _legacy_pin_iter(layer, raw_locations)
    pins = []
    for entry in pins_iter:
        entry["xyz"] = _subtract_offset(entry["xyz"], offset)
        pins.append(entry)

    mtime_iso = (
        dt.datetime.fromtimestamp(legacy_path.stat().st_mtime, tz=dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    return {
        "taken_at": mtime_iso,
        "calibration_camera_id": camera_id,
        "operator": None,
        "notes": f"Imported from legacy {legacy_path.name}",
        "pins": pins,
    }


def convert(
    *,
    legacy_u: Path | None,
    legacy_v: Path | None,
    machine_id: str,
    camera_id: str,
) -> dict:
    snapshots: list[dict] = []
    for path, layer_hint in ((legacy_u, "U"), (legacy_v, "V")):
        if path is None:
            continue
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open("r", encoding="utf-8") as fh:
            legacy = json.load(fh)
        snapshots.append(
            _legacy_to_snapshot(
                path, legacy, layer_hint=layer_hint, camera_id=camera_id
            )
        )

    snapshots.sort(key=lambda s: s["taken_at"])
    return {"machine_id": machine_id, "snapshots": snapshots}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-u", type=Path, default=None)
    parser.add_argument("--legacy-v", type=Path, default=None)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument(
        "--camera-id",
        default="default",
        help="ID of the calibration camera that produced the legacy data.",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output path.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to --out (which must be set). Without --write, prints to stdout.",
    )
    args = parser.parse_args(argv)

    if args.legacy_u is None and args.legacy_v is None:
        parser.error("at least one of --legacy-u / --legacy-v is required")

    new_doc = convert(
        legacy_u=args.legacy_u,
        legacy_v=args.legacy_v,
        machine_id=args.machine_id,
        camera_id=args.camera_id,
    )
    text = json.dumps(new_doc, indent=2) + "\n"

    if args.write:
        if args.out is None:
            parser.error("--write requires --out")
        args.out.write_text(text, encoding="utf-8")
        sys.stderr.write(f"wrote {args.out}\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
