from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from .alternating import (
    _alternating_plane_for_face,
    _compute_alternating_projection_data,
)
from .calibration import (
    _all_wire_space_pins,
    _cached_all_wire_space_pins,
    _load_layer_calibration,
    _load_machine_calibration,
    _location_to_point3,
    _wire_space_pin,
)
from .geometry2d import (
    _apa_bounds_from_points,
    _choose_outbound_intercept,
    _compute_arm_corrected_outbound,
    _line_equation_from_tangent_points,
    _line_match,
    _select_tangent_solution,
    _tangent_candidates_for_pin_pair,
)
from .models import (
    Point2D,
    Point3D,
    RectBounds,
    UvHeadTargetError,
    UvTangentViewRequest,
    UvTangentViewResult,
)
from .pin_layout import (
    _b_side_face_for_pin,
    _format_tangent_sides,
    _normalize_layer,
    _normalize_pin_name,
    _pin_family_side,
    tangent_sides,
)
from .recipe_sites import _infer_local_pair_pin_from_wrap_side
from .runtime import _probe_runtime_orientation, _runtime_projection_points


def compute_uv_tangent_view(
    request: UvTangentViewRequest,
    *,
    machine_calibration_path: str | Path | None = None,
    layer_calibration_path: str | Path | None = None,
    pin_b_point_override: Point3D | None = None,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
) -> UvTangentViewResult:
    normalized_request = UvTangentViewRequest(
        layer=_normalize_layer(request.layer),
        pin_a=_normalize_pin_name(request.pin_a, "Pin A"),
        pin_b=_normalize_pin_name(request.pin_b, "Pin B"),
        g103_adjacent_pin=(
            _normalize_pin_name(request.g103_adjacent_pin, "Adjacent pin")
            if request.g103_adjacent_pin is not None
            else None
        ),
    )
    if normalized_request.pin_a == normalized_request.pin_b:
        raise UvHeadTargetError("Pin A and Pin B must be different pins.")

    machine_calibration = _load_machine_calibration(machine_calibration_path)
    layer_calibration = _load_layer_calibration(
        normalized_request.layer,
        layer_calibration_path,
    )
    resolved_roller_arm_y_offsets = roller_arm_y_offsets
    if (
        resolved_roller_arm_y_offsets is None
        and machine_calibration.rollerArmCalibration is not None
    ):
        resolved_roller_arm_y_offsets = (
            machine_calibration.rollerArmCalibration.fitted_y_cals
        )

    pin_a_location = _wire_space_pin(layer_calibration, normalized_request.pin_a)
    pin_a_point = _location_to_point3(pin_a_location)
    if pin_b_point_override is None:
        pin_b_location = _wire_space_pin(layer_calibration, normalized_request.pin_b)
        pin_b_point = _location_to_point3(pin_b_location)
    else:
        pin_b_point = Point3D(
            float(pin_b_point_override.x),
            float(pin_b_point_override.y),
            float(pin_b_point_override.z),
        )
    pin_radius = float(machine_calibration.pinDiameter) / 2.0
    transfer_bounds = RectBounds(
        left=float(machine_calibration.transferLeft),
        top=float(machine_calibration.transferTop),
        right=float(machine_calibration.transferRight),
        bottom=float(machine_calibration.transferBottom),
    )
    # Use cached all_wire_space_pins with layer calibration path
    lc_path = (
        str(layer_calibration_path) if layer_calibration_path is not None else None
    )
    if lc_path is not None and os.path.isfile(lc_path):
        wire_pins = {
            name: Point2D(x, y)
            for name, x, y, z in _cached_all_wire_space_pins(lc_path)
        }
    else:
        wire_pins = {
            name: Point2D(pt.x, pt.y)
            for name, pt in _all_wire_space_pins(layer_calibration).items()
        }
    apa_pin_points = tuple(wire_pins.values())
    apa_pin_points_by_name = tuple(wire_pins.items())
    apa_bounds = _apa_bounds_from_points(apa_pin_points)
    pin_a_face = _b_side_face_for_pin(
        normalized_request.layer, normalized_request.pin_a
    )
    pin_b_face = _b_side_face_for_pin(
        normalized_request.layer, normalized_request.pin_b
    )
    alternating_plane = None
    alternating_face = None
    alternating_projection_data: dict[str, Point2D | None] | None = None
    z_retracted = float(machine_calibration.zFront)
    z_extended = float(machine_calibration.zBack)
    pin_a_family = _pin_family_side(normalized_request.pin_a)
    pin_b_family = _pin_family_side(normalized_request.pin_b)
    if pin_a_family != pin_b_family:
        if {pin_a_family, pin_b_family} != {"A", "B"}:
            raise UvHeadTargetError(
                "Alternating-side view requires exactly one B pin and one A pin."
            )
        if pin_a_face != pin_b_face:
            raise UvHeadTargetError(
                "Alternating-side view requires both pins to lie on the same face after converting the A pin to the B side."
            )
        alternating_face = pin_b_face
        alternating_plane = _alternating_plane_for_face(pin_b_face)
    anchor_side = _pin_family_side(normalized_request.pin_a)
    anchor_face = pin_a_face
    anchor_tangent_sides = tangent_sides(
        normalized_request.layer,
        normalized_request.pin_a,
    )
    wrapped_side = _pin_family_side(normalized_request.pin_b)
    wrapped_face = pin_b_face
    wrapped_tangent_sides = tangent_sides(
        normalized_request.layer,
        normalized_request.pin_b,
    )
    if normalized_request.g103_adjacent_pin is not None:
        inferred_pair_pin = _normalize_pin_name(
            normalized_request.g103_adjacent_pin, "Adjacent pin"
        )
    else:
        inferred_pair_pin = _infer_local_pair_pin_from_wrap_side(
            layer_calibration,
            normalized_request.pin_b,
            wrapped_tangent_sides,
        )
    runtime_tangent_point = None
    runtime_target_point = None
    runtime_line_equation = None
    runtime_clipped_segment_start = None
    runtime_clipped_segment_end = None
    runtime_orientation_token = None
    runtime_outbound_intercept = None
    arm_head_center = None
    arm_left_endpoint = None
    arm_right_endpoint = None
    roller_centers: tuple[Point2D, ...] = ()
    arm_corrected_outbound_point = None
    arm_corrected_head_center = None
    arm_corrected_selected_roller_index = None
    arm_corrected_quadrant = None
    arm_corrected_available = False
    arm_corrected_error = None
    head_arm_length = float(machine_calibration.headArmLength)
    head_roller_radius = float(machine_calibration.headRollerRadius)
    head_roller_gap = float(machine_calibration.headRollerGap)

    candidates = _tangent_candidates_for_pin_pair(
        Point2D(pin_a_point.x, pin_a_point.y),
        Point2D(pin_b_point.x, pin_b_point.y),
        pin_radius,
    )
    tangent_point_a, tangent_point_b, clipped_start, clipped_end = (
        _select_tangent_solution(
            candidates,
            transfer_bounds,
            anchor_pin_point=Point2D(pin_a_point.x, pin_a_point.y),
            anchor_tangent_sides=anchor_tangent_sides,
            wrapped_pin_point=Point2D(pin_b_point.x, pin_b_point.y),
            wrapped_tangent_sides=wrapped_tangent_sides,
        )
    )
    outbound_intercept = _choose_outbound_intercept(
        tangent_point_a,
        tangent_point_b,
        clipped_start,
        clipped_end,
    )
    line_equation = _line_equation_from_tangent_points(tangent_point_a, tangent_point_b)
    runtime_candidate = _probe_runtime_orientation(
        layer=normalized_request.layer,
        anchor_pin=normalized_request.pin_a,
        wrapped_pin=normalized_request.pin_b,
        inferred_pair_pin=inferred_pair_pin,
        anchor_tangent_sides=anchor_tangent_sides,
        selected_tangent_point_a=tangent_point_a,
        machine_calibration=machine_calibration,
        layer_calibration=layer_calibration,
        transfer_bounds=transfer_bounds,
        roller_arm_y_offsets=resolved_roller_arm_y_offsets,
    )
    if runtime_candidate is not None:
        (
            runtime_orientation_token,
            runtime_tangent_point,
            runtime_target_point,
            runtime_line_equation,
            runtime_clipped_segment_start,
            runtime_clipped_segment_end,
            runtime_outbound_intercept,
            arm_head_center,
            arm_left_endpoint,
            arm_right_endpoint,
            roller_centers,
        ) = runtime_candidate
    if alternating_plane is None:
        try:
            (
                arm_corrected_outbound_point,
                arm_corrected_head_center,
                arm_corrected_selected_roller_index,
                arm_corrected_quadrant,
            ) = _compute_arm_corrected_outbound(
                anchor_pin_point=Point2D(pin_a_point.x, pin_a_point.y),
                target_pin_point=Point2D(pin_b_point.x, pin_b_point.y),
                tangent_point_a=tangent_point_a,
                tangent_point_b=tangent_point_b,
                transfer_bounds=transfer_bounds,
                head_arm_length=head_arm_length,
                head_roller_radius=head_roller_radius,
                head_roller_gap=head_roller_gap,
                roller_arm_y_offsets=resolved_roller_arm_y_offsets,
            )
            arm_corrected_available = True
        except UvHeadTargetError as exc:
            arm_corrected_error = str(exc)
    if alternating_plane is not None:
        if runtime_orientation_token is None:
            raise UvHeadTargetError(
                "Could not determine a runtime G109 orientation for alternating-side view."
            )
        runtime_g109_location, runtime_g103_location = _runtime_projection_points(
            layer=normalized_request.layer,
            anchor_pin=normalized_request.pin_a,
            wrapped_pin=normalized_request.pin_b,
            inferred_pair_pin=inferred_pair_pin,
            orientation_token=runtime_orientation_token,
            machine_calibration=machine_calibration,
            layer_calibration=layer_calibration,
        )
        alternating_projection_data = _compute_alternating_projection_data(
            plane=alternating_plane,
            pin_a_point=pin_a_point,
            pin_b_point=pin_b_point,
            pin_radius=pin_radius,
            anchor_tangent_sides=anchor_tangent_sides,
            wrapped_tangent_sides=wrapped_tangent_sides,
            z_retracted=z_retracted,
            z_extended=z_extended,
            runtime_g109_location=runtime_g109_location,
            runtime_g103_location=runtime_g103_location,
        )
        tangent_point_a = cast(Point2D, alternating_projection_data["anchor_contact"])
        tangent_point_b = cast(Point2D, alternating_projection_data["wrapped_contact"])
        clipped_start = cast(Point2D, alternating_projection_data["wrap_line_start"])
        clipped_end = cast(Point2D, alternating_projection_data["wrap_line_end"])
        outbound_intercept = cast(Point2D, alternating_projection_data["wrap_line_end"])
        line_equation = _line_equation_from_tangent_points(
            tangent_point_a, tangent_point_b
        )
    return UvTangentViewResult(
        request=normalized_request,
        pin_a_point=pin_a_point,
        pin_b_point=pin_b_point,
        tangent_point_a=tangent_point_a,
        tangent_point_b=tangent_point_b,
        line_equation=line_equation,
        clipped_segment_start=clipped_start,
        clipped_segment_end=clipped_end,
        outbound_intercept=outbound_intercept,
        transfer_bounds=transfer_bounds,
        apa_bounds=apa_bounds,
        apa_pin_points=apa_pin_points,
        apa_pin_points_by_name=apa_pin_points_by_name,
        pin_radius=pin_radius,
        anchor_side=anchor_side,
        anchor_face=anchor_face,
        anchor_tangent_sides=anchor_tangent_sides,
        wrapped_side=wrapped_side,
        wrapped_face=wrapped_face,
        wrap_sides=wrapped_tangent_sides,
        runtime_orientation_token=runtime_orientation_token,
        runtime_tangent_point=runtime_tangent_point,
        runtime_target_point=runtime_target_point,
        runtime_line_equation=runtime_line_equation,
        runtime_clipped_segment_start=runtime_clipped_segment_start,
        runtime_clipped_segment_end=runtime_clipped_segment_end,
        runtime_outbound_intercept=runtime_outbound_intercept,
        arm_head_center=arm_head_center,
        arm_left_endpoint=arm_left_endpoint,
        arm_right_endpoint=arm_right_endpoint,
        roller_centers=roller_centers,
        arm_corrected_outbound_point=arm_corrected_outbound_point,
        arm_corrected_head_center=arm_corrected_head_center,
        arm_corrected_selected_roller_index=arm_corrected_selected_roller_index,
        arm_corrected_quadrant=arm_corrected_quadrant,
        arm_corrected_available=arm_corrected_available,
        arm_corrected_error=arm_corrected_error,
        head_arm_length=head_arm_length,
        head_roller_radius=head_roller_radius,
        head_roller_gap=head_roller_gap,
        alternating_plane=alternating_plane,
        alternating_face=alternating_face,
        alternating_anchor_center=(
            alternating_projection_data["anchor_center"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_wrapped_center=(
            alternating_projection_data["wrapped_center"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_anchor_segment_start=(
            alternating_projection_data["anchor_segment_start"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_anchor_segment_end=(
            alternating_projection_data["anchor_segment_end"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_wrapped_segment_start=(
            alternating_projection_data["wrapped_segment_start"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_wrapped_segment_end=(
            alternating_projection_data["wrapped_segment_end"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_anchor_contact=(
            alternating_projection_data["anchor_contact"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_wrapped_contact=(
            alternating_projection_data["wrapped_contact"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_wrap_line_start=(
            alternating_projection_data["wrap_line_start"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_wrap_line_end=(
            alternating_projection_data["wrap_line_end"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_g109_projection=(
            alternating_projection_data["g109_projection"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_g103_projection=(
            alternating_projection_data["g103_projection"]
            if alternating_projection_data is not None
            else None
        ),
        alternating_g108_projection=(
            alternating_projection_data["g108_projection"]
            if alternating_projection_data is not None
            else None
        ),
        z_retracted=z_retracted,
        z_extended=z_extended,
        matches_runtime_line=_line_match(line_equation, runtime_line_equation),
        tangent_selection_rule=(
            (
                f"Project the alternating-side wrap in the {alternating_plane} plane using "
                f"{_format_tangent_sides(anchor_tangent_sides)} on anchor {normalized_request.pin_a} and "
                f"{_format_tangent_sides(wrapped_tangent_sides)} "
                f"on wrapped pin {normalized_request.pin_b}; extend the selected contact line to "
                "the machine zRetracted/zExtended planes and overlay the runtime G109-G103 projection only."
            )
            if alternating_plane is not None
            else (
                "Score tangent candidates by whether the anchor tangent lies on "
                f"{_format_tangent_sides(anchor_tangent_sides)} for pin {normalized_request.pin_a} and "
                "whether the target tangent lies on "
                f"{_format_tangent_sides(wrapped_tangent_sides)} for pin {normalized_request.pin_b}; "
                "prefer the candidate satisfying more "
                "of those two constraints, break ties by preferring the target-side match, then choose the "
                "one whose outbound transfer intercept has the higher Y coordinate, breaking ties with higher X."
            )
        ),
        validation_error=None,
    )
