from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import os
import re
from pathlib import Path

from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.gcode.runtime import GCodeExecutionError, execute_text_line
from dune_winder.library.Geometry.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.geometry.uv_layout import get_uv_layout
from dune_winder.machine.geometry.uv_wrap_geometry import (
    _arm_correction_head_shift_signs as _shared_arm_correction_head_shift_signs,
    _choose_outbound_intercept as _shared_choose_outbound_intercept,
    _clip_infinite_line_to_bounds as _shared_clip_infinite_line_to_bounds,
    _length_2d as _shared_length_2d,
    _roller_index_for_head_shift_signs as _shared_roller_index_for_head_shift_signs,
    _sign_with_epsilon as _shared_sign_with_epsilon,
)
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.paths import PACKAGE_ROOT, REPO_ROOT
from dune_winder.queued_motion.filleted_path import (
    WaypointCircle,
    circle_pair_tangent_pairs,
)
from dune_winder.recipes.u_template_gcode import (
    iter_u_wrap_primary_sites,
    render_u_template_lines,
)
from dune_winder.recipes.v_template_gcode import (
    iter_v_wrap_primary_sites,
    render_v_template_lines,
)


_PIN_NAME_RE = re.compile(r"^P?[ABF]\d+$")
_RECIPE_SITE_RE = re.compile(
    r"G109\s+(P[AB]\d+)\s+P([A-Z]{2})\s+G103\s+(P[AB]\d+)\s+(P[AB]\d+).*?\(([^()]*)\)"
)
_DEFAULT_MACHINE_CALIBRATION_PATH = (
    REPO_ROOT / "dune_winder" / "config" / "machineCalibration.json"
)
_DEFAULT_LAYER_CALIBRATION_DIRECTORIES = (PACKAGE_ROOT / "config" / "APA",)
_AXIS_EPSILON = 1e-9
_ORIENTATION_TOKENS = ("BR", "BL", "LT", "LB", "RT", "RB", "TR", "TL")
_ANCHOR_TO_TARGET_RE = re.compile(
    r"~anchorToTarget\("
    r"(?P<anchor>[PAB]\d+),(?P<target>[PAB]\d+)"
    r"(?:,(?:offset=\([^)]+\)|hover=(?:True|False|1|0|yes|no|on|off))){0,2}"
    r"\)",
    re.IGNORECASE,
)


class UvHeadTargetError(ValueError):
    pass


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class RectBounds:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class LineEquation:
    slope: float
    intercept: float
    is_vertical: bool = False


@dataclass(frozen=True)
class RecipeSite:
    anchor_pin: str
    orientation_token: str
    recipe_pair_pin_a: str
    recipe_pair_pin_b: str
    site_label: str
    side: str
    position: str


@dataclass(frozen=True)
class UvHeadTargetRequest:
    layer: str
    anchor_pin: str
    wrapped_pin: str
    head_z_mode: str


@dataclass(frozen=True)
class UvTangentViewRequest:
    layer: str
    pin_a: str
    pin_b: str
    g103_adjacent_pin: str | None = None


@dataclass(frozen=True)
class UvHeadTargetResult:
    request: UvHeadTargetRequest
    site_label: str
    site_side: str
    site_position: str
    wrap_sides: tuple[str, str]
    orientation_token: str
    anchor_pin_point: Point3D
    wrapped_pin_point: Point3D
    inferred_pair_pin: str
    inferred_pair_pin_point: Point3D
    midpoint_point: Point3D
    transfer_point: Point2D
    effective_anchor_point: Point3D
    final_head_point: Point3D
    final_wire_point: Point3D
    transfer_bounds: RectBounds
    pin_radius: float
    head_arm_length: float
    head_roller_radius: float
    head_roller_gap: float
    validation_error: str | None = None


@dataclass(frozen=True)
class UvTangentViewResult:
    request: UvTangentViewRequest
    pin_a_point: Point3D
    pin_b_point: Point3D
    tangent_point_a: Point2D
    tangent_point_b: Point2D
    line_equation: LineEquation
    clipped_segment_start: Point2D
    clipped_segment_end: Point2D
    outbound_intercept: Point2D
    transfer_bounds: RectBounds
    apa_bounds: RectBounds
    apa_pin_points: tuple[Point2D, ...]
    apa_pin_points_by_name: tuple[tuple[str, Point2D], ...]
    pin_radius: float
    tangent_selection_rule: str
    anchor_side: str
    anchor_face: str
    anchor_tangent_sides: tuple[str, str]
    wrapped_side: str
    wrapped_face: str
    wrap_sides: tuple[str, str] | None = None
    runtime_orientation_token: str | None = None
    runtime_tangent_point: Point2D | None = None
    runtime_target_point: Point2D | None = None
    runtime_line_equation: LineEquation | None = None
    runtime_clipped_segment_start: Point2D | None = None
    runtime_clipped_segment_end: Point2D | None = None
    runtime_outbound_intercept: Point2D | None = None
    arm_head_center: Point2D | None = None
    arm_left_endpoint: Point2D | None = None
    arm_right_endpoint: Point2D | None = None
    roller_centers: tuple[Point2D, ...] = ()
    arm_corrected_outbound_point: Point2D | None = None
    arm_corrected_head_center: Point2D | None = None
    arm_corrected_selected_roller_index: int | None = None
    arm_corrected_quadrant: str | None = None
    arm_corrected_available: bool = False
    arm_corrected_error: str | None = None
    head_arm_length: float = 0.0
    head_roller_radius: float = 0.0
    head_roller_gap: float = 0.0
    alternating_plane: str | None = None
    alternating_face: str | None = None
    alternating_anchor_center: Point2D | None = None
    alternating_wrapped_center: Point2D | None = None
    alternating_anchor_segment_start: Point2D | None = None
    alternating_anchor_segment_end: Point2D | None = None
    alternating_wrapped_segment_start: Point2D | None = None
    alternating_wrapped_segment_end: Point2D | None = None
    alternating_anchor_contact: Point2D | None = None
    alternating_wrapped_contact: Point2D | None = None
    alternating_wrap_line_start: Point2D | None = None
    alternating_wrap_line_end: Point2D | None = None
    alternating_g109_projection: Point2D | None = None
    alternating_g103_projection: Point2D | None = None
    alternating_g108_projection: Point2D | None = None
    z_retracted: float = 0.0
    z_extended: float = 0.0
    matches_runtime_line: bool | None = None
    validation_error: str | None = None


