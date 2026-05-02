"""Generate golden fixtures for `_select_tangent_solution`.

Run from the repo root:

    uv run python scripts/generate_select_tangent_solution_fixtures.py

Writes one JSON file per case under
`tests/golden/geometry/select_tangent_solution/`. The JSON shape is the
authoritative parity contract between the legacy Python implementation
in `src/dune_winder/uv_head_target_parts/geometry2d.py` and the new Rust
implementation in `dune_geometry::wire::select_tangent_solution`.

Each case captures:

- The two circles whose tangents are enumerated by
  `circle_pair_tangent_pairs`.
- The transfer-zone rectangle.
- Optional anchor- and wrapped-pin centers and tangent-side preferences
  (`"plus"` / `"minus"` per axis).
- The selected `(tangent_a, tangent_b, clipped_start, clipped_end)`
  tuple — or `null` plus an `error` field when no candidate clips into
  the transfer rectangle (the legacy raises `UvHeadTargetError`).

Cases are synthetic and chosen to cover: matching-only-anchor,
matching-only-wrapped, matching-both, no-match-with-tiebreaker, and
no-clip-error.
"""

from __future__ import annotations

import json
from pathlib import Path

from dune_winder.queued_motion.filleted_path import (
    WaypointCircle,
    circle_pair_tangent_pairs,
)
from dune_winder.uv_head_target_parts.geometry2d import _select_tangent_solution
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
    / "select_tangent_solution"
)


_CASES: list[dict] = [
    {
        "name": "internal_tangent_full_match_realistic_pin_pair",
        "notes": (
            "Two pins at realistic UV spacing; anchor wraps on -x/-y, "
            "wrapped on +x/+y — picks the lower-to-upper internal tangent "
            "(the only candidate satisfying both constraints)."
        ),
        "first_circle": {"cx": 100.0, "cy": 50.0, "r": 0.5},
        "second_circle": {"cx": 105.75, "cy": 50.0, "r": 0.5},
        "transfer_bounds": {
            "left": 95.0,
            "top": 60.0,
            "right": 115.0,
            "bottom": 40.0,
        },
        "anchor_pin_point": {"x": 100.0, "y": 50.0},
        "anchor_tangent_sides": ["minus", "minus"],
        "wrapped_pin_point": {"x": 105.75, "y": 50.0},
        "wrapped_tangent_sides": ["plus", "plus"],
    },
    {
        "name": "no_side_constraints_falls_back_to_outbound_y",
        "notes": (
            "Identical circles, no side constraints — every candidate ties "
            "on match score, so outbound.y descending is the tiebreaker."
        ),
        "first_circle": {"cx": 0.0, "cy": 0.0, "r": 1.0},
        "second_circle": {"cx": 5.0, "cy": 0.0, "r": 1.0},
        "transfer_bounds": {
            "left": -2.0,
            "top": 2.0,
            "right": 7.0,
            "bottom": -2.0,
        },
        "anchor_pin_point": None,
        "anchor_tangent_sides": None,
        "wrapped_pin_point": None,
        "wrapped_tangent_sides": None,
    },
    {
        "name": "wrapped_only_match_outranks_anchor_only",
        "notes": (
            "Constraints satisfiable on wrapped only — the rank key uses "
            "target_matches as the secondary ordering, so the wrapped-only "
            "match should win even if some other candidate has higher "
            "outbound.y."
        ),
        "first_circle": {"cx": 0.0, "cy": 0.0, "r": 1.0},
        "second_circle": {"cx": 5.0, "cy": 2.0, "r": 1.0},
        "transfer_bounds": {
            "left": -2.0,
            "top": 5.0,
            "right": 7.0,
            "bottom": -5.0,
        },
        # Anchor side intentionally infeasible (no candidate lands on the
        # +x/-y quadrant of the anchor circle for this geometry).
        "anchor_pin_point": {"x": 0.0, "y": 0.0},
        "anchor_tangent_sides": ["plus", "minus"],
        "wrapped_pin_point": {"x": 5.0, "y": 2.0},
        "wrapped_tangent_sides": ["minus", "plus"],
    },
    {
        "name": "diagonal_unequal_radii_with_full_match",
        "notes": (
            "Asymmetric radii, both pins constrained — exercises an "
            "unambiguous full-match winner."
        ),
        "first_circle": {"cx": 0.0, "cy": 0.0, "r": 1.5},
        "second_circle": {"cx": 4.0, "cy": 3.0, "r": 0.5},
        "transfer_bounds": {
            "left": -3.0,
            "top": 6.0,
            "right": 7.0,
            "bottom": -3.0,
        },
        "anchor_pin_point": {"x": 0.0, "y": 0.0},
        "anchor_tangent_sides": ["plus", "plus"],
        "wrapped_pin_point": {"x": 4.0, "y": 3.0},
        "wrapped_tangent_sides": ["minus", "plus"],
    },
    {
        "name": "no_candidate_clips_raises",
        "notes": (
            "Transfer bounds set well outside the candidate tangents — "
            "no candidate clips, legacy raises UvHeadTargetError."
        ),
        "first_circle": {"cx": 0.0, "cy": 0.0, "r": 1.0},
        "second_circle": {"cx": 5.0, "cy": 0.0, "r": 1.0},
        "transfer_bounds": {
            "left": 100.0,
            "top": 110.0,
            "right": 110.0,
            "bottom": 100.0,
        },
        "anchor_pin_point": None,
        "anchor_tangent_sides": None,
        "wrapped_pin_point": None,
        "wrapped_tangent_sides": None,
    },
]


