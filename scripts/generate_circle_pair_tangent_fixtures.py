"""Generate golden fixtures for `circle_pair_tangent_pairs`.

Run from the repo root:

    uv run python scripts/generate_circle_pair_tangent_fixtures.py

Writes one JSON file per case under
`tests/golden/geometry/circle_pair_tangent/`. The JSON shape is the
authoritative parity contract that both the legacy Python implementation
in `src/dune_winder/queued_motion/filleted_path.py` and the new Rust
implementation in `dune_geometry::wire::circle_pair_tangent_pairs` must
match.

Cases are synthetic and chosen to exercise the four sign combinations the
tangent solver enumerates plus a few near-edge configurations. Add a new
case by appending to `_CASES` and re-running this script.
"""

from __future__ import annotations

import json
from pathlib import Path

from dune_winder.queued_motion.filleted_path import (
    WaypointCircle,
    circle_pair_tangent_pairs,
)


_OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "golden"
    / "geometry"
    / "circle_pair_tangent"
)


_CASES: list[dict] = [
    {
        "name": "equal_radius_horizontal_separation",
        "notes": "Canonical external + internal tangents between two identical circles on the x-axis.",
        "first": {"cx": 0.0, "cy": 0.0, "r": 1.0},
        "second": {"cx": 5.0, "cy": 0.0, "r": 1.0},
    },
    {
        "name": "equal_radius_vertical_separation",
        "notes": "Same as horizontal case but rotated 90°.",
        "first": {"cx": 0.0, "cy": 0.0, "r": 1.0},
        "second": {"cx": 0.0, "cy": 5.0, "r": 1.0},
    },
    {
        "name": "unequal_radius_diagonal",
        "notes": "Asymmetric radii at a 45° offset — exercises asymmetric tangent points.",
        "first": {"cx": 0.0, "cy": 0.0, "r": 1.5},
        "second": {"cx": 4.0, "cy": 3.0, "r": 0.5},
    },
    {
        "name": "pin_pair_realistic_uv_geometry",
        "notes": "Two pins at realistic APA spacing (~5.75 mm) with the standard 0.5 mm pin radius.",
        "first": {"cx": 100.0, "cy": 50.0, "r": 0.5},
        "second": {"cx": 105.75, "cy": 50.0, "r": 0.5},
    },
    {
        "name": "pin_pair_with_target_clearance",
        "notes": "Anchor pin at 0.5 mm, target with extra clearance at 0.6 mm.",
        "first": {"cx": 0.0, "cy": 0.0, "r": 0.5},
        "second": {"cx": 10.0, "cy": 2.0, "r": 0.6},
    },
    {
        "name": "small_separation_internal_tangent_invalid",
        "notes": (
            "Centers separated by exactly 2*r — internal tangents collapse, only external "
            "tangents are valid; expect 2 tangent pairs."
        ),
        "first": {"cx": 0.0, "cy": 0.0, "r": 1.0},
        "second": {"cx": 2.0, "cy": 0.0, "r": 1.0},
    },
]


def _build_case(case: dict) -> dict:
    first = WaypointCircle(
        waypoint_xy=(case["first"]["cx"], case["first"]["cy"]),
        center_xy=(case["first"]["cx"], case["first"]["cy"]),
        radius=case["first"]["r"],
    )
    second = WaypointCircle(
        waypoint_xy=(case["second"]["cx"], case["second"]["cy"]),
        center_xy=(case["second"]["cx"], case["second"]["cy"]),
        radius=case["second"]["r"],
    )
    pairs = circle_pair_tangent_pairs(first, second)
    return {
        "name": case["name"],
        "notes": case["notes"],
        "first": case["first"],
        "second": case["second"],
        "tangent_pairs": [
            {
                "first_xy": [first_xy[0], first_xy[1]],
                "second_xy": [second_xy[0], second_xy[1]],
            }
            for first_xy, second_xy in pairs
        ],
    }


def main() -> None:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for case in _CASES:
        fixture = _build_case(case)
        out_path = _OUTPUT_DIR / f"{case['name']}.json"
        out_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path.relative_to(_OUTPUT_DIR.parents[3])}")


if __name__ == "__main__":
    main()
