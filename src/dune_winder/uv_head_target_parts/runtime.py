from __future__ import annotations

from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.gcode.runtime import GCodeExecutionError, execute_text_line
from dune_winder.library.Geometry.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.head_compensation import WirePathModel

from .calibration import _wire_space_pin
from .constants import _ORIENTATION_TOKENS
from .geometry2d import (
    _build_arm_geometry,
    _choose_outbound_intercept,
    _clip_infinite_line_to_bounds,
    _is_on_wrap_side,
    _line_deviation_at_point,
    _line_equation_from_tangent_points,
)
from .models import LineEquation, Point2D, RectBounds, UvHeadTargetError


def _runtime_projection_points(
    *,
    layer: str,
    anchor_pin: str,
    wrapped_pin: str,
    inferred_pair_pin: str,
    orientation_token: str,
    machine_calibration: MachineCalibration,
    layer_calibration: LayerCalibration,
) -> tuple[Location, Location]:
    handler = _initial_handler(machine_calibration, layer_calibration)
    _execute_line(handler, "G106 P1")
    _execute_line(handler, f"G109 P{anchor_pin} P{orientation_token}")
    g109_location = handler._headCompensation.anchorPoint()
    _execute_line(handler, f"G103 P{wrapped_pin} P{inferred_pair_pin} PXY")
    g103_location = Location(float(handler._x), float(handler._y), float(handler._z))
    return (g109_location, g103_location)


def _initial_handler(
    machine_calibration: MachineCalibration,
    layer_calibration: LayerCalibration,
) -> GCodeHandlerBase:
    handler = GCodeHandlerBase(machine_calibration, WirePathModel(machine_calibration))
    handler.useLayerCalibration(layer_calibration)
    handler._x = 0.0
    handler._y = 0.0
    handler._z = 0.0
    handler._headPosition = None
    return handler


def _probe_runtime_orientation(
    *,
    layer: str,
    anchor_pin: str,
    wrapped_pin: str,
    inferred_pair_pin: str,
    anchor_tangent_sides: tuple[str, str],
    selected_tangent_point_a: Point2D,
    machine_calibration: MachineCalibration,
    layer_calibration: LayerCalibration,
    transfer_bounds: RectBounds,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
) -> (
    tuple[
        str,
        Point2D,
        Point2D,
        LineEquation,
        Point2D,
        Point2D,
        Point2D,
        Point2D,
        Point2D,
        Point2D,
        tuple[Point2D, ...],
    ]
    | None
):
    head_position = 1
    anchor_center = _wire_space_pin(layer_calibration, anchor_pin)
    anchor_center_point = Point2D(float(anchor_center.x), float(anchor_center.y))
    best_candidate = None

    for orientation_token in _ORIENTATION_TOKENS:
        handler = _initial_handler(machine_calibration, layer_calibration)
        try:
            _execute_line(handler, f"G106 P{head_position}")
            _execute_line(handler, f"G109 P{anchor_pin} P{orientation_token}")
            _execute_line(handler, f"G103 P{wrapped_pin} P{inferred_pair_pin} PXY")
            _execute_line(handler, "G102")
            runtime_tangent_location = (
                handler._headCompensation.compensatedAnchorPoint()
            )
            runtime_tangent_point = Point2D(
                float(runtime_tangent_location.x), float(runtime_tangent_location.y)
            )
            if not (
                _is_on_wrap_side(
                    runtime_tangent_point,
                    anchor_center_point,
                    "x",
                    anchor_tangent_sides[0],
                )
                or _is_on_wrap_side(
                    runtime_tangent_point,
                    anchor_center_point,
                    "y",
                    anchor_tangent_sides[1],
                )
            ):
                continue
            _execute_line(handler, "G108")
            head_z = float(handler._getHeadPosition(head_position))
            final_head_location = Location(float(handler._x), float(handler._y), head_z)
            final_wire_location = handler._headCompensation.getActualLocation(
                final_head_location
            )
            runtime_target_point = Point2D(
                float(final_wire_location.x), float(final_wire_location.y)
            )
            runtime_line_equation = _line_equation_from_tangent_points(
                runtime_tangent_point,
                runtime_target_point,
            )
            clipped = _clip_infinite_line_to_bounds(
                runtime_tangent_point,
                Point2D(
                    runtime_target_point.x - runtime_tangent_point.x,
                    runtime_target_point.y - runtime_tangent_point.y,
                ),
                transfer_bounds,
            )
            if clipped is None:
                continue
            clipped_start, clipped_end = clipped
            runtime_outbound_intercept = _choose_outbound_intercept(
                runtime_tangent_point,
                runtime_target_point,
                clipped_start,
                clipped_end,
            )
            arm_head_center = Point2D(
                float(final_head_location.x), float(final_head_location.y)
            )
            arm_left_endpoint, arm_right_endpoint, roller_centers = _build_arm_geometry(
                arm_head_center,
                head_arm_length=float(machine_calibration.headArmLength),
                head_roller_radius=float(machine_calibration.headRollerRadius),
                head_roller_gap=float(machine_calibration.headRollerGap),
                roller_arm_y_offsets=roller_arm_y_offsets,
            )
        except Exception:
            # Any runtime probe failure invalidates only this orientation candidate.
            # The caller already has a pure-geometry fallback, so keep searching.
            continue

        deviation = _line_deviation_at_point(
            selected_tangent_point_a, runtime_tangent_point
        )
        ranking = (
            deviation,
            -runtime_outbound_intercept.y,
            -runtime_outbound_intercept.x,
            orientation_token,
        )
        candidate = (
            orientation_token,
            runtime_tangent_point,
            runtime_target_point,
            runtime_line_equation,
            clipped_start,
            clipped_end,
            runtime_outbound_intercept,
            arm_head_center,
            arm_left_endpoint,
            arm_right_endpoint,
            roller_centers,
        )
        if best_candidate is None or ranking < best_candidate[0]:
            best_candidate = (ranking, candidate)

    if best_candidate is None:
        return None
    return best_candidate[1]


def _execute_line(handler: GCodeHandlerBase, line: str) -> None:
    try:
        execute_text_line(line, handler._callbacks.get)
    except GCodeExecutionError as exc:
        raise UvHeadTargetError(f"Failed to execute {line!r}: {exc}.") from exc