def _build_case(case: dict) -> dict:
    first = WaypointCircle(
        waypoint_xy=(case["first_circle"]["cx"], case["first_circle"]["cy"]),
        center_xy=(case["first_circle"]["cx"], case["first_circle"]["cy"]),
        radius=case["first_circle"]["r"],
    )
    second = WaypointCircle(
        waypoint_xy=(case["second_circle"]["cx"], case["second_circle"]["cy"]),
        center_xy=(case["second_circle"]["cx"], case["second_circle"]["cy"]),
        radius=case["second_circle"]["r"],
    )
    raw_pairs = circle_pair_tangent_pairs(first, second)
    candidates = [
        (Point2D(first_xy[0], first_xy[1]), Point2D(second_xy[0], second_xy[1]))
        for first_xy, second_xy in raw_pairs
    ]
    bounds = RectBounds(
        left=case["transfer_bounds"]["left"],
        top=case["transfer_bounds"]["top"],
        right=case["transfer_bounds"]["right"],
        bottom=case["transfer_bounds"]["bottom"],
    )
    anchor_point = (
        Point2D(case["anchor_pin_point"]["x"], case["anchor_pin_point"]["y"])
        if case["anchor_pin_point"] is not None
        else None
    )
    anchor_sides = (
        tuple(case["anchor_tangent_sides"])
        if case["anchor_tangent_sides"] is not None
        else None
    )
    wrapped_point = (
        Point2D(case["wrapped_pin_point"]["x"], case["wrapped_pin_point"]["y"])
        if case["wrapped_pin_point"] is not None
        else None
    )
    wrapped_sides = (
        tuple(case["wrapped_tangent_sides"])
        if case["wrapped_tangent_sides"] is not None
        else None
    )

    error: str | None = None
    selected: dict | None = None
    try:
        ta, tb, cs, ce = _select_tangent_solution(
            candidates,
            bounds,
            anchor_pin_point=anchor_point,
            anchor_tangent_sides=anchor_sides,
            wrapped_pin_point=wrapped_point,
            wrapped_tangent_sides=wrapped_sides,
        )
    except UvHeadTargetError as exc:
        error = str(exc)
    else:
        selected = {
            "tangent_a": [ta.x, ta.y],
            "tangent_b": [tb.x, tb.y],
            "clipped_start": [cs.x, cs.y],
            "clipped_end": [ce.x, ce.y],
        }

    return {
        "name": case["name"],
        "notes": case["notes"],
        "first_circle": case["first_circle"],
        "second_circle": case["second_circle"],
        "transfer_bounds": case["transfer_bounds"],
        "anchor_pin_point": case["anchor_pin_point"],
        "anchor_tangent_sides": case["anchor_tangent_sides"],
        "wrapped_pin_point": case["wrapped_pin_point"],
        "wrapped_tangent_sides": case["wrapped_tangent_sides"],
        "candidates": [
            {
                "first_xy": [first_xy[0], first_xy[1]],
                "second_xy": [second_xy[0], second_xy[1]],
            }
            for first_xy, second_xy in raw_pairs
        ],
        "selected": selected,
        "error": error,
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
