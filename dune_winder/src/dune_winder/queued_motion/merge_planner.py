from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional

from .filleted_path import (
  distance_xy,
  dynamic_min_radius,
  filleted_polygon_segments,
)
from .jerk_limits import (
  DEFAULT_QUEUED_MOTION_ACCEL_JERK,
  DEFAULT_QUEUED_MOTION_DECEL_JERK,
  normalize_queued_motion_jerk,
)
from .safety import (
  MotionSafetyLimits,
  QueuedMotionCollisionState,
  validate_segments_within_safety_limits,
)
from .segment_patterns import (
  DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  apply_merge_term_types,
  cap_segments_speed_by_axis_velocity,
  _max_abs_cos_over_sweep,
  _max_abs_sin_over_sweep,
)
from .segment_types import (
  MotionSegment,
  circle_center_for_segment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)


MERGE_MODE_PRECISE = "PRECISE"
MERGE_MODE_TOLERANT = "TOLERANT"
_COMMAND_POSITION_RESOLUTION_MM = 0.1
_PLANNER_RADIUS_EPS = 1e-6
_MAX_RADIUS_REFINEMENT_PASSES = 4


@dataclass(frozen=True)
class MergeWaypoint:
  line_index: int
  x: float
  y: float
  mode: Optional[str]


def _distance(p0: tuple[float, float], p1: tuple[float, float]) -> float:
  return distance_xy(p0, p1)


def _planner_radius(
  speed: float,
  min_arc_radius: float,
  accel_limit: float,
  jerk_limit: float,
) -> float:
  return dynamic_min_radius(
    speed=speed,
    base_min_radius=min_arc_radius,
    accel_limit=accel_limit,
    jerk_limit=jerk_limit,
  )


def _shortest_signed_angle_delta(start_angle: float, end_angle: float) -> float:
  delta = (end_angle - start_angle + math.pi) % (2.0 * math.pi) - math.pi
  if delta <= -math.pi:
    delta += 2.0 * math.pi
  return delta


def _axis_limited_speed(
  requested_speed: float,
  *,
  max_tx: float,
  max_ty: float,
  v_x_max: Optional[float],
  v_y_max: Optional[float],
) -> float:
  if v_x_max is None or v_y_max is None:
    return float(requested_speed)

  limit_x = float("inf") if max_tx <= _PLANNER_RADIUS_EPS else (float(v_x_max) / max_tx)
  limit_y = float("inf") if max_ty <= _PLANNER_RADIUS_EPS else (float(v_y_max) / max_ty)
  return min(float(requested_speed), limit_x, limit_y)


def _planner_seed_speed(
  *,
  start_xy: tuple[float, float],
  waypoints: list[MergeWaypoint],
  requested_speed: float,
  v_x_max: Optional[float],
  v_y_max: Optional[float],
) -> float:
  if v_x_max is None or v_y_max is None or len(waypoints) < 2:
    return float(requested_speed)

  points = [start_xy]
  points.extend((float(waypoint.x), float(waypoint.y)) for waypoint in waypoints)

  capped_corner_speeds: list[float] = []
  for index in range(1, len(points) - 1):
    prev_xy = points[index - 1]
    point_xy = points[index]
    next_xy = points[index + 1]
    incoming_angle = math.atan2(point_xy[1] - prev_xy[1], point_xy[0] - prev_xy[0])
    outgoing_angle = math.atan2(next_xy[1] - point_xy[1], next_xy[0] - point_xy[0])
    sweep = _shortest_signed_angle_delta(incoming_angle, outgoing_angle)
    if abs(sweep) <= _PLANNER_RADIUS_EPS:
      continue
    capped_corner_speeds.append(
      _axis_limited_speed(
        requested_speed,
        max_tx=_max_abs_cos_over_sweep(incoming_angle, sweep),
        max_ty=_max_abs_sin_over_sweep(incoming_angle, sweep),
        v_x_max=v_x_max,
        v_y_max=v_y_max,
      )
    )

  if not capped_corner_speeds:
    return float(requested_speed)
  return max(capped_corner_speeds)


