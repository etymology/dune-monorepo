from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path

from dune_winder.library.Geometry.location import Location

from .calibration import (
    _load_layer_calibration,
    _load_machine_calibration,
    _location_to_point3,
    _wire_space_pin,
)
from .constants import _ANCHOR_TO_TARGET_RE, _AXIS_EPSILON
from .geometry2d import (
    _choose_outbound_intercept,
    _clip_infinite_line_to_bounds,
    _length_2d,
    _sign_with_epsilon,
)
from .models import (
    AnchorToTargetCommand,
    AnchorToTargetViewResult,
    Point2D,
    Point3D,
    UvHeadTargetError,
    UvTangentViewRequest,
)
from .pin_layout import _normalize_pin_name
from .runtime import _execute_line, _initial_handler
from .tangent_view import compute_uv_tangent_view


def parse_anchor_to_target_command(command_text: str) -> AnchorToTargetCommand:
    raw_text = str(command_text).strip()
    match = _ANCHOR_TO_TARGET_RE.fullmatch(raw_text)
    if match is None:
        raise UvHeadTargetError(
            "Command must match ~anchorToTarget(pinA,pinB[,offset=(x,y)][,hover=True])."
        )
    anchor_pin = _normalize_pin_name(match.group("anchor"), "Anchor pin")
    target_pin = _normalize_pin_name(match.group("target"), "Target pin")
    arguments = raw_text[raw_text.index("(") + 1 : -1]
    extras: list[str] = []
    current: list[str] = []
    depth = 0
    for char in arguments:
        if char == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                extras.append(token)
            current = []
            continue
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        current.append(char)
    token = "".join(current).strip()
    if token:
        extras.append(token)
    extras = extras[2:]
    target_offset = None
    hover = False
    for keyword in extras:
        if "=" not in keyword:
            raise UvHeadTargetError(
                "~anchorToTarget keyword arguments must be written as name=value."
            )
        keyword_name, keyword_value = keyword.split("=", 1)
        keyword_name = keyword_name.strip().lower()
        keyword_value = keyword_value.strip()
        if keyword_name == "offset":
            if not keyword_value.startswith("(") or not keyword_value.endswith(")"):
                raise UvHeadTargetError(
                    "~anchorToTarget offset must be written as offset=(x,y)."
                )
            offset_values = [part.strip() for part in keyword_value[1:-1].split(",")]
            if len(offset_values) != 2:
                raise UvHeadTargetError(
                    "~anchorToTarget offset requires exactly two values."
                )
            target_offset = (float(offset_values[0]), float(offset_values[1]))
            continue
        if keyword_name == "hover":
            hover_value = keyword_value.lower()
            if hover_value in ("true", "1", "yes", "on"):
                hover = True
                continue
            if hover_value in ("false", "0", "no", "off"):
                hover = False
                continue
            raise UvHeadTargetError(
                "~anchorToTarget hover must be written as hover=True or hover=False."
            )
        raise UvHeadTargetError(
            "~anchorToTarget only supports offset and hover keyword arguments."
        )
    return AnchorToTargetCommand(
        raw_text=raw_text,
        anchor_pin=anchor_pin,
        target_pin=target_pin,
        target_offset=target_offset,
        hover=hover,
    )


@lru_cache(maxsize=128)
def _cached_compute_uv_anchor_to_target_view(
    command_text: str,
    layer: str,
    machine_calibration_path: str | None,
    layer_calibration_path: str | None,
    roller_arm_y_offsets: tuple[float, float, float, float] | None,
) -> AnchorToTargetViewResult:
    """Cached version - all arguments must be hashable."""
    machine_calibration = _load_machine_calibration(machine_calibration_path)
    layer_calibration = _load_layer_calibration(layer, layer_calibration_path)
    command = parse_anchor_to_target_command(command_text)
    target_location = _wire_space_pin(layer_calibration, command.target_pin)
    if command.target_offset is not None:
        target_location = Location(
            float(target_location.x) + float(command.target_offset[0]),
            float(target_location.y) + float(command.target_offset[1]),
            float(target_location.z),
        )
    raw_result = compute_uv_tangent_view(
        UvTangentViewRequest(
            layer=layer,
            pin_a=command.anchor_pin,
            pin_b=command.target_pin,
        ),
        machine_calibration_path=machine_calibration_path,
        layer_calibration_path=layer_calibration_path,
        pin_b_point_override=_location_to_point3(target_location),
        roller_arm_y_offsets=roller_arm_y_offsets,
    )
    handler = _initial_handler(machine_calibration, layer_calibration)
    _execute_line(handler, command.raw_text)
    interpreter_head_point = Point2D(float(handler._x), float(handler._y))
    interpreter_wire_location = handler._headCompensation.getActualLocation(
        Location(float(handler._x), float(handler._y), float(handler._z))
    )
    interpreter_wire_point = Point2D(
        float(interpreter_wire_location.x), float(interpreter_wire_location.y)
    )
    return AnchorToTargetViewResult(
        command=command,
        raw_result=raw_result,
        interpreter_head_point=interpreter_head_point,
        interpreter_wire_point=interpreter_wire_point,
    )


