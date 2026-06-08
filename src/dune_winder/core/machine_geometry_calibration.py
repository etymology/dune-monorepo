from __future__ import annotations

from typing import Any
import errno
import copy
import json
import math
import multiprocessing
import os
import pathlib
import queue
import threading
import time
import uuid
import traceback

from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.gcode.runtime import GCodeExecutionError, execute_text_line
from dune_winder.geometry.primitives.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.calibration.roller_arm import (
    RollerArmCalibration,
    RollerArmMeasurement,
    roller_arm_calibration_to_dict,
    roller_y_cal_from_measurement,
)
from dune_winder.machine.calibration.z_plane import (
    LayerZPlaneMeasurement,
    empty_layer_z_plane_calibration,
    layer_z_plane_calibration_from_dict,
    layer_z_plane_calibration_to_dict,
)
from dune_winder.machine.calibration.z_plane_solver import (
    apply_layer_z_plane_calibration,
    fit_layer_z_plane,
    has_valid_layer_z_plane_fit,
)
from dune_winder.machine.geometry.uv_wrap_geometry import (
    Point2D as WrapPoint2D,
    Point3D as WrapPoint3D,
    RectBounds as WrapRectBounds,
    plan_wrap_transition,
)
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.recipes.line_offset_overrides import (
    extract_line_key,
    line_offset_override_items,
    normalize_line_key,
    set_anchor_to_target_offset,
)
from dune_winder.recipes.offset_axis_policy import (
    enforce_offset_axes,
    natural_axis_for_pin,
)
from dune_winder.uv_head_target import (
    clear_uv_head_target_caches,
    compute_pin_pair_tangent_geometry,
    _lookup_recipe_site,
    parse_anchor_to_target_command,
)


_SUPPORTED_LAYERS = ("U", "V")
_TRACE_LINE_REQUIRES = "~anchorToTarget("
_EPSILON = 1e-9
_CAMERA_OFFSET_BOUND_MM = 10.0
_ROLLER_Y_BOUND_MM = 5.0
# Caps on how much a single re-solve is allowed to shift any per-line
# override from its current live value.  The solver writes the full
# residual back out as the per-line override, so the residual itself
# can legitimately be large (cross-side anchor sites carry overrides
# tens to hundreds of mm wide); what we gate is the *change* relative
# to the override that's already in production.
_MAX_LINE_OFFSET_DELTA_X_MM = 8.0
_MAX_LINE_OFFSET_DELTA_Y_MM = 5.0
_SANITY_CHECK_TOLERANCE_MM = 1.0
# A recalibration re-expresses the same physical wrap geometry: the camera-wire
# offset shift is cancelled by the per-corner offset shift, leaving the
# commanded head target nearly unchanged.  Any line whose end-to-end head
# command moves more than this when swapping the live calibration for the
# drafted one is flagged.  The floor on how unchanged that target can be is set
# by the winder's backlash: the X axis has a 0.4 mm reversal zone, so a jog
# measurement can place the wire up to ~0.4 mm either side of the true target
# depending on approach direction, and a re-solve will fan that into the
# per-corner offset.  The bound therefore sits above the backlash reversal zone
# (0.4 mm) plus the global camera-offset fit (~0.15 mm) and 0.1 mm offset
# quantisation, so it still catches gross regressions (multi-mm, e.g. a dropped
# live offset) without blocking moves that are really just backlash.
_COMMAND_TARGET_TOLERANCE_MM = 0.5
_CALIBRATION_PATH_CACHE: dict[tuple, str] = {}  # (roller_y_cals,) -> path
_CALIBRATION_OBJECT_CACHE: dict[
    tuple, MachineCalibration
] = {}  # (roller_y_cals,) -> object


def _wire_space_pin_location(
    layer_calibration: LayerCalibration,
    pin_name: str,
    machine_calibration: MachineCalibration | None = None,
    *,
    camera_wire_offset: tuple[float, float] | None = None,
) -> Location:
    """
    Wire-space pin location.  Stored pin positions are raw winder coordinates
    (no camera-wire offset baked in); the offset is added at runtime.

    Pass `camera_wire_offset` to use a candidate offset (used by the Machine
    XY solver while iterating); otherwise the offset is read from the
    supplied `machine_calibration`.
    """
    raw = layer_calibration.getPinLocation(str(pin_name))
    layer_offset = layer_calibration.offset
    if camera_wire_offset is not None:
        cam_x = float(camera_wire_offset[0])
        cam_y = float(camera_wire_offset[1])
    elif machine_calibration is not None:
        cam_x = float(getattr(machine_calibration, "cameraWireOffsetX", None) or 0.0)
        cam_y = float(getattr(machine_calibration, "cameraWireOffsetY", None) or 0.0)
    else:
        cam_x = 0.0
        cam_y = 0.0
    return Location(
        float(raw.x) + float(layer_offset.x) + cam_x,
        float(raw.y) + float(layer_offset.y) + cam_y,
        float(raw.z) + float(layer_offset.z),
    )


def _transfer_edge_for_point(bounds, point, *, tolerance=1e-6):
    distances = (
        ("left", abs(float(point.x) - float(bounds.left))),
        ("right", abs(float(point.x) - float(bounds.right))),
        ("top", abs(float(point.y) - float(bounds.top))),
        ("bottom", abs(float(point.y) - float(bounds.bottom))),
    )
    edge, distance = min(distances, key=lambda item: float(item[1]))
    if float(distance) > float(tolerance):
        return None
    return edge


def _actual_wire_point_from_machine_target(
    *,
    final_head_xy,
    compensated_anchor_xy,
    anchor_z,
    head_z,
    head_arm_length,
    head_roller_radius,
    head_roller_gap,
):
    delta_x = float(final_head_xy[0]) - float(compensated_anchor_xy[0])
    delta_z = float(head_z) - float(anchor_z)
    length_xz = ((delta_x**2) + (delta_z**2)) ** 0.5
    if length_xz <= _EPSILON:
        return (
            float(final_head_xy[0]),
            float(final_head_xy[1]),
        )

    head_ratio = float(head_arm_length) / float(length_xz)
    x = float(final_head_xy[0]) - (float(delta_x) * float(head_ratio))
    y = float(final_head_xy[1])
    z = float(head_z) - (float(delta_z) * float(head_ratio))

    delta_x = float(x) - float(compensated_anchor_xy[0])
    delta_y = float(y) - float(compensated_anchor_xy[1])
    delta_z = float(z) - float(anchor_z)
    length_xz = ((delta_x**2) + (delta_z**2)) ** 0.5
    length_xyz = ((delta_x**2) + (delta_y**2) + (delta_z**2)) ** 0.5
    if length_xz <= _EPSILON or length_xyz <= _EPSILON:
        return (float(x), float(y))

    roller_offset_y = float(head_roller_radius) * float(length_xz) / float(length_xyz)
    roller_offset_xz = float(head_roller_radius) * float(delta_y) / float(length_xyz)
    roller_offset_x = abs(float(roller_offset_xz) * float(delta_x) / float(length_xz))
    roller_offset_z = abs(float(roller_offset_xz) * float(delta_z) / float(length_xz))
    roller_offset_y -= float(head_roller_radius)
    roller_offset_y -= float(head_roller_gap) / 2.0

    if delta_x < 0:
        roller_offset_x = -float(roller_offset_x)
    if delta_z < 0:
        roller_offset_z = -float(roller_offset_z)
    if delta_y > 0:
        roller_offset_y = -float(roller_offset_y)

    return (
        float(x) - float(roller_offset_x),
        float(y) - float(roller_offset_y),
    )


def _translate_projection_payload(payload, camera_offset):
    delta_x = float(camera_offset[0])
    delta_y = float(camera_offset[1])
    base_head_x = float(payload["projectedHeadX"])
    base_head_y = float(payload["projectedHeadY"])
    base_wire_x = float(payload["projectedX"])
    base_wire_y = float(payload["projectedY"])

    def _result(head_x, head_y, wire_x, wire_y):
        # The camera-wire offset shifts every wire-space pin by exactly the
        # offset, so the pin centres translate by delta regardless of side;
        # only the head/wire targets re-project non-linearly (same-side).
        return {
            "sameSide": bool(payload.get("sameSide", False)),
            "projectedHeadX": float(head_x),
            "projectedHeadY": float(head_y),
            "projectedX": float(wire_x),
            "projectedY": float(wire_y),
            "headZ": float(payload.get("headZ", 0.0)),
            "anchorPinX": float(payload.get("anchorPinX", 0.0)) + delta_x,
            "anchorPinY": float(payload.get("anchorPinY", 0.0)) + delta_y,
            "anchorPinZ": float(payload.get("anchorPinZ", 0.0)),
            "targetPinX": float(payload.get("targetPinX", 0.0)) + delta_x,
            "targetPinY": float(payload.get("targetPinY", 0.0)) + delta_y,
            "targetPinZ": float(payload.get("targetPinZ", 0.0)),
        }

    if abs(delta_x) <= _EPSILON and abs(delta_y) <= _EPSILON:
        return _result(base_head_x, base_head_y, base_wire_x, base_wire_y)

    if not bool(payload.get("sameSide", False)):
        return _result(
            base_head_x + delta_x,
            base_head_y + delta_y,
            base_wire_x + delta_x,
            base_wire_y + delta_y,
        )

    direction_x = float(payload["targetTangentX"]) - float(payload["anchorTangentX"])
    direction_y = float(payload["targetTangentY"]) - float(payload["anchorTangentY"])
    translated_head_x = float(base_head_x) + float(delta_x)
    translated_head_y = float(base_head_y) + float(delta_y)
    transfer_edge = payload.get("transferEdge")
    bounds = payload.get("transferBounds") or {}

    if transfer_edge in ("top", "bottom") and abs(direction_y) > _EPSILON:
        translated_head_y = float(bounds[transfer_edge])
        parameter = (
            float(translated_head_y) - (float(base_head_y) + float(delta_y))
        ) / float(direction_y)
        translated_head_x = (float(base_head_x) + float(delta_x)) + (
            parameter * float(direction_x)
        )
    elif transfer_edge in ("left", "right") and abs(direction_x) > _EPSILON:
        translated_head_x = float(bounds[transfer_edge])
        parameter = (
            float(translated_head_x) - (float(base_head_x) + float(delta_x))
        ) / float(direction_x)
        translated_head_y = (float(base_head_y) + float(delta_y)) + (
            parameter * float(direction_y)
        )

    translated_wire_x, translated_wire_y = _actual_wire_point_from_machine_target(
        final_head_xy=(float(translated_head_x), float(translated_head_y)),
        compensated_anchor_xy=(
            float(payload["anchorTangentX"]) + float(delta_x),
            float(payload["anchorTangentY"]) + float(delta_y),
        ),
        anchor_z=float(payload["anchorZ"]),
        head_z=float(payload["headZ"]),
        head_arm_length=float(payload["headArmLength"]),
        head_roller_radius=float(payload["headRollerRadius"]),
        head_roller_gap=float(payload["headRollerGap"]),
    )
    return _result(
        translated_head_x,
        translated_head_y,
        translated_wire_x,
        translated_wire_y,
    )


def _implied_pin_offset(observed_x, observed_y, projection):
    """Residual between observation and projection as an implied pin shift.

    The operator jogs the *head* until the wire is tangent to the pin, so a
    measurement records a head position.  An ``~anchorToTarget`` offset, by
    contrast, shifts the *target pin*: the head sweeps a longer lever arm
    than the pin, so a head-space error has to be scaled by the
    anchor->target / anchor->head distance ratio to become the pin-position
    shift the solver should write back as a per-line override.  This mirrors
    ``_head_delta_to_pin_delta`` in the jog-calibration path so solver-fitted
    overrides are in the same units as jog-fitted ones.

    Falls back to the plain head/wire residual when the projection lacks the
    geometry (e.g. simplified projections from tests that only return
    ``projectedX``/``projectedY``).
    """
    if "projectedHeadX" not in projection:
        return (
            float(observed_x) - float(projection["projectedX"]),
            float(observed_y) - float(projection["projectedY"]),
        )

    head_dx = float(observed_x) - float(projection["projectedHeadX"])
    head_dy = float(observed_y) - float(projection["projectedHeadY"])
    anchor_x = float(projection.get("anchorPinX", 0.0))
    anchor_y = float(projection.get("anchorPinY", 0.0))
    anchor_z = float(projection.get("anchorPinZ", 0.0))
    target_x = float(projection.get("targetPinX", 0.0))
    target_y = float(projection.get("targetPinY", 0.0))
    target_z = float(projection.get("targetPinZ", 0.0))

    if bool(projection.get("sameSide", False)):
        wire_x = float(projection["projectedX"])
        wire_y = float(projection["projectedY"])
        d_at = math.hypot(target_x - anchor_x, target_y - anchor_y)
        d_ah = math.hypot(wire_x - anchor_x, wire_y - anchor_y)
        if d_at <= _EPSILON or d_ah <= _EPSILON:
            return (head_dx, head_dy)
        ratio = d_at / d_ah
        return (head_dx * ratio, head_dy * ratio)

    # Alternating side: scale only the axis in the dominant pin-pair plane,
    # measured against the head Z, exactly as the jog path does.
    head_x = float(projection["projectedHeadX"])
    head_y = float(projection["projectedHeadY"])
    head_z = float(projection.get("headZ", 0.0))
    if abs(target_x - anchor_x) >= abs(target_y - anchor_y):
        d_at = math.hypot(target_x - anchor_x, target_z - anchor_z)
        d_ah = math.hypot(head_x - anchor_x, head_z - anchor_z)
        if d_at <= _EPSILON or d_ah <= _EPSILON:
            return (head_dx, head_dy)
        ratio = d_at / d_ah
        return (head_dx * ratio, head_dy)

    d_at = math.hypot(target_y - anchor_y, target_z - anchor_z)
    d_ah = math.hypot(head_y - anchor_y, head_z - anchor_z)
    if d_at <= _EPSILON or d_ah <= _EPSILON:
        return (head_dx, head_dy)
    ratio = d_at / d_ah
    return (head_dx, head_dy * ratio)


def _project_machine_xy_measurement_payload(
    measurement,
    *,
    layer_path,
    machine_path=None,
    roller_y_cals,
    _layer_calibration=None,
    _machine_calibration=None,
    cameraWireOffset: tuple[float, float] = (0.0, 0.0),
):
    """
    Project a single measurement.

    Pin positions in `LayerCalibration` are stored raw (no camera-wire
    offset baked in).  The projection is computed in *raw* camera space
    by default (`cameraWireOffset=(0,0)`).  Callers compose the camera
    offset on top via `_translate_projection_payload` so the solver can
    iterate candidate offsets without re-projecting from scratch.
    """
    layer_name = str(measurement["layer"])
    machine_calibration_for_load = None
    if _layer_calibration is not None:
        layer_calibration = _layer_calibration
    else:
        layer_calibration = LayerCalibration(layer_name)
        layer_directory, layer_filename = os.path.split(str(layer_path))
        if _machine_calibration is not None:
            machine_calibration_for_load = _machine_calibration
        elif machine_path is not None:
            machine_directory_load, machine_filename_load = os.path.split(
                str(machine_path)
            )
            machine_calibration_for_load = MachineCalibration(
                machine_directory_load, machine_filename_load
            )
            machine_calibration_for_load.load()
        layer_calibration.load(
            layer_directory,
            layer_filename,
            exceptionForMismatch=False,
            machineCalibration=machine_calibration_for_load,
        )
    if _machine_calibration is not None:
        machine_calibration = _machine_calibration
    else:
        machine_directory, machine_filename = os.path.split(str(machine_path))
        machine_calibration = MachineCalibration(machine_directory, machine_filename)
        machine_calibration.load()

    # The projection runs in raw-camera space by default.  We override the
    # candidate's camera-wire offset locally (without persisting the change)
    # so the GCode handler invoked below also treats the pin as raw.
    saved_offset_x = machine_calibration.cameraWireOffsetX
    saved_offset_y = machine_calibration.cameraWireOffsetY
    machine_calibration.cameraWireOffsetX = float(cameraWireOffset[0])
    machine_calibration.cameraWireOffsetY = float(cameraWireOffset[1])
    try:
        return _project_machine_xy_measurement_payload_inner(
            measurement,
            layer_calibration=layer_calibration,
            machine_calibration=machine_calibration,
            roller_y_cals=roller_y_cals,
        )
    finally:
        machine_calibration.cameraWireOffsetX = saved_offset_x
        machine_calibration.cameraWireOffsetY = saved_offset_y


