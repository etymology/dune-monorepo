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


def _circle_from_start_tangent_to_point(
  start_xy: tuple[float, float],
  tangent_xy: tuple[float, float],
  end_xy: tuple[float, float],
) -> Optional[tuple[float, float, int]]:
  sx, sy = start_xy
  ex, ey = end_xy
  tx, ty = _normalize(tangent_xy[0], tangent_xy[1])
  dx = ex - sx
  dy = ey - sy
  chord2 = dx * dx + dy * dy
  if chord2 <= 1e-12:
    return None

  nx, ny = _left_normal((tx, ty))
  denom = dx * nx + dy * ny
  if abs(denom) <= 1e-9:
    return None

  signed_radius = chord2 / (2.0 * denom)
  if abs(signed_radius) > 1e9:
    return None

  cx = sx + nx * signed_radius
  cy = sy + ny * signed_radius
  direction = MCCM_DIR_2D_CCW if signed_radius > 0.0 else MCCM_DIR_2D_CW
  return (cx, cy, direction)


def _arc_tangent(
  center_xy: tuple[float, float],
  point_xy: tuple[float, float],
  direction: int,
) -> Optional[tuple[float, float]]:
  radial_x = point_xy[0] - center_xy[0]
  radial_y = point_xy[1] - center_xy[1]
  radius = math.hypot(radial_x, radial_y)
  if radius <= 1e-9:
    return None

  if direction == MCCM_DIR_2D_CCW:
    return (-radial_y / radius, radial_x / radius)
  if direction == MCCM_DIR_2D_CW:
    return (radial_y / radius, -radial_x / radius)
  return None


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


def _single_tangent_arc_segment(
  *,
  start_xy: tuple[float, float],
  end_xy: tuple[float, float],
  start_tangent_xy: tuple[float, float],
  end_tangent_xy: tuple[float, float],
  tangent_tolerance_deg: float = 2.0,
) -> Optional[MotionSegment]:
  circle = _circle_from_start_tangent_to_point(start_xy, start_tangent_xy, end_xy)
  if circle is None:
    return None

  cx, cy, direction = circle
  actual_end_tangent = _arc_tangent((cx, cy), end_xy, direction)
  if actual_end_tangent is None:
    return None

  expected_end_tangent = _normalize(end_tangent_xy[0], end_tangent_xy[1])
  dot = (
    actual_end_tangent[0] * expected_end_tangent[0]
    + actual_end_tangent[1] * expected_end_tangent[1]
  )
  dot = max(-1.0, min(1.0, dot))
  if math.degrees(math.acos(dot)) > tangent_tolerance_deg:
    return None

  return MotionSegment(
    seq=0,
    x=end_xy[0],
    y=end_xy[1],
    term_type=4,
    seg_type=SEG_TYPE_CIRCLE,
    circle_type=CIRCLE_TYPE_CENTER,
    via_center_x=cx,
    via_center_y=cy,
    direction=direction,
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


def _alternating_line_arc_segments(
  *,
  start_xy: tuple[float, float],
  waypoints: list[MergeWaypoint],
) -> Optional[list[MotionSegment]]:
  if len(waypoints) < 3:
    return None

  points = [(float(start_xy[0]), float(start_xy[1]))]
  points.extend((float(waypoint.x), float(waypoint.y)) for waypoint in waypoints)

  segments: list[MotionSegment] = []
  edge_count = len(points) - 1
  for edge_index in range(edge_count):
    edge_start = points[edge_index]
    edge_end = points[edge_index + 1]

    if edge_index == 0 or edge_index % 2 == 0 or edge_index == edge_count - 1:
      segments.append(
        MotionSegment(
          seq=0,
          x=edge_end[0],
          y=edge_end[1],
          term_type=4,
          seg_type=SEG_TYPE_LINE,
        )
      )
      continue

    next_edge_end = points[edge_index + 2]
    start_tangent = _unit_vector_between(points[edge_index - 1], edge_start)
    end_tangent = _unit_vector_between(edge_end, next_edge_end)
    if start_tangent is None or end_tangent is None:
      return None

    arc_segment = _single_tangent_arc_segment(
      start_xy=edge_start,
      end_xy=edge_end,
      start_tangent_xy=start_tangent,
      end_tangent_xy=end_tangent,
    )
    if arc_segment is None:
      return None
    segments.append(arc_segment)

  return segments


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

  alternating = _alternating_line_arc_segments(
    start_xy=start_xy,
    waypoints=filtered_waypoints,
  )
  if alternating is not None and _segments_are_valid(
    alternating,
    start_xy=start_xy,
    min_arc_radius=min_arc_radius,
    safety_limits=safety_limits,
    queued_motion_collision_state=queued_motion_collision_state,
  ):
    alternating = _decorate_segments(
      alternating,
      start_seq=start_seq,
      speed=speed,
      accel=accel,
      decel=decel,
      jerk_accel=jerk_accel,
      jerk_decel=jerk_decel,
    )
    return apply_merge_term_types(
      alternating,
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