def compute_uv_anchor_to_target_view(
    command_text: str,
    *,
    layer: str,
    machine_calibration_path: str | Path | None = None,
    layer_calibration_path: str | Path | None = None,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
) -> AnchorToTargetViewResult:
    """Compute with memoization cache."""
    # Convert paths to strings for hashability
    mc_path = (
        str(machine_calibration_path) if machine_calibration_path is not None else None
    )
    lc_path = (
        str(layer_calibration_path) if layer_calibration_path is not None else None
    )
    return _cached_compute_uv_anchor_to_target_view(
        command_text, layer, mc_path, lc_path, roller_arm_y_offsets
    )
    command = parse_anchor_to_target_command(command_text)
    machine_calibration = _load_machine_calibration(machine_calibration_path)
    layer_calibration = _load_layer_calibration(layer, layer_calibration_path)
    target_location = _wire_space_pin(layer_calibration, command.target_pin)
    if command.target_offset is not None:
        target_location = Location(
            float(target_location.x) + float(command.target_offset[0]),
            float(target_location.y) + float(command.target_offset[1]),
            float(target_location.z),
        )
    raw_result = compute_uv_tangent_view(
        UvTangentViewRequest(
            layer=layer,
            pin_a=command.anchor_pin,
            pin_b=command.target_pin,
        ),
        machine_calibration_path=machine_calibration_path,
        layer_calibration_path=layer_calibration_path,
        pin_b_point_override=_location_to_point3(target_location),
        roller_arm_y_offsets=roller_arm_y_offsets,
    )
    handler = _initial_handler(machine_calibration, layer_calibration)
    _execute_line(handler, command.raw_text)
    interpreter_head_point = Point2D(float(handler._x), float(handler._y))
    interpreter_wire_location = handler._headCompensation.getActualLocation(
        Location(float(handler._x), float(handler._y), float(handler._z))
    )
    interpreter_wire_point = Point2D(
        float(interpreter_wire_location.x), float(interpreter_wire_location.y)
    )
    return AnchorToTargetViewResult(
        command=command,
        raw_result=raw_result,
        interpreter_head_point=interpreter_head_point,
        interpreter_wire_point=interpreter_wire_point,
    )


def _translated_point2(point: Point2D, delta_x: float, delta_y: float) -> Point2D:
    return Point2D(float(point.x) + float(delta_x), float(point.y) + float(delta_y))


def _actual_wire_point_from_machine_target(
    *,
    final_head_xy: Point2D,
    compensated_anchor_xy: Point2D,
    anchor_z: float,
    head_z: float,
    head_arm_length: float,
    head_roller_radius: float,
    head_roller_gap: float,
) -> Point2D:
    delta_x = float(final_head_xy.x) - float(compensated_anchor_xy.x)
    delta_z = float(head_z) - float(anchor_z)
    length_xz = math.sqrt((delta_x**2) + (delta_z**2))
    if length_xz <= _AXIS_EPSILON:
        return Point2D(float(final_head_xy.x), float(final_head_xy.y))
    head_ratio = float(head_arm_length) / float(length_xz)
    x = float(final_head_xy.x) - (float(delta_x) * float(head_ratio))
    y = float(final_head_xy.y)
    z = float(head_z) - (float(delta_z) * float(head_ratio))

    delta_x = float(x) - float(compensated_anchor_xy.x)
    delta_y = float(y) - float(compensated_anchor_xy.y)
    delta_z = float(z) - float(anchor_z)
    length_xz = math.sqrt((delta_x**2) + (delta_z**2))
    length_xyz = math.sqrt((delta_x**2) + (delta_y**2) + (delta_z**2))
    if length_xz <= _AXIS_EPSILON or length_xyz <= _AXIS_EPSILON:
        return Point2D(float(x), float(y))

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

    return Point2D(float(x) - float(roller_offset_x), float(y) - float(roller_offset_y))