def _project_machine_xy_measurement_payload_inner(
    measurement,
    *,
    layer_calibration,
    machine_calibration,
    roller_y_cals,
):
    command = parse_anchor_to_target_command(
        _extract_anchor_to_target_command_text(measurement["gcodeLine"])
    )

    anchor_location = _wire_space_pin_location(
        layer_calibration, command.anchor_pin, machine_calibration
    )
    target_location = _wire_space_pin_location(
        layer_calibration, command.target_pin, machine_calibration
    )
    if command.target_offset is not None:
        target_location = Location(
            float(target_location.x) + float(command.target_offset[0]),
            float(target_location.y) + float(command.target_offset[1]),
            float(target_location.z),
        )

    pin_radius = float(machine_calibration.pinDiameter) / 2.0
    target_pin_clearance = float(machine_calibration.targetPinClearance)
    target_pin_radius = pin_radius + target_pin_clearance

    plan = plan_wrap_transition(
        layer=str(measurement["layer"]),
        anchor_pin=command.anchor_pin,
        target_pin=command.target_pin,
        anchor_pin_point=WrapPoint3D(
            float(anchor_location.x),
            float(anchor_location.y),
            float(anchor_location.z),
        ),
        target_pin_point=WrapPoint3D(
            float(target_location.x),
            float(target_location.y),
            float(target_location.z),
        ),
        transfer_bounds=WrapRectBounds(
            left=float(machine_calibration.transferLeft),
            top=float(machine_calibration.transferTop),
            right=float(machine_calibration.transferRight),
            bottom=float(machine_calibration.transferBottom),
        ),
        z_front=float(machine_calibration.zFront),
        z_back=float(machine_calibration.zBack),
        pin_radius=pin_radius,
        target_pin_radius=target_pin_radius,
        head_arm_length=float(machine_calibration.headArmLength),
        head_roller_radius=float(machine_calibration.headRollerRadius),
        head_roller_gap=float(machine_calibration.headRollerGap),
        roller_arm_y_offsets=tuple(float(value) for value in roller_y_cals[:4]),
    )

    handler = GCodeHandlerBase(machine_calibration, WirePathModel(machine_calibration))
    handler.useLayerCalibration(layer_calibration)
    try:
        execute_text_line(command.raw_text, handler._callbacks.get)
    except GCodeExecutionError as exc:
        raise ValueError(str(exc)) from exc

    projected_head_x = float(handler._x)
    projected_head_y = float(handler._y)
    projected_head_z = float(handler._z)
    projected_wire = handler._headCompensation.getActualLocation(
        Location(projected_head_x, projected_head_y, projected_head_z)
    )

    transfer_bounds = {
        "left": float(machine_calibration.transferLeft),
        "right": float(machine_calibration.transferRight),
        "top": float(machine_calibration.transferTop),
        "bottom": float(machine_calibration.transferBottom),
    }
    return {
        "sameSide": bool(plan.same_side),
        "projectedHeadX": float(projected_head_x),
        "projectedHeadY": float(projected_head_y),
        "projectedX": float(projected_wire.x),
        "projectedY": float(projected_wire.y),
        "anchorTangentX": float(plan.anchor_tangent_point.x),
        "anchorTangentY": float(plan.anchor_tangent_point.y),
        "targetTangentX": float(plan.target_tangent_point.x),
        "targetTangentY": float(plan.target_tangent_point.y),
        # Pin centres (raw-camera space; the camera offset is composed on
        # top in _translate_projection_payload).  Carried so the residual
        # can be expressed as an implied pin-position shift -- see
        # _implied_pin_offset / _head_delta_to_pin_delta.
        "anchorPinX": float(anchor_location.x),
        "anchorPinY": float(anchor_location.y),
        "anchorPinZ": float(anchor_location.z),
        "targetPinX": float(target_location.x),
        "targetPinY": float(target_location.y),
        "targetPinZ": float(target_location.z),
        "anchorZ": float(anchor_location.z),
        "headZ": float(projected_head_z),
        "headArmLength": float(machine_calibration.headArmLength),
        "headRollerRadius": float(machine_calibration.headRollerRadius),
        "headRollerGap": float(machine_calibration.headRollerGap),
        "transferBounds": dict(transfer_bounds),
        "transferEdge": _transfer_edge_for_point(
            WrapRectBounds(
                left=float(transfer_bounds["left"]),
                top=float(transfer_bounds["top"]),
                right=float(transfer_bounds["right"]),
                bottom=float(transfer_bounds["bottom"]),
            ),
            WrapPoint2D(float(projected_head_x), float(projected_head_y)),
        ),
    }


def _normalize_layer(layer) -> str:
    normalized = str(layer).strip().upper()
    if normalized not in _SUPPORTED_LAYERS:
        raise ValueError("Machine geometry calibration only supports U and V layers.")
    return normalized


def _deep_copy_json(value):
    return json.loads(json.dumps(value))


def _nominal_roller_y(machine_calibration: MachineCalibration) -> float:
    return (float(machine_calibration.headRollerGap) / 2.0) + float(
        machine_calibration.headRollerRadius
    )


def _live_roller_y_cals(
    machine_calibration: MachineCalibration,
) -> tuple[float, float, float, float]:
    nominal = _nominal_roller_y(machine_calibration)
    calibration = getattr(machine_calibration, "rollerArmCalibration", None)
    if calibration is None:
        return (nominal, nominal, nominal, nominal)
    vals = [float(value) for value in calibration.fitted_y_cals[:4]]
    return (vals[0], vals[1], vals[2], vals[3])


def _error_text(exception):
    text = str(exception).strip()
    if text:
        return text
    return repr(exception)


def _clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def _extract_anchor_to_target_command_text(command_text) -> str:
    line_text = str(command_text).strip()
    start = line_text.find(_TRACE_LINE_REQUIRES)
    if start < 0:
        return line_text
    depth = 0
    started = False
    for index in range(start, len(line_text)):
        char = line_text[index]
        if char == "(":
            depth += 1
            started = True
        elif char == ")" and started:
            depth -= 1
            if depth == 0:
                return line_text[start : index + 1]
    return line_text[start:]


def _baked_anchor_to_target_offset(command_text) -> tuple[float, float]:
    """Offset already present in a measured ``~anchorToTarget`` line.

    Measurements are recorded against the live recipe, so each line carries the
    live per-corner offset (e.g. ``offset=(0,-2.5)``).  Returns ``(0.0, 0.0)``
    when the line has no offset term or cannot be parsed.
    """
    if not command_text:
        return (0.0, 0.0)
    try:
        command = parse_anchor_to_target_command(
            _extract_anchor_to_target_command_text(command_text)
        )
    except Exception:
        return (0.0, 0.0)
    if command.target_offset is None:
        return (0.0, 0.0)
    return (float(command.target_offset[0]), float(command.target_offset[1]))


def _measurement_site_label(measurement) -> str | None:
    cached = measurement.get("siteLabel") or measurement.get("site_label")
    if cached:
        return str(cached)

    command_text = measurement.get("gcodeLine") or measurement.get("traceLine")
    layer = measurement.get("layer")
    if not command_text or not layer:
        return None

    try:
        command = parse_anchor_to_target_command(
            _extract_anchor_to_target_command_text(command_text)
        )
        site = _lookup_recipe_site(str(layer), command.anchor_pin, command.target_pin)
        return str(site.site_label)
    except Exception:
        return None


def _line_natural_axis(layer, measurement):
    """Natural offset axis for a measurement's ~anchorToTarget target pin.

    Returns ``"x"``/``"y"`` from the target pin's face, or ``None`` when the
    command cannot be parsed (the caller then leaves the offset unchanged).
    """
    if not measurement:
        return None
    command_text = measurement.get("gcodeLine") or measurement.get("traceLine")
    if not command_text:
        return None
    try:
        command = parse_anchor_to_target_command(
            _extract_anchor_to_target_command_text(command_text)
        )
        return natural_axis_for_pin(layer, command.target_pin)
    except Exception:
        return None


def _corner_offsets_from_overrides(template_service, overrides):
    """Collapse solved per-line overrides into one entry per corner.

    The machine-XY solver fits a single offset per *corner* (site) and then
    fans that value out across every measured ``(wrap,line)`` of that corner.
    Map each override's ``siteLabel`` back to its corner offset id via the
    template's ``LABEL_TO_OFFSET_ID`` and merge -- entries that share a corner
    carry identical values, so the first wins and their measurement ids and
    line keys are unioned.  Returns ``{offset_id: {offsetId, siteLabel, x, y,
    measurementIds, lineKeys}}``; overrides whose site has no recognised corner
    id are dropped.
    """
    label_to_id = getattr(template_service, "LABEL_TO_OFFSET_ID", {}) or {}
    by_offset_id: dict[str, dict] = {}
    for line_key, entry in (overrides or {}).items():
        if not isinstance(entry, dict):
            continue
        offset_id = label_to_id.get(entry.get("siteLabel"))
        if offset_id is None:
            continue
        bucket = by_offset_id.setdefault(
            offset_id,
            {
                "offsetId": offset_id,
                "siteLabel": entry.get("siteLabel"),
                "x": float(entry.get("x", 0.0) or 0.0),
                "y": float(entry.get("y", 0.0) or 0.0),
                "measurementIds": [],
                "lineKeys": [],
            },
        )
        for measurement_id in entry.get("measurementIds", []) or []:
            if measurement_id not in bucket["measurementIds"]:
                bucket["measurementIds"].append(measurement_id)
        if line_key not in bucket["lineKeys"]:
            bucket["lineKeys"].append(line_key)
    return by_offset_id


def _corner_offset_items(template_service, draft_overrides, live_offsets):
    """Build aligned ``(current, draft)`` per-corner offset rows for the page.

    ``draft`` rows are the solved corner offsets (already natural-axis
    enforced upstream); ``current`` rows are the live corner offset in effect
    for the same corner.  Both lists are ordered by ``OFFSET_IDS`` so they line
    up row-for-row in the UI.
    """
    by_offset_id = _corner_offsets_from_overrides(template_service, draft_overrides)
    offset_ids = list(getattr(template_service, "OFFSET_IDS", ()) or ())
    order = {offset_id: index for index, offset_id in enumerate(offset_ids)}
    natural_axis_by_id = getattr(template_service, "OFFSET_NATURAL_AXIS", {}) or {}

    sorted_items = sorted(
        by_offset_id.values(),
        key=lambda item: order.get(item["offsetId"], len(order)),
    )
    draft_items = []
    current_items = []
    for item in sorted_items:
        offset_id = item["offsetId"]
        # Show the value that Apply would actually write: it lands the offset on
        # the corner's natural axis and quantises to 0.1 mm (see setOffset).
        draft_x, draft_y = enforce_offset_axes(
            item["x"], item["y"], natural_axis_by_id.get(offset_id, "x")
        )
        draft_items.append(
            {
                "offsetId": offset_id,
                "siteLabel": item["siteLabel"],
                "x": draft_x,
                "y": draft_y,
                "measurementIds": list(item.get("measurementIds", [])),
                "lineKeys": list(item.get("lineKeys", [])),
            }
        )
        live = (live_offsets or {}).get(offset_id) or {}
        current_items.append(
            {
                "offsetId": offset_id,
                "siteLabel": item["siteLabel"],
                "x": float(live.get("x", 0.0) or 0.0),
                "y": float(live.get("y", 0.0) or 0.0),
            }
        )
    return current_items, draft_items


def _measurement_site_key(measurement) -> str:
    label = _measurement_site_label(measurement)
    if label:
        return label
    line_key = measurement.get("lineKey")
    if line_key is not None:
        return str(line_key)
    measurement_id = measurement.get("id")
    return str(measurement_id)


def _group_measurements_by_site_label(measurements):
    grouped = {}
    for measurement in measurements:
        key = _measurement_site_key(measurement)
        grouped.setdefault(key, []).append(measurement)
    return grouped


def _most_recent_per_corner(measurements):
    """Keep only the newest measurement for each corner (site label).

    Measurements accumulate over time against an evolving recipe: an older
    sample for a corner can carry a per-corner offset (baked into its
    ``~anchorToTarget`` line) that no longer matches the live calibration.
    Averaging such a stale sample with a fresh one pulls the solved corner away
    from its live value and trips the command-target invariance gate.  For each
    corner we therefore keep only the most recent sample (by ``timestamp``);
    samples whose corner cannot be resolved fall back to a per-measurement key
    so they are always retained.  Original order is preserved for determinism.
    """
    best: dict[str, tuple] = {}
    for index, measurement in enumerate(measurements):
        label = _measurement_site_label(measurement)
        key = label or ("\x00id\x00" + str(measurement.get("id") or index))
        sort_key = (str(measurement.get("timestamp") or ""), index)
        existing = best.get(key)
        if existing is None or sort_key > existing[0]:
            best[key] = (sort_key, index, measurement)
    kept = sorted(best.values(), key=lambda item: item[1])
    return [measurement for _sort_key, _index, measurement in kept]


def _parameter_vector_to_calibration(vector):
    vector = [float(value) for value in vector[:6]]
    return (
        (float(vector[0]), float(vector[1])),
        [float(value) for value in vector[2:6]],
    )


def _format_machine_xy_parameters(vector):
    return {
        "cameraOffsetX": float(vector[0]),
        "cameraOffsetY": float(vector[1]),
        "rollerYCals": [float(value) for value in vector[2:6]],
    }


def _mean(values):
    values = [float(value) for value in values]
    if not values:
        return 0.0
    return float(sum(values) / len(values))


class _MachineXYSolveCancelled(RuntimeError):
    pass


class _MachineXYSolveKilled(RuntimeError):
    pass


class _MachineXYEvaluationWorker:
    def __init__(self, process, result_queue):
        self._process = process
        self._result_queue = result_queue

    @property
    def exitcode(self):
        return self._process.exitcode

    def start(self):
        self._process.start()

    def is_alive(self):
        return self._process.is_alive()

    def poll(self, timeout=0.0):
        try:
            return self._result_queue.get(timeout=max(0.0, float(timeout)))
        except queue.Empty:
            return None

    def terminate(self):
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)
        if self._process.is_alive() and hasattr(self._process, "kill"):
            self._process.kill()
            self._process.join(timeout=1.0)

    def close(self):
        try:
            if self._process.is_alive():
                self._process.join(timeout=0.1)
        except Exception:
            pass
        try:
            if hasattr(self._result_queue, "close"):
                self._result_queue.close()
        except Exception:
            pass
        try:
            if hasattr(self._result_queue, "join_thread"):
                self._result_queue.join_thread()
        except Exception:
            pass


def _project_machine_xy_measurements(
    group_measurements,
    *,
    layer_path,
    machine_path,
    roller_y_cals,
):
    if not group_measurements:
        return []
    layer_name = str(group_measurements[0]["layer"])
    machine_directory, machine_filename = os.path.split(str(machine_path))
    machine_calibration = MachineCalibration(machine_directory, machine_filename)
    machine_calibration.load()
    layer_calibration = LayerCalibration(layer_name)
    layer_directory, layer_filename = os.path.split(str(layer_path))
    layer_calibration.load(
        layer_directory,
        layer_filename,
        exceptionForMismatch=False,
        machineCalibration=machine_calibration,
    )
    results = []
    for measurement in group_measurements:
        results.append(
            (
                measurement,
                _project_machine_xy_measurement_payload(
                    measurement,
                    layer_path=layer_path,
                    machine_path=machine_path,
                    roller_y_cals=roller_y_cals,
                    _layer_calibration=layer_calibration,
                    _machine_calibration=machine_calibration,
                ),
            )
        )
    return results


def _machine_xy_evaluation_worker(
    result_queue,
    group_measurements,
    *,
    layer_path,
    machine_path,
    roller_y_cals,
):
    try:
        result_queue.put(
            {
                "ok": True,
                "results": _project_machine_xy_measurements(
                    group_measurements,
                    layer_path=layer_path,
                    machine_path=machine_path,
                    roller_y_cals=roller_y_cals,
                ),
            }
        )
    except Exception as exception:
        result_queue.put(
            {
                "ok": False,
                "error": _error_text(exception),
                "traceback": traceback.format_exc(),
            }
        )