def _cap_planner_segments(
  segments: list[MotionSegment],
  *,
  start_xy: tuple[float, float],
  v_x_max: Optional[float],
  v_y_max: Optional[float],
) -> list[MotionSegment]:
  if v_x_max is None or v_y_max is None:
    return segments
  return cap_segments_speed_by_axis_velocity(
    segments=segments,
    v_x_max=float(v_x_max),
    v_y_max=float(v_y_max),
    start_xy=start_xy,
  )


def _planner_radius_speed_from_segments(segments: list[MotionSegment]) -> float:
  arc_speeds = [float(seg.speed) for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE]
  if not arc_speeds:
    return 0.0
  return max(arc_speeds)


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
  jerk_accel: float = DEFAULT_QUEUED_MOTION_ACCEL_JERK,
  jerk_decel: float = DEFAULT_QUEUED_MOTION_DECEL_JERK,
  min_arc_radius: float = DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  safety_limits: MotionSafetyLimits,
  queued_motion_collision_state: Optional[QueuedMotionCollisionState] = None,
  v_x_max: Optional[float] = None,
  v_y_max: Optional[float] = None,
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

  jerk_accel = normalize_queued_motion_jerk(
    jerk_accel,
    default=DEFAULT_QUEUED_MOTION_ACCEL_JERK,
  )
  jerk_decel = normalize_queued_motion_jerk(
    jerk_decel,
    default=DEFAULT_QUEUED_MOTION_DECEL_JERK,
  )

  accel_limit = max(1.0, min(float(accel), float(decel)))
  jerk_limit = min(float(jerk_accel), float(jerk_decel))
  planner_speed = _planner_seed_speed(
    start_xy=start_xy,
    waypoints=filtered_waypoints,
    requested_speed=speed,
    v_x_max=v_x_max,
    v_y_max=v_y_max,
  )
  planner_radius = _planner_radius(
    speed=planner_speed,
    min_arc_radius=min_arc_radius,
    accel_limit=accel_limit,
    jerk_limit=jerk_limit,
  )
  waypoints_xy = [(float(point.x), float(point.y)) for point in filtered_waypoints]

  filleted: Optional[list[MotionSegment]] = None
  for _ in range(_MAX_RADIUS_REFINEMENT_PASSES):
    candidate = filleted_polygon_segments(
      start_xy=start_xy,
      waypoints=waypoints_xy,
      radius=planner_radius,
      line_term_type=4,
      arc_term_type=4,
      final_term_type=0,
    )
    if candidate is None or not _segments_are_valid(
      candidate,
      start_xy=start_xy,
      min_arc_radius=min_arc_radius,
      safety_limits=safety_limits,
      queued_motion_collision_state=queued_motion_collision_state,
    ):
      filleted = None
      break

    filleted = _cap_planner_segments(
      _decorate_segments(
        candidate,
        start_seq=start_seq,
        speed=speed,
        accel=accel,
        decel=decel,
        jerk_accel=jerk_accel,
        jerk_decel=jerk_decel,
      ),
      start_xy=start_xy,
      v_x_max=v_x_max,
      v_y_max=v_y_max,
    )
    refined_radius = _planner_radius(
      speed=_planner_radius_speed_from_segments(filleted),
      min_arc_radius=min_arc_radius,
      accel_limit=accel_limit,
      jerk_limit=jerk_limit,
    )
    if abs(refined_radius - planner_radius) <= _PLANNER_RADIUS_EPS:
      break
    planner_radius = refined_radius

  if filleted is not None:
    return apply_merge_term_types(
      filleted,
      start_xy=start_xy,
      final_term_type=0,
    )

  precise = _cap_planner_segments(
    _decorate_segments(
      _precise_stop_segments(filtered_waypoints),
      start_seq=start_seq,
      speed=speed,
      accel=accel,
      decel=decel,
      jerk_accel=jerk_accel,
      jerk_decel=jerk_decel,
    ),
    start_xy=start_xy,
    v_x_max=v_x_max,
    v_y_max=v_y_max,
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
