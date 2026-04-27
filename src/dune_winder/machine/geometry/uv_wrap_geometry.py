from __future__ import annotations

from dataclasses import dataclass
import math

from dune_winder.machine.geometry.uv_layout import get_uv_layout
from dune_winder.queued_motion.filleted_path import (
    WaypointCircle,
    circle_pair_tangent_pairs,
)


_AXIS_EPSILON = 1e-9
ALTERNATING_SIDE_HOVER_Y = 5.0


class UvWrapGeometryError(ValueError):
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
class WrapTransitionPlan:
    layer: str
    anchor_pin: str
    target_pin: str
    same_side: bool
    head_position: int
    final_xy: Point2D
    transfer_xy: Point2D | None
    transfer_required: bool
    plane: str | None
    face: str | None
    anchor_tangent_point: Point2D
    target_tangent_point: Point2D
    clipped_start: Point2D
    clipped_end: Point2D
    outbound_intercept: Point2D
    front_projection: Point2D | None = None
    back_projection: Point2D | None = None


def _normalize_layer(layer: str) -> str:
    value = str(layer).strip().upper()
    if value not in {"U", "V"}:
        raise UvWrapGeometryError("Layer must be 'U' or 'V'.")
    return value


def _normalize_pin_name(pin_name: str, label: str = "Pin") -> str:
    value = str(pin_name).strip().upper()
    if value.startswith("P"):
        value = value[1:]
    if len(value) < 2 or value[:1] not in {"A", "B", "F"} or not value[1:].isdigit():
        raise UvWrapGeometryError(f"{label} must be a pin name like B1201 or A799.")
    if value.startswith("F"):
        value = "A" + value[1:]
    return value


def pin_family(pin_name: str) -> str:
    return _normalize_pin_name(pin_name)[:1]


def translate_pin_family(layer: str, pin_name: str, *, target_family: str) -> str:
    normalized_layer = _normalize_layer(layer)
    normalized_pin = _normalize_pin_name(pin_name)
    try:
        return get_uv_layout(normalized_layer).translate_pin(
            normalized_pin,
            target_family=target_family,
        )
    except ValueError as exc:
        raise UvWrapGeometryError(str(exc)) from exc


def b_to_a_pin(layer: str, pin_name: str) -> str:
    return translate_pin_family(layer, pin_name, target_family="A")


def _b_side_equivalent_pin(layer: str, pin_name: str) -> str:
    return translate_pin_family(layer, pin_name, target_family="B")


def face_for_pin(layer: str, pin_name: str) -> str:
    normalized_layer = _normalize_layer(layer)
    normalized_pin = _normalize_pin_name(pin_name)
    try:
        return get_uv_layout(normalized_layer).face_for_pin(normalized_pin)
    except ValueError as exc:
        raise UvWrapGeometryError(str(exc)) from exc


def _b_side_face_for_pin(layer: str, pin_name: str) -> str:
    return face_for_pin(layer, _b_side_equivalent_pin(layer, pin_name))


def tangent_sides(layer: str, pin_name: str) -> tuple[str, str]:
    normalized_layer = _normalize_layer(layer)
    normalized_pin = _normalize_pin_name(pin_name)
    try:
        return get_uv_layout(normalized_layer).tangent_sides(normalized_pin)
    except ValueError as exc:
        raise UvWrapGeometryError(str(exc)) from exc


def _alternating_plane_for_face(face: str) -> str:
    face_value = str(face).strip().lower()
    if face_value in ("top", "bottom"):
        return "xz"
    if face_value in ("head", "foot"):
        return "yz"
    raise UvWrapGeometryError(f"Unsupported face {face!r} for alternating-side view.")


def alternating_side_hover_y_offset(
    face: str, hover_y: float = ALTERNATING_SIDE_HOVER_Y
) -> float:
    face_value = str(face).strip().lower()
    if face_value in ("top", "head"):
        return float(hover_y)
    if face_value in ("bottom", "foot"):
        return -float(hover_y)
    raise UvWrapGeometryError(f"Unsupported face {face!r} for alternating-side hover.")


def _project_point3_to_plane(point: Point3D, plane: str) -> Point2D:
    if plane == "xz":
        return Point2D(point.x, point.z)
    if plane == "yz":
        return Point2D(point.z, point.y)
    raise UvWrapGeometryError(f"Unsupported alternating plane {plane!r}.")


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
    raise UvWrapGeometryError(f"Unsupported alternating plane {plane!r}.")


