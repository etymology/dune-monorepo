from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional

from .safety import (
  MotionSafetyLimits,
  QueuedMotionCollisionState,
  validate_segments_within_safety_limits,
)
from .segment_patterns import (
  DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  apply_merge_term_types,
  _tangent_biarc_tessellation,
  _waypoint_tangents,
)
from .segment_types import (
  CIRCLE_TYPE_CENTER,
  MCCM_DIR_2D_CCW,
  MCCM_DIR_2D_CW,
  MotionSegment,
  circle_center_for_segment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)


MERGE_MODE_PRECISE = "PRECISE"
MERGE_MODE_TOLERANT = "TOLERANT"
_EPS = 1e-6
_COMMAND_POSITION_RESOLUTION_MM = 0.1


@dataclass(frozen=True)
class MergeWaypoint:
  line_index: int
  x: float
  y: float
  mode: Optional[str]


def _distance(p0: tuple[float, float], p1: tuple[float, float]) -> float:
  return math.hypot(p1[0] - p0[0], p1[1] - p0[1])


def _normalize(x: float, y: float) -> tuple[float, float]:
  mag = math.hypot(x, y)
  if mag <= _EPS:
    return (1.0, 0.0)
  return (x / mag, y / mag)


def _left_normal(direction: tuple[float, float]) -> tuple[float, float]:
  return (-direction[1], direction[0])


def _unit_vector_between(
  start_xy: tuple[float, float],
  end_xy: tuple[float, float],
) -> Optional[tuple[float, float]]:
  dx = end_xy[0] - start_xy[0]
  dy = end_xy[1] - start_xy[1]
  mag = math.hypot(dx, dy)
  if mag <= _EPS:
    return None
  return (dx / mag, dy / mag)


@dataclass(frozen=True)
class _WaypointCircle:
  waypoint_xy: tuple[float, float]
  center_xy: tuple[float, float]
  radius: float


def _planner_radius(
  *,
  start_xy: tuple[float, float],
  waypoints: list[MergeWaypoint],
  min_arc_radius: float,
) -> float:
  if min_arc_radius > 0.0:
    return float(min_arc_radius)

  points = [start_xy]
  points.extend((float(waypoint.x), float(waypoint.y)) for waypoint in waypoints)
  spans = [
    _distance(points[index], points[index + 1])
    for index in range(len(points) - 1)
    if _distance(points[index], points[index + 1]) > _EPS
  ]
  if not spans:
    return 0.0
  return 0.25 * min(spans)


def _build_waypoint_circles(
  *,
  start_xy: tuple[float, float],
  waypoints: list[MergeWaypoint],
  radius: float,
) -> Optional[list[_WaypointCircle]]:
  if radius <= _EPS:
    return []

  circles: list[_WaypointCircle] = []
  prev_xy = (float(start_xy[0]), float(start_xy[1]))
  for index, waypoint in enumerate(waypoints[:-1]):
    point_xy = (float(waypoint.x), float(waypoint.y))
    next_xy = (float(waypoints[index + 1].x), float(waypoints[index + 1].y))
    incoming = _unit_vector_between(prev_xy, point_xy)
    outgoing = _unit_vector_between(point_xy, next_xy)
    if incoming is None or outgoing is None:
      return None

    bisector = _unit_vector_between(
      (0.0, 0.0),
      (incoming[0] + outgoing[0], incoming[1] + outgoing[1]),
    )
    if bisector is None:
      return None

    center_xy = (
      point_xy[0] + bisector[0] * radius,
      point_xy[1] + bisector[1] * radius,
    )
    circles.append(
      _WaypointCircle(
        waypoint_xy=point_xy,
        center_xy=center_xy,
        radius=radius,
      )
    )
    prev_xy = point_xy

  return circles


def _point_circle_tangent_points(
  point_xy: tuple[float, float],
  circle: _WaypointCircle,
) -> list[tuple[float, float]]:
  dx = point_xy[0] - circle.center_xy[0]
  dy = point_xy[1] - circle.center_xy[1]
  distance_to_center = math.hypot(dx, dy)
  if distance_to_center <= circle.radius + 1e-9:
    return []

  base_angle = math.atan2(dy, dx)
  delta_angle = math.acos(circle.radius / distance_to_center)
  tangent_points: list[tuple[float, float]] = []
  for sign in (-1.0, 1.0):
    angle = base_angle + sign * delta_angle
    tangent_xy = (
      circle.center_xy[0] + circle.radius * math.cos(angle),
      circle.center_xy[1] + circle.radius * math.sin(angle),
    )
    if not any(_distance(tangent_xy, existing) <= 1e-6 for existing in tangent_points):
      tangent_points.append(tangent_xy)
  return tangent_points


