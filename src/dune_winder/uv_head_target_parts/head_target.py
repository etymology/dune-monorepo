from __future__ import annotations

from pathlib import Path

from dune_winder.library.Geometry.location import Location

from .calibration import (
    _load_layer_calibration,
    _load_machine_calibration,
    _location_to_point3,
    _wire_space_pin,
)
from .models import (
    Point2D,
    Point3D,
    RectBounds,
    UvHeadTargetRequest,
    UvHeadTargetResult,
)
from .pin_layout import (
    _normalize_head_z_mode,
    _normalize_layer,
    _normalize_pin_name,
    tangent_sides,
)
from .recipe_sites import _lookup_recipe_site
from .runtime import _execute_line, _initial_handler


def compute_uv_head_target(
    request: UvHeadTargetRequest,
    *,
    machine_calibration_path: str | Path | None = None,
    layer_calibration_path: str | Path | None = None,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
) -> UvHeadTargetResult:
    normalized_request = UvHeadTargetRequest(
        layer=_normalize_layer(request.layer),
        anchor_pin=_normalize_pin_name(request.anchor_pin, "Anchor pin"),
        wrapped_pin=_normalize_pin_name(request.wrapped_pin, "Wrapped pin"),
        head_z_mode=_normalize_head_z_mode(request.head_z_mode),
    )
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
    anchor_point = _wire_space_pin(layer_calibration, normalized_request.anchor_pin)
    wrapped_point = _wire_space_pin(layer_calibration, normalized_request.wrapped_pin)
    recipe_anchor_pin = f"P{normalized_request.anchor_pin}"
    recipe_wrapped_pin = f"P{normalized_request.wrapped_pin}"

    recipe_site = _lookup_recipe_site(
        normalized_request.layer,
        recipe_anchor_pin,
        recipe_wrapped_pin,
    )
    wrap_sides_value = tangent_sides(
        normalized_request.layer,
        normalized_request.wrapped_pin,
    )
    inferred_pair_pin = (
        recipe_site.recipe_pair_pin_b
        if recipe_wrapped_pin == recipe_site.recipe_pair_pin_a
        else recipe_site.recipe_pair_pin_a
    )
    inferred_pair_pin_name = (
        inferred_pair_pin[1:]
        if inferred_pair_pin.startswith("P")
        else inferred_pair_pin
    )
    inferred_pair_point = _wire_space_pin(layer_calibration, inferred_pair_pin_name)
    display_inferred_pair_pin = inferred_pair_pin_name
    if str(request.wrapped_pin).strip().upper().startswith(
        "F"
    ) and display_inferred_pair_pin.startswith("A"):
        display_inferred_pair_pin = "F" + display_inferred_pair_pin[1:]

    head_position = 1 if normalized_request.head_z_mode == "front" else 2
    handler = _initial_handler(machine_calibration, layer_calibration)
    _execute_line(handler, f"G106 P{head_position}")
    _execute_line(
        handler,
        f"G109 P{normalized_request.anchor_pin} P{recipe_site.orientation_token}",
    )
    _execute_line(
        handler,
        f"G103 P{normalized_request.wrapped_pin} P{inferred_pair_pin_name} PXY",
    )
    midpoint_point = Point3D(float(handler._x), float(handler._y), float(handler._z))
    _execute_line(handler, "G102")
    transfer_point = Point2D(float(handler._x), float(handler._y))
    effective_anchor = handler._headCompensation.compensatedAnchorPoint()
    _execute_line(handler, "G108")
    head_z = float(handler._getHeadPosition(head_position))
    final_head_location = Location(float(handler._x), float(handler._y), head_z)
    final_wire_location = handler._headCompensation.getActualLocation(
        final_head_location
    )

    return UvHeadTargetResult(
        request=normalized_request,
        site_label=recipe_site.site_label,
        site_side=recipe_site.side,
        site_position=recipe_site.position,
        wrap_sides=wrap_sides_value,
        orientation_token=recipe_site.orientation_token,
        anchor_pin_point=_location_to_point3(anchor_point),
        wrapped_pin_point=_location_to_point3(wrapped_point),
        inferred_pair_pin=display_inferred_pair_pin,
        inferred_pair_pin_point=_location_to_point3(inferred_pair_point),
        midpoint_point=midpoint_point,
        transfer_point=transfer_point,
        effective_anchor_point=_location_to_point3(effective_anchor),
        final_head_point=_location_to_point3(final_head_location),
        final_wire_point=_location_to_point3(final_wire_location),
        transfer_bounds=RectBounds(
            left=float(machine_calibration.transferLeft),
            top=float(machine_calibration.transferTop),
            right=float(machine_calibration.transferRight),
            bottom=float(machine_calibration.transferBottom),
        ),
        pin_radius=float(machine_calibration.pinDiameter) / 2.0,
        head_arm_length=float(machine_calibration.headArmLength),
        head_roller_radius=float(machine_calibration.headRollerRadius),
        head_roller_gap=float(machine_calibration.headRollerGap),
        validation_error=None,
    )