class MachineGeometryCalibration:
    FILE_NAME = "machineGeometryCalibration.json"

    def __init__(self, process):
        self._process = process
        self._state = None
        self._loadedPath = None
        self._cancelRequestedMachineSolveOperationIds = set()
        self._killRequestedMachineSolveOperationIds = set()
        self._activeMachineSolveOperationIds = set()
        self._activeMachineSolveEvaluations = {}
        self._machineSolveEvaluationLock = threading.RLock()

    # -------------------------------------------------------------------
    def _stateDirectory(self):
        workspace = getattr(self._process, "workspace", None)
        if workspace is not None and hasattr(workspace, "getPath"):
            return workspace.getPath()
        return self._process._workspaceCalibrationDirectory

    # -------------------------------------------------------------------
    def _statePath(self):
        return os.path.join(self._stateDirectory(), self.FILE_NAME)

    # -------------------------------------------------------------------
    def _tempDirectory(self):
        return os.path.join(self._stateDirectory(), "MachineGeometryTemp")

    # -------------------------------------------------------------------
    def _emptyState(self):
        return {
            "measurementRevision": 0,
            "measurements": [],
            "machineDraft": None,
            "layerDrafts": {},
        }

    # -------------------------------------------------------------------
    def _loadState(self):
        path = self._statePath()
        if self._loadedPath == path and self._state is not None:
            return self._state

        state = self._emptyState()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    loaded = json.load(handle)
                if isinstance(loaded, dict):
                    state.update(loaded)
            except (OSError, ValueError, TypeError) as exception:
                self._process._log.add(
                    "MachineGeometryCalibration",
                    "DRAFT_LOAD",
                    "Failed to load machine geometry calibration state.",
                    [path, exception],
                )
        if not isinstance(state.get("layerDrafts"), dict):
            state["layerDrafts"] = {}
        if not isinstance(state.get("measurements"), list):
            state["measurements"] = []
        self._state = state
        self._loadedPath = path
        return self._state

    # -------------------------------------------------------------------
    def _log(self, event, message, details=None):
        log = getattr(self._process, "_log", None)
        if log is None or not hasattr(log, "add"):
            return
        log.add(
            "MachineGeometryCalibration",
            str(event),
            str(message),
            [] if details is None else details,
        )

    # -------------------------------------------------------------------
    def _timestamp(self):
        source = getattr(self._process, "_systemTime", None)
        if source is not None and hasattr(source, "get"):
            try:
                return str(source.get())
            except Exception:
                pass
        return str(time.time())

    # -------------------------------------------------------------------
    def _machineSolveStatus(self, layer, *, create=False):
        draft = self._layerDraft(layer, create=create)
        if draft is None:
            return None
        status = draft.get("machineSolveStatus")
        if status is None and create:
            status = {}
            draft["machineSolveStatus"] = status
        return status

    # -------------------------------------------------------------------
    def _updateMachineSolveStatus(self, layer, **fields):
        status = self._machineSolveStatus(layer, create=True)
        status.update(fields)
        status["updatedAt"] = self._timestamp()
        self._saveState()
        return dict(status)

    # -------------------------------------------------------------------
    def _isMachineSolveCancellationRequested(self, operation_id):
        return str(operation_id) in self._cancelRequestedMachineSolveOperationIds

    # -------------------------------------------------------------------
    def _isMachineSolveKillRequested(self, operation_id):
        return str(operation_id) in self._killRequestedMachineSolveOperationIds

    # -------------------------------------------------------------------
    def _raiseIfMachineSolveCancelled(self, layer, operation_id):
        if self._isMachineSolveCancellationRequested(operation_id):
            raise _MachineXYSolveCancelled("Machine XY solve canceled at user request.")

    # -------------------------------------------------------------------
    def _raiseIfMachineSolveKilled(self, operation_id):
        if self._isMachineSolveKillRequested(operation_id):
            raise _MachineXYSolveKilled("Machine XY solve killed at user request.")

    # -------------------------------------------------------------------
    def _clearMachineSolveRequests(self, operation_id):
        self._cancelRequestedMachineSolveOperationIds.discard(str(operation_id))
        self._killRequestedMachineSolveOperationIds.discard(str(operation_id))

    # -------------------------------------------------------------------
    def _registerMachineSolveOperation(self, operation_id):
        with self._machineSolveEvaluationLock:
            self._activeMachineSolveOperationIds.add(str(operation_id))

    # -------------------------------------------------------------------
    def _unregisterMachineSolveOperation(self, operation_id):
        with self._machineSolveEvaluationLock:
            self._activeMachineSolveOperationIds.discard(str(operation_id))
            self._activeMachineSolveEvaluations.pop(str(operation_id), None)

    # -------------------------------------------------------------------
    def _isMachineSolveOperationActive(self, operation_id):
        with self._machineSolveEvaluationLock:
            return str(operation_id) in self._activeMachineSolveOperationIds

    # -------------------------------------------------------------------
    def _reconcileMachineSolveStatus(self, layer, status=None):
        resolved_layer = self._resolvedLayer(layer)
        current_status = status
        if current_status is None:
            current_status = self._machineSolveStatus(resolved_layer, create=False)
        if current_status is None:
            return None

        state_name = str(current_status.get("status", "")).strip().lower()
        operation_id = current_status.get("operationId")
        if state_name not in ("running", "cancel_requested", "kill_requested"):
            return current_status
        if operation_id and self._isMachineSolveOperationActive(operation_id):
            return current_status

        message = str(current_status.get("message") or "").strip()
        if not message:
            message = "Machine XY solve is no longer running."
        else:
            message = message.rstrip(".") + ". Machine XY solve is no longer running."
        reconciled = self._updateMachineSolveStatus(
            resolved_layer,
            operationId=operation_id,
            status="interrupted",
            step="interrupted",
            message=message,
            cancelRequested=False,
            killRequested=False,
            finishedAt=self._timestamp(),
            estimatedSecondsRemaining=0.0,
        )
        self._clearMachineSolveRequests(operation_id)
        self._log(
            "SOLVE_MACHINE_XY_RECONCILED",
            "Reconciled stale Machine XY solve status.",
            [operation_id, resolved_layer, state_name],
        )
        return reconciled

    # -------------------------------------------------------------------
    def _registerActiveMachineSolveEvaluation(self, operation_id, evaluation):
        with self._machineSolveEvaluationLock:
            operation_key = str(operation_id)
            active = self._activeMachineSolveEvaluations.setdefault(
                operation_key, set()
            )
            active.add(evaluation)

    # -------------------------------------------------------------------
    def _unregisterActiveMachineSolveEvaluation(self, operation_id, evaluation):
        with self._machineSolveEvaluationLock:
            operation_key = str(operation_id)
            active = self._activeMachineSolveEvaluations.get(operation_key)
            if not active:
                return
            active.discard(evaluation)
            if not active:
                self._activeMachineSolveEvaluations.pop(operation_key, None)

    # -------------------------------------------------------------------
    def _terminateActiveMachineSolveEvaluations(self, operation_id):
        with self._machineSolveEvaluationLock:
            active = list(
                self._activeMachineSolveEvaluations.get(str(operation_id), ())
            )
        for evaluation in active:
            try:
                evaluation.terminate()
            except Exception:
                pass
        return len(active)

    # -------------------------------------------------------------------
    def _spawnMachineSolveEvaluation(
        self,
        group_measurements,
        *,
        layer_path,
        machine_path,
        roller_y_cals,
    ):
        context = multiprocessing.get_context("spawn")
        result_queue = context.Queue()
        process = context.Process(
            target=_machine_xy_evaluation_worker,
            args=(result_queue, group_measurements),
            kwargs={
                "layer_path": layer_path,
                "machine_path": machine_path,
                "roller_y_cals": tuple(float(value) for value in roller_y_cals[:4]),
            },
        )
        return _MachineXYEvaluationWorker(process, result_queue)

    # -------------------------------------------------------------------
    def _useIsolatedMachineSolveEvaluation(self):
        bound_method = getattr(self._projectMeasurement, "__func__", None)
        return bound_method is MachineGeometryCalibration._projectMeasurement

    # -------------------------------------------------------------------
    def _saveState(self):
        state = self._loadState()
        path = self._statePath()
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        temporary_path = path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
        last_error = None
        for attempt in range(6):
            try:
                os.replace(temporary_path, path)
                return
            except PermissionError as error:
                last_error = error
            except OSError as error:
                if getattr(error, "errno", None) not in (errno.EACCES, errno.EPERM):
                    raise
                last_error = error
            if attempt < 5:
                time.sleep(0.05 * (attempt + 1))
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        if last_error is not None:
            raise last_error

    # -------------------------------------------------------------------
    def _measurementRevision(self):
        return int(self._loadState().get("measurementRevision", 0))

    # -------------------------------------------------------------------
    def _bumpMeasurementRevision(self):
        state = self._loadState()
        state["measurementRevision"] = int(state.get("measurementRevision", 0)) + 1

    # -------------------------------------------------------------------
    def _layerDraft(self, layer, *, create=False):
        layer_key = _normalize_layer(layer)
        state = self._loadState()
        drafts = state.setdefault("layerDrafts", {})
        draft = drafts.get(layer_key)
        if draft is None and create:
            draft = {
                "zPlaneCalibration": None,
                "zPlaneSolve": None,
                "machineSolve": None,
                "lineOffsetOverrides": {},
            }
            drafts[layer_key] = draft
        return draft

    # -------------------------------------------------------------------
    def _activeLayer(self):
        layer = self._process.getRecipeLayer()
        if layer is None:
            raise ValueError("Load an active U or V recipe first.")
        return _normalize_layer(layer)

    # -------------------------------------------------------------------
    def _resolvedLayer(self, layer):
        active_layer = self._activeLayer()
        if layer is None:
            return active_layer
        normalized = _normalize_layer(layer)
        if normalized != active_layer:
            raise ValueError(
                "Requested layer "
                + normalized
                + " does not match active loaded recipe layer "
                + active_layer
                + "."
            )
        return normalized

    # -------------------------------------------------------------------
    def _machineCalibration(self):
        calibration = getattr(self._process, "_machineCalibration", None)
        if calibration is None:
            calibration = getattr(
                getattr(self._process, "controlStateMachine", None),
                "machineCalibration",
                None,
            )
        if calibration is None:
            raise ValueError("Machine calibration is not available.")
        return calibration

    # -------------------------------------------------------------------
    def _machineCalibrationPath(self):
        calibration = self._machineCalibration()
        output_path = getattr(calibration, "_outputFilePath", None)
        output_name = getattr(calibration, "_outputFileName", None)
        if output_path is None or output_name is None:
            raise ValueError("Machine calibration file path is not configured.")
        return str(pathlib.Path(output_path) / output_name)

    # -------------------------------------------------------------------
    def _activeLayerCalibration(self, layer):
        if hasattr(self._process, "_getActiveLayerCalibration"):
            return self._process._getActiveLayerCalibration(layer)

        calibration = None
        workspace = getattr(self._process, "workspace", None)
        if workspace is not None:
            calibration = getattr(workspace, "_calibration", None)
        if calibration is None:
            handler = getattr(self._process, "gCodeHandler", None)
            if handler is not None and hasattr(handler, "getLayerCalibration"):
                calibration = handler.getLayerCalibration()
        if calibration is None:
            raise ValueError(
                "No layer calibration is loaded for active layer " + str(layer) + "."
            )
        return calibration

    # -------------------------------------------------------------------
    def _syncLayerCalibrationHandlers(self, calibration):
        handlers = []
        direct_handler = getattr(self._process, "gCodeHandler", None)
        if direct_handler is not None:
            handlers.append(direct_handler)
        workspace_handler = getattr(
            getattr(self._process, "workspace", None), "_gCodeHandler", None
        )
        if workspace_handler is not None and workspace_handler not in handlers:
            handlers.append(workspace_handler)

        for handler in handlers:
            if not hasattr(handler, "useLayerCalibration"):
                continue
            loaded = (
                handler.getLayerCalibration()
                if hasattr(handler, "getLayerCalibration")
                else None
            )
            if loaded is calibration or loaded is None:
                handler.useLayerCalibration(calibration)
                continue
            if (
                str(getattr(loaded, "getLayerNames", lambda: None)()).strip().upper()
                == str(calibration.getLayerNames()).strip().upper()
            ):
                handler.useLayerCalibration(calibration)

    # -------------------------------------------------------------------
    def _templateService(self, layer):
        normalized = _normalize_layer(layer)
        if normalized == "U":
            return self._process.uTemplateRecipe
        return self._process.vTemplateRecipe

    # -------------------------------------------------------------------
    def _isGCodeExecutionActive(self):
        if hasattr(self._process, "isGCodeExecutionActive"):
            return bool(self._process.isGCodeExecutionActive())
        state = getattr(
            getattr(self._process, "controlStateMachine", None), "state", None
        )
        return getattr(state.__class__, "__name__", None) == "WindMode"

    # -------------------------------------------------------------------
    def _geometryMutationGuard(self):
        if self._isGCodeExecutionActive():
            raise ValueError(
                "Cannot change machine geometry during active G-code execution."
            )

    # -------------------------------------------------------------------
    def _currentCameraOffset(self):
        calibration = self._machineCalibration()
        offset_x = getattr(calibration, "cameraWireOffsetX", None)
        offset_y = getattr(calibration, "cameraWireOffsetY", None)
        if offset_x is None or offset_y is None:
            manual = getattr(self._process, "manualCalibration", None)
            if manual is not None and hasattr(manual, "_sharedCameraOffset"):
                offset_x, offset_y = manual._sharedCameraOffset()
            else:
                offset_x = 0.0 if offset_x is None else offset_x
                offset_y = 0.0 if offset_y is None else offset_y
        return (float(offset_x), float(offset_y))

    # -------------------------------------------------------------------
    def _currentPositions(self):
        io = self._process._io
        raw_camera_x = float(io.xAxis.getPosition())
        raw_camera_y = float(io.yAxis.getPosition())
        current_z = float(io.zAxis.getPosition()) if hasattr(io, "zAxis") else None
        effective_camera_x = float(self._process._xBacklash.getEffectiveX(raw_camera_x))
        return {
            "rawCameraX": raw_camera_x,
            "rawCameraY": raw_camera_y,
            "effectiveCameraX": effective_camera_x,
            "currentZ": current_z,
        }

    # -------------------------------------------------------------------
    def _extractAnchorToTargetLine(self, trace_payload):
        line_text = str((trace_payload or {}).get("line", "")).strip()
        start = line_text.find(_TRACE_LINE_REQUIRES)
        if start < 0:
            raise ValueError(
                "The last traced line is not a ~anchorToTarget(...) wrap line. Use a wrapping trace line."
            )
        depth = 0
        for index in range(start, len(line_text)):
            char = line_text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return line_text[start : index + 1]
        raise ValueError("Failed to parse the last traced ~anchorToTarget(...) line.")

    # -------------------------------------------------------------------
    def _measurementFromTrace(self, layer, *, capture_xy, capture_z):
        if not capture_xy and not capture_z:
            raise ValueError("Capture requires at least one observed channel.")

        trace_payload = getattr(
            self._process, "getLastInstructionTrace", lambda: None
        )()
        if not trace_payload:
            raise ValueError("No motion trace is available yet.")

        gcode_line = self._extractAnchorToTargetLine(trace_payload)
        command = parse_anchor_to_target_command(gcode_line)
        positions = self._currentPositions()
        camera_offset_x, camera_offset_y = self._currentCameraOffset()
        line_key = extract_line_key(trace_payload.get("line"))
        wrap_number = None
        wrap_line_number = None
        if line_key is not None:
            wrap_number, wrap_line_number = (
                int(line_key[1:-1].split(",")[0]),
                int(line_key[1:-1].split(",")[1]),
            )

        kind = (
            "same_side"
            if command.anchor_pin[:1] == command.target_pin[:1]
            else "alternating_side"
        )
        site_label = None
        try:
            site_label = _lookup_recipe_site(
                layer, command.anchor_pin, command.target_pin
            ).site_label
        except Exception:
            site_label = None
        roller_index = None
        if kind == "same_side":
            geometry = compute_pin_pair_tangent_geometry(
                layer=layer,
                pin_a=command.anchor_pin,
                pin_b=command.target_pin,
            )
            roller_index = int(geometry.roller_index)

        measurement = {
            "id": uuid.uuid4().hex,
            "layer": layer,
            "timestamp": str(self._process._systemTime.get()),
            "kind": kind,
            "gcodeLine": gcode_line,
            "traceLine": str(trace_payload.get("line", "")),
            "lineKey": line_key,
            "wrapNumber": wrap_number,
            "wrapLineNumber": wrap_line_number,
            "tracePayload": _deep_copy_json(trace_payload),
            "rawCameraX": positions["rawCameraX"],
            "rawCameraY": positions["rawCameraY"],
            "effectiveCameraX": positions["effectiveCameraX"],
            "currentZ": positions["currentZ"],
            "cameraOffsetX": camera_offset_x,
            "cameraOffsetY": camera_offset_y,
            "siteLabel": site_label,
            "actualWireX": (positions["effectiveCameraX"] if capture_xy else None),
            "actualWireY": (positions["rawCameraY"] if capture_xy else None),
            "actualZ": positions["currentZ"] if capture_z else None,
            "projectedX": (
                None
                if trace_payload.get("resultingWireTarget") is None
                else trace_payload["resultingWireTarget"].get("x")
            ),
            "projectedY": (
                None
                if trace_payload.get("resultingWireTarget") is None
                else trace_payload["resultingWireTarget"].get("y")
            ),
            "rollerIndex": roller_index,
        }
        return measurement

    # -------------------------------------------------------------------
    def recordMeasurement(self, *, layer=None, capture_xy=True, capture_z=False):
        target_layer = _normalize_layer(layer or self._activeLayer())
        measurement = self._measurementFromTrace(
            target_layer,
            capture_xy=bool(capture_xy),
            capture_z=bool(capture_z),
        )
        state = self._loadState()
        state["measurements"].append(measurement)
        self._bumpMeasurementRevision()
        self._saveState()
        return measurement

    # -------------------------------------------------------------------
    def recordJogMeasurement(
        self,
        *,
        layer,
        line_index,
        gcode_line,
        label,
        offset_id,
        commanded,
        actual,
        delta,
        previous_offset=None,
        new_offset=None,
        same_side=None,
    ):
        """Persist a jog-derived calibration sample alongside camera-trace samples.

        Stored as `kind = "jog_calibration"` so the existing solvers can
        distinguish it from automated trace measurements.  Returns the
        measurement dict that was appended.
        """
        target_layer = _normalize_layer(layer)
        line_key = extract_line_key(gcode_line)
        wrap_number = wrap_line_number = None
        if line_key is not None:
            inner = line_key[1:-1].split(",")
            try:
                wrap_number = int(inner[0])
                wrap_line_number = int(inner[1])
            except (IndexError, ValueError):
                wrap_number = wrap_line_number = None

        measurement = {
            "id": uuid.uuid4().hex,
            "layer": target_layer,
            "timestamp": str(self._process._systemTime.get()),
            "kind": "jog_calibration",
            "gcodeLine": gcode_line,
            "lineIndex": line_index,
            "lineKey": line_key,
            "wrapNumber": wrap_number,
            "wrapLineNumber": wrap_line_number,
            "siteLabel": label,
            "offsetId": offset_id,
            "sameSide": None if same_side is None else bool(same_side),
            "commandedX": float(commanded["x"]),
            "commandedY": float(commanded["y"]),
            "commandedZ": float(commanded["z"]),
            "actualWireX": float(actual["x"]),
            "actualWireY": float(actual["y"]),
            "actualZ": float(actual["z"]),
            "deltaX": float(delta["x"]),
            "deltaY": float(delta["y"]),
            "deltaZ": float(delta["z"]),
            "previousOffset": (
                None if previous_offset is None else dict(previous_offset)
            ),
            "newOffset": None if new_offset is None else dict(new_offset),
        }
        state = self._loadState()
        state["measurements"].append(measurement)
        self._bumpMeasurementRevision()
        self._saveState()
        self._log(
            "RECORD_JOG",
            "Jog calibration recorded for " + str(label),
            [target_layer, offset_id, dict(delta)],
        )
        return measurement

    # -------------------------------------------------------------------
    def deleteMeasurement(self, measurement_id):
        state = self._loadState()
        target_id = str(measurement_id)
        state["measurements"] = [
            measurement
            for measurement in state.get("measurements", [])
            if str(measurement.get("id")) != target_id
        ]
        self._bumpMeasurementRevision()
        self._saveState()
        return {"measurementId": target_id}

    # -------------------------------------------------------------------
    def _usableMeasurements(self, layer):
        normalized = _normalize_layer(layer)
        measurements = []
        for measurement in self._loadState().get("measurements", []):
            if str(measurement.get("layer")).strip().upper() != normalized:
                continue
            measurement = dict(measurement)
            same_side = measurement.get("sameSide")
            kind = measurement.get("kind")
            measurement["usableForLayerZ"] = (
                kind == "same_side" or (kind == "jog_calibration" and same_side is True)
            ) and measurement.get("actualZ") is not None
            measurement["usableForMachineXY"] = (
                measurement.get("actualWireX") is not None
                and measurement.get("actualWireY") is not None
                and measurement.get("lineKey") is not None
                and measurement.get("gcodeLine")
            )
            measurements.append(measurement)
        return measurements

    # -------------------------------------------------------------------
    def solveLayerZ(self, layer=None):
        target_layer = self._resolvedLayer(layer)
        calibration = self._activeLayerCalibration(target_layer)
        measurements = []
        for measurement in self._usableMeasurements(target_layer):
            if not measurement["usableForLayerZ"]:
                continue
            measurements.append(
                LayerZPlaneMeasurement(
                    gcode_line=str(measurement["gcodeLine"]),
                    layer=target_layer,
                    actual_x=float(measurement.get("actualWireX", 0.0) or 0.0),
                    actual_y=float(measurement.get("actualWireY", 0.0) or 0.0),
                    actual_z=float(measurement["actualZ"]),
                )
            )

        if measurements:
            fitted = fit_layer_z_plane(
                measurements,
                machine_calibration_path=self._machineCalibrationPath(),
                layer_calibration_path=calibration.getFullFileName(),
            )
        else:
            fitted = empty_layer_z_plane_calibration()

        draft = self._layerDraft(target_layer, create=True)
        draft["zPlaneCalibration"] = layer_z_plane_calibration_to_dict(fitted)
        draft["zPlaneSolve"] = {
            "measurementRevision": self._measurementRevision(),
            "measurementIds": [
                measurement["id"]
                for measurement in self._usableMeasurements(target_layer)
                if measurement["usableForLayerZ"]
            ],
        }
        self._saveState()
        return draft["zPlaneCalibration"]

    # -------------------------------------------------------------------
    def cancelMachineXY(self, layer=None):
        target_layer = self._resolvedLayer(layer)
        status = self._reconcileMachineSolveStatus(target_layer)
        if status is None:
            return {
                "layer": target_layer,
                "canceled": False,
                "message": "No Machine XY solve is active.",
            }

        current_status = str(status.get("status", "")).strip().lower()
        operation_id = status.get("operationId")
        if current_status not in ("running", "cancel_requested") or not operation_id:
            return {
                "layer": target_layer,
                "canceled": False,
                "message": "No Machine XY solve is active.",
            }

        self._cancelRequestedMachineSolveOperationIds.add(str(operation_id))
        updated_status = self._updateMachineSolveStatus(
            target_layer,
            operationId=operation_id,
            status="cancel_requested",
            message="Cancel requested. Stopping after the current evaluation batch.",
            cancelRequested=True,
            cancelRequestedAt=self._timestamp(),
        )
        self._log(
            "SOLVE_MACHINE_XY_CANCEL_REQUESTED",
            "Machine XY solve cancel requested.",
            [operation_id, target_layer],
        )
        return {
            "layer": target_layer,
            "canceled": True,
            "message": "Cancel requested.",
            "status": updated_status,
        }

    # -------------------------------------------------------------------
    def killMachineXY(self, layer=None):
        target_layer = self._resolvedLayer(layer)
        status = self._reconcileMachineSolveStatus(target_layer)
        if status is None:
            return {
                "layer": target_layer,
                "killed": False,
                "message": "No Machine XY solve is active.",
            }

        current_status = str(status.get("status", "")).strip().lower()
        operation_id = status.get("operationId")
        if (
            current_status not in ("running", "cancel_requested", "kill_requested")
            or not operation_id
        ):
            return {
                "layer": target_layer,
                "killed": False,
                "message": "No Machine XY solve is active.",
            }

        self._killRequestedMachineSolveOperationIds.add(str(operation_id))
        terminated_evaluations = self._terminateActiveMachineSolveEvaluations(
            operation_id
        )
        updated_status = self._updateMachineSolveStatus(
            target_layer,
            operationId=operation_id,
            status="kill_requested",
            message="Kill requested. Terminating all active evaluations.",
            cancelRequested=True,
            cancelRequestedAt=self._timestamp(),
            killRequested=True,
            killRequestedAt=self._timestamp(),
            terminatedEvaluations=int(terminated_evaluations),
        )
        self._log(
            "SOLVE_MACHINE_XY_KILL_REQUESTED",
            "Machine XY solve kill requested.",
            [operation_id, target_layer, terminated_evaluations],
        )
        return {
            "layer": target_layer,
            "killed": True,
            "message": "Kill requested.",
            "terminatedEvaluations": int(terminated_evaluations),
            "status": updated_status,
        }

    # -------------------------------------------------------------------
    def applyLayerZ(self, layer=None):
        self._geometryMutationGuard()
        target_layer = self._resolvedLayer(layer)
        draft = self._layerDraft(target_layer)
        if draft is None or draft.get("zPlaneCalibration") is None:
            raise ValueError("Run layer Z solve before applying.")
        fitted = layer_z_plane_calibration_from_dict(draft["zPlaneCalibration"])
        if not has_valid_layer_z_plane_fit(fitted):
            raise ValueError("Current layer Z draft fit is not valid.")

        calibration = self._activeLayerCalibration(target_layer)
        calibration.zPlaneCalibration = fitted
        apply_layer_z_plane_calibration(calibration, fitted)
        calibration.save()
        clear_uv_head_target_caches(layer_calibration=True, machine_calibration=False)
        self._syncLayerCalibrationHandlers(calibration)
        return layer_z_plane_calibration_to_dict(fitted)

    # -------------------------------------------------------------------
    def _liveLayerCalibrationCopy(self, layer):
        calibration = self._activeLayerCalibration(layer)
        return calibration.copy()

    # -------------------------------------------------------------------
    def _candidateLayerCalibrationPath(self, layer):
        draft = self._layerDraft(layer)
        if draft is None or draft.get("zPlaneCalibration") is None:
            calibration = self._activeLayerCalibration(layer)
            return calibration.getFullFileName()

        fitted = layer_z_plane_calibration_from_dict(draft["zPlaneCalibration"])
        if not has_valid_layer_z_plane_fit(fitted):
            calibration = self._activeLayerCalibration(layer)
            return calibration.getFullFileName()

        temporary_directory = self._tempDirectory()
        if not os.path.isdir(temporary_directory):
            os.makedirs(temporary_directory)
        temporary_path = os.path.join(temporary_directory, f"{layer}_solve_layer.json")
        calibration = self._liveLayerCalibrationCopy(layer)
        calibration.zPlaneCalibration = fitted
        apply_layer_z_plane_calibration(calibration, fitted)
        calibration.save(temporary_directory, os.path.basename(temporary_path))
        clear_uv_head_target_caches(layer_calibration=True, machine_calibration=False)
        return temporary_path

    # -------------------------------------------------------------------
    def _candidateMachineCalibrationPath(self, roller_y_cals, *, camera_offset=None):
        roller_tuple = tuple(float(value) for value in roller_y_cals[:4])
        cache_key = (roller_tuple,)
        if cache_key in _CALIBRATION_PATH_CACHE:
            cached_path = _CALIBRATION_PATH_CACHE[cache_key]
            if os.path.isfile(cached_path):
                return cached_path
        live = self._machineCalibration()
        temporary_directory = self._tempDirectory()
        if not os.path.isdir(temporary_directory):
            os.makedirs(temporary_directory)
        temporary_name = "machine_geometry_solve_machine_" + uuid.uuid4().hex + ".json"
        candidate = MachineCalibration(temporary_directory, temporary_name)
        candidate._from_dict(copy.deepcopy(live._to_dict()))
        candidate.rollerArmCalibration = RollerArmCalibration(
            measurements=[],
            fitted_y_cals=roller_tuple,
            center_displacement=0.0,
            arm_tilt_rad=0.0,
        )
        temporary_path = os.path.join(temporary_directory, temporary_name)
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(candidate._to_dict(), handle, indent=2)
        _CALIBRATION_PATH_CACHE[cache_key] = temporary_path
        clear_uv_head_target_caches(layer_calibration=False, machine_calibration=True)
        return temporary_path

    # -------------------------------------------------------------------
    def _removeTemporaryCandidatePath(self, path):
        # Remove from cache if present
        keys_to_remove = [k for k, v in _CALIBRATION_PATH_CACHE.items() if v == path]
        for key in keys_to_remove:
            del _CALIBRATION_PATH_CACHE[key]
        try:
            os.unlink(path)
        except OSError:
            pass

    # -------------------------------------------------------------------
    def _candidateMachineCalibrationObject(self, roller_y_cals):
        roller_tuple = tuple(float(value) for value in roller_y_cals[:4])
        cache_key = (roller_tuple,)
        if cache_key in _CALIBRATION_OBJECT_CACHE:
            return _CALIBRATION_OBJECT_CACHE[cache_key]
        live = self._machineCalibration()
        candidate = MachineCalibration.__new__(MachineCalibration)
        candidate._from_dict(copy.deepcopy(live._to_dict()))
        candidate.rollerArmCalibration = RollerArmCalibration(
            measurements=[],
            fitted_y_cals=(
                roller_tuple[0],
                roller_tuple[1],
                roller_tuple[2],
                roller_tuple[3],
            ),
            center_displacement=0.0,
            arm_tilt_rad=0.0,
        )
        _CALIBRATION_OBJECT_CACHE[cache_key] = candidate
        return candidate

    # -------------------------------------------------------------------
    def _projectMeasurement(
        self,
        measurement,
        *,
        layer_path,
        machine_path=None,
        roller_y_cals,
        _layer_calibration=None,
        _machine_calibration=None,
    ):
        payload = _project_machine_xy_measurement_payload(
            measurement,
            layer_path=layer_path,
            machine_path=machine_path,
            roller_y_cals=roller_y_cals,
            _layer_calibration=_layer_calibration,
            _machine_calibration=_machine_calibration,
        )
        return _translate_projection_payload(payload, (0.0, 0.0))

    # -------------------------------------------------------------------
    def _xyConflictError(self, usable_measurements):
        by_line_key = {}
        for measurement in usable_measurements:
            line_key = str(measurement["lineKey"])
            entry = by_line_key.setdefault(line_key, measurement)
            if entry is measurement:
                continue
            delta = abs(
                float(entry["actualWireX"]) - float(measurement["actualWireX"])
            ) + abs(float(entry["actualWireY"]) - float(measurement["actualWireY"]))
            if delta > 1e-6:
                return (
                    "Multiple XY measurements target line "
                    + line_key
                    + ". Prune duplicates before solving machine XY."
                )
        return None

    # -------------------------------------------------------------------
    def _sanityCheckLineOffsets(self, layer, machine_draft, line_offset_overrides):
        usable = [
            measurement
            for measurement in self._usableMeasurements(layer)
            if measurement["usableForMachineXY"]
        ]
        if not usable or not line_offset_overrides:
            return {
                "ok": True,
                "checkedCount": 0,
                "maxDiscrepancyX": 0.0,
                "maxDiscrepancyY": 0.0,
                "discrepancyCount": 0,
                "discrepancies": [],
            }

        roller_y_cals = tuple(
            float(value) for value in machine_draft["rollerYCals"][:4]
        )
        camera_offset = (
            float(machine_draft["cameraWireOffsetX"]),
            float(machine_draft["cameraWireOffsetY"]),
        )

        layer_path = self._candidateLayerCalibrationPath(layer)
        machine_calibration = self._candidateMachineCalibrationObject(roller_y_cals)

        max_discrepancy_x = 0.0
        max_discrepancy_y = 0.0
        checked = 0
        discrepancies = []

        for measurement in usable:
            line_key = measurement.get("lineKey")
            if line_key is None:
                continue
            try:
                normalized_key = normalize_line_key(line_key)
            except Exception:
                continue
            override = line_offset_overrides.get(normalized_key)
            if override is None:
                continue

            payload = _project_machine_xy_measurement_payload(
                measurement,
                layer_path=layer_path,
                roller_y_cals=roller_y_cals,
                _machine_calibration=machine_calibration,
            )
            translated = _translate_projection_payload(payload, camera_offset)
            # Same implied-pin-shift residual the solver writes as the
            # override, so this consistency check compares like with like.
            residual_x, residual_y = _implied_pin_offset(
                float(measurement["actualWireX"]),
                float(measurement["actualWireY"]),
                translated,
            )

            override_x = float(override["x"])
            override_y = float(override["y"])
            # The stored override is constrained to the corner's natural axis
            # (off-axis component dropped, on-axis quantised to 0.1 mm).  Apply
            # the same constraint to the freshly computed residual so the
            # deliberately-zeroed off-axis component is not mistaken for an
            # inconsistency -- compare on-axis to on-axis.
            natural_axis = _line_natural_axis(layer, measurement)
            if natural_axis in ("x", "y"):
                residual_x, residual_y = enforce_offset_axes(
                    residual_x, residual_y, natural_axis
                )
                override_x, override_y = enforce_offset_axes(
                    override_x, override_y, natural_axis
                )

            dx = abs(residual_x - override_x)
            dy = abs(residual_y - override_y)

            checked += 1
            max_discrepancy_x = max(max_discrepancy_x, dx)
            max_discrepancy_y = max(max_discrepancy_y, dy)

            if dx > _SANITY_CHECK_TOLERANCE_MM or dy > _SANITY_CHECK_TOLERANCE_MM:
                discrepancies.append(
                    {
                        "lineKey": normalized_key,
                        "measurementId": str(measurement["id"]),
                        "residualX": float(residual_x),
                        "residualY": float(residual_y),
                        "lineOffsetX": float(override_x),
                        "lineOffsetY": float(override_y),
                        "discrepancyX": float(dx),
                        "discrepancyY": float(dy),
                    }
                )

        return {
            "ok": len(discrepancies) == 0,
            "checkedCount": checked,
            "maxDiscrepancyX": float(max_discrepancy_x),
            "maxDiscrepancyY": float(max_discrepancy_y),
            "discrepancyCount": len(discrepancies),
            "discrepancies": discrepancies[:10],
        }

    # -------------------------------------------------------------------
    def _commandTargetHead(
        self,
        measurement,
        *,
        camera_offset,
        corner_offset,
        roller_y_cals,
        layer_path,
        machine_calibration,
    ):
        """End-to-end commanded head target for one line under a calibration.

        Rewrites the measurement's ``~anchorToTarget`` offset to ``corner_offset``
        -- exactly what recipe regeneration bakes in for that corner -- and
        projects the line through the real G-code pipeline with ``camera_offset``
        applied.  Returns the commanded head position ``(x, y)``: the literal
        winder move, before head/roller compensation resolves the wire contact.
        """
        synthetic = dict(measurement)
        synthetic["gcodeLine"] = set_anchor_to_target_offset(
            str(measurement["gcodeLine"]),
            float(corner_offset[0]),
            float(corner_offset[1]),
            normalize_line_text_fn=lambda text: text,
        )
        payload = _project_machine_xy_measurement_payload(
            synthetic,
            layer_path=layer_path,
            roller_y_cals=roller_y_cals,
            _machine_calibration=machine_calibration,
            cameraWireOffset=(float(camera_offset[0]), float(camera_offset[1])),
        )
        return (float(payload["projectedHeadX"]), float(payload["projectedHeadY"]))

    # -------------------------------------------------------------------
    def _checkCommandTargetInvariance(
        self, layer, machine_draft, line_offset_overrides
    ):
        """Confirm the drafted calibration does not move any commanded head target.

        For every usable calibration-point line, re-project the ``~anchorToTarget``
        head command end-to-end under the *live* calibration (current camera-wire
        offset + current per-corner offset) and under the *drafted* calibration
        (solved camera-wire offset + solved per-corner offset, axis-enforced and
        quantised exactly as ``setOffset`` will store it).  Recalibration only
        re-expresses the same wrap geometry, so the two head commands should
        coincide; any line that moves more than ``_COMMAND_TARGET_TOLERANCE_MM`` on
        either axis is a discrepancy that blocks apply.

        No-ops (returns a passing zero-count result) when there are no usable
        measurements or none of them map to a solved corner offset.
        """
        normalized_layer = _normalize_layer(layer)
        usable = _most_recent_per_corner(
            [
                measurement
                for measurement in self._usableMeasurements(normalized_layer)
                if measurement["usableForMachineXY"]
            ]
        )
        empty = {
            "ok": True,
            "checkedCount": 0,
            "maxDiscrepancyX": 0.0,
            "maxDiscrepancyY": 0.0,
            "discrepancyCount": 0,
            "discrepancies": [],
            "toleranceMm": _COMMAND_TARGET_TOLERANCE_MM,
        }
        if not usable:
            return empty

        template_service = self._templateService(normalized_layer)
        label_to_id = getattr(template_service, "LABEL_TO_OFFSET_ID", {}) or {}
        natural_axis_by_id = getattr(template_service, "OFFSET_NATURAL_AXIS", {}) or {}
        live_offsets = template_service.getState().get("offsets", {}) or {}
        # The drafted per-corner offsets that apply would write (one per corner,
        # fanned across the corner's measured lines), keyed by corner offset id.
        draft_corners = _corner_offsets_from_overrides(
            template_service, line_offset_overrides or {}
        )
        if not draft_corners:
            return empty

        old_camera = self._currentCameraOffset()
        new_camera = (
            float(machine_draft["cameraWireOffsetX"]),
            float(machine_draft["cameraWireOffsetY"]),
        )
        # Roller calibrations are not touched by apply, so both sides project
        # against the live roller cals -- only camera offset and corner offset
        # differ between the live and drafted calibrations.
        machine_calibration = self._machineCalibration()
        roller_y_cals = _live_roller_y_cals(machine_calibration)
        layer_path = self._candidateLayerCalibrationPath(normalized_layer)
        candidate_calibration = self._candidateMachineCalibrationObject(roller_y_cals)

        max_dx = 0.0
        max_dy = 0.0
        checked = 0
        discrepancies = []
        for measurement in usable:
            site_label = _measurement_site_label(measurement)
            offset_id = label_to_id.get(site_label)
            if offset_id is None or offset_id not in draft_corners:
                continue
            # Compare on the corner's natural axis, quantised to the same 0.1 mm
            # grid the offset store uses, so neither the live nor the drafted
            # corner carries an off-axis component the recipe would never apply.
            natural_axis = natural_axis_by_id.get(offset_id, "x")
            live = live_offsets.get(offset_id) or {}
            old_corner = enforce_offset_axes(
                float(live.get("x", 0.0) or 0.0),
                float(live.get("y", 0.0) or 0.0),
                natural_axis,
            )
            draft_corner = draft_corners[offset_id]
            new_corner = enforce_offset_axes(
                float(draft_corner.get("x", 0.0) or 0.0),
                float(draft_corner.get("y", 0.0) or 0.0),
                natural_axis,
            )

            old_head = self._commandTargetHead(
                measurement,
                camera_offset=old_camera,
                corner_offset=old_corner,
                roller_y_cals=roller_y_cals,
                layer_path=layer_path,
                machine_calibration=candidate_calibration,
            )
            new_head = self._commandTargetHead(
                measurement,
                camera_offset=new_camera,
                corner_offset=new_corner,
                roller_y_cals=roller_y_cals,
                layer_path=layer_path,
                machine_calibration=candidate_calibration,
            )

            dx = abs(new_head[0] - old_head[0])
            dy = abs(new_head[1] - old_head[1])
            checked += 1
            max_dx = max(max_dx, dx)
            max_dy = max(max_dy, dy)
            if dx > _COMMAND_TARGET_TOLERANCE_MM or dy > _COMMAND_TARGET_TOLERANCE_MM:
                discrepancies.append(
                    {
                        "lineKey": measurement.get("lineKey"),
                        "measurementId": str(measurement["id"]),
                        "siteLabel": site_label,
                        "offsetId": offset_id,
                        "oldHeadX": float(old_head[0]),
                        "oldHeadY": float(old_head[1]),
                        "newHeadX": float(new_head[0]),
                        "newHeadY": float(new_head[1]),
                        "discrepancyX": float(dx),
                        "discrepancyY": float(dy),
                    }
                )

        return {
            "ok": len(discrepancies) == 0,
            "checkedCount": checked,
            "maxDiscrepancyX": float(max_dx),
            "maxDiscrepancyY": float(max_dy),
            "discrepancyCount": len(discrepancies),
            "discrepancies": discrepancies[:10],
            "toleranceMm": _COMMAND_TARGET_TOLERANCE_MM,
        }

    # -------------------------------------------------------------------
    def _fitRollersFromMeasurements(
        self, measurements, *, layer_path, initial_roller_y_cals
    ):
        """Closed-form per-roller y-cal fit from same-side measurements.

        Each same-side measurement back-solves its roller's y-offset in closed
        form (``roller_y_cal_from_measurement``); values are grouped by roller
        index and averaged.  Rollers with no measurement keep their initial
        (live/nominal) value.  The back-solve is independent of the camera
        offset and of the roller y-cals themselves, so this runs once up front
        with no iteration.
        """
        machine_calibration = self._machineCalibration()
        machine_path = self._machineCalibrationPath()
        head_arm_length = float(machine_calibration.headArmLength)
        head_roller_radius = float(machine_calibration.headRollerRadius)
        by_index: dict[int, list[float]] = {}
        for measurement in measurements:
            actual_x = measurement.get("actualWireX")
            actual_y = measurement.get("actualWireY")
            if actual_x is None or actual_y is None:
                continue
            try:
                command = parse_anchor_to_target_command(
                    _extract_anchor_to_target_command_text(measurement["gcodeLine"])
                )
            except Exception:
                continue
            if str(command.anchor_pin)[:1] != str(command.target_pin)[:1]:
                # Alternating-side measurements carry no roller contact.
                continue
            try:
                roller_index, y_cal = roller_y_cal_from_measurement(
                    layer=str(measurement["layer"]),
                    anchor_pin=command.anchor_pin,
                    target_pin=command.target_pin,
                    actual_x=float(actual_x),
                    actual_y=float(actual_y),
                    head_arm_length=head_arm_length,
                    head_roller_radius=head_roller_radius,
                    machine_calibration_path=machine_path,
                    layer_calibration_path=layer_path,
                )
            except Exception:
                continue
            if 0 <= int(roller_index) < 4:
                by_index.setdefault(int(roller_index), []).append(float(y_cal))
        fitted = [float(value) for value in initial_roller_y_cals[:4]]
        for index, values in by_index.items():
            if values:
                fitted[index] = float(sum(values) / len(values))
        return tuple(fitted)

    # -------------------------------------------------------------------
    def _evaluateMachineXY(
        self,
        measurements,
        *,
        layer,
        operation_id,
        layer_path,
        nominal_roller_y,
        current_camera_offset,
        initial_roller_y_cals,
        live_line_offsets=None,
        progress_callback=None,
        fit_rollers=False,
    ):
        measurements = list(measurements)
        measurement_order = [str(measurement["id"]) for measurement in measurements]
        measurement_site_labels = {}
        # Natural offset axis per measurement (head/foot in Y, top/bottom in X),
        # cached once so summarize_results can project residuals without re-parsing
        # the command on every SGD evaluation.
        measurement_natural_axes = {}
        # Offset already baked into each measured ~anchorToTarget line.  The
        # measurement is recorded against the *live* recipe, so the line carries
        # the live per-corner offset (e.g. ``offset=(0,-2.5)``).  The projection
        # runs through that offset, so the residual it yields is only the
        # *leftover* correction; the absolute offset we must write back is this
        # baked (live) offset plus that residual.  Parsed once here so
        # summarize_results need not re-parse on every evaluation.
        measurement_baked_offsets: dict[str, tuple[float, float]] = {}
        site_order = []
        for measurement in measurements:
            site_label = _measurement_site_label(measurement)
            if not site_label:
                site_label = str(measurement.get("lineKey") or measurement.get("id"))
            measurement_site_labels[str(measurement["id"])] = site_label
            measurement_natural_axes[str(measurement["id"])] = _line_natural_axis(
                layer, measurement
            )
            measurement_baked_offsets[str(measurement["id"])] = (
                _baked_anchor_to_target_offset(measurement.get("gcodeLine"))
            )
            if site_label not in site_order:
                site_order.append(site_label)

        # The live per-corner offset baseline now comes from the offset baked
        # into each measured line (see measurement_baked_offsets) rather than the
        # separate per-line override store, so the recorded recipe state is the
        # single source of truth for "what is live".  The ``live_line_offsets``
        # argument is retained for API compatibility but no longer consulted.
        _ = live_line_offsets

        # Optional roller fit (Block 0): when enabled, back-solve each roller's
        # y-cal from its same-side measurements in closed form and freeze the
        # result for the camera-offset solve below.  When disabled (default),
        # the live/nominal rollers pass through unchanged.
        if fit_rollers and measurements:
            initial_roller_y_cals = self._fitRollersFromMeasurements(
                measurements,
                layer_path=layer_path,
                initial_roller_y_cals=initial_roller_y_cals,
            )

        projection_cache: dict[tuple[str, tuple[float, ...]], dict] = {}
        initial_vector = [
            float(current_camera_offset[0]),
            float(current_camera_offset[1]),
            *[float(value) for value in initial_roller_y_cals[:4]],
        ]
        # Roller calibrations are held constant during the camera-offset solve
        # (either frozen at the live value, or at the Block 0 fit above) --
        # clamp them tightly to their value so any stray drift is squashed.
        lower_bounds = [
            float(initial_vector[0]) - _CAMERA_OFFSET_BOUND_MM,
            float(initial_vector[1]) - _CAMERA_OFFSET_BOUND_MM,
            *[float(value) for value in initial_roller_y_cals[:4]],
        ]
        upper_bounds = [
            float(initial_vector[0]) + _CAMERA_OFFSET_BOUND_MM,
            float(initial_vector[1]) + _CAMERA_OFFSET_BOUND_MM,
            *[float(value) for value in initial_roller_y_cals[:4]],
        ]

        def clamp_vector(vector):
            return [
                _clamp(float(value), float(lower), float(upper))
                for value, lower, upper in zip(vector[:6], lower_bounds, upper_bounds)
            ]

        def axis_within_bounds(axis_index, value):
            return (
                float(lower_bounds[axis_index]) - _EPSILON
                <= float(value)
                <= float(upper_bounds[axis_index]) + _EPSILON
            )

        def objective_tuple(summary):
            return (
                int(summary.get("violationCount", 0)),
                float(summary.get("violationMagnitude", 0.0)),
                float(summary.get("loss", 0.0)),
            )

        def objective_better(candidate, incumbent):
            return objective_tuple(candidate) < objective_tuple(incumbent)

        def format_violation(violation):
            line_key = violation.get("lineKey")
            line_label = (
                "line " + str(line_key)
                if line_key is not None
                else "measurement " + str(violation["measurementId"])
            )
            return (
                line_label
                + " site="
                + str(violation["siteLabel"])
                + " measurement="
                + str(violation["measurementId"])
                + " deltaX="
                + "{0:.3f}".format(float(violation["deltaX"]))
                + " deltaY="
                + "{0:.3f}".format(float(violation["deltaY"]))
                + " (offset="
                + "{0:.3f},{1:.3f}".format(
                    float(violation["offsetX"]), float(violation["offsetY"])
                )
                + " live="
                + "{0:.3f},{1:.3f})".format(
                    float(violation["liveOffsetX"]),
                    float(violation["liveOffsetY"]),
                )
            )

        def _cached_project(measurement, roller_y_cals, camera_offset):
            cache_key = (
                str(measurement["gcodeLine"]),
                tuple(float(v) for v in roller_y_cals[:4]),
            )
            if cache_key in projection_cache:
                cached = projection_cache[cache_key]
                if "projectedHeadX" in cached:
                    return _translate_projection_payload(cached, camera_offset)
                return {
                    "projectedX": float(cached["projectedX"]) + float(camera_offset[0]),
                    "projectedY": float(cached["projectedY"]) + float(camera_offset[1]),
                }
            if self._useIsolatedMachineSolveEvaluation():
                machine_path = self._candidateMachineCalibrationPath(roller_y_cals)
                try:
                    payload = _project_machine_xy_measurement_payload(
                        measurement,
                        layer_path=layer_path,
                        machine_path=machine_path,
                        roller_y_cals=roller_y_cals,
                        _layer_calibration=layer_calibration,
                    )
                finally:
                    self._removeTemporaryCandidatePath(machine_path)
            else:
                machine_calibration_obj = self._candidateMachineCalibrationObject(
                    roller_y_cals
                )
                payload = self._projectMeasurement(
                    measurement,
                    layer_path=layer_path,
                    roller_y_cals=roller_y_cals,
                    _layer_calibration=layer_calibration,
                    _machine_calibration=machine_calibration_obj,
                )
            projection_cache[cache_key] = dict(payload)
            if "projectedHeadX" in payload:
                return _translate_projection_payload(payload, camera_offset)
            return {
                "projectedX": float(payload["projectedX"]) + float(camera_offset[0]),
                "projectedY": float(payload["projectedY"]) + float(camera_offset[1]),
            }

        def project_group(group_measurements, roller_y_cals, camera_offset):
            if not group_measurements:
                return []
            self._raiseIfMachineSolveCancelled(layer, operation_id)
            self._raiseIfMachineSolveKilled(operation_id)
            if not self._useIsolatedMachineSolveEvaluation():
                results = []
                for measurement in group_measurements:
                    self._raiseIfMachineSolveCancelled(layer, operation_id)
                    self._raiseIfMachineSolveKilled(operation_id)
                    projection = _cached_project(
                        measurement, roller_y_cals, camera_offset
                    )
                    results.append((measurement, projection))
                return results
            machine_path = self._candidateMachineCalibrationPath(roller_y_cals)
            try:
                evaluation = self._spawnMachineSolveEvaluation(
                    group_measurements,
                    layer_path=layer_path,
                    machine_path=machine_path,
                    roller_y_cals=roller_y_cals,
                )
                self._registerActiveMachineSolveEvaluation(operation_id, evaluation)
                evaluation.start()
                payload = None
                try:
                    while payload is None:
                        self._raiseIfMachineSolveKilled(operation_id)
                        payload = evaluation.poll(timeout=0.1)
                        if payload is not None:
                            break
                        if not evaluation.is_alive():
                            payload = evaluation.poll(timeout=0.0)
                            break
                    self._raiseIfMachineSolveKilled(operation_id)
                    self._raiseIfMachineSolveCancelled(layer, operation_id)
                    if payload is None:
                        raise RuntimeError(
                            "Machine XY evaluation exited before returning a result."
                        )
                    if not bool(payload.get("ok")):
                        raise RuntimeError(
                            "Machine XY evaluation failed: "
                            + str(payload.get("error") or "unknown error")
                        )
                    translated_results = []
                    for measurement, projection_payload in list(
                        payload.get("results") or []
                    ):
                        translated_results.append(
                            (
                                measurement,
                                _translate_projection_payload(
                                    projection_payload, camera_offset
                                ),
                            )
                        )
                    return translated_results
                finally:
                    self._unregisterActiveMachineSolveEvaluation(
                        operation_id, evaluation
                    )
                    evaluation.close()
            finally:
                self._removeTemporaryCandidatePath(machine_path)

        def summarize_results(results, camera_offset):
            camera_x = float(camera_offset[0])
            camera_y = float(camera_offset[1])
            by_measurement = {}
            by_site_label = {}
            total_loss = 0.0
            violation_count = 0
            violation_magnitude = 0.0
            violations = []
            for measurement, projection in results:
                site_label = measurement_site_labels.get(str(measurement["id"]))
                if not site_label:
                    site_label = str(
                        measurement.get("lineKey") or measurement.get("id")
                    )
                line_key = measurement.get("lineKey")
                if line_key is not None:
                    try:
                        line_key = normalize_line_key(line_key)
                    except Exception:
                        line_key = str(line_key)
                actual_wire_x = measurement.get("actualWireX")
                actual_wire_y = measurement.get("actualWireY")
                if actual_wire_x is not None:
                    observed_x = float(actual_wire_x)
                    observed_y = float(actual_wire_y)
                else:
                    observed_x = float(measurement["effectiveCameraX"])
                    observed_y = float(measurement["rawCameraY"])
                residual_x, residual_y = _implied_pin_offset(
                    observed_x, observed_y, projection
                )
                # The projection runs through the offset already baked into the
                # measured line (the live per-corner offset), so the implied
                # residual is only the leftover correction.  The absolute offset
                # we write back is that baked (live) offset plus the residual --
                # writing the residual alone would drop the live offset and move
                # every commanded head by its magnitude, which is exactly what
                # the command-target invariance gate catches.  The live baseline
                # for the change/violation checks is therefore the baked offset.
                baked_x, baked_y = measurement_baked_offsets.get(
                    str(measurement["id"]), (0.0, 0.0)
                )
                offset_x = float(baked_x) + float(residual_x)
                offset_y = float(baked_y) + float(residual_y)
                live_x, live_y = float(baked_x), float(baked_y)
                # A corner offset can only ever be written along its target pin's
                # natural axis -- the off-axis component is dropped at apply (see
                # enforce_offset_axes).  Project the residual onto that axis
                # *before* it feeds the loss so the solver minimises only the part
                # it can actually represent, and so the camera offset is not pulled
                # off-axis chasing a residual the per-corner offset will discard.
                # That discarded off-axis residual is exactly what resurfaces as a
                # commanded-head shift and trips the command-target invariance gate.
                # Quantisation is deferred to write time to keep the loss surface
                # smooth for SGD.
                natural_axis = measurement_natural_axes.get(str(measurement["id"]))
                if natural_axis == "x":
                    offset_y = 0.0
                    live_y = 0.0
                elif natural_axis == "y":
                    offset_x = 0.0
                    live_x = 0.0
                delta_x = float(offset_x) - float(live_x)
                delta_y = float(offset_y) - float(live_y)
                excess_x = max(0.0, abs(delta_x) - _MAX_LINE_OFFSET_DELTA_X_MM)
                excess_y = max(0.0, abs(delta_y) - _MAX_LINE_OFFSET_DELTA_Y_MM)
                summary = {
                    "measurementId": str(measurement["id"]),
                    "siteLabel": site_label,
                    "lineKey": line_key,
                    "measurement": measurement,
                    "projection": projection,
                    "offsetX": float(offset_x),
                    "offsetY": float(offset_y),
                    "liveOffsetX": float(live_x),
                    "liveOffsetY": float(live_y),
                    "deltaX": float(delta_x),
                    "deltaY": float(delta_y),
                    "valid": bool(excess_x <= _EPSILON and excess_y <= _EPSILON),
                    "violationMagnitude": float(excess_x + excess_y),
                }
                if not summary["valid"]:
                    violation = {
                        "measurementId": str(measurement["id"]),
                        "siteLabel": site_label,
                        "lineKey": line_key,
                        "offsetX": float(offset_x),
                        "offsetY": float(offset_y),
                        "liveOffsetX": float(live_x),
                        "liveOffsetY": float(live_y),
                        "deltaX": float(delta_x),
                        "deltaY": float(delta_y),
                        "excessX": float(excess_x),
                        "excessY": float(excess_y),
                    }
                    summary["violation"] = violation
                    violation_count += 1
                    violation_magnitude += float(summary["violationMagnitude"])
                    violations.append(violation)
                by_measurement[str(measurement["id"])] = summary
                by_site_label.setdefault(site_label, []).append(summary)
                # Loss is the squared *change from the live offset* (see
                # newton_axis): the camera solve and the baseline-vs-solved
                # selection both score how far the recalibration moves the
                # per-corner offsets, not their absolute size, so a solve that
                # merely confirms the current placement scores zero and the
                # camera stays put.
                total_loss += (delta_x * delta_x) + (delta_y * delta_y)
            violations.sort(
                key=lambda item: (
                    -(float(item["excessX"]) + float(item["excessY"])),
                    -max(abs(float(item["deltaX"])), abs(float(item["deltaY"]))),
                    str(item["measurementId"]),
                )
            )
            return {
                "loss": float(total_loss),
                "by_measurement": by_measurement,
                "by_site_label": by_site_label,
                "valid": violation_count == 0,
                "violationCount": int(violation_count),
                "violationMagnitude": float(violation_magnitude),
                "violations": violations,
            }

        def ordered_summaries(summary_by_measurement):
            return [
                summary_by_measurement[measurement_id]
                for measurement_id in measurement_order
                if measurement_id in summary_by_measurement
            ]

        def build_site_offset_items(by_site_label):
            items = []
            for site_label in site_order:
                site_summaries = by_site_label.get(site_label)
                if not site_summaries:
                    continue
                offsets_x = [float(summary["offsetX"]) for summary in site_summaries]
                offsets_y = [float(summary["offsetY"]) for summary in site_summaries]
                measurement_ids = [
                    str(summary["measurementId"]) for summary in site_summaries
                ]
                line_keys = [
                    str(summary["lineKey"])
                    for summary in site_summaries
                    if summary.get("lineKey") is not None
                ]
                item = {
                    "siteLabel": site_label,
                    "x": _mean(offsets_x),
                    "y": _mean(offsets_y),
                    "measurementIds": measurement_ids,
                    "lineKeys": line_keys,
                    "measurementCount": len(site_summaries),
                    "violationCount": int(
                        sum(
                            0 if summary.get("valid", True) else 1
                            for summary in site_summaries
                        )
                    ),
                    "violationMagnitude": float(
                        sum(
                            float(summary.get("violationMagnitude", 0.0))
                            for summary in site_summaries
                        )
                    ),
                    "loss": float(
                        sum(
                            (float(summary["offsetX"]) ** 2)
                            + (float(summary["offsetY"]) ** 2)
                            for summary in site_summaries
                        )
                    ),
                }
                items.append(item)
            return items

        def build_site_offsets(by_site_label):
            items = build_site_offset_items(by_site_label)
            offsets = {item["siteLabel"]: dict(item) for item in items}
            return offsets, items

        def build_line_offset_overrides(summary_by_measurement, site_offsets):
            overrides = {}
            for measurement_id in measurement_order:
                summary = summary_by_measurement.get(measurement_id)
                if summary is None:
                    continue
                site_label = summary["siteLabel"]
                site_offset = site_offsets.get(site_label)
                if site_offset is None:
                    continue
                line_key = summary.get("lineKey")
                if line_key is None:
                    continue
                line_key = normalize_line_key(line_key)
                if line_key not in overrides:
                    # A solved override may move only along the target pin's
                    # natural axis (head/foot in Y, top/bottom in X), quantised
                    # to 0.1 mm; an unknown target leaves the offset untouched.
                    natural_axis = _line_natural_axis(layer, summary.get("measurement"))
                    offset_x = float(site_offset["x"])
                    offset_y = float(site_offset["y"])
                    if natural_axis in ("x", "y"):
                        offset_x, offset_y = enforce_offset_axes(
                            offset_x, offset_y, natural_axis
                        )
                    overrides[line_key] = {
                        "x": offset_x,
                        "y": offset_y,
                        "siteLabel": site_label,
                        "measurementIds": [],
                    }
                overrides[line_key].setdefault("measurementIds", []).append(
                    measurement_id
                )
            return overrides

        def progress_fields(**fields):
            payload = dict(fields)
            total = progress_state["total"]
            completed = int(
                payload.get("completedEvaluations", progress_state["completed"])
            )
            if total is not None:
                payload["totalEvaluations"] = int(total)
                payload["completedEvaluations"] = completed
                payload["percentComplete"] = min(
                    100.0,
                    max(0.0, (float(completed) / float(total)) * 100.0),
                )
                elapsed = max(0.0, time.time() - float(progress_state["startedAt"]))
                payload["elapsedSeconds"] = float(elapsed)
                if completed > 0 and completed < total:
                    remaining = int(total) - completed
                    payload["estimatedSecondsRemaining"] = float(
                        (elapsed / float(completed)) * float(remaining)
                    )
                elif completed >= total:
                    payload["estimatedSecondsRemaining"] = 0.0
            return payload

        progress_state: dict[str, Any] = {
            "startedAt": time.time(),
            "completed": 0,
            "total": None,
        }

        def publish(step, message, **fields):
            if progress_callback is None:
                return
            progress_callback(step, message, **progress_fields(**fields))

        def evaluate_full(vector, *, step, message, candidate_label=""):
            camera_offset = (float(vector[0]), float(vector[1]))
            roller_y_cals = [float(value) for value in vector[2:6]]
            publish(
                step,
                message,
                candidateLabel=candidate_label,
                loss=None,
                bestLoss=None,
                parameters=_format_machine_xy_parameters(vector),
                bestParameters=None,
                siteLabel=None,
            )
            results = project_group(measurements, roller_y_cals, camera_offset)
            progress_state["completed"] += 1
            return summarize_results(results, camera_offset)

        if not measurements:
            camera_offset = (
                float(current_camera_offset[0]),
                float(current_camera_offset[1]),
            )
            roller_y_cals = [float(value) for value in initial_roller_y_cals[:4]]
            publish(
                "done",
                "No machine XY measurements were available. Draft mirrors the current machine camera offset and roller values.",
                completedEvaluations=0,
                totalEvaluations=0,
                percentComplete=100.0,
                phase="done",
                elapsedSeconds=0.0,
                estimatedSecondsRemaining=0.0,
            )
            return {
                "cameraOffsetX": float(camera_offset[0]),
                "cameraOffsetY": float(camera_offset[1]),
                "rollerYCals": roller_y_cals,
                "siteOffsets": {},
                "siteOffsetItems": [],
                "lineOffsetOverrides": {},
                "lineOffsetOverrideItems": [],
                "score": {
                    "lineOffsetNorm": 0.0,
                    "rollerOffsetNorm": 0.0,
                    "cameraOffsetDeltaNorm": 0.0,
                    "loss": 0.0,
                },
                "summaries": [],
                "diagnostics": [],
                "valid": True,
                "violationCount": 0,
                "violationMagnitude": 0.0,
                "violations": [],
                "progress": {
                    "completedEvaluations": 0,
                    "totalEvaluations": 0,
                },
            }

        layer_calibration = LayerCalibration(layer)
        _layer_dir, _layer_file = os.path.split(str(layer_path))
        layer_calibration.load(
            _layer_dir,
            _layer_file,
            exceptionForMismatch=False,
            machineCalibration=self._machineCalibration(),
        )

        # ---- Closed-form camera-offset solve --------------------------------
        # With the rollers fixed, the projection is computed once per measurement
        # and then translated analytically by the candidate camera offset (see
        # _translate_projection_payload), so the loss Sum_i (offsetX_i^2 +
        # offsetY_i^2) is a (near-)quadratic in the 2-vector (cameraX, cameraY):
        # alternating-side residuals are exactly affine in the offset, same-side
        # residuals add a mild smooth nonlinearity.  We take coordinate-wise
        # Newton steps -- each axis' optimum is
        #   c* = c - Sum_i(slope_i * r_i) / Sum_i(slope_i^2)
        # with the per-measurement slope dr_i/dc read numerically from one small
        # probe through the cached translate -- and iterate a few times to absorb
        # any same-side coupling.  No RNG and no mini-batching: every evaluation
        # is over the full measurement set, so the result is deterministic.
        _MAX_REFINEMENTS = 3
        progress_state["total"] = int(1 + (_MAX_REFINEMENTS * 3))

        baseline_summary = evaluate_full(
            initial_vector,
            step="baseline",
            message="Evaluating the current machine XY candidate.",
            candidate_label="baseline",
        )

        camera_probe = 0.02  # mm: small step for the numerical per-axis slope

        def newton_axis(center_vector, center_summary, axis):
            probe_vector = list(center_vector)
            probe_vector[axis] = float(probe_vector[axis]) + camera_probe
            probe_summary = evaluate_full(
                probe_vector,
                step="solving",
                message="Probing the machine XY loss gradient.",
                candidate_label="probe",
            )
            key = "offsetX" if axis == 0 else "offsetY"
            delta_key = "deltaX" if axis == 0 else "deltaY"
            numerator = 0.0
            denominator = 0.0
            probe_by_measurement = probe_summary["by_measurement"]
            for measurement_id, center in center_summary["by_measurement"].items():
                probe = probe_by_measurement.get(measurement_id)
                if probe is None:
                    continue
                # Drive the *change from the live offset* to zero, not the
                # absolute offset.  Camera offset and per-corner offset are a
                # redundant (gauge) pair: any camera shift can be cancelled by an
                # equal-and-opposite per-corner shift, leaving the placement
                # unchanged.  Minimising the absolute offset anchors that gauge at
                # "all corners zero", which forces the global camera offset to
                # absorb whatever per-corner offsets the live recipe already
                # carries -- moving every commanded head by roughly the live
                # offset magnitude and tripping the command-target invariance
                # gate.  Minimising the delta anchors the gauge at "corners
                # unchanged", so the camera only moves to absorb a genuine
                # common-mode error and a recalibration that merely confirms the
                # current placement is a no-op.  The slope d(offset)/d(camera) is
                # unchanged by the constant live term, so only the residual moves.
                residual = float(center[delta_key])
                slope = (float(probe[key]) - float(center[key])) / camera_probe
                numerator += slope * residual
                denominator += slope * slope
            if denominator <= _EPSILON:
                return float(center_vector[axis])
            return float(center_vector[axis]) - (numerator / denominator)

        working_vector = list(initial_vector)
        current_summary = baseline_summary
        for _refinement in range(_MAX_REFINEMENTS):
            self._raiseIfMachineSolveCancelled(layer, operation_id)
            new_x = newton_axis(working_vector, current_summary, 0)
            new_y = newton_axis(working_vector, current_summary, 1)
            candidate_vector = clamp_vector([new_x, new_y, *working_vector[2:6]])
            step_size = max(
                abs(float(candidate_vector[0]) - float(working_vector[0])),
                abs(float(candidate_vector[1]) - float(working_vector[1])),
            )
            working_vector = candidate_vector
            current_summary = evaluate_full(
                working_vector,
                step="solving",
                message="Solving machine XY camera offset.",
                candidate_label="solve",
            )
            if step_size < 1e-4:
                break

        # Never return something worse than the starting point on the
        # lexicographic objective (violationCount, violationMagnitude, loss).
        if objective_better(baseline_summary, current_summary):
            selected_vector = list(initial_vector)
            selected_summary = baseline_summary
        else:
            selected_vector = list(working_vector)
            selected_summary = current_summary

        publish(
            "finalizing",
            "Finalizing machine XY solution.",
            loss=float(selected_summary["loss"]),
            bestLoss=float(selected_summary["loss"]),
            parameters=_format_machine_xy_parameters(selected_vector),
            bestParameters=_format_machine_xy_parameters(selected_vector),
        )
        site_offsets, site_offset_items = build_site_offsets(
            selected_summary["by_site_label"]
        )
        line_offset_overrides = build_line_offset_overrides(
            selected_summary["by_measurement"], site_offsets
        )

        diagnostics = []
        for site_label in site_order:
            site_summary = selected_summary["by_site_label"].get(site_label)
            if not site_summary:
                continue
            diagnostics.append(
                {
                    "siteLabel": site_label,
                    "measurementIds": [
                        str(summary["measurementId"]) for summary in site_summary
                    ],
                    "lineKeys": [
                        str(summary["lineKey"])
                        for summary in site_summary
                        if summary.get("lineKey") is not None
                    ],
                    "meanOffsetX": _mean(
                        summary["offsetX"] for summary in site_summary
                    ),
                    "meanOffsetY": _mean(
                        summary["offsetY"] for summary in site_summary
                    ),
                    "maxAbsOffsetX": max(
                        abs(float(summary["offsetX"])) for summary in site_summary
                    ),
                    "maxAbsOffsetY": max(
                        abs(float(summary["offsetY"])) for summary in site_summary
                    ),
                    "violationCount": int(
                        sum(
                            0 if summary.get("valid", True) else 1
                            for summary in site_summary
                        )
                    ),
                    "violationMagnitude": float(
                        sum(
                            float(summary.get("violationMagnitude", 0.0))
                            for summary in site_summary
                        )
                    ),
                    "loss": float(
                        sum(
                            (float(summary["offsetX"]) ** 2)
                            + (float(summary["offsetY"]) ** 2)
                            for summary in site_summary
                        )
                    ),
                    "measurementCount": len(site_summary),
                }
            )

        selected_loss = float(selected_summary["loss"])
        camera_offset = (float(selected_vector[0]), float(selected_vector[1]))
        roller_y_cals = [float(value) for value in selected_vector[2:6]]
        camera_offset_delta_norm = float(
            (
                ((float(selected_vector[0]) - float(initial_vector[0])) ** 2)
                + ((float(selected_vector[1]) - float(initial_vector[1])) ** 2)
            )
            ** 0.5
        )
        roller_offset_delta_norm = float(
            sum(
                (float(selected_vector[index]) - float(initial_vector[index])) ** 2
                for index in range(2, 6)
            )
            ** 0.5
        )
        if not bool(selected_summary.get("valid", True)):
            worst_violations = [
                format_violation(item)
                for item in selected_summary.get("violations", [])[:3]
            ]
            raise RuntimeError(
                "No valid bounded Machine XY solution found. Per-line "
                "override change limits are X <= "
                + "{0:.3f}".format(_MAX_LINE_OFFSET_DELTA_X_MM)
                + " mm and Y <= "
                + "{0:.3f}".format(_MAX_LINE_OFFSET_DELTA_Y_MM)
                + " mm (change from current live override). "
                + "Worst offenders: "
                + "; ".join(worst_violations)
            )

        return {
            "cameraOffsetX": float(camera_offset[0]),
            "cameraOffsetY": float(camera_offset[1]),
            "rollerYCals": roller_y_cals,
            "siteOffsets": site_offsets,
            "siteOffsetItems": site_offset_items,
            "lineOffsetOverrides": line_offset_overrides,
            "lineOffsetOverrideItems": line_offset_override_items(
                line_offset_overrides
            ),
            "score": {
                "lineOffsetNorm": float(selected_loss),
                "rollerOffsetNorm": float(roller_offset_delta_norm),
                "cameraOffsetDeltaNorm": float(camera_offset_delta_norm),
                "loss": float(selected_loss),
            },
            "summaries": ordered_summaries(selected_summary["by_measurement"]),
            "diagnostics": diagnostics,
            "valid": bool(selected_summary.get("valid", True)),
            "violationCount": int(selected_summary.get("violationCount", 0)),
            "violationMagnitude": float(
                selected_summary.get("violationMagnitude", 0.0)
            ),
            "violations": list(selected_summary.get("violations", [])),
            "progress": {
                "completedEvaluations": int(progress_state["completed"]),
                "totalEvaluations": int(
                    progress_state["total"] or progress_state["completed"]
                ),
            },
        }

    # -------------------------------------------------------------------
    def solveMachineXY(self, layer=None, *, fit_rollers=False):
        target_layer = self._resolvedLayer(layer)
        operation_id = uuid.uuid4().hex
        _CALIBRATION_OBJECT_CACHE.clear()
        solve_started_at = time.time()
        self._clearMachineSolveRequests(operation_id)
        self._registerMachineSolveOperation(operation_id)
        progress_checkpoint: dict[str, Any] = {
            "time": 0.0,
            "step": None,
            "message": None,
            "completed": None,
            "total": None,
            "status": None,
            "signature": None,
        }

        def progress(step, message, **fields):
            now = time.time()
            payload = dict(fields)
            completed = payload.get("completedEvaluations")
            total = payload.get("totalEvaluations")
            signature = json.dumps(
                {
                    "loss": payload.get("loss"),
                    "bestLoss": payload.get("bestLoss"),
                    "gradientNorm": payload.get("gradientNorm"),
                    "learningRate": payload.get("learningRate"),
                    "batchIndex": payload.get("batchIndex"),
                    "epoch": payload.get("epoch"),
                    "candidateLabel": payload.get("candidateLabel"),
                    "siteLabel": payload.get("siteLabel"),
                    "parameters": payload.get("parameters"),
                    "bestParameters": payload.get("bestParameters"),
                },
                sort_keys=True,
                default=str,
            )
            should_emit = (
                progress_checkpoint["step"] != step
                or progress_checkpoint["message"] != message
                or progress_checkpoint["completed"] != completed
                or progress_checkpoint["total"] != total
                or progress_checkpoint["status"] != "running"
                or progress_checkpoint["signature"] != signature
                or progress_checkpoint["time"] <= 0.0
                or (now - progress_checkpoint["time"]) >= 0.25
            )
            if not should_emit:
                return
            progress_checkpoint["time"] = now
            progress_checkpoint["step"] = step
            progress_checkpoint["message"] = message
            progress_checkpoint["completed"] = completed
            progress_checkpoint["total"] = total
            progress_checkpoint["status"] = "running"
            progress_checkpoint["signature"] = signature
            status_fields = dict(payload)
            if "elapsedSeconds" not in status_fields:
                status_fields["elapsedSeconds"] = float(
                    max(0.0, now - solve_started_at)
                )
            self._updateMachineSolveStatus(
                target_layer,
                operationId=operation_id,
                status="running",
                step=step,
                message=message,
                **status_fields,
            )
            self._log(
                "SOLVE_MACHINE_XY_PROGRESS",
                str(message),
                [operation_id, target_layer, step, status_fields],
            )

        try:
            usable_measurements = _most_recent_per_corner(
                [
                    measurement
                    for measurement in self._usableMeasurements(target_layer)
                    if measurement["usableForMachineXY"]
                ]
            )
            self._log(
                "SOLVE_MACHINE_XY_START",
                "Machine XY solve started.",
                [operation_id, target_layer, len(usable_measurements)],
            )
            self._updateMachineSolveStatus(
                target_layer,
                operationId=operation_id,
                status="running",
                step="starting",
                message="Preparing machine XY solve.",
                startedAt=self._timestamp(),
                finishedAt=None,
                solveLayer=target_layer,
                measurementRevision=self._measurementRevision(),
                measurementCount=len(usable_measurements),
                fitError=None,
                cancelRequested=False,
                cancelRequestedAt=None,
                killRequested=False,
                killRequestedAt=None,
                terminatedEvaluations=0,
                completedEvaluations=0,
                totalEvaluations=None,
                percentComplete=0.0,
                elapsedSeconds=0.0,
                estimatedSecondsRemaining=None,
            )

            conflict = self._xyConflictError(usable_measurements)
            draft = self._layerDraft(target_layer, create=True)
            state = self._loadState()
            current_camera_offset = self._currentCameraOffset()
            machine_calibration = self._machineCalibration()
            current_roller_y_cals = _live_roller_y_cals(machine_calibration)
            nominal_roller_y = _nominal_roller_y(machine_calibration)

            if conflict is not None:
                result = {
                    "fitError": conflict,
                    "measurementRevision": self._measurementRevision(),
                }
                draft["machineSolve"] = result
                draft["lineOffsetOverrides"] = {}
                state["machineDraft"] = None
                self._updateMachineSolveStatus(
                    target_layer,
                    operationId=operation_id,
                    status="failed",
                    step="validation",
                    message=conflict,
                    fitError=conflict,
                    finishedAt=self._timestamp(),
                    percentComplete=100.0,
                    completedEvaluations=0,
                    totalEvaluations=0,
                    elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
                    estimatedSecondsRemaining=0.0,
                )
                self._log(
                    "SOLVE_MACHINE_XY_FAILED",
                    "Machine XY solve failed validation.",
                    [operation_id, target_layer, conflict],
                )
                self._clearMachineSolveRequests(operation_id)
                self._saveState()
                return result

            progress("layer_calibration", "Preparing layer calibration candidate.")
            layer_path = self._candidateLayerCalibrationPath(target_layer)

            template_state = self._templateService(target_layer).getState()
            live_line_offsets = template_state.get("lineOffsetOverrides", {})
            live_draft = {
                "cameraWireOffsetX": float(current_camera_offset[0]),
                "cameraWireOffsetY": float(current_camera_offset[1]),
                "rollerYCals": list(current_roller_y_cals),
            }
            progress(
                "active_sanity_check",
                "Checking active calibration consistency against measurements.",
            )
            active_sanity = self._sanityCheckLineOffsets(
                target_layer, live_draft, live_line_offsets
            )

            evaluation = self._evaluateMachineXY(
                usable_measurements,
                layer=target_layer,
                operation_id=operation_id,
                layer_path=layer_path,
                nominal_roller_y=nominal_roller_y,
                current_camera_offset=current_camera_offset,
                initial_roller_y_cals=current_roller_y_cals,
                live_line_offsets=live_line_offsets,
                progress_callback=progress,
                fit_rollers=fit_rollers,
            )

            # Simultaneously fit the layer Z plane from same-side
            # measurements that carry a Z observation.  Roller calibrations
            # are no longer fit; instead the wire-tangent Z plane captures
            # the frame's actual 3D pose.  solveLayerZ writes its result
            # into the same draft consumed by applyMachineXY below.
            progress(
                "solving_z_plane", "Fitting layer Z plane from same-side measurements."
            )
            try:
                self.solveLayerZ(target_layer)
            except Exception as z_exception:
                self._log(
                    "SOLVE_LAYER_Z_FAILED_DURING_MACHINE_XY",
                    "Layer Z plane fit failed during Machine XY solve.",
                    [operation_id, target_layer, repr(z_exception)],
                )

            progress("building_draft", "Building line-offset draft and diagnostics.")
            overrides = dict(evaluation.get("lineOffsetOverrides", {}))
            diagnostics = list(evaluation.get("diagnostics", []))
            measurement_ids = [
                str(summary["measurementId"])
                for summary in evaluation.get("summaries", [])
            ]

            sanity_checked = 0
            sanity_max_dx = 0.0
            sanity_max_dy = 0.0
            sanity_discrepancy_count = 0
            sanity_discrepancies = []
            for summary in evaluation.get("summaries", []):
                line_key = summary.get("lineKey")
                if line_key is None:
                    continue
                try:
                    normalized_key = normalize_line_key(line_key)
                except Exception:
                    continue
                override = overrides.get(normalized_key)
                if override is None:
                    continue
                sanity_checked += 1
                dx = abs(float(summary["offsetX"]) - float(override["x"]))
                dy = abs(float(summary["offsetY"]) - float(override["y"]))
                sanity_max_dx = max(sanity_max_dx, dx)
                sanity_max_dy = max(sanity_max_dy, dy)
                if dx > _SANITY_CHECK_TOLERANCE_MM or dy > _SANITY_CHECK_TOLERANCE_MM:
                    sanity_discrepancy_count += 1
                    sanity_discrepancies.append(
                        {
                            "lineKey": normalized_key,
                            "measurementId": summary["measurementId"],
                            "residualX": float(summary["offsetX"]),
                            "residualY": float(summary["offsetY"]),
                            "lineOffsetX": float(override["x"]),
                            "lineOffsetY": float(override["y"]),
                            "discrepancyX": float(dx),
                            "discrepancyY": float(dy),
                        }
                    )
            sanity_check = {
                "ok": sanity_discrepancy_count == 0,
                "checkedCount": sanity_checked,
                "maxDiscrepancyX": float(sanity_max_dx),
                "maxDiscrepancyY": float(sanity_max_dy),
                "discrepancyCount": sanity_discrepancy_count,
                "discrepancies": sanity_discrepancies[:10],
            }

            # Direct invariant: applying the draft (new camera offset + new
            # per-corner offsets) must not move the commanded head target of any
            # measured line versus the live calibration (old camera offset + old
            # per-corner offsets).  Surfaced now and re-checked as a hard gate in
            # applyMachineXY.
            command_target_check = self._checkCommandTargetInvariance(
                target_layer,
                {
                    "cameraWireOffsetX": evaluation["cameraOffsetX"],
                    "cameraWireOffsetY": evaluation["cameraOffsetY"],
                },
                overrides,
            )

            machine_draft = {
                "layer": target_layer,
                "cameraWireOffsetX": evaluation["cameraOffsetX"],
                "cameraWireOffsetY": evaluation["cameraOffsetY"],
                "rollerYCals": list(evaluation["rollerYCals"]),
                "siteOffsets": dict(evaluation.get("siteOffsets", {})),
                "siteOffsetItems": list(evaluation.get("siteOffsetItems", [])),
                "nominalRollerY": float(nominal_roller_y),
                "measurementRevision": self._measurementRevision(),
                "measurementIds": measurement_ids,
                "objective": dict(evaluation["score"]),
                "diagnostics": diagnostics,
                "valid": bool(evaluation.get("valid", True)),
                "violationCount": int(evaluation.get("violationCount", 0)),
                "violationMagnitude": float(evaluation.get("violationMagnitude", 0.0)),
                "violations": list(evaluation.get("violations", [])),
                "sanityCheck": sanity_check,
                "activeSanityCheck": active_sanity,
                "commandTargetCheck": command_target_check,
            }
            machine_solve = {
                "fitError": None,
                "measurementRevision": self._measurementRevision(),
                "measurementIds": measurement_ids,
                "objective": dict(evaluation["score"]),
                "siteOffsets": dict(evaluation.get("siteOffsets", {})),
                "siteOffsetItems": list(evaluation.get("siteOffsetItems", [])),
                "lineOffsetOverrides": dict(overrides),
                "lineOffsetOverrideItems": line_offset_override_items(overrides),
                "diagnostics": diagnostics,
                "valid": bool(evaluation.get("valid", True)),
                "violationCount": int(evaluation.get("violationCount", 0)),
                "violationMagnitude": float(evaluation.get("violationMagnitude", 0.0)),
                "violations": list(evaluation.get("violations", [])),
                "sanityCheck": sanity_check,
                "activeSanityCheck": active_sanity,
                "commandTargetCheck": command_target_check,
            }
            draft["machineSolve"] = machine_solve
            draft["lineOffsetOverrides"] = dict(overrides)
            state["machineDraft"] = machine_draft
            self._updateMachineSolveStatus(
                target_layer,
                operationId=operation_id,
                status="succeeded",
                step="done",
                message=(
                    "Machine XY solve completed with "
                    + str(len(measurement_ids))
                    + " measurement"
                    + ("" if len(measurement_ids) == 1 else "s")
                    + "."
                ),
                fitError=None,
                finishedAt=self._timestamp(),
                cancelRequested=False,
                completedEvaluations=int(
                    evaluation.get("progress", {}).get("completedEvaluations", 0)
                ),
                totalEvaluations=int(
                    evaluation.get("progress", {}).get("totalEvaluations", 0)
                ),
                percentComplete=100.0,
                elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
                estimatedSecondsRemaining=0.0,
                siteOffsets=dict(evaluation.get("siteOffsets", {})),
                siteOffsetItems=list(evaluation.get("siteOffsetItems", [])),
            )
            self._clearMachineSolveRequests(operation_id)
            self._saveState()
            self._log(
                "SOLVE_MACHINE_XY_DONE",
                "Machine XY solve completed.",
                [
                    operation_id,
                    target_layer,
                    len(measurement_ids),
                    dict(evaluation["score"]),
                ],
            )
            return machine_solve
        except _MachineXYSolveKilled:
            self._terminateActiveMachineSolveEvaluations(operation_id)
            self._clearMachineSolveRequests(operation_id)
            self._updateMachineSolveStatus(
                target_layer,
                operationId=operation_id,
                status="killed",
                step="killed",
                message="Machine XY solve killed. Active evaluation terminated.",
                fitError=None,
                finishedAt=self._timestamp(),
                cancelRequested=False,
                killRequested=False,
                percentComplete=100.0,
                elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
                estimatedSecondsRemaining=0.0,
            )
            self._log(
                "SOLVE_MACHINE_XY_KILLED",
                "Machine XY solve killed.",
                [operation_id, target_layer],
            )
            return {
                "canceled": True,
                "killed": True,
                "fitError": None,
                "measurementRevision": self._measurementRevision(),
            }
        except _MachineXYSolveCancelled:
            self._clearMachineSolveRequests(operation_id)
            self._updateMachineSolveStatus(
                target_layer,
                operationId=operation_id,
                status="canceled",
                step="canceled",
                message="Machine XY solve canceled.",
                fitError=None,
                finishedAt=self._timestamp(),
                cancelRequested=False,
                percentComplete=100.0,
                elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
                estimatedSecondsRemaining=0.0,
            )
            self._log(
                "SOLVE_MACHINE_XY_CANCELED",
                "Machine XY solve canceled.",
                [operation_id, target_layer],
            )
            return {
                "canceled": True,
                "fitError": None,
                "measurementRevision": self._measurementRevision(),
            }
        except Exception as exception:
            self._terminateActiveMachineSolveEvaluations(operation_id)
            self._clearMachineSolveRequests(operation_id)
            message = "Machine XY solve failed: " + _error_text(exception)
            self._updateMachineSolveStatus(
                target_layer,
                operationId=operation_id,
                status="failed",
                step="failed",
                message=message,
                fitError=message,
                finishedAt=self._timestamp(),
                cancelRequested=False,
                percentComplete=100.0,
                elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
                estimatedSecondsRemaining=0.0,
            )
            draft = self._layerDraft(target_layer, create=True)
            draft["machineSolve"] = {
                "fitError": message,
                "measurementRevision": self._measurementRevision(),
            }
            self._saveState()
            self._log(
                "SOLVE_MACHINE_XY_FAILED",
                "Machine XY solve failed.",
                [operation_id, target_layer, repr(exception), traceback.format_exc()],
            )
            raise ValueError(message)
        finally:
            self._unregisterMachineSolveOperation(operation_id)
            self._clearMachineSolveRequests(operation_id)

    # -------------------------------------------------------------------
    def applyMachineXY(self, layer=None):
        self._geometryMutationGuard()
        target_layer = self._resolvedLayer(layer)
        state = self._loadState()
        machine_draft = state.get("machineDraft")
        draft = self._layerDraft(target_layer)
        if machine_draft is None or str(machine_draft.get("layer")) != target_layer:
            raise ValueError(
                "Run machine XY solve for the active layer before applying."
            )
        if draft is None or not draft.get("lineOffsetOverrides"):
            raise ValueError("No solved line offsets are available to apply.")

        sanity = self._sanityCheckLineOffsets(
            target_layer, machine_draft, draft["lineOffsetOverrides"]
        )
        if not sanity["ok"]:
            self._log(
                "SANITY_CHECK_FAILED",
                "Line offset sanity check failed.",
                [
                    sanity["discrepancyCount"],
                    sanity["maxDiscrepancyX"],
                    sanity["maxDiscrepancyY"],
                ],
            )
            raise ValueError(
                "Line offset sanity check failed: "
                + str(sanity["discrepancyCount"])
                + " discrepancy(ies), "
                + "max deltaX="
                + "{0:.3f}".format(sanity["maxDiscrepancyX"])
                + " deltaY="
                + "{0:.3f}".format(sanity["maxDiscrepancyY"])
                + "mm. Re-run machine XY solve."
            )
        self._log(
            "SANITY_CHECK_PASSED",
            "Line offset sanity check passed.",
            [
                sanity["checkedCount"],
                sanity["maxDiscrepancyX"],
                sanity["maxDiscrepancyY"],
            ],
        )

        # Hard gate: applying must not move the commanded head target of any
        # measured line.  Run while the live calibration is still in effect (the
        # camera offset and corner-offset store are mutated below) so "old" is
        # genuinely the current calibration.
        command_target = self._checkCommandTargetInvariance(
            target_layer, machine_draft, draft["lineOffsetOverrides"]
        )
        if not command_target["ok"]:
            self._log(
                "COMMAND_TARGET_CHECK_FAILED",
                "Command target invariance check failed.",
                [
                    command_target["discrepancyCount"],
                    command_target["maxDiscrepancyX"],
                    command_target["maxDiscrepancyY"],
                ],
            )
            raise ValueError(
                "Command target invariance check failed: "
                + str(command_target["discrepancyCount"])
                + " line(s) move more than "
                + "{0:.1f}".format(_COMMAND_TARGET_TOLERANCE_MM)
                + "mm when applying the draft (max deltaX="
                + "{0:.3f}".format(command_target["maxDiscrepancyX"])
                + " deltaY="
                + "{0:.3f}".format(command_target["maxDiscrepancyY"])
                + "mm). Re-run machine XY solve."
            )
        self._log(
            "COMMAND_TARGET_CHECK_PASSED",
            "Command target invariance check passed.",
            [
                command_target["checkedCount"],
                command_target["maxDiscrepancyX"],
                command_target["maxDiscrepancyY"],
            ],
        )

        machine_calibration = self._machineCalibration()
        camera_offset_x = float(machine_draft["cameraWireOffsetX"])
        camera_offset_y = float(machine_draft["cameraWireOffsetY"])
        manual = getattr(self._process, "manualCalibration", None)
        machine_calibration.cameraWireOffsetX = camera_offset_x
        machine_calibration.cameraWireOffsetY = camera_offset_y
        if manual is not None and hasattr(manual, "_applySharedCameraOffset"):
            manual._applySharedCameraOffset(camera_offset_x, camera_offset_y)

        # The Machine XY solver no longer fits roller calibrations -- the
        # rollerArmCalibration on disk is left untouched and only the
        # camera offset (and Z plane via the layer calibration below) are
        # updated.
        machine_calibration.save()
        clear_uv_head_target_caches(layer_calibration=False, machine_calibration=True)

        # If the solve also produced a Z-plane draft, commit it to the
        # layer calibration so the new pin Z values feed downstream
        # geometry computations.
        z_plane_dict = draft.get("zPlaneCalibration")
        applied_z_plane = None
        if z_plane_dict is not None:
            fitted_plane = layer_z_plane_calibration_from_dict(z_plane_dict)
            if has_valid_layer_z_plane_fit(fitted_plane):
                layer_calibration = self._activeLayerCalibration(target_layer)
                layer_calibration.zPlaneCalibration = fitted_plane
                apply_layer_z_plane_calibration(layer_calibration, fitted_plane)
                layer_calibration.save()
                clear_uv_head_target_caches(
                    layer_calibration=True, machine_calibration=False
                )
                self._syncLayerCalibrationHandlers(layer_calibration)
                applied_z_plane = layer_z_plane_calibration_to_dict(fitted_plane)

        template_service = self._templateService(target_layer)
        # The solver fits one offset per corner (fanned out across the measured
        # lines of that corner).  Collapse back to per-corner and write each to
        # the corner-offset store so it applies to *every* corner of that kind
        # at regeneration -- not just the lines that happened to be measured.
        corner_offsets = _corner_offsets_from_overrides(
            template_service, draft["lineOffsetOverrides"]
        )
        if not corner_offsets:
            raise ValueError("No solved corner offsets are available to apply.")
        for offset_id, corner in corner_offsets.items():
            offset_result = template_service.setOffset(
                offset_id, x=corner["x"], y=corner["y"]
            )
            if not offset_result.get("ok", False):
                raise ValueError(
                    str(offset_result.get("error", "Failed to apply corner offset."))
                )
        script_variant = getattr(template_service, "_lastGeneratedScriptVariant", None)
        generation_result = template_service.generateRecipeFile(
            scriptVariant=script_variant
        )
        if not generation_result.get("ok", False):
            raise ValueError(
                str(generation_result.get("error", "Failed to regenerate recipe file."))
            )
        return {
            "machineCalibration": {
                "cameraWireOffsetX": float(machine_calibration.cameraWireOffsetX),
                "cameraWireOffsetY": float(machine_calibration.cameraWireOffsetY),
                "rollerArmCalibration": roller_arm_calibration_to_dict(
                    machine_calibration.rollerArmCalibration
                ),
            },
            "zPlaneCalibration": applied_z_plane,
            "siteOffsets": dict(machine_draft.get("siteOffsets", {})),
            "siteOffsetItems": list(machine_draft.get("siteOffsetItems", [])),
            "lineOffsetOverrideItems": line_offset_override_items(
                draft["lineOffsetOverrides"]
            ),
            "lineOffsetOverrides": dict(draft["lineOffsetOverrides"]),
            "scriptVariant": script_variant,
            "generation": generation_result.get("data"),
        }

    # -------------------------------------------------------------------
    def setLineOffsetOverride(self, layer, line_key, x_value, y_value):
        self._geometryMutationGuard()
        service = self._templateService(layer)
        return service.setLineOffsetOverride(line_key, x_value, y_value)

    # -------------------------------------------------------------------
    def deleteLineOffsetOverride(self, layer, line_key):
        self._geometryMutationGuard()
        service = self._templateService(layer)
        return service.deleteLineOffsetOverride(line_key)

    # -------------------------------------------------------------------
    def _liveLayerPlaneSummary(self, layer):
        calibration = self._activeLayerCalibration(layer)
        z_plane = getattr(calibration, "zPlaneCalibration", None)
        if z_plane is None:
            return None
        return layer_z_plane_calibration_to_dict(z_plane)

    # -------------------------------------------------------------------
    def getState(self):
        state = self._loadState()
        layer = self._process.getRecipeLayer()
        enabled = layer in _SUPPORTED_LAYERS
        disabled_reason = None
        if not enabled:
            if layer is None:
                disabled_reason = "Load an active U or V recipe first."
            else:
                disabled_reason = "Machine geometry calibration only supports U and V."

        last_trace = getattr(self._process, "getLastInstructionTrace", lambda: None)()
        machine_calibration = self._machineCalibration()
        machine_live = {
            "cameraWireOffsetX": self._currentCameraOffset()[0],
            "cameraWireOffsetY": self._currentCameraOffset()[1],
            "nominalRollerY": _nominal_roller_y(machine_calibration),
            "rollerYCals": list(_live_roller_y_cals(machine_calibration)),
        }

        layer_state = None
        if enabled:
            template_service = self._templateService(layer)
            template_state = template_service.getState()
            draft = self._layerDraft(layer, create=False) or {
                "zPlaneCalibration": None,
                "machineSolve": None,
                "lineOffsetOverrides": {},
            }
            machine_solve_status = self._reconcileMachineSolveStatus(
                layer,
                draft.get("machineSolveStatus"),
            )
            # The solver fits one offset per corner; expose Current (live) and
            # Draft (solved) per-corner rows so the operator compares like with
            # like.  Applying writes these to the corner-offset store, so they
            # land on every corner of that kind at regeneration.
            current_corner_items, draft_corner_items = _corner_offset_items(
                template_service,
                draft.get("lineOffsetOverrides", {}),
                template_state.get("offsets", {}),
            )
            layer_state = {
                "layer": layer,
                "liveZPlaneCalibration": self._liveLayerPlaneSummary(layer),
                "draftZPlaneCalibration": draft.get("zPlaneCalibration"),
                "draftZPlaneStale": (
                    (draft.get("zPlaneSolve") or {}).get("measurementRevision")
                    != self._measurementRevision()
                    if draft.get("zPlaneSolve")
                    else False
                ),
                "currentCornerOffsetItems": current_corner_items,
                "draftCornerOffsetItems": draft_corner_items,
                "machineSolve": draft.get("machineSolve"),
                "machineSolveStatus": machine_solve_status,
            }

        measurements = []
        for measurement in self._loadState().get("measurements", []):
            item = dict(measurement)
            item["siteLabel"] = item.get("siteLabel") or _measurement_site_label(item)
            item["usableForLayerZ"] = (
                item.get("kind") == "same_side" and item.get("actualZ") is not None
            )
            item["usableForMachineXY"] = (
                item.get("actualWireX") is not None
                and item.get("actualWireY") is not None
                and item.get("lineKey") is not None
            )
            measurements.append(item)

        return {
            "enabled": enabled,
            "disabledReason": disabled_reason,
            "activeLayer": layer,
            "gcodeExecutionActive": self._isGCodeExecutionActive(),
            "measurementRevision": self._measurementRevision(),
            "lastMotionTrace": last_trace,
            "currentPositions": self._currentPositions(),
            "measurements": measurements,
            "machine": {
                "live": machine_live,
                "draft": state.get("machineDraft"),
                "draftStale": (
                    state.get("machineDraft", {}).get("measurementRevision")
                    != self._measurementRevision()
                    if state.get("machineDraft")
                    else False
                ),
            },
            "layerState": layer_state,
        }