def _side_sign_for_axis(tangent_sides_value: tuple[str, str], axis: str) -> str:
    if axis == "x":
        return tangent_sides_value[0]
    if axis == "y":
        return tangent_sides_value[1]
    raise UvWrapGeometryError(f"Unsupported axis {axis!r}.")


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


def _extend_segment_to_machine_z_planes(
    start: Point2D,
    end: Point2D,
    *,
    plane: str,
    z_front: float,
    z_back: float,
) -> tuple[Point2D, Point2D]:
    if plane == "xz":
        delta_z = end.y - start.y
        if abs(delta_z) <= _AXIS_EPSILON:
            return (Point2D(start.x, z_front), Point2D(end.x, z_back))

        def point_at_z(z_value: float) -> Point2D:
            parameter = (z_value - start.y) / delta_z
            return Point2D(start.x + (parameter * (end.x - start.x)), z_value)

        return (point_at_z(z_front), point_at_z(z_back))

    if plane == "yz":
        delta_z = end.x - start.x
        if abs(delta_z) <= _AXIS_EPSILON:
            return (Point2D(z_front, start.y), Point2D(z_back, end.y))

        def point_at_z(z_value: float) -> Point2D:
            parameter = (z_value - start.x) / delta_z
            return Point2D(z_value, start.y + (parameter * (end.y - start.y)))

        return (point_at_z(z_front), point_at_z(z_back))

    raise UvWrapGeometryError(f"Unsupported alternating plane {plane!r}.")


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
    point: Point2D,
    center: Point2D,
    axis: str,
    side_sign: str,
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
    ) and _is_on_wrap_side(point, center, "y", tangent_sides_value[1])


def matches_tangent_sides(
    point: Point2D,
    center: Point2D,
    tangent_sides_value: tuple[str, str],
) -> bool:
    return _matches_tangent_sides(point, center, tangent_sides_value)


def _line_equation_from_tangent_points(
    tangent_a: Point2D,
    tangent_b: Point2D,
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
    *,
    point_b_radius: float | None = None,
) -> list[tuple[Point2D, Point2D]]:
    if (
        _length_2d(Point2D(point_b.x - point_a.x, point_b.y - point_a.y))
        <= _AXIS_EPSILON
    ):
        raise UvWrapGeometryError(
            "Cannot compute a tangent for coincident pin centers."
        )
    radius_a = pin_radius
    radius_b = pin_radius if point_b_radius is None else point_b_radius
    tangent_pairs = circle_pair_tangent_pairs(
        WaypointCircle(
            waypoint_xy=(point_a.x, point_a.y),
            center_xy=(point_a.x, point_a.y),
            radius=radius_a,
        ),
        WaypointCircle(
            waypoint_xy=(point_b.x, point_b.y),
            center_xy=(point_b.x, point_b.y),
            radius=radius_b,
        ),
    )
    return [
        (Point2D(first_xy[0], first_xy[1]), Point2D(second_xy[0], second_xy[1]))
        for first_xy, second_xy in tangent_pairs
    ]


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
            tangent_a,
            tangent_b,
            clipped_start,
            clipped_end,
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
        raise UvWrapGeometryError("Could not clip a tangent line to the transfer zone.")

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


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
    sign_x = _sign_with_epsilon(anchor_pin_point.x - target_pin_point.x)
    sign_y = _sign_with_epsilon(anchor_pin_point.y - target_pin_point.y)
    if sign_x == 0 or sign_y == 0:
        return None
    return (sign_x, sign_y)


def _roller_index_for_head_shift_signs(sign_x: int, sign_y: int) -> int:
    mapping = {
        (-1, -1): 0,
        (-1, 1): 1,
        (1, -1): 2,
        (1, 1): 3,
    }
    return mapping[(sign_x, sign_y)]


