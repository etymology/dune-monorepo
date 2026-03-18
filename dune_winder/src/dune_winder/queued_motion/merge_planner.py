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
  DEFAULT_QUEUED_MOTION_JERK_PERCENT,
  normalize_queued_motion_jerk_percent,
)
from .safety import (
  MotionSafetyLimits,
  QueuedMotionCollisionState,
  validate_segments_within_safety_limits,
)
from .segment_patterns import (
  DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  apply_merge_term_types,
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
  jerk_accel: float = DEFAULT_QUEUED_MOTION_JERK_PERCENT,
  jerk_decel: float = DEFAULT_QUEUED_MOTION_JERK_PERCENT,
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

  jerk_accel = normalize_queued_motion_jerk_percent(jerk_accel)
  jerk_decel = normalize_queued_motion_jerk_percent(jerk_decel)

  filleted = filleted_polygon_segments(
    start_xy=start_xy,
    waypoints=[(float(point.x), float(point.y)) for point in filtered_waypoints],
    radius=_planner_radius(
      speed=speed,
      min_arc_radius=min_arc_radius,
      accel_limit=max(1.0, min(float(accel), float(decel))),
      # PLC queued-motion jerk is configured as S-curve "% of Time", not a
      # physical jerk limit, so fillet sizing only uses the accel constraint.
      jerk_limit=0.0,
    ),
    line_term_type=4,
    arc_term_type=4,
    final_term_type=0,
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
