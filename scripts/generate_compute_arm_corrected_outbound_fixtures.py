"""Generate golden fixtures for `_compute_arm_corrected_outbound`.

Run from the repo root:

    uv run python scripts/generate_compute_arm_corrected_outbound_fixtures.py

Writes one JSON file per case under
`tests/golden/geometry/compute_arm_corrected_outbound/`. The JSON shape
is the authoritative parity contract between the legacy Python
implementation in `src/dune_winder/uv_head_target_parts/geometry2d.py`
and the new Rust implementation in
`dune_geometry::wire::compute_arm_corrected_outbound`.

Each case captures the four arm-correction inputs (anchor pin, target
pin, two tangent points), the transfer-zone rectangle, the head
geometry (arm length, roller radius, roller gap), an optional
roller_arm_y_offsets tuple, and the legacy outputs (corrected_outbound,
corrected_head_center, roller_index, quadrant) — or the legacy error.
"""

from __future__ import annotations

import json
from pathlib import Path

from dune_winder.uv_head_target_parts.geometry2d import _compute_arm_corrected_outbound
from dune_winder.uv_head_target_parts.models import (
    Point2D,
    RectBounds,
    UvHeadTargetError,
)


_OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "golden"
    / "geometry"
    / "compute_arm_corrected_outbound"
)


_CASES: list[dict] = [
    {
        "name": "northeast_quadrant_diagonal_pins",
        "notes": (
            "Anchor up-right of target (anchor.x>target.x, anchor.y>target.y) "
            "→ NE quadrant, roller_index 3."
        ),
        "anchor_pin_point": {"x": 5.0, "y": 5.0},
        "target_pin_point": {"x": -5.0, "y": -5.0},
        "tangent_point_a": {"x": 0.0, "y": 0.0},
        "tangent_point_b": {"x": -1.0, "y": -1.0},
        "transfer_bounds": {
            "left": -100.0,
            "top": 100.0,
            "right": 100.0,
            "bottom": -100.0,
        },
        "head_arm_length": 10.0,
        "head_roller_radius": 1.0,
        "head_roller_gap": 2.0,
        "roller_arm_y_offsets": None,
    },
    {
        "name": "southwest_quadrant_diagonal_pins",
        "notes": (
            "Anchor down-left of target (anchor.x<target.x, anchor.y<target.y) "
            "→ SW quadrant, roller_index 0."
        ),
        "anchor_pin_point": {"x": -5.0, "y": -5.0},
        "target_pin_point": {"x": 5.0, "y": 5.0},
        "tangent_point_a": {"x": 0.0, "y": 0.0},
        "tangent_point_b": {"x": 1.0, "y": 1.0},
        "transfer_bounds": {
            "left": -100.0,
            "top": 100.0,
            "right": 100.0,
            "bottom": -100.0,
        },
        "head_arm_length": 10.0,
        "head_roller_radius": 1.0,
        "head_roller_gap": 2.0,
        "roller_arm_y_offsets": None,
    },
    {
        "name": "northwest_quadrant_with_custom_roller_y_offsets",
        "notes": (
            "Anchor up-left of target → NW quadrant, roller_index 1; "
            "non-default roller_arm_y_offsets exercise the override branch."
        ),
        "anchor_pin_point": {"x": -5.0, "y": 5.0},
        "target_pin_point": {"x": 5.0, "y": -5.0},
        "tangent_point_a": {"x": 0.0, "y": 0.0},
        "tangent_point_b": {"x": 1.0, "y": -1.0},
        "transfer_bounds": {
            "left": -100.0,
            "top": 100.0,
            "right": 100.0,
            "bottom": -100.0,
        },
        "head_arm_length": 12.5,
        "head_roller_radius": 1.0,
        "head_roller_gap": 2.0,
        "roller_arm_y_offsets": [1.9, 2.1, 2.05, 1.95],
    },
    {
        "name": "southeast_quadrant_realistic_uv_geometry",
        "notes": (
            "Realistic UV pin spacing: anchor at (100, 47), target at "
            "(98, 50). Anchor is down-right of target → SE quadrant, "
            "roller_index 2."
        ),
        "anchor_pin_point": {"x": 100.0, "y": 47.0},
        "target_pin_point": {"x": 98.0, "y": 50.0},
        "tangent_point_a": {"x": 99.95, "y": 47.5},
        "tangent_point_b": {"x": 98.05, "y": 49.5},
        "transfer_bounds": {
            "left": 50.0,
            "top": 200.0,
            "right": 200.0,
            "bottom": 0.0,
        },
        "head_arm_length": 35.0,
        "head_roller_radius": 1.5,
        "head_roller_gap": 3.0,
        "roller_arm_y_offsets": None,
    },
    {
        "name": "rejects_axis_aligned_pins_indeterminate",
        "notes": (
            "Anchor and target share x → indeterminate direction; legacy "
            "raises UvHeadTargetError."
        ),
        "anchor_pin_point": {"x": 0.0, "y": 0.0},
        "target_pin_point": {"x": 0.0, "y": 5.0},
        "tangent_point_a": {"x": 0.0, "y": 0.0},
        "tangent_point_b": {"x": 1.0, "y": 0.0},
        "transfer_bounds": {
            "left": -10.0,
            "top": 10.0,
            "right": 10.0,
            "bottom": -10.0,
        },
        "head_arm_length": 10.0,
        "head_roller_radius": 1.0,
        "head_roller_gap": 2.0,
        "roller_arm_y_offsets": None,
    },
]


def _build_case(case: dict) -> dict:
    bounds = RectBounds(
        left=case["transfer_bounds"]["left"],
        top=case["transfer_bounds"]["top"],
        right=case["transfer_bounds"]["right"],
        bottom=case["transfer_bounds"]["bottom"],
    )
    roller_offsets = (
        tuple(case["roller_arm_y_offsets"])
        if case["roller_arm_y_offsets"] is not None
        else None
    )
    error: str | None = None
    selected: dict | None = None
    try:
        outbound, head_center, roller_index, quadrant = _compute_arm_corrected_outbound(
            anchor_pin_point=Point2D(
                case["anchor_pin_point"]["x"], case["anchor_pin_point"]["y"]
            ),
            target_pin_point=Point2D(
                case["target_pin_point"]["x"], case["target_pin_point"]["y"]
            ),
            tangent_point_a=Point2D(
                case["tangent_point_a"]["x"], case["tangent_point_a"]["y"]
            ),
            tangent_point_b=Point2D(
                case["tangent_point_b"]["x"], case["tangent_point_b"]["y"]
            ),
            transfer_bounds=bounds,
            head_arm_length=case["head_arm_length"],
            head_roller_radius=case["head_roller_radius"],
            head_roller_gap=case["head_roller_gap"],
            roller_arm_y_offsets=roller_offsets,
        )
    except UvHeadTargetError as exc:
        error = str(exc)
    else:
        selected = {
            "corrected_outbound": [outbound.x, outbound.y],
            "corrected_head_center": [head_center.x, head_center.y],
            "roller_index": int(roller_index),
            "quadrant": str(quadrant),
        }

    return {**case, "selected": selected, "error": error}


def main() -> None:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for case in _CASES:
        fixture = _build_case(case)
        out_path = _OUTPUT_DIR / f"{case['name']}.json"
        out_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path.relative_to(_OUTPUT_DIR.parents[3])}")


if __name__ == "__main__":
    main()
