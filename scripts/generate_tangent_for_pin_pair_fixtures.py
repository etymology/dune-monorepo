"""Generate golden fixtures for `tangent_for_pin_pair`.

Run from the repo root:

    uv run python scripts/generate_tangent_for_pin_pair_fixtures.py

Writes one JSON file per case under
`tests/golden/geometry/tangent_for_pin_pair/`. The JSON shape is the
authoritative parity contract that both the legacy Python `tangent_sides`
+ `circle_pair_tangent_pairs` pipeline and the new Rust analytic
`dune_geometry::wire::tangent_for_pin_pair` must match.

For each case the generator:

1. Looks up the wrap-side preferences for anchor and target via the legacy
   `dune_winder.uv_head_target_parts.pin_layout.tangent_sides`.
2. Enumerates the (up to four) tangent pairs with the legacy
   `dune_winder.queued_motion.filleted_path.circle_pair_tangent_pairs`.
3. Picks the unique candidate whose anchor-side normal matches the anchor
   wrap sides and whose target-side normal matches the target wrap sides.

If zero or more than one candidate matches, the case is rejected — a
properly chosen test geometry must yield exactly one match (this is the
whole reason the analytic solver exists).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from dune_winder.queued_motion.filleted_path import (
    WaypointCircle,
    circle_pair_tangent_pairs,
)
from dune_winder.uv_head_target_parts.pin_layout import tangent_sides


_OUTPUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "golden"
    / "geometry"
    / "tangent_for_pin_pair"
)

_AXIS_EPS = 1.0e-9


# Pin names in legacy Python are `{side}{number}` (e.g., "A100", "B1201") —
# the layer is passed alongside.
_CASES: list[dict] = [
    {
        "name": "ua_head_pair_canonical",
        "notes": "UA pins (n ≤ 1200), sa = (1, -1). AB direction in NE quadrant.",
        "layer": "U",
        "anchor": {"pin": "A100", "xy": [100.0, 50.0], "r": 0.5},
        "target": {"pin": "A101", "xy": [105.0, 51.0], "r": 0.5},
    },
    {
        "name": "ub_head_pair",
        "notes": "UB pins, sa = (1, 1). AB direction in SE quadrant.",
        "layer": "U",
        "anchor": {"pin": "B50", "xy": [10.0, 10.0], "r": 0.5},
        "target": {"pin": "B51", "xy": [15.0, 9.0], "r": 0.5},
    },
    {
        "name": "ua_past_n1200_pair",
        "notes": "UA pins (n > 1200), sa = (-1, 1). AB direction in NE quadrant.",
        "layer": "U",
        "anchor": {"pin": "A1300", "xy": [0.0, 0.0], "r": 0.5},
        "target": {"pin": "A1301", "xy": [5.0, 1.0], "r": 0.5},
    },
    {
        "name": "va_head_pair",
        "notes": "VA pins (head edge), sa = (1, 1). AB direction in SE quadrant.",
        "layer": "V",
        "anchor": {"pin": "A100", "xy": [0.0, 0.0], "r": 0.5},
        "target": {"pin": "A101", "xy": [5.0, -1.0], "r": 0.5},
    },
    {
        "name": "vb_head_pair",
        "notes": "VB pins (head edge), sa = (1, -1). AB direction in NE quadrant.",
        "layer": "V",
        "anchor": {"pin": "B100", "xy": [0.0, 0.0], "r": 0.5},
        "target": {"pin": "B101", "xy": [5.0, 1.0], "r": 0.5},
    },
    {
        "name": "ua_unequal_radii",
        "notes": (
            "Anchor at the standard 0.5 mm pin radius, target with extra "
            "clearance — exercises radius_sign × tangent_sign with r != 0."
        ),
        "layer": "U",
        "anchor": {"pin": "A200", "xy": [0.0, 0.0], "r": 0.5},
        "target": {"pin": "A201", "xy": [10.0, 2.0], "r": 0.6},
    },
]


def _sign_for_side(side: str) -> int:
    if side == "plus":
        return 1
    if side == "minus":
        return -1
    raise ValueError(f"unexpected tangent side {side!r}")


def _normal_signs_at(
    point_xy: tuple[float, float], center_xy: tuple[float, float], radius: float
) -> tuple[int, int]:
    nx = (point_xy[0] - center_xy[0]) / radius
    ny = (point_xy[1] - center_xy[1]) / radius
    return (
        1 if nx > _AXIS_EPS else -1 if nx < -_AXIS_EPS else 0,
        1 if ny > _AXIS_EPS else -1 if ny < -_AXIS_EPS else 0,
    )


def _build_case(case: dict) -> dict:
    layer = case["layer"]
    anchor_pin = case["anchor"]["pin"]
    target_pin = case["target"]["pin"]
    anchor_xy = tuple(case["anchor"]["xy"])
    target_xy = tuple(case["target"]["xy"])
    anchor_r = float(case["anchor"]["r"])
    target_r = float(case["target"]["r"])

    anchor_sides = tangent_sides(layer, anchor_pin)
    target_sides = tangent_sides(layer, target_pin)
    want_anchor = (_sign_for_side(anchor_sides[0]), _sign_for_side(anchor_sides[1]))
    want_target = (_sign_for_side(target_sides[0]), _sign_for_side(target_sides[1]))

    candidates = circle_pair_tangent_pairs(
        WaypointCircle(waypoint_xy=anchor_xy, center_xy=anchor_xy, radius=anchor_r),
        WaypointCircle(waypoint_xy=target_xy, center_xy=target_xy, radius=target_r),
    )

    matches: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for tangent_a, tangent_b in candidates:
        if (
            _normal_signs_at(tangent_a, anchor_xy, anchor_r) == want_anchor
            and _normal_signs_at(tangent_b, target_xy, target_r) == want_target
        ):
            matches.append((tangent_a, tangent_b))

    if len(matches) != 1:
        raise ValueError(
            f"{case['name']}: expected exactly 1 matching tangent, got {len(matches)} "
            f"(anchor sides {anchor_sides}, target sides {target_sides}, "
            f"candidates {candidates})"
        )
    tangent_a, tangent_b = matches[0]

    return {
        "name": case["name"],
        "notes": case["notes"],
        "layer": layer,
        "anchor": {
            "pin": anchor_pin,
            "xy": [anchor_xy[0], anchor_xy[1]],
            "r": anchor_r,
            "tangent_sides": list(anchor_sides),
        },
        "target": {
            "pin": target_pin,
            "xy": [target_xy[0], target_xy[1]],
            "r": target_r,
            "tangent_sides": list(target_sides),
        },
        "tangent_a": [tangent_a[0], tangent_a[1]],
        "tangent_b": [tangent_b[0], tangent_b[1]],
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
