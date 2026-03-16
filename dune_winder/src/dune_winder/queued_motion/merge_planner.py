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


def _build_fillet_segments(
  start_xy: tuple[float, float],
  corner_xy: tuple[float, float],
  next_xy: tuple[float, float],
  radius: float,
) -> Optional[list[MotionSegment]]:
  if radius <= 0.0:
    return None

  d_in = _normalize(corner_xy[0] - start_xy[0], corner_xy[1] - start_xy[1])
  d_out = _normalize(next_xy[0] - corner_xy[0], next_xy[1] - corner_xy[1])
  dot = max(-1.0, min(1.0, d_in[0] * d_out[0] + d_in[1] * d_out[1]))
  theta = math.acos(dot)
  if theta <= 1e-4 or abs(theta - math.pi) <= 1e-4:
    return None

  inset = radius * math.tan(theta / 2.0)
  if inset <= _EPS:
    return None
  if inset >= _distance(start_xy, corner_xy) - _EPS:
    return None
  if inset >= _distance(corner_xy, next_xy) - _EPS:
    return None

  tangent_in = (
    corner_xy[0] - d_in[0] * inset,
    corner_xy[1] - d_in[1] * inset,
  )
  tangent_out = (
    corner_xy[0] + d_out[0] * inset,
    corner_xy[1] + d_out[1] * inset,
  )

  cross = d_in[0] * d_out[1] - d_in[1] * d_out[0]
  if abs(cross) <= 1e-6:
    return None

  if cross > 0.0:
    normal = (-d_in[1], d_in[0])
    direction = MCCM_DIR_2D_CCW
  else:
    normal = (d_in[1], -d_in[0])
    direction = MCCM_DIR_2D_CW

  center = (
    tangent_in[0] + normal[0] * radius,
    tangent_in[1] + normal[1] * radius,
  )

  return [
    MotionSegment(
      seq=0,
      x=tangent_in[0],
      y=tangent_in[1],
      term_type=4,
      seg_type=SEG_TYPE_LINE,
    ),
    MotionSegment(
      seq=1,
      x=tangent_out[0],
      y=tangent_out[1],
      term_type=4,
      seg_type=SEG_TYPE_CIRCLE,
      circle_type=CIRCLE_TYPE_CENTER,
      via_center_x=center[0],
      via_center_y=center[1],
      direction=direction,
    ),
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

  exact = _exact_biarc_segments(start_xy=start_xy, waypoints=waypoints)
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
    if exact:
      exact[-1] = replace(exact[-1], term_type=0)
    return exact

  segments: list[MotionSegment] = []
  cursor = (float(start_xy[0]), float(start_xy[1]))

  for index, waypoint in enumerate(waypoints):
    point_xy = (float(waypoint.x), float(waypoint.y))
    next_point = waypoints[index + 1] if index + 1 < len(waypoints) else None

    if waypoint.mode == MERGE_MODE_TOLERANT and next_point is not None:
      fillet_segments = _build_fillet_segments(
        cursor,
        point_xy,
        (float(next_point.x), float(next_point.y)),
        min_arc_radius,
      )
      if fillet_segments is not None:
        decorated = _decorate_segments(
          fillet_segments,
          start_seq=start_seq + len(segments),
          speed=speed,
          accel=accel,
          decel=decel,
          jerk_accel=jerk_accel,
          jerk_decel=jerk_decel,
        )
        if _segments_are_valid(
          segments + decorated,
          start_xy=start_xy,
          min_arc_radius=min_arc_radius,
          safety_limits=safety_limits,
          queued_motion_collision_state=queued_motion_collision_state,
        ):
          if _distance(cursor, (decorated[0].x, decorated[0].y)) <= _EPS:
            decorated = decorated[1:]
          segments.extend(decorated)
          cursor = (
            float(segments[-1].x),
            float(segments[-1].y),
          )
          continue

    line_segment = MotionSegment(
      seq=start_seq + len(segments),
      x=point_xy[0],
      y=point_xy[1],
      speed=speed,
      accel=accel,
      decel=decel,
      jerk_accel=jerk_accel,
      jerk_decel=jerk_decel,
      term_type=0,
      seg_type=SEG_TYPE_LINE,
    )
    candidate = segments + [line_segment]
    if not _segments_are_valid(
      candidate,
      start_xy=start_xy,
      min_arc_radius=min_arc_radius,
      safety_limits=safety_limits,
      queued_motion_collision_state=queued_motion_collision_state,
    ):
      raise ValueError(
        f"Unable to build a valid queued path through waypoint line {waypoint.line_index}"
      )
    segments = candidate
    cursor = point_xy

  if segments:
    segments[-1] = replace(segments[-1], term_type=0)
  return segments
