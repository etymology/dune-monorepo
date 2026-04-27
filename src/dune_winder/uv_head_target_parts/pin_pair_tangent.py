from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .calibration import (
    _load_layer_calibration,
    _load_machine_calibration,
    _wire_space_pin,
)
from .geometry2d import (
    _arm_correction_head_shift_signs,
    _arm_correction_tangent_y_side,
    _roller_index_for_head_shift_signs,
    _select_tangent_solution,
    _sign_with_epsilon,
    _tangent_candidates_for_pin_pair,
)
from .models import Point2D, RectBounds, UvHeadTargetError
from .pin_layout import _normalize_layer, _normalize_pin_name, tangent_sides


@dataclass(frozen=True)
class PinPairTangentGeometry:
    """Minimal tangent-line geometry needed to back-solve a roller y-offset."""

    tangent_point_a: Point2D
    tangent_point_b: Point2D
    unit_direction: Point2D
    normal: Point2D
    roller_index: int
    pin_a_point: Point2D
    pin_b_point: Point2D


@lru_cache(maxsize=256)
def _cached_compute_pin_pair_tangent_geometry(
    layer: str,
    pin_a: str,
    pin_b: str,
    machine_calibration_path: str | None,
    layer_calibration_path: str | None,
) -> PinPairTangentGeometry:
    """Cached version with hashable arguments."""
    normalized_layer = _normalize_layer(layer)
    pin_a_name = _normalize_pin_name(pin_a, "Pin A")
    pin_b_name = _normalize_pin_name(pin_b, "Pin B")
    if pin_a_name == pin_b_name:
        raise UvHeadTargetError("Pin A and Pin B must be different pins.")

    machine_cal = _load_machine_calibration(machine_calibration_path)
    layer_cal = _load_layer_calibration(normalized_layer, layer_calibration_path)

    pin_a_loc = _wire_space_pin(layer_cal, pin_a_name)
    pin_b_loc = _wire_space_pin(layer_cal, pin_b_name)
    pin_a_pt = Point2D(float(pin_a_loc.x), float(pin_a_loc.y))
    pin_b_pt = Point2D(float(pin_b_loc.x), float(pin_b_loc.y))

    head_shift_signs = _arm_correction_head_shift_signs(
        anchor_pin_point=pin_a_pt,
        target_pin_point=pin_b_pt,
    )
    if head_shift_signs is None:
        raise UvHeadTargetError(
            f"Cannot determine roller: pins {pin_a_name} and {pin_b_name} share an x or y coordinate."
        )
    sign_x, sign_y = head_shift_signs
    roller_index = _roller_index_for_head_shift_signs(sign_x, sign_y)

    tangent_y_side = _arm_correction_tangent_y_side(
        anchor_pin_point=pin_a_pt,
        target_pin_point=pin_b_pt,
    )
    if tangent_y_side is None:
        raise UvHeadTargetError(
            f"Cannot determine wire side: pins {pin_a_name} and {pin_b_name} have the same y coordinate."
        )

    pin_radius = float(machine_cal.pinDiameter) / 2.0
    transfer_bounds = RectBounds(
        left=float(machine_cal.transferLeft),
        top=float(machine_cal.transferTop),
        right=float(machine_cal.transferRight),
        bottom=float(machine_cal.transferBottom),
    )
    anchor_tangent_sides = tangent_sides(normalized_layer, pin_a_name)
    wrapped_tangent_sides = tangent_sides(normalized_layer, pin_b_name)

    candidates = _tangent_candidates_for_pin_pair(pin_a_pt, pin_b_pt, pin_radius)
    tangent_a, tangent_b, _, _ = _select_tangent_solution(
        candidates,
        transfer_bounds,
        anchor_pin_point=pin_a_pt,
        anchor_tangent_sides=anchor_tangent_sides,
        wrapped_pin_point=pin_b_pt,
        wrapped_tangent_sides=wrapped_tangent_sides,
    )

    direction = Point2D(tangent_b.x - tangent_a.x, tangent_b.y - tangent_a.y)
    dir_len = (direction.x**2 + direction.y**2) ** 0.5
    if dir_len < 1e-9:
        raise UvHeadTargetError("Selected tangent line is degenerate.")
    unit_direction = Point2D(direction.x / dir_len, direction.y / dir_len)

    normal_candidates = (
        Point2D(-unit_direction.y, unit_direction.x),
        Point2D(unit_direction.y, -unit_direction.x),
    )
    matching_normals = [
        n for n in normal_candidates if _sign_with_epsilon(n.y) == tangent_y_side
    ]
    if len(matching_normals) != 1:
        raise UvHeadTargetError(
            "Could not select a unique normal for the tangent line."
        )
    normal = matching_normals[0]

    return PinPairTangentGeometry(
        tangent_point_a=tangent_a,
        tangent_point_b=tangent_b,
        unit_direction=unit_direction,
        normal=normal,
        roller_index=roller_index,
        pin_a_point=pin_a_pt,
        pin_b_point=pin_b_pt,
    )


def compute_pin_pair_tangent_geometry(
    *,
    layer: str,
    pin_a: str,
    pin_b: str,
    machine_calibration_path: str | None = None,
    layer_calibration_path: str | None = None,
) -> PinPairTangentGeometry:
    """
    Compute the outbound tangent line and active roller index for an anchor→target pin pair.

    This is the minimal geometry required to back-solve a roller y-offset:
    - tangent_point_a / tangent_point_b  — the selected external tangent line
    - unit_direction                     — normalised direction along that line
    - normal                             — unit normal pointing toward the wire side
    - roller_index                       — which of the 4 rollers contacts the wire (0-3)

    Raises UvHeadTargetError (a ValueError subclass) on any geometry failure.
    """
    mc_path = (
        str(machine_calibration_path) if machine_calibration_path is not None else None
    )
    lc_path = (
        str(layer_calibration_path) if layer_calibration_path is not None else None
    )
    return _cached_compute_pin_pair_tangent_geometry(
        layer, pin_a, pin_b, mc_path, lc_path
    )