@dataclass(frozen=True)
class WrappedPinResolution:
    wrapped_pin: str
    adjacent_pin: str
    wrap_sides: tuple[str, str]


@dataclass(frozen=True)
class AnchorToTargetCommand:
    raw_text: str
    anchor_pin: str
    target_pin: str
    target_offset: tuple[float, float] | None
    hover: bool


@dataclass(frozen=True)
class AnchorToTargetViewResult:
    command: AnchorToTargetCommand
    raw_result: UvTangentViewResult
    interpreter_head_point: Point2D
    interpreter_wire_point: Point2D


def _normalize_layer(layer: str) -> str:
    value = str(layer).strip().upper()
    if value not in {"U", "V"}:
        raise UvHeadTargetError("Layer must be 'U' or 'V'.")
    return value


def _normalize_head_z_mode(mode: str) -> str:
    value = str(mode).strip().lower()
    if value not in {"front", "back"}:
        raise UvHeadTargetError("Head Z mode must be 'front' or 'back'.")
    return value


def _normalize_pin_name(pin_name: str, label: str) -> str:
    value = str(pin_name).strip().upper()
    if not _PIN_NAME_RE.match(value):
        raise UvHeadTargetError(f"{label} must be a pin name like B1201 or A799.")
    if value.startswith("F"):
        value = "A" + value[1:]
    return value


def _default_layer_calibration_path(layer: str) -> Path:
    file_name = f"{layer}_Calibration.json"
    for directory in _DEFAULT_LAYER_CALIBRATION_DIRECTORIES:
        candidate = directory / file_name
        if candidate.exists():
            return candidate
    return _DEFAULT_LAYER_CALIBRATION_DIRECTORIES[0] / file_name


@lru_cache(maxsize=4)
def _load_machine_calibration(path: str | Path | None = None) -> MachineCalibration:
    resolved_path = (
        Path(path) if path is not None else _DEFAULT_MACHINE_CALIBRATION_PATH
    )
    calibration = MachineCalibration(str(resolved_path.parent), resolved_path.name)
    calibration.load()
    return calibration


@lru_cache(maxsize=8)
def _load_layer_calibration(
    layer: str, path: str | Path | None = None
) -> LayerCalibration:
    resolved_path = (
        Path(path) if path is not None else _default_layer_calibration_path(layer)
    )
    calibration = LayerCalibration(layer)
    calibration.load(
        str(resolved_path.parent), resolved_path.name, exceptionForMismatch=False
    )
    return calibration