def translated_anchor_to_target_projection(
    view: AnchorToTargetViewResult,
    *,
    pin_translation_xy: tuple[float, float],
) -> dict[str, float]:
    delta_x = float(pin_translation_xy[0])
    delta_y = float(pin_translation_xy[1])
    if abs(delta_x) <= _AXIS_EPSILON and abs(delta_y) <= _AXIS_EPSILON:
        return {
            "projectedHeadX": float(view.interpreter_head_point.x),
            "projectedHeadY": float(view.interpreter_head_point.y),
            "projectedX": float(view.interpreter_wire_point.x),
            "projectedY": float(view.interpreter_wire_point.y),
        }

    raw = view.raw_result
    target_family = str(view.command.target_pin).strip().upper()[:1]
    head_z = float(raw.z_retracted if target_family == "A" else raw.z_extended)

    if raw.alternating_plane is not None:
        translated_head = _translated_point2(
            view.interpreter_head_point, delta_x, delta_y
        )
        translated_wire = _translated_point2(
            view.interpreter_wire_point, delta_x, delta_y
        )
        return {
            "projectedHeadX": float(translated_head.x),
            "projectedHeadY": float(translated_head.y),
            "projectedX": float(translated_wire.x),
            "projectedY": float(translated_wire.y),
        }

    if (
        raw.arm_corrected_outbound_point is None
        or raw.arm_corrected_head_center is None
        or raw.arm_corrected_selected_roller_index is None
        or not raw.roller_centers
    ):
        translated_wire = _translated_point2(
            view.interpreter_wire_point, delta_x, delta_y
        )
        translated_head = _translated_point2(
            view.interpreter_head_point, delta_x, delta_y
        )
        return {
            "projectedHeadX": float(translated_head.x),
            "projectedHeadY": float(translated_head.y),
            "projectedX": float(translated_wire.x),
            "projectedY": float(translated_wire.y),
        }

    translated_anchor_pin = Point2D(
        float(raw.pin_a_point.x) + float(delta_x),
        float(raw.pin_a_point.y) + float(delta_y),
    )
    translated_target_pin = Point2D(
        float(raw.pin_b_point.x) + float(delta_x),
        float(raw.pin_b_point.y) + float(delta_y),
    )
    translated_tangent_a = _translated_point2(raw.tangent_point_a, delta_x, delta_y)
    translated_tangent_b = _translated_point2(raw.tangent_point_b, delta_x, delta_y)
    roller_index = int(raw.arm_corrected_selected_roller_index)
    roller_center = raw.roller_centers[roller_index]
    roller_offset = Point2D(
        float(roller_center.x) - float(raw.arm_corrected_head_center.x),
        float(roller_center.y) - float(raw.arm_corrected_head_center.y),
    )
    direction = Point2D(
        float(translated_tangent_b.x) - float(translated_tangent_a.x),
        float(translated_tangent_b.y) - float(translated_tangent_a.y),
    )
    direction_length = _length_2d(direction)
    if direction_length <= _AXIS_EPSILON:
        raise UvHeadTargetError("Translated anchor-to-target line is degenerate.")
    unit_direction = Point2D(
        float(direction.x) / float(direction_length),
        float(direction.y) / float(direction_length),
    )
    tangent_x_side = _sign_with_epsilon(
        float(translated_target_pin.x) - float(translated_anchor_pin.x)
    )
    candidate_normals = (
        Point2D(-float(unit_direction.y), float(unit_direction.x)),
        Point2D(float(unit_direction.y), -float(unit_direction.x)),
    )
    matching_normals = [
        normal
        for normal in candidate_normals
        if _sign_with_epsilon(normal.x) == tangent_x_side
    ]
    if len(matching_normals) != 1:
        raise UvHeadTargetError(
            "Translated anchor-to-target line could not determine a unique tangent side."
        )
    normal = matching_normals[0]
    locus_origin = Point2D(
        float(translated_tangent_a.x)
        + (float(normal.x) * float(raw.head_roller_radius))
        - float(roller_offset.x),
        float(translated_tangent_a.y)
        + (float(normal.y) * float(raw.head_roller_radius))
        - float(roller_offset.y),
    )
    clipped = _clip_infinite_line_to_bounds(
        locus_origin,
        direction,
        raw.transfer_bounds,
    )
    if clipped is None:
        raise UvHeadTargetError(
            "Translated anchor-to-target line does not intersect the transfer bounds."
        )
    translated_head = _choose_outbound_intercept(
        locus_origin,
        Point2D(
            float(locus_origin.x) + float(direction.x),
            float(locus_origin.y) + float(direction.y),
        ),
        clipped[0],
        clipped[1],
    )
    translated_wire = _actual_wire_point_from_machine_target(
        final_head_xy=translated_head,
        compensated_anchor_xy=translated_tangent_a,
        anchor_z=float(raw.pin_a_point.z),
        head_z=head_z,
        head_arm_length=float(raw.head_arm_length),
        head_roller_radius=float(raw.head_roller_radius),
        head_roller_gap=float(raw.head_roller_gap),
    )
    return {
        "projectedHeadX": float(translated_head.x),
        "projectedHeadY": float(translated_head.y),
        "projectedX": float(translated_wire.x),
        "projectedY": float(translated_wire.y),
    }
