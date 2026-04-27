from __future__ import annotations

import math

from dune_winder.queued_motion.filleted_path import (
    WaypointCircle,
    circle_pair_tangent_pairs,
)

from .constants import _AXIS_EPSILON
from .models import LineEquation, Point2D, RectBounds, UvHeadTargetError


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
    *,
    point_b_radius: float | None = None,
) -> list[tuple[Point2D, Point2D]]:
    radius_a = pin_radius
    radius_b = pin_radius if point_b_radius is None else point_b_radius
    if (
        _length_2d(Point2D(point_b.x - point_a.x, point_b.y - point_a.y))
        <= _AXIS_EPSILON
    ):
        raise UvHeadTargetError("Cannot compute a tangent for coincident pin centers.")
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
    sign_x = _sign_with_epsilon(anchor_pin_point.x - target_pin_point.x)
    sign_y = _sign_with_epsilon(anchor_pin_point.y - target_pin_point.y)
    if sign_x == 0 or sign_y == 0:
        return None
    return (sign_x, sign_y)


def _roller_index_for_head_shift_signs(sign_x: int, sign_y: int) -> int:
    return {
        (-1, -1): 0,
        (-1, 1): 1,
        (1, -1): 2,
        (1, 1): 3,
    }[(sign_x, sign_y)]


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