def clear_uv_head_target_caches(
    *, layer_calibration: bool = True, machine_calibration: bool = False
) -> None:
    if layer_calibration:
        _load_layer_calibration.cache_clear()
        _cached_all_wire_space_pins.cache_clear()
    if machine_calibration:
        _load_machine_calibration.cache_clear()
        _cached_compute_uv_anchor_to_target_view.cache_clear()
        _cached_compute_pin_pair_tangent_geometry.cache_clear()


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
    current = []
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
    direction_length = _shared_length_2d(direction)
    if direction_length <= _AXIS_EPSILON:
        raise UvHeadTargetError("Translated anchor-to-target line is degenerate.")
    unit_direction = Point2D(
        float(direction.x) / float(direction_length),
        float(direction.y) / float(direction_length),
    )
    tangent_x_side = _shared_sign_with_epsilon(
        float(translated_target_pin.x) - float(translated_anchor_pin.x)
    )
    candidate_normals = (
        Point2D(-float(unit_direction.y), float(unit_direction.x)),
        Point2D(float(unit_direction.y), -float(unit_direction.x)),
    )
    matching_normals = [
        normal
        for normal in candidate_normals
        if _shared_sign_with_epsilon(normal.x) == tangent_x_side
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
    clipped = _shared_clip_infinite_line_to_bounds(
        locus_origin,
        direction,
        raw.transfer_bounds,
    )
    if clipped is None:
        raise UvHeadTargetError(
            "Translated anchor-to-target line does not intersect the transfer bounds."
        )
    translated_head = _shared_choose_outbound_intercept(
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


def _location_to_point3(location: Location) -> Point3D:
    return Point3D(float(location.x), float(location.y), float(location.z))


def _location_to_point2(location: Location) -> Point2D:
    return Point2D(float(location.x), float(location.y))


def _wire_space_pin(layer_calibration: LayerCalibration, pin_name: str) -> Location:
    if not layer_calibration.getPinExists(pin_name):
        raise UvHeadTargetError(
            f"Pin {pin_name} is not present in {layer_calibration.getLayerNames()} calibration."
        )
    return layer_calibration.getPinLocation(pin_name).add(layer_calibration.offset)


def _all_wire_space_pins(layer_calibration: LayerCalibration) -> dict[str, Point3D]:
    return {
        pin_name: _location_to_point3(_wire_space_pin(layer_calibration, pin_name))
        for pin_name in layer_calibration.getPinNames()
    }


def _pin_number(pin_name: str) -> int:
    return int(str(pin_name)[1:])


def _derive_wrap_context(layer: str, wrapped_pin: str) -> tuple[str, str]:
    layout = get_uv_layout(layer)
    side = _pin_family_side(wrapped_pin)
    try:
        face = layout.face_for_pin(wrapped_pin)
    except ValueError as exc:
        raise UvHeadTargetError(
            f"Could not determine board metadata for wrapped pin {wrapped_pin} on layer {layer}."
        ) from exc
    return (side, face)


def _wrap_context_for_pin(
    layer: str, pin_name: str
) -> tuple[str, str, tuple[str, str]]:
    side, face = _derive_wrap_context(layer, pin_name)
    return (side, face, tangent_sides(layer, pin_name))


def _pin_family_side(pin_name: str) -> str:
    normalized_pin = _normalize_pin_name(pin_name, "Pin")
    return "B" if normalized_pin.startswith("B") else "A"


def _face_for_pin(layer: str, pin_name: str) -> str:
    try:
        return get_uv_layout(layer).face_for_pin(pin_name)
    except ValueError as exc:
        raise UvHeadTargetError(
            f"Could not determine board metadata for pin {pin_name} on layer {layer}."
        ) from exc


def _b_side_equivalent_pin(layer: str, pin_name: str) -> str:
    normalized_layer = _normalize_layer(layer)
    normalized_pin = _normalize_pin_name(pin_name, "Pin")
    return get_uv_layout(normalized_layer).translate_pin(
        normalized_pin,
        target_family="B",
    )


def _b_side_face_for_pin(layer: str, pin_name: str) -> str:
    return _face_for_pin(layer, _b_side_equivalent_pin(layer, pin_name))


def tangent_sides(layer: str, pin_name: str) -> tuple[str, str]:
    normalized_layer = _normalize_layer(layer)
    normalized_pin = _normalize_pin_name(pin_name, "Pin")
    try:
        return get_uv_layout(normalized_layer).tangent_sides(normalized_pin)
    except ValueError as exc:
        raise UvHeadTargetError(str(exc)) from exc


def _format_tangent_sides(tangent_sides_value: tuple[str, str] | None) -> str:
    if tangent_sides_value is None:
        return "n/a"
    x_side, y_side = tangent_sides_value
    return f"x={x_side}, y={y_side}"


def _alternating_plane_for_face(face: str) -> str:
    face_value = str(face).strip().lower()
    if face_value in ("top", "bottom"):
        return "xz"
    if face_value in ("head", "foot"):
        return "yz"
    raise UvHeadTargetError(f"Unsupported face {face!r} for alternating-side view.")


def _project_point3_to_plane(point: Point3D, plane: str) -> Point2D:
    if plane == "xz":
        return Point2D(point.x, point.z)
    if plane == "yz":
        return Point2D(point.z, point.y)
    raise UvHeadTargetError(f"Unsupported alternating plane {plane!r}.")


def _project_location_to_plane(location: Location, plane: str) -> Point2D:
    return _project_point3_to_plane(_location_to_point3(location), plane)


def _segment_endpoints_for_plane(
    center: Point2D,
    *,
    plane: str,
    pin_radius: float,
) -> tuple[Point2D, Point2D]:
    if plane == "xz":
        return (
            Point2D(center.x - pin_radius, center.y),
            Point2D(center.x + pin_radius, center.y),
        )
    if plane == "yz":
        return (
            Point2D(center.x, center.y - pin_radius),
            Point2D(center.x, center.y + pin_radius),
        )
    raise UvHeadTargetError(f"Unsupported alternating plane {plane!r}.")


def _segment_contact_for_wrap_side(
    center: Point2D,
    *,
    plane: str,
    pin_radius: float,
    tangent_sides_value: tuple[str, str],
) -> Point2D:
    negative_endpoint, positive_endpoint = _segment_endpoints_for_plane(
        center,
        plane=plane,
        pin_radius=pin_radius,
    )
    axis = "x" if plane == "xz" else "y"
    if _side_sign_for_axis(tangent_sides_value, axis) == "plus":
        return positive_endpoint
    return negative_endpoint


def _side_sign_for_axis(tangent_sides_value: tuple[str, str], axis: str) -> str:
    if axis == "x":
        return tangent_sides_value[0]
    if axis == "y":
        return tangent_sides_value[1]
    raise UvHeadTargetError(f"Unsupported axis {axis!r}.")


def _extend_segment_to_machine_z_planes(
    start: Point2D,
    end: Point2D,
    *,
    plane: str,
    z_retracted: float,
    z_extended: float,
) -> tuple[Point2D, Point2D]:
    if plane == "xz":
        delta_z = end.y - start.y
        if abs(delta_z) <= _AXIS_EPSILON:
            return (Point2D(start.x, z_retracted), Point2D(end.x, z_extended))

        def point_at_z(z_value: float) -> Point2D:
            parameter = (z_value - start.y) / delta_z
            return Point2D(start.x + (parameter * (end.x - start.x)), z_value)

        return (point_at_z(z_retracted), point_at_z(z_extended))

    if plane == "yz":
        delta_z = end.x - start.x
        if abs(delta_z) <= _AXIS_EPSILON:
            return (Point2D(z_retracted, start.y), Point2D(z_extended, end.y))

        def point_at_z(z_value: float) -> Point2D:
            parameter = (z_value - start.x) / delta_z
            return Point2D(z_value, start.y + (parameter * (end.y - start.y)))

        return (point_at_z(z_retracted), point_at_z(z_extended))

    raise UvHeadTargetError(f"Unsupported alternating plane {plane!r}.")


def _compute_alternating_projection_data(
    *,
    plane: str,
    pin_a_point: Point3D,
    pin_b_point: Point3D,
    pin_radius: float,
    anchor_tangent_sides: tuple[str, str],
    wrapped_tangent_sides: tuple[str, str],
    z_retracted: float,
    z_extended: float,
    runtime_g109_location: Location,
    runtime_g103_location: Location,
) -> dict[str, Point2D]:
    anchor_center = _project_point3_to_plane(pin_a_point, plane)
    wrapped_center = _project_point3_to_plane(pin_b_point, plane)
    anchor_segment_start, anchor_segment_end = _segment_endpoints_for_plane(
        anchor_center,
        plane=plane,
        pin_radius=pin_radius,
    )
    wrapped_segment_start, wrapped_segment_end = _segment_endpoints_for_plane(
        wrapped_center,
        plane=plane,
        pin_radius=pin_radius,
    )
    anchor_contact = _segment_contact_for_wrap_side(
        anchor_center,
        plane=plane,
        pin_radius=pin_radius,
        tangent_sides_value=anchor_tangent_sides,
    )
    wrapped_contact = _segment_contact_for_wrap_side(
        wrapped_center,
        plane=plane,
        pin_radius=pin_radius,
        tangent_sides_value=wrapped_tangent_sides,
    )
    wrap_line_start, wrap_line_end = _extend_segment_to_machine_z_planes(
        anchor_contact,
        wrapped_contact,
        plane=plane,
        z_retracted=z_retracted,
        z_extended=z_extended,
    )
    return {
        "anchor_center": anchor_center,
        "wrapped_center": wrapped_center,
        "anchor_segment_start": anchor_segment_start,
        "anchor_segment_end": anchor_segment_end,
        "wrapped_segment_start": wrapped_segment_start,
        "wrapped_segment_end": wrapped_segment_end,
        "anchor_contact": anchor_contact,
        "wrapped_contact": wrapped_contact,
        "wrap_line_start": wrap_line_start,
        "wrap_line_end": wrap_line_end,
        "g109_projection": _project_location_to_plane(runtime_g109_location, plane),
        "g103_projection": _project_location_to_plane(runtime_g103_location, plane),
        "g108_projection": None,
    }


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


def _parse_site_label(site_label: str) -> tuple[str, str]:
    label = str(site_label).strip().lower()
    if " a " in f" {label} ":
        side = "A"
    elif " b " in f" {label} ":
        side = "B"
    else:
        raise UvHeadTargetError(f"Could not determine site side from {site_label!r}.")

    for position in ("top", "bottom", "head", "foot"):
        if position in label:
            return (side, position)
    raise UvHeadTargetError(f"Could not determine site position from {site_label!r}.")


def _strip_p_prefix(pin_name: str) -> str:
    value = str(pin_name).strip().upper()
    if value.startswith("P"):
        return value[1:]
    return value


def _render_lines_for_layer(layer: str) -> list[str]:
    if layer == "U":
        return render_u_template_lines(strip_g113_params=True)
    return render_v_template_lines(strip_g113_params=True)


def iter_uv_wrap_primary_sites(
    layer: str,
    *,
    named_inputs=None,
    special_inputs=None,
    cell_overrides=None,
):
    normalized_layer = _normalize_layer(layer)
    if normalized_layer == "U":
        return iter_u_wrap_primary_sites(
            named_inputs=named_inputs,
            special_inputs=special_inputs,
            cell_overrides=cell_overrides,
        )
    return iter_v_wrap_primary_sites(
        named_inputs=named_inputs,
        special_inputs=special_inputs,
        cell_overrides=cell_overrides,
    )


@lru_cache(maxsize=2)
def _recipe_sites_by_anchor(layer: str) -> dict[str, list[RecipeSite]]:
    result: dict[str, list[RecipeSite]] = {}
    for line in _render_lines_for_layer(layer):
        match = _RECIPE_SITE_RE.search(line)
        if match is None:
            continue
        anchor_pin, orientation_token, pair_pin_a, pair_pin_b, site_label = (
            match.groups()
        )
        anchor_pin = _strip_p_prefix(anchor_pin)
        pair_pin_a = _strip_p_prefix(pair_pin_a)
        pair_pin_b = _strip_p_prefix(pair_pin_b)
        side, position = _parse_site_label(site_label)
        candidate = RecipeSite(
            anchor_pin=anchor_pin,
            orientation_token=orientation_token,
            recipe_pair_pin_a=pair_pin_a,
            recipe_pair_pin_b=pair_pin_b,
            site_label=site_label,
            side=side,
            position=position,
        )
        result.setdefault(anchor_pin, []).append(candidate)
    return result


def _lookup_recipe_site(layer: str, *args) -> RecipeSite:
    if len(args) == 2:
        anchor_pin, wrapped_pin = args
    elif len(args) == 3:
        _layer_calibration, anchor_pin, wrapped_pin = args
    else:
        raise TypeError("_lookup_recipe_site expects layer plus anchor/wrapped pins.")
    normalized_layer = _normalize_layer(layer)
    normalized_anchor_pin = _strip_p_prefix(
        _normalize_pin_name(anchor_pin, "Anchor pin")
    )
    normalized_wrapped_pin = _strip_p_prefix(
        _normalize_pin_name(wrapped_pin, "Wrapped pin")
    )

    candidates = _recipe_sites_by_anchor(normalized_layer).get(
        normalized_anchor_pin, []
    )
    if not candidates:
        raise UvHeadTargetError(
            f"No recipe site found for anchor pin {normalized_anchor_pin} in layer {normalized_layer}."
        )

    for candidate in candidates:
        if normalized_wrapped_pin in {
            candidate.recipe_pair_pin_a,
            candidate.recipe_pair_pin_b,
        }:
            return candidate

    raise UvHeadTargetError(
        f"No recipe site found for anchor pin {normalized_anchor_pin} and wrapped pin {normalized_wrapped_pin} in layer {normalized_layer}."
    )


def _infer_pair_pin_from_wrap_side(
    layer_calibration: LayerCalibration,
    wrapped_pin: str,
    tangent_sides_value: tuple[str, str],
) -> str:
    wrapped_pin_name = (
        wrapped_pin[1:] if str(wrapped_pin).upper().startswith("P") else wrapped_pin
    )
    wrapped_location = _wire_space_pin(layer_calibration, wrapped_pin_name)
    wrapped_face = _face_for_pin(layer_calibration.getLayerNames(), wrapped_pin_name)
    same_face_pins = [
        pin_name
        for pin_name in layer_calibration.getPinNames()
        if (
            pin_name.startswith(wrapped_pin_name[0])
            and pin_name != wrapped_pin_name
            and _face_for_pin(layer_calibration.getLayerNames(), pin_name)
            == wrapped_face
        )
    ]
    if not same_face_pins:
        raise UvHeadTargetError(f"No same-face candidate pins found for {wrapped_pin}.")

    best_pin = None
    best_score = None
    x_sign = 1.0 if tangent_sides_value[0] == "plus" else -1.0

    def candidate_specs():
        for pin_name in same_face_pins:
            location = _wire_space_pin(layer_calibration, pin_name)
            delta_x = float(location.x - wrapped_location.x)
            delta_y = float(location.y - wrapped_location.y)
            signed_x = x_sign * delta_x
            if signed_x <= _AXIS_EPSILON:
                continue
            yield (pin_name, signed_x, abs(delta_y))

    candidates = list(candidate_specs())
    if candidates:
        local_pitch_x = min(spec[1] for spec in candidates)
    else:
        local_pitch_x = 0.0
    local_min_signed_x = local_pitch_x * 4.0
    local_max_signed_x = local_pitch_x * 12.0
    preferred_candidates = [
        spec
        for spec in candidates
        if local_min_signed_x - 1e-6 <= spec[1] <= local_max_signed_x + 1e-6
    ]

    for pin_name, signed_x, abs_delta_y in preferred_candidates or candidates:
        score = (abs_delta_y, signed_x)
        if best_score is None or score < best_score:
            best_score = score
            best_pin = pin_name

    if best_pin is None:
        raise UvHeadTargetError(
            "Could not infer the second G103 pin from wrapped pin "
            f"{wrapped_pin} and tangent sides {_format_tangent_sides(tangent_sides_value)}."
        )

    if str(wrapped_pin).upper().startswith("P"):
        return f"P{best_pin}"
    return best_pin


def _infer_local_pair_pin_from_wrap_side(
    layer_calibration: LayerCalibration,
    wrapped_pin: str,
    tangent_sides_value: tuple[str, str],
) -> str:
    wrapped_pin_label = str(wrapped_pin).strip().upper()
    wrapped_pin_name = (
        wrapped_pin[1:] if str(wrapped_pin).upper().startswith("P") else wrapped_pin
    )
    wrapped_location = _wire_space_pin(layer_calibration, wrapped_pin_name)
    family_pins = [
        pin_name
        for pin_name in layer_calibration.getPinNames()
        if pin_name.startswith(wrapped_pin_name[0]) and pin_name != wrapped_pin_name
    ]
    if not family_pins:
        raise UvHeadTargetError(
            f"No same-family candidate pins found for {wrapped_pin}."
        )

    def best_match(candidate_pins: list[str]) -> str | None:
        best_pin = None
        best_score = None
        wrapped_point = Point2D(float(wrapped_location.x), float(wrapped_location.y))
        for pin_name in candidate_pins:
            location = _wire_space_pin(layer_calibration, pin_name)
            delta_x = float(location.x - wrapped_location.x)
            delta_y = float(location.y - wrapped_location.y)
            candidate_point = Point2D(float(location.x), float(location.y))
            x_match = _is_on_wrap_side(
                candidate_point,
                wrapped_point,
                "x",
                tangent_sides_value[0],
            )
            y_match = _is_on_wrap_side(
                candidate_point,
                wrapped_point,
                "y",
                tangent_sides_value[1],
            )
            if not (x_match or y_match):
                continue
            match_count = int(x_match) + int(y_match)
            orthogonal_error = min(
                abs(delta_y) if x_match else math.inf,
                abs(delta_x) if y_match else math.inf,
            )
            distance = math.hypot(delta_x, delta_y)
            pin_number_gap = abs(_pin_number(pin_name) - _pin_number(wrapped_pin_name))
            score = (
                pin_number_gap,
                orthogonal_error,
                distance,
                -match_count,
            )
            if best_score is None or score < best_score:
                best_score = score
                best_pin = pin_name
        return best_pin

    wrapped_face = _face_for_pin(layer_calibration.getLayerNames(), wrapped_pin_name)
    same_face_pins = [
        pin_name
        for pin_name in family_pins
        if _face_for_pin(layer_calibration.getLayerNames(), pin_name) == wrapped_face
    ]
    best_pin = best_match(same_face_pins) or best_match(family_pins)
    if best_pin is None:
        raise UvHeadTargetError(
            "Could not infer a nearby G103 pair pin from wrapped pin "
            f"{wrapped_pin} and tangent sides {_format_tangent_sides(tangent_sides_value)}."
        )
    if wrapped_pin_label.startswith("P"):
        return f"P{best_pin}"
    if wrapped_pin_label.startswith("F"):
        return f"F{best_pin[1:]}"
    return best_pin


def resolve_wrapped_pin_from_g103_pair(
    layer: str,
    g103_pin_a: str,
    g103_pin_b: str,
    *,
    layer_calibration_path: str | Path | None = None,
    preferred_wrapped_pin: str | None = None,
) -> WrappedPinResolution:
    normalized_layer = _normalize_layer(layer)
    candidate_a = _normalize_pin_name(g103_pin_a, "G103 pin A")
    candidate_b = _normalize_pin_name(g103_pin_b, "G103 pin B")
    preferred_candidate = None
    if preferred_wrapped_pin is not None:
        preferred_candidate = _normalize_pin_name(
            preferred_wrapped_pin, "Preferred wrapped pin"
        )
    if candidate_a == candidate_b:
        raise UvHeadTargetError("G103 pin pair must contain two different pins.")
    if candidate_a[:1] != candidate_b[:1]:
        raise UvHeadTargetError(
            f"G103 pin pair must be same-side; got {candidate_a} and {candidate_b}."
        )

    layer_calibration = _load_layer_calibration(
        normalized_layer,
        layer_calibration_path,
    )
    geometric_matches: list[WrappedPinResolution] = []
    inferred_matches: list[WrappedPinResolution] = []
    for wrapped_candidate, adjacent_candidate in (
        (candidate_a, candidate_b),
        (candidate_b, candidate_a),
    ):
        wrapped_side, wrapped_face = _derive_wrap_context(
            normalized_layer, wrapped_candidate
        )
        tangent_sides_value = tangent_sides(normalized_layer, wrapped_candidate)
        wrapped_point = _location_to_point2(
            _wire_space_pin(layer_calibration, wrapped_candidate)
        )
        adjacent_point = _location_to_point2(
            _wire_space_pin(layer_calibration, adjacent_candidate)
        )
        if _is_on_wrap_side(
            adjacent_point, wrapped_point, "x", tangent_sides_value[0]
        ) or _is_on_wrap_side(
            adjacent_point, wrapped_point, "y", tangent_sides_value[1]
        ):
            geometric_matches.append(
                WrappedPinResolution(
                    wrapped_pin=wrapped_candidate,
                    adjacent_pin=adjacent_candidate,
                    wrap_sides=tangent_sides_value,
                )
            )
        inferred_adjacent = _infer_pair_pin_from_wrap_side(
            layer_calibration,
            wrapped_candidate,
            tangent_sides_value,
        )
        if inferred_adjacent == adjacent_candidate:
            inferred_matches.append(
                WrappedPinResolution(
                    wrapped_pin=wrapped_candidate,
                    adjacent_pin=adjacent_candidate,
                    wrap_sides=tangent_sides_value,
                )
            )

    if len(geometric_matches) == 1:
        return geometric_matches[0]
    if len(geometric_matches) != 1 and len(inferred_matches) == 1:
        return inferred_matches[0]
    if preferred_candidate is not None:
        ordered_matches = geometric_matches or inferred_matches
        preferred_matches = [
            match
            for match in ordered_matches
            if match.wrapped_pin == preferred_candidate
        ]
        if len(preferred_matches) == 1:
            return preferred_matches[0]
    if not geometric_matches and not inferred_matches:
        raise UvHeadTargetError(
            "Could not resolve wrapped pin from G103 pair "
            f"{candidate_a}/{candidate_b} on layer {normalized_layer}."
        )
    raise UvHeadTargetError(
        "Ambiguous wrapped pin from G103 pair "
        f"{candidate_a}/{candidate_b} on layer {normalized_layer}."
    )


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


def _dot_2d(a: Point2D, b: Point2D) -> float:
    return (a.x * b.x) + (a.y * b.y)


def _subtract_2d(a: Point2D, b: Point2D) -> Point2D:
    return Point2D(a.x - b.x, a.y - b.y)


def _length_2d(point: Point2D) -> float:
    return math.hypot(point.x, point.y)


def _point_on_line(point: Point2D, origin: Point2D, direction: Point2D) -> float:
    return _dot_2d(_subtract_2d(point, origin), direction)


def _choose_outbound_intercept(
    tangent_a: Point2D,
    tangent_b: Point2D,
    clipped_start: Point2D,
    clipped_end: Point2D,
) -> Point2D:
    direction = _subtract_2d(tangent_b, tangent_a)
    start_projection = _point_on_line(clipped_start, tangent_a, direction)
    end_projection = _point_on_line(clipped_end, tangent_a, direction)
    if end_projection >= start_projection:
        return clipped_end
    return clipped_start


def _is_on_wrap_side(
    point: Point2D, center: Point2D, axis: str, side_sign: str
) -> bool:
    sign = 1.0 if side_sign == "plus" else -1.0
    axis_delta = (point.x - center.x) if axis == "x" else (point.y - center.y)
    return (sign * axis_delta) > _AXIS_EPSILON


def _matches_tangent_sides(
    point: Point2D,
    center: Point2D,
    tangent_sides_value: tuple[str, str],
) -> bool:
    return _is_on_wrap_side(
        point, center, "x", tangent_sides_value[0]
    ) and _is_on_wrap_side(
        point,
        center,
        "y",
        tangent_sides_value[1],
    )


def matches_tangent_sides(
    point: Point2D,
    center: Point2D,
    tangent_sides_value: tuple[str, str],
) -> bool:
    return _matches_tangent_sides(point, center, tangent_sides_value)


def _line_equation_from_tangent_points(
    tangent_a: Point2D, tangent_b: Point2D
) -> LineEquation:
    delta_x = tangent_b.x - tangent_a.x
    delta_y = tangent_b.y - tangent_a.y
    if abs(delta_x) <= _AXIS_EPSILON:
        return LineEquation(slope=float("inf"), intercept=tangent_a.x, is_vertical=True)
    slope = delta_y / delta_x
    intercept = tangent_a.y - (slope * tangent_a.x)
    return LineEquation(slope=slope, intercept=intercept, is_vertical=False)


def _clip_infinite_line_to_bounds(
    line_point: Point2D,
    line_direction: Point2D,
    bounds: RectBounds,
) -> tuple[Point2D, Point2D] | None:
    dx = line_direction.x
    dy = line_direction.y
    if abs(dx) <= _AXIS_EPSILON and abs(dy) <= _AXIS_EPSILON:
        return None

    candidates: list[tuple[float, Point2D]] = []

    def add_candidate(parameter: float, x: float, y: float) -> None:
        if x < bounds.left - _AXIS_EPSILON or x > bounds.right + _AXIS_EPSILON:
            return
        if y < bounds.bottom - _AXIS_EPSILON or y > bounds.top + _AXIS_EPSILON:
            return
        point = Point2D(x, y)
        for existing_parameter, existing_point in candidates:
            if math.isclose(existing_parameter, parameter, abs_tol=1e-8) or (
                math.isclose(existing_point.x, point.x, abs_tol=1e-8)
                and math.isclose(existing_point.y, point.y, abs_tol=1e-8)
            ):
                return
        candidates.append((parameter, point))

    if abs(dx) > _AXIS_EPSILON:
        for x in (bounds.left, bounds.right):
            parameter = (x - line_point.x) / dx
            add_candidate(parameter, x, line_point.y + (parameter * dy))
    if abs(dy) > _AXIS_EPSILON:
        for y in (bounds.bottom, bounds.top):
            parameter = (y - line_point.y) / dy
            add_candidate(parameter, line_point.x + (parameter * dx), y)

    if len(candidates) < 2:
        return None
    candidates.sort(key=lambda item: item[0])
    return (candidates[0][1], candidates[-1][1])


def _tangent_candidates_for_pin_pair(
    point_a: Point2D,
    point_b: Point2D,
    pin_radius: float,
) -> list[tuple[Point2D, Point2D]]:
    if (
        _length_2d(Point2D(point_b.x - point_a.x, point_b.y - point_a.y))
        <= _AXIS_EPSILON
    ):
        raise UvHeadTargetError("Cannot compute a tangent for coincident pin centers.")
    tangent_pairs = circle_pair_tangent_pairs(
        WaypointCircle(
            waypoint_xy=(point_a.x, point_a.y),
            center_xy=(point_a.x, point_a.y),
            radius=pin_radius,
        ),
        WaypointCircle(
            waypoint_xy=(point_b.x, point_b.y),
            center_xy=(point_b.x, point_b.y),
            radius=pin_radius,
        ),
    )
    return [
        (Point2D(first_xy[0], first_xy[1]), Point2D(second_xy[0], second_xy[1]))
        for first_xy, second_xy in tangent_pairs
    ]


def _apa_bounds_from_points(points: tuple[Point2D, ...]) -> RectBounds:
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    return RectBounds(left=min(xs), top=max(ys), right=max(xs), bottom=min(ys))


def _select_tangent_solution(
    candidates: list[tuple[Point2D, Point2D]],
    transfer_bounds: RectBounds,
    anchor_pin_point: Point2D | None = None,
    anchor_tangent_sides: tuple[str, str] | None = None,
    wrapped_pin_point: Point2D | None = None,
    wrapped_tangent_sides: tuple[str, str] | None = None,
) -> tuple[Point2D, Point2D, Point2D, Point2D]:
    ranked: list[
        tuple[
            tuple[int, int, float, float, float],
            tuple[Point2D, Point2D, Point2D, Point2D],
        ]
    ] = []
    for tangent_a, tangent_b in candidates:
        anchor_matches = (
            anchor_pin_point is not None
            and anchor_tangent_sides is not None
            and _matches_tangent_sides(
                tangent_a, anchor_pin_point, anchor_tangent_sides
            )
        )
        target_matches = (
            wrapped_pin_point is not None
            and wrapped_tangent_sides is not None
            and _matches_tangent_sides(
                tangent_b, wrapped_pin_point, wrapped_tangent_sides
            )
        )
        clipped = _clip_infinite_line_to_bounds(
            tangent_a,
            Point2D(tangent_b.x - tangent_a.x, tangent_b.y - tangent_a.y),
            transfer_bounds,
        )
        if clipped is None:
            continue
        clipped_start, clipped_end = clipped
        outbound = _choose_outbound_intercept(
            tangent_a, tangent_b, clipped_start, clipped_end
        )
        ranked.append(
            (
                (
                    int(anchor_matches) + int(target_matches),
                    int(target_matches),
                    outbound.y,
                    outbound.x,
                    tangent_a.y,
                ),
                (tangent_a, tangent_b, clipped_start, clipped_end),
            )
        )

    if not ranked:
        raise UvHeadTargetError("Could not clip a tangent line to the transfer zone.")

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _line_match(
    left: LineEquation | None,
    right: LineEquation | None,
    *,
    tolerance: float = 1e-3,
) -> bool | None:
    if left is None or right is None:
        return None
    if left.is_vertical or right.is_vertical:
        return (
            left.is_vertical
            and right.is_vertical
            and math.isclose(left.intercept, right.intercept, abs_tol=tolerance)
        )
    return math.isclose(left.slope, right.slope, abs_tol=tolerance) and math.isclose(
        left.intercept, right.intercept, abs_tol=tolerance
    )


def _line_deviation_at_point(
    reference_point: Point2D, candidate_point: Point2D
) -> float:
    return math.hypot(
        candidate_point.x - reference_point.x, candidate_point.y - reference_point.y
    )


def _build_arm_geometry(
    head_center: Point2D,
    *,
    head_arm_length: float,
    head_roller_radius: float,
    head_roller_gap: float,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
) -> tuple[Point2D, Point2D, tuple[Point2D, ...]]:
    if roller_arm_y_offsets is not None:
        y_offsets = roller_arm_y_offsets
    else:
        y_nom = (head_roller_gap / 2.0) + head_roller_radius
        y_offsets = (y_nom, y_nom, y_nom, y_nom)
    left_endpoint = Point2D(head_center.x - head_arm_length, head_center.y)
    right_endpoint = Point2D(head_center.x + head_arm_length, head_center.y)
    rollers = (
        Point2D(left_endpoint.x, head_center.y - y_offsets[0]),
        Point2D(left_endpoint.x, head_center.y + y_offsets[1]),
        Point2D(right_endpoint.x, head_center.y - y_offsets[2]),
        Point2D(right_endpoint.x, head_center.y + y_offsets[3]),
    )
    return (left_endpoint, right_endpoint, rollers)


def _sign_with_epsilon(value: float, *, epsilon: float = _AXIS_EPSILON) -> int:
    if value > epsilon:
        return 1
    if value < -epsilon:
        return -1
    return 0


def _arm_correction_tangent_y_side(
    *,
    anchor_pin_point: Point2D,
    target_pin_point: Point2D,
) -> int | None:
    sign_y = _sign_with_epsilon(target_pin_point.y - anchor_pin_point.y)
    if sign_y == 0:
        return None
    return -1 if sign_y > 0 else 1


def _arm_correction_head_shift_signs(
    *,
    anchor_pin_point: Point2D,
    target_pin_point: Point2D,
) -> tuple[int, int] | None:
    return _shared_arm_correction_head_shift_signs(
        anchor_pin_point=anchor_pin_point,
        target_pin_point=target_pin_point,
    )


def _roller_index_for_head_shift_signs(sign_x: int, sign_y: int) -> int:
    return _shared_roller_index_for_head_shift_signs(sign_x, sign_y)


def _roller_offset_for_index(
    roller_index: int,
    *,
    head_arm_length: float,
    head_roller_radius: float,
    head_roller_gap: float,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
) -> Point2D:
    if roller_arm_y_offsets is not None:
        y_offset = roller_arm_y_offsets[roller_index]
    else:
        y_offset = (head_roller_gap / 2.0) + head_roller_radius
    y_sign = -1 if roller_index in (0, 2) else 1
    x_offset = -head_arm_length if roller_index in (0, 1) else head_arm_length
    return Point2D(x_offset, y_sign * y_offset)


def _distance_point_to_line(
    point: Point2D,
    *,
    line_point: Point2D,
    line_direction: Point2D,
) -> float:
    numerator = abs(
        ((point.x - line_point.x) * line_direction.y)
        - ((point.y - line_point.y) * line_direction.x)
    )
    denominator = _length_2d(line_direction)
    if denominator <= _AXIS_EPSILON:
        raise UvHeadTargetError("Cannot measure distance to a degenerate line.")
    return numerator / denominator


def _compute_arm_corrected_outbound(
    *,
    anchor_pin_point: Point2D,
    target_pin_point: Point2D,
    tangent_point_a: Point2D,
    tangent_point_b: Point2D,
    transfer_bounds: RectBounds,
    head_arm_length: float,
    head_roller_radius: float,
    head_roller_gap: float,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
) -> tuple[Point2D, Point2D, int, str]:
    head_shift_signs = _arm_correction_head_shift_signs(
        anchor_pin_point=anchor_pin_point,
        target_pin_point=target_pin_point,
    )
    tangent_x_side = _sign_with_epsilon(target_pin_point.x - anchor_pin_point.x)
    if tangent_x_side == 0 or head_shift_signs is None:
        raise UvHeadTargetError(
            "Arm correction is unavailable because the anchor-to-target pin direction is indeterminate."
        )
    sign_x, sign_y = head_shift_signs
    roller_index = _roller_index_for_head_shift_signs(sign_x, sign_y)
    quadrant = {
        (-1, -1): "SW",
        (-1, 1): "NW",
        (1, -1): "SE",
        (1, 1): "NE",
    }[(sign_x, sign_y)]
    roller_offset = _roller_offset_for_index(
        roller_index,
        head_arm_length=head_arm_length,
        head_roller_radius=head_roller_radius,
        head_roller_gap=head_roller_gap,
        roller_arm_y_offsets=roller_arm_y_offsets,
    )
    direction = Point2D(
        tangent_point_b.x - tangent_point_a.x,
        tangent_point_b.y - tangent_point_a.y,
    )
    direction_length = _length_2d(direction)
    if direction_length <= _AXIS_EPSILON:
        raise UvHeadTargetError(
            "Arm correction requires a non-degenerate tangent line."
        )
    unit_direction = Point2D(
        direction.x / direction_length, direction.y / direction_length
    )
    candidate_normals = (
        Point2D(-unit_direction.y, unit_direction.x),
        Point2D(unit_direction.y, -unit_direction.x),
    )
    matching_normals = [
        normal
        for normal in candidate_normals
        if _sign_with_epsilon(normal.x) == tangent_x_side
    ]
    if len(matching_normals) != 1:
        raise UvHeadTargetError(
            "Arm correction could not determine a unique tangent side for the selected roller."
        )
    normal = matching_normals[0]
    locus_origin = Point2D(
        tangent_point_a.x + (normal.x * head_roller_radius) - roller_offset.x,
        tangent_point_a.y + (normal.y * head_roller_radius) - roller_offset.y,
    )
    clipped = _clip_infinite_line_to_bounds(locus_origin, direction, transfer_bounds)
    if clipped is None:
        raise UvHeadTargetError(
            "Arm correction could not find a transfer-zone point tangent to the selected roller."
        )
    corrected_outbound = _choose_outbound_intercept(
        locus_origin,
        Point2D(locus_origin.x + direction.x, locus_origin.y + direction.y),
        clipped[0],
        clipped[1],
    )
    corrected_head_center = corrected_outbound
    selected_roller_center = Point2D(
        corrected_head_center.x + roller_offset.x,
        corrected_head_center.y + roller_offset.y,
    )
    if not math.isclose(
        _distance_point_to_line(
            selected_roller_center,
            line_point=tangent_point_a,
            line_direction=direction,
        ),
        head_roller_radius,
        abs_tol=1e-6,
    ):
        raise UvHeadTargetError(
            "Arm correction did not place the selected roller tangent to the outbound line."
        )
    return (corrected_outbound, corrected_head_center, roller_index, quadrant)


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
    alternating_projection_data: dict[str, Point2D] | None = None
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
        tangent_point_a = alternating_projection_data["anchor_contact"]
        tangent_point_b = alternating_projection_data["wrapped_contact"]
        clipped_start = alternating_projection_data["wrap_line_start"]
        clipped_end = alternating_projection_data["wrap_line_end"]
        outbound_intercept = alternating_projection_data["wrap_line_end"]
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


@lru_cache(maxsize=8)
def _cached_all_wire_space_pins(
    layer_calibration_path: str,
) -> tuple[tuple[str, float, float, float], ...]:
    """Cached version - returns tuple of (pin_name, x, y, z) for hashability."""
    layer_cal = _load_layer_calibration(None, layer_calibration_path)
    return tuple(
        (pin_name,) + (float(loc.x), float(loc.y), float(loc.z))
        for pin_name, loc in (
            (name, layer_cal.getPinLocation(name).add(layer_cal.offset))
            for name in layer_cal.getPinNames()
        )
    )


def _all_wire_space_pins(layer_calibration: LayerCalibration) -> dict[str, Point3D]:
    """Get all wire space pins with caching by calibration path."""
    # Try to get the path from the calibration object
    cal_path = getattr(layer_calibration, "_fullFileName", None)
    if cal_path is not None and os.path.isfile(cal_path):
        points = _cached_all_wire_space_pins(cal_path)
        return {pin_name: Point3D(x, y, z) for pin_name, x, y, z in points}
    # Fallback to uncached if path not available
    return {
        pin_name: _location_to_point3(_wire_space_pin(layer_calibration, pin_name))
        for pin_name in layer_calibration.getPinNames()
    }


__all__ = [
    "LineEquation",
    "PinPairTangentGeometry",
    "Point2D",
    "Point3D",
    "RecipeSite",
    "RectBounds",
    "AnchorToTargetCommand",
    "AnchorToTargetViewResult",
    "UvHeadTargetError",
    "UvHeadTargetRequest",
    "UvHeadTargetResult",
    "UvTangentViewRequest",
    "UvTangentViewResult",
    "WrappedPinResolution",
    "clear_uv_head_target_caches",
    "compute_pin_pair_tangent_geometry",
    "compute_uv_anchor_to_target_view",
    "compute_uv_head_target",
    "compute_uv_tangent_view",
    "iter_uv_wrap_primary_sites",
    "_lookup_recipe_site",
    "matches_tangent_sides",
    "parse_anchor_to_target_command",
    "resolve_wrapped_pin_from_g103_pair",
    "tangent_sides",
]