def _roller_offset_for_index(
    roller_index: int,
    *,
    head_arm_length: float,
    head_roller_radius: float,
    head_roller_gap: float,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
) -> Point2D:
    if roller_arm_y_offsets is not None:
        y_offset = float(roller_arm_y_offsets[roller_index])
    else:
        y_offset = (head_roller_gap / 2.0) + head_roller_radius
    offsets = (
        Point2D(-head_arm_length, -y_offset),
        Point2D(-head_arm_length, y_offset),
        Point2D(head_arm_length, -y_offset),
        Point2D(head_arm_length, y_offset),
    )
    return offsets[roller_index]


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
        raise UvWrapGeometryError("Cannot measure distance to a degenerate line.")
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
        raise UvWrapGeometryError(
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
        raise UvWrapGeometryError(
            "Arm correction requires a non-degenerate tangent line."
        )
    unit_direction = Point2D(
        direction.x / direction_length,
        direction.y / direction_length,
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
        raise UvWrapGeometryError(
            "Arm correction could not determine a unique tangent side for the selected roller."
        )
    normal = matching_normals[0]
    locus_origin = Point2D(
        tangent_point_a.x + (normal.x * head_roller_radius) - roller_offset.x,
        tangent_point_a.y + (normal.y * head_roller_radius) - roller_offset.y,
    )
    clipped = _clip_infinite_line_to_bounds(locus_origin, direction, transfer_bounds)
    if clipped is None:
        raise UvWrapGeometryError(
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
        raise UvWrapGeometryError(
            "Arm correction did not place the selected roller tangent to the outbound line."
        )
    return (corrected_outbound, corrected_head_center, roller_index, quadrant)


def _nearest_point_in_bounds(point: Point2D, bounds: RectBounds) -> Point2D:
    return Point2D(
        min(max(float(point.x), float(bounds.left)), float(bounds.right)),
        min(max(float(point.y), float(bounds.bottom)), float(bounds.top)),
    )


def _point_inside_bounds(point: Point2D, bounds: RectBounds) -> bool:
    return (
        float(bounds.left) - _AXIS_EPSILON
        <= float(point.x)
        <= float(bounds.right) + _AXIS_EPSILON
        and float(bounds.bottom) - _AXIS_EPSILON
        <= float(point.y)
        <= float(bounds.top) + _AXIS_EPSILON
    )


def _wrap_xy_from_plane_point(
    *,
    anchor_pin_point: Point3D,
    target_pin_point: Point3D,
    plane: str,
    plane_point: Point2D,
) -> Point2D:
    if plane == "xz":
        return Point2D(
            float(plane_point.x),
            float((anchor_pin_point.y + target_pin_point.y) / 2.0),
        )
    if plane == "yz":
        return Point2D(
            float((anchor_pin_point.x + target_pin_point.x) / 2.0),
            float(plane_point.y),
        )
    raise UvWrapGeometryError(f"Unsupported alternating plane {plane!r}.")


def plan_wrap_transition(
    *,
    layer: str,
    anchor_pin: str,
    target_pin: str,
    anchor_pin_point: Point3D,
    target_pin_point: Point3D,
    transfer_bounds: RectBounds,
    z_front: float,
    z_back: float,
    pin_radius: float,
    target_pin_radius: float | None = None,
    head_arm_length: float,
    head_roller_radius: float,
    head_roller_gap: float,
    roller_arm_y_offsets: tuple[float, float, float, float] | None = None,
    current_xy: Point2D | None = None,
) -> WrapTransitionPlan:
    normalized_layer = _normalize_layer(layer)
    normalized_anchor_pin = _normalize_pin_name(anchor_pin, "Anchor pin")
    normalized_target_pin = _normalize_pin_name(target_pin, "Target pin")
    target_family = pin_family(normalized_target_pin)
    head_position = 1 if target_family == "A" else 2
    anchor_point_2d = Point2D(float(anchor_pin_point.x), float(anchor_pin_point.y))
    target_point_2d = Point2D(float(target_pin_point.x), float(target_pin_point.y))
    transfer_xy = None
    transfer_required = False
    if current_xy is not None:
        transfer_required = not _point_inside_bounds(current_xy, transfer_bounds)
        if transfer_required:
            transfer_xy = _nearest_point_in_bounds(current_xy, transfer_bounds)

    actual_target_pin_radius = (
        pin_radius if target_pin_radius is None else target_pin_radius
    )

    same_side = pin_family(normalized_anchor_pin) == target_family
    if same_side:
        candidates = _tangent_candidates_for_pin_pair(
            anchor_point_2d,
            target_point_2d,
            pin_radius,
            point_b_radius=actual_target_pin_radius,
        )
        tangent_point_a, tangent_point_b, clipped_start, clipped_end = (
            _select_tangent_solution(
                candidates,
                transfer_bounds,
                anchor_pin_point=anchor_point_2d,
                anchor_tangent_sides=tangent_sides(
                    normalized_layer, normalized_anchor_pin
                ),
                wrapped_pin_point=target_point_2d,
                wrapped_tangent_sides=tangent_sides(
                    normalized_layer, normalized_target_pin
                ),
            )
        )
        outbound_intercept = _choose_outbound_intercept(
            tangent_point_a,
            tangent_point_b,
            clipped_start,
            clipped_end,
        )
        corrected_outbound, _head_center, _roller_index, _quadrant = (
            _compute_arm_corrected_outbound(
                anchor_pin_point=anchor_point_2d,
                target_pin_point=target_point_2d,
                tangent_point_a=tangent_point_a,
                tangent_point_b=tangent_point_b,
                transfer_bounds=transfer_bounds,
                head_arm_length=head_arm_length,
                head_roller_radius=head_roller_radius,
                head_roller_gap=head_roller_gap,
                roller_arm_y_offsets=roller_arm_y_offsets,
            )
        )
        return WrapTransitionPlan(
            layer=normalized_layer,
            anchor_pin=normalized_anchor_pin,
            target_pin=normalized_target_pin,
            same_side=True,
            head_position=head_position,
            final_xy=corrected_outbound,
            transfer_xy=transfer_xy,
            transfer_required=transfer_required,
            plane=None,
            face=None,
            anchor_tangent_point=tangent_point_a,
            target_tangent_point=tangent_point_b,
            clipped_start=clipped_start,
            clipped_end=clipped_end,
            outbound_intercept=outbound_intercept,
        )

    anchor_face = _b_side_face_for_pin(normalized_layer, normalized_anchor_pin)
    target_face = _b_side_face_for_pin(normalized_layer, normalized_target_pin)
    if anchor_face != target_face:
        raise UvWrapGeometryError(
            "Alternating-side wrap requires both pins to lie on the same face after converting the A pin to the B side."
        )
    plane = _alternating_plane_for_face(target_face)
    anchor_contact = _segment_contact_for_wrap_side(
        _project_point3_to_plane(anchor_pin_point, plane),
        plane=plane,
        pin_radius=pin_radius,
        tangent_sides_value=tangent_sides(normalized_layer, normalized_anchor_pin),
    )
    target_contact = _segment_contact_for_wrap_side(
        _project_point3_to_plane(target_pin_point, plane),
        plane=plane,
        pin_radius=actual_target_pin_radius,
        tangent_sides_value=tangent_sides(normalized_layer, normalized_target_pin),
    )
    front_projection, back_projection = _extend_segment_to_machine_z_planes(
        anchor_contact,
        target_contact,
        plane=plane,
        z_front=z_front,
        z_back=z_back,
    )
    plane_point = front_projection if target_family == "A" else back_projection
    final_xy = _wrap_xy_from_plane_point(
        anchor_pin_point=anchor_pin_point,
        target_pin_point=target_pin_point,
        plane=plane,
        plane_point=plane_point,
    )
    return WrapTransitionPlan(
        layer=normalized_layer,
        anchor_pin=normalized_anchor_pin,
        target_pin=normalized_target_pin,
        same_side=False,
        head_position=head_position,
        final_xy=final_xy,
        transfer_xy=transfer_xy,
        transfer_required=transfer_required,
        plane=plane,
        face=target_face,
        anchor_tangent_point=anchor_contact,
        target_tangent_point=target_contact,
        clipped_start=front_projection,
        clipped_end=back_projection,
        outbound_intercept=plane_point,
        front_projection=front_projection,
        back_projection=back_projection,
    )


__all__ = [
    "LineEquation",
    "Point2D",
    "Point3D",
    "RectBounds",
    "UvWrapGeometryError",
    "ALTERNATING_SIDE_HOVER_Y",
    "WrapTransitionPlan",
    "_arm_correction_head_shift_signs",
    "_arm_correction_tangent_y_side",
    "_b_side_equivalent_pin",
    "_choose_outbound_intercept",
    "_clip_infinite_line_to_bounds",
    "_compute_arm_corrected_outbound",
    "_distance_point_to_line",
    "_is_on_wrap_side",
    "_line_equation_from_tangent_points",
    "_matches_tangent_sides",
    "_roller_index_for_head_shift_signs",
    "_roller_offset_for_index",
    "_select_tangent_solution",
    "_tangent_candidates_for_pin_pair",
    "b_to_a_pin",
    "alternating_side_hover_y_offset",
    "face_for_pin",
    "matches_tangent_sides",
    "pin_family",
    "plan_wrap_transition",
    "tangent_sides",
    "translate_pin_family",
]
