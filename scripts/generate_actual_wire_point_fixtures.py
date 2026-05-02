"""Generate golden fixtures for `_actual_wire_point_from_machine_target`.

Run from the repo root:

    uv run python scripts/generate_actual_wire_point_fixtures.py

Writes one JSON file per case under
`tests/golden/geometry/actual_wire_point/`. The JSON shape is the
authoritative parity contract between the legacy Python implementation
in `src/dune_winder/uv_head_target_parts/anchor_to_target.py` and the
new Rust implementation in
`dune_geometry::wire::actual_wire_point_from_machine_target`.

Cases exercise:
- The two early returns (length_xz collapse and second-pass collapse).
- The four sign branches on delta_x / delta_y.
- A realistic UV configuration with non-zero head_roller_gap.
"""

from __future__ import annotations

import json
from pathlib import Path

from dune_winder.uv_head_target_parts.anchor_to_target import (
    _actual_wire_point_from_machine_target,
)
from dune_winder.uv_head_target_parts.models import Point2D


_OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "golden"
    / "geometry"
    / "actual_wire_point"
)


_CASES: list[dict] = [
    {
        "name": "anchor_directly_below_head_collapses_to_input",
        "notes": (
            "anchor_xy == final_head_xy and head_z == anchor_z → length_xz "
            "is 0, function short-circuits and returns final_head_xy."
        ),
        "final_head_xy": {"x": 10.0, "y": 5.0},
        "compensated_anchor_xy": {"x": 10.0, "y": 99.0},
        "anchor_z": 7.0,
        "head_z": 7.0,
        "head_arm_length": 10.0,
        "head_roller_radius": 1.0,
        "head_roller_gap": 2.0,
    },
    {
        "name": "positive_delta_x_positive_delta_z_no_y",
        "notes": "Head right of and above anchor in xz; y aligned.",
        "final_head_xy": {"x": 10.0, "y": 0.0},
        "compensated_anchor_xy": {"x": 0.0, "y": 0.0},
        "anchor_z": 0.0,
        "head_z": 5.0,
        "head_arm_length": 10.0,
        "head_roller_radius": 1.0,
        "head_roller_gap": 2.0,
    },
    {
        "name": "negative_delta_x_with_positive_delta_y",
        "notes": "Head left of anchor in x, above in y → roller offset signs flip.",
        "final_head_xy": {"x": -10.0, "y": 4.0},
        "compensated_anchor_xy": {"x": 0.0, "y": 0.0},
        "anchor_z": 0.0,
        "head_z": 5.0,
        "head_arm_length": 10.0,
        "head_roller_radius": 1.5,
        "head_roller_gap": 3.0,
    },
    {
        "name": "negative_delta_y_realistic_uv_geometry",
        "notes": "Realistic UV pose with negative delta_y; exercises full math.",
        "final_head_xy": {"x": 100.0, "y": 50.0},
        "compensated_anchor_xy": {"x": 95.0, "y": 53.0},
        "anchor_z": 145.0,
        "head_z": 150.0,
        "head_arm_length": 35.0,
        "head_roller_radius": 1.5,
        "head_roller_gap": 3.0,
    },
    {
        "name": "second_pass_length_collapse_returns_intermediate_xy",
        "notes": (
            "After the first pass, anchor and intermediate point coincide in "
            "xz with the recomputed head pose → second-pass length_xz is 0 "
            "and function returns the intermediate (x, y)."
        ),
        # Choose head_arm_length so x = final_head_xy.x - delta_x*head_ratio
        # equals compensated_anchor_xy.x and z equals anchor_z. With delta_x=
        # delta_z and head_ratio=length_xz/length_xz=1 the intermediate
        # collapses onto the anchor.
        "final_head_xy": {"x": 10.0, "y": 0.0},
        "compensated_anchor_xy": {"x": 0.0, "y": 0.0},
        "anchor_z": 0.0,
        "head_z": 10.0,
        "head_arm_length": 14.142135623730951,  # sqrt(2) * 10 → ratio = 1.0
        "head_roller_radius": 1.0,
        "head_roller_gap": 2.0,
    },
]


def _build_case(case: dict) -> dict:
    final_head = Point2D(case["final_head_xy"]["x"], case["final_head_xy"]["y"])
    anchor_xy = Point2D(
        case["compensated_anchor_xy"]["x"], case["compensated_anchor_xy"]["y"]
    )
    point = _actual_wire_point_from_machine_target(
        final_head_xy=final_head,
        compensated_anchor_xy=anchor_xy,
        anchor_z=case["anchor_z"],
        head_z=case["head_z"],
        head_arm_length=case["head_arm_length"],
        head_roller_radius=case["head_roller_radius"],
        head_roller_gap=case["head_roller_gap"],
    )
    return {**case, "wire_point": [point.x, point.y]}


def main() -> None:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for case in _CASES:
        fixture = _build_case(case)
        out_path = _OUTPUT_DIR / f"{case['name']}.json"
        out_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path.relative_to(_OUTPUT_DIR.parents[3])}")


if __name__ == "__main__":
    main()