def _circle_pair_tangent_pairs(
  first: _WaypointCircle,
  second: _WaypointCircle,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
  if abs(first.radius - second.radius) > 1e-9:
    return []

  center_dir = _unit_vector_between(first.center_xy, second.center_xy)
  if center_dir is None:
    return []
  normal = _left_normal(center_dir)

  tangent_pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
  for sign in (-1.0, 1.0):
    offset = (normal[0] * first.radius * sign, normal[1] * first.radius * sign)
    tangent_pairs.append(
      (
        (first.center_xy[0] + offset[0], first.center_xy[1] + offset[1]),
        (second.center_xy[0] + offset[0], second.center_xy[1] + offset[1]),
      )
    )
  return tangent_pairs


def _arc_direction_through_waypoint(
  circle: _WaypointCircle,
  line_start_xy: tuple[float, float],
  incoming_xy: tuple[float, float],
  outgoing_xy: tuple[float, float],
  line_end_xy: tuple[float, float],
) -> Optional[int]:
  if (
    _distance(incoming_xy, circle.waypoint_xy) <= _COMMAND_POSITION_RESOLUTION_MM
    or _distance(outgoing_xy, circle.waypoint_xy) <= _COMMAND_POSITION_RESOLUTION_MM
  ):
    return None

  incoming_dir = _unit_vector_between(line_start_xy, incoming_xy)
  outgoing_dir = _unit_vector_between(outgoing_xy, line_end_xy)
  if incoming_dir is None or outgoing_dir is None:
    return None

  def tangent_at(point_xy: tuple[float, float], direction: int) -> tuple[float, float]:
    radial_x = point_xy[0] - circle.center_xy[0]
    radial_y = point_xy[1] - circle.center_xy[1]
    radial_mag = math.hypot(radial_x, radial_y)
    if direction == MCCM_DIR_2D_CCW:
      return (-radial_y / radial_mag, radial_x / radial_mag)
    return (radial_y / radial_mag, -radial_x / radial_mag)

  tau = 2.0 * math.pi
  start_angle = math.atan2(
    incoming_xy[1] - circle.center_xy[1],
    incoming_xy[0] - circle.center_xy[0],
  )
  waypoint_angle = math.atan2(
    circle.waypoint_xy[1] - circle.center_xy[1],
    circle.waypoint_xy[0] - circle.center_xy[0],
  )
  end_angle = math.atan2(
    outgoing_xy[1] - circle.center_xy[1],
    outgoing_xy[0] - circle.center_xy[0],
  )

  candidates: list[tuple[float, int]] = []
  ccw_total = (end_angle - start_angle) % tau
  ccw_waypoint = (waypoint_angle - start_angle) % tau
  if 1e-6 < ccw_waypoint < ccw_total - 1e-6:
    candidates.append((ccw_total, MCCM_DIR_2D_CCW))

  cw_total = (start_angle - end_angle) % tau
  cw_waypoint = (start_angle - waypoint_angle) % tau
  if 1e-6 < cw_waypoint < cw_total - 1e-6:
    candidates.append((cw_total, MCCM_DIR_2D_CW))

  if not candidates:
    return None

  valid_candidates: list[tuple[float, int]] = []
  for sweep, direction in candidates:
    start_tangent = tangent_at(incoming_xy, direction)
    end_tangent = tangent_at(outgoing_xy, direction)
    start_dot = start_tangent[0] * incoming_dir[0] + start_tangent[1] * incoming_dir[1]
    end_dot = end_tangent[0] * outgoing_dir[0] + end_tangent[1] * outgoing_dir[1]
    if start_dot >= 1.0 - 1e-6 and end_dot >= 1.0 - 1e-6:
      valid_candidates.append((sweep, direction))

  if not valid_candidates:
    return None

  valid_candidates.sort(key=lambda item: item[0])
  return valid_candidates[0][1]


def _filleted_polygon_segments(
  *,
  start_xy: tuple[float, float],
  waypoints: list[MergeWaypoint],
  radius: float,
) -> Optional[list[MotionSegment]]:
  if not waypoints:
    return []

  if len(waypoints) == 1:
    return [
      MotionSegment(
        seq=0,
        x=float(waypoints[0].x),
        y=float(waypoints[0].y),
        term_type=0,
        seg_type=SEG_TYPE_LINE,
      )
    ]

  circles = _build_waypoint_circles(
    start_xy=start_xy,
    waypoints=waypoints,
    radius=radius,
  )
  if circles is None or not circles:
    return None

  start_tangent_options = sorted(
    _point_circle_tangent_points(start_xy, circles[0]),
    key=lambda tangent_xy: _distance(start_xy, tangent_xy),
  )
  if not start_tangent_options:
    return None

  end_xy = (float(waypoints[-1].x), float(waypoints[-1].y))
  end_tangent_options = sorted(
    _point_circle_tangent_points(end_xy, circles[-1]),
    key=lambda tangent_xy: _distance(end_xy, tangent_xy),
  )
  if not end_tangent_options:
    return None

  pair_tangent_options = [
    sorted(
      _circle_pair_tangent_pairs(circles[index], circles[index + 1]),
      key=lambda pair: _distance(pair[0], pair[1]),
    )
    for index in range(len(circles) - 1)
  ]
  if any(not options for options in pair_tangent_options):
    return None

  chosen_arcs: list[tuple[tuple[float, float], tuple[float, float], int]] = []

  def search(
    circle_index: int,
    incoming_xy: tuple[float, float],
  ) -> bool:
    circle = circles[circle_index]
    line_start_xy = start_xy if circle_index == 0 else chosen_arcs[-1][1]
    if circle_index == len(circles) - 1:
      for outgoing_xy in end_tangent_options:
        direction = _arc_direction_through_waypoint(
          circle,
          line_start_xy,
          incoming_xy,
          outgoing_xy,
          end_xy,
        )
        if direction is None:
          continue
        chosen_arcs.append((incoming_xy, outgoing_xy, direction))
        return True
      return False

    for outgoing_xy, next_incoming_xy in pair_tangent_options[circle_index]:
      direction = _arc_direction_through_waypoint(
        circle,
        line_start_xy,
        incoming_xy,
        outgoing_xy,
        next_incoming_xy,
      )
      if direction is None:
        continue
      chosen_arcs.append((incoming_xy, outgoing_xy, direction))
      if search(circle_index + 1, next_incoming_xy):
        return True
      chosen_arcs.pop()
    return False

  if not any(search(0, incoming_xy) for incoming_xy in start_tangent_options):
    return None

  segments: list[MotionSegment] = []
  cursor_xy = (float(start_xy[0]), float(start_xy[1]))
  for circle, (incoming_xy, outgoing_xy, direction) in zip(circles, chosen_arcs):
    if _distance(cursor_xy, incoming_xy) > _EPS:
      segments.append(
        MotionSegment(
          seq=0,
          x=incoming_xy[0],
          y=incoming_xy[1],
          term_type=4,
          seg_type=SEG_TYPE_LINE,
        )
      )
    segments.append(
      MotionSegment(
        seq=0,
        x=outgoing_xy[0],
        y=outgoing_xy[1],
        term_type=4,
        seg_type=SEG_TYPE_CIRCLE,
        circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=circle.center_xy[0],
        via_center_y=circle.center_xy[1],
        direction=direction,
      )
    )
    cursor_xy = outgoing_xy

  if _distance(cursor_xy, end_xy) > _EPS:
    segments.append(
      MotionSegment(
        seq=0,
        x=end_xy[0],
        y=end_xy[1],
        term_type=0,
        seg_type=SEG_TYPE_LINE,
      )
    )

  return segments


def _decorate_segments(
  segments: list[MotionSegment],
  *,
  start_seq: int,
  speed: float,
  accel: float,
  decel: float,
  jerk_accel: float,
  jerk_decel: float,
) -> list[MotionSegment]:
  out: list[MotionSegment] = []
  for index, seg in enumerate(segments):
    term_type = seg.term_type
    out.append(
      replace(
        seg,
        seq=start_seq + index,
        speed=speed,
        accel=accel,
        decel=decel,
        jerk_accel=jerk_accel,
        jerk_decel=jerk_decel,
        term_type=term_type,
      )
    )
  return out


def _min_radius_ok(
  segments: list[MotionSegment],
  *,
  start_xy: tuple[float, float],
  min_arc_radius: float,
) -> bool:
  if min_arc_radius <= 0.0:
    return True

  prev_x = float(start_xy[0])
  prev_y = float(start_xy[1])
  for seg in segments:
    if seg.seg_type == SEG_TYPE_CIRCLE:
      start = MotionSegment(seq=seg.seq - 1, x=prev_x, y=prev_y)
      center = circle_center_for_segment(start, seg)
      if center is None:
        return False
      radius = math.hypot(prev_x - center[0], prev_y - center[1])
      if radius + 1e-9 < min_arc_radius:
        return False
    prev_x = float(seg.x)
    prev_y = float(seg.y)
  return True


def _segments_are_valid(
  segments: list[MotionSegment],
  *,
  start_xy: tuple[float, float],
  min_arc_radius: float,
  safety_limits: MotionSafetyLimits,
  queued_motion_collision_state: Optional[QueuedMotionCollisionState],
) -> bool:
  if not _min_radius_ok(segments, start_xy=start_xy, min_arc_radius=min_arc_radius):
    return False
  try:
    validate_segments_within_safety_limits(
      segments,
      safety_limits,
      start_xy=start_xy,
      queued_motion_collision_state=queued_motion_collision_state,
    )
  except ValueError:
    return False
  return True


def _exact_biarc_segments(
  *,
  start_xy: tuple[float, float],
  waypoints: list[MergeWaypoint],
) -> list[MotionSegment]:
  points = [(float(start_xy[0]), float(start_xy[1]))]
  points.extend((float(point.x), float(point.y)) for point in waypoints)
  tangents = _waypoint_tangents(points)
  segments = _tangent_biarc_tessellation(points, tangents, start_seq=0, term_type=4)
  return segments[1:]


def _precise_stop_segments(waypoints: list[MergeWaypoint]) -> list[MotionSegment]:
  return [
    MotionSegment(
      seq=0,
      x=float(waypoint.x),
      y=float(waypoint.y),
      term_type=0,
      seg_type=SEG_TYPE_LINE,
    )
    for waypoint in waypoints
  ]


def build_merge_path_segments(
  *,
  start_xy: tuple[float, float],
  waypoints: list[MergeWaypoint],
  start_seq: int,
  speed: float,
  accel: float,
  decel: float,
  jerk_accel: float = 100.0,
  jerk_decel: float = 100.0,
  min_arc_radius: float = DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  safety_limits: MotionSafetyLimits,
  queued_motion_collision_state: Optional[QueuedMotionCollisionState] = None,
) -> list[MotionSegment]:
  if not waypoints:
    return []

  filtered_waypoints: list[MergeWaypoint] = []
  cursor_xy = (float(start_xy[0]), float(start_xy[1]))
  for waypoint in waypoints:
    point_xy = (float(waypoint.x), float(waypoint.y))
    if _distance(cursor_xy, point_xy) < _COMMAND_POSITION_RESOLUTION_MM:
      # Skip sub-resolution waypoints (already at command position).
      continue
    filtered_waypoints.append(waypoint)
    cursor_xy = point_xy

  if not filtered_waypoints:
    return []

  filleted = _filleted_polygon_segments(
    start_xy=start_xy,
    waypoints=filtered_waypoints,
    radius=_planner_radius(
      start_xy=start_xy,
      waypoints=filtered_waypoints,
      min_arc_radius=min_arc_radius,
    ),
  )
  if filleted is not None and _segments_are_valid(
    filleted,
    start_xy=start_xy,
    min_arc_radius=min_arc_radius,
    safety_limits=safety_limits,
    queued_motion_collision_state=queued_motion_collision_state,
  ):
    filleted = _decorate_segments(
      filleted,
      start_seq=start_seq,
      speed=speed,
      accel=accel,
      decel=decel,
      jerk_accel=jerk_accel,
      jerk_decel=jerk_decel,
    )
    return apply_merge_term_types(
      filleted,
      start_xy=start_xy,
      final_term_type=0,
    )

  exact = _exact_biarc_segments(start_xy=start_xy, waypoints=filtered_waypoints)
  if _segments_are_valid(
    exact,
    start_xy=start_xy,
    min_arc_radius=min_arc_radius,
    safety_limits=safety_limits,
    queued_motion_collision_state=queued_motion_collision_state,
  ):
    exact = _decorate_segments(
      exact,
      start_seq=start_seq,
      speed=speed,
      accel=accel,
      decel=decel,
      jerk_accel=jerk_accel,
      jerk_decel=jerk_decel,
    )
    return apply_merge_term_types(
      exact,
      start_xy=start_xy,
      final_term_type=0,
    )

  precise = _decorate_segments(
    _precise_stop_segments(filtered_waypoints),
    start_seq=start_seq,
    speed=speed,
    accel=accel,
    decel=decel,
    jerk_accel=jerk_accel,
    jerk_decel=jerk_decel,
  )
  precise = [replace(seg, term_type=0) for seg in precise]
  if _segments_are_valid(
    precise,
    start_xy=start_xy,
    min_arc_radius=min_arc_radius,
    safety_limits=safety_limits,
    queued_motion_collision_state=queued_motion_collision_state,
  ):
    return precise

  raise ValueError(
    f"Unable to build a valid queued path through waypoint line {filtered_waypoints[-1].line_index}"
  )
