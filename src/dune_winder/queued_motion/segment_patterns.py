from __future__ import annotations

import colorsys
import math
import time
from dataclasses import replace
from pathlib import Path
from typing import Optional

from .filleted_path import filleted_polygon_segments
from .segment_types import (
  CIRCLE_TYPE_CENTER,
  MCCM_DIR_2D_CCW,
  MCCM_DIR_2D_CCW_FULL,
  MCCM_DIR_2D_CW,
  MCCM_DIR_2D_CW_FULL,
  MotionSegment,
  arc_sweep_rad,
  circle_center_for_segment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
  has_circle_segments,
  segment_path_length,
)


LISSAJOUS_TESSELLATION_SEGMENTS = 400
TESTABLE_TERM_TYPES = (0, 1, 2, 3, 4, 5, 6)
DEFAULT_TEST_TERM_TYPE = 4
DEFAULT_MIN_SEGMENT_LENGTH = 0.0
DEFAULT_CONSTANT_VELOCITY_MODE = True
DEFAULT_CURVATURE_SPEED_SAFETY = 0.92
DEFAULT_MIN_JERK_RATIO = 0.0
DEFAULT_MAX_SEGMENT_FACTOR = 4.0

DEFAULT_FIBONACCI_ARC_COUNT = 8
DEFAULT_FIBONACCI_X_MIN = 1000.0
DEFAULT_FIBONACCI_X_MAX = 6000.0
DEFAULT_FIBONACCI_Y_MIN = 100.0
DEFAULT_FIBONACCI_Y_MAX = 2500.0
DEFAULT_FIBONACCI_DIRECTION = "ccw"
DEFAULT_TANGENCY_ANGLE_TOLERANCE_DEG = 2.0
DEFAULT_ORBIT_REVOLUTIONS = 6.0
DEFAULT_ORBIT_POINTS_PER_REVOLUTION = 120
DEFAULT_ORBIT_ECCENTRICITY = 0.6
DEFAULT_ORBIT_PRECESSION_DEG_PER_REVOLUTION = 18.0
DEFAULT_ORBIT_INITIAL_APSIS_DEG = 0.0
DEFAULT_ORBIT_BOUNDARY_MARGIN = 20.0
DEFAULT_ARCHIMEDEAN_TURNS = 6.0
DEFAULT_ARCHIMEDEAN_POINTS_PER_TURN = 120
DEFAULT_ARCHIMEDEAN_INITIAL_ANGLE_DEG = 0.0
DEFAULT_ARCHIMEDEAN_BOUNDARY_MARGIN = 20.0
DEFAULT_ARCHIMEDEAN_DIRECTION = "ccw"
DEFAULT_WAYPOINT_MIN_ARC_RADIUS = 50.0
DEFAULT_WAYPOINT_ORDER_MODE = "input"
DEFAULT_WAYPOINT_PLANNER_TIMEOUT_S = 3.0
DEFAULT_WAYPOINT_ALLOW_STOPS = False
DEFAULT_V_X_MAX = 825.0
DEFAULT_V_Y_MAX = 600.0


def validate_term_type(term_type: int) -> None:
  if term_type not in TESTABLE_TERM_TYPES:
    allowed = ", ".join(str(t) for t in TESTABLE_TERM_TYPES)
    raise ValueError(f"term_type must be one of: {allowed}")


def _normalize_xy(x: float, y: float) -> tuple[float, float]:
  mag = math.hypot(x, y)
  if mag <= 1e-9:
    return (1.0, 0.0)
  return (x / mag, y / mag)


def _distance_xy(p0: tuple[float, float], p1: tuple[float, float]) -> float:
  return math.hypot(p1[0] - p0[0], p1[1] - p0[1])


def _path_length(points: list[tuple[float, float]], start_xy: Optional[tuple[float, float]]) -> float:
  if not points:
    return 0.0

  total = 0.0
  if start_xy is not None:
    total += _distance_xy((float(start_xy[0]), float(start_xy[1])), points[0])

  for i in range(1, len(points)):
    total += _distance_xy(points[i - 1], points[i])
  return total


def _planner_deadline(timeout_s: float) -> Optional[float]:
  if timeout_s <= 0.0 and not math.isinf(timeout_s):
    raise ValueError("waypoint_planner_timeout_s must be > 0 or inf")
  if math.isinf(timeout_s):
    return None
  return time.monotonic() + timeout_s


def _planner_timed_out(deadline: Optional[float]) -> bool:
  return deadline is not None and time.monotonic() >= deadline


def _raise_planner_timeout(timeout_s: float, phase: str) -> None:
  raise TimeoutError(
    f"Waypoint planner timed out after {timeout_s:.1f}s while {phase}. "
    "Try fewer waypoints or use waypoint_order_mode='input'."
  )


def _nearest_neighbor_order(
  points: list[tuple[float, float]],
  start_idx: int,
  planner_deadline: Optional[float] = None,
  planner_timeout_s: float = DEFAULT_WAYPOINT_PLANNER_TIMEOUT_S,
) -> list[tuple[float, float]]:
  remaining = set(range(len(points)))
  remaining.remove(start_idx)
  ordered = [points[start_idx]]
  cur_idx = start_idx

  while remaining:
    if _planner_timed_out(planner_deadline):
      _raise_planner_timeout(planner_timeout_s, "building nearest-neighbor seed path")
    next_idx = min(
      remaining,
      key=lambda idx: _distance_xy(points[cur_idx], points[idx]),
    )
    ordered.append(points[next_idx])
    remaining.remove(next_idx)
    cur_idx = next_idx

  return ordered


def _two_opt_open_path(
  points: list[tuple[float, float]],
  planner_deadline: Optional[float] = None,
  planner_timeout_s: float = DEFAULT_WAYPOINT_PLANNER_TIMEOUT_S,
) -> list[tuple[float, float]]:
  if len(points) < 4:
    return points

  out = list(points)
  improved = True
  while improved:
    if _planner_timed_out(planner_deadline):
      _raise_planner_timeout(planner_timeout_s, "running 2-opt waypoint optimization")
    improved = False
    n = len(out)
    for i in range(0, n - 3):
      if _planner_timed_out(planner_deadline):
        _raise_planner_timeout(planner_timeout_s, "running 2-opt waypoint optimization")
      a = out[i]
      b = out[i + 1]
      for k in range(i + 2, n - 1):
        if _planner_timed_out(planner_deadline):
          _raise_planner_timeout(planner_timeout_s, "running 2-opt waypoint optimization")
        c = out[k]
        d = out[k + 1]
        old_len = _distance_xy(a, b) + _distance_xy(c, d)
        new_len = _distance_xy(a, c) + _distance_xy(b, d)
        if new_len + 1e-9 < old_len:
          out[i + 1 : k + 1] = reversed(out[i + 1 : k + 1])
          improved = True
    # For open paths, also allow reversing the tail to improve final edge.
    n = len(out)
    for i in range(0, n - 2):
      if _planner_timed_out(planner_deadline):
        _raise_planner_timeout(planner_timeout_s, "running 2-opt waypoint optimization")
      a = out[i]
      b = out[i + 1]
      c = out[-1]
      old_len = _distance_xy(a, b)
      new_len = _distance_xy(a, c)
      if new_len + 1e-9 < old_len:
        out[i + 1 :] = reversed(out[i + 1 :])
        improved = True
  return out


def _order_waypoints_for_short_path(
  points: list[tuple[float, float]],
  start_xy: Optional[tuple[float, float]] = None,
  waypoint_planner_timeout_s: float = DEFAULT_WAYPOINT_PLANNER_TIMEOUT_S,
) -> list[tuple[float, float]]:
  if len(points) <= 2:
    return points
  planner_deadline = _planner_deadline(waypoint_planner_timeout_s)

  if start_xy is not None:
    sx, sy = float(start_xy[0]), float(start_xy[1])
    start_idx_candidates = [
      min(range(len(points)), key=lambda i: _distance_xy((sx, sy), points[i]))
    ]
  else:
    start_idx_candidates = list(range(len(points)))

  best: Optional[list[tuple[float, float]]] = None
  best_len = float("inf")
  for start_idx in start_idx_candidates:
    if _planner_timed_out(planner_deadline):
      _raise_planner_timeout(
        waypoint_planner_timeout_s,
        "evaluating waypoint start candidates",
      )
    candidate = _nearest_neighbor_order(
      points,
      start_idx,
      planner_deadline=planner_deadline,
      planner_timeout_s=waypoint_planner_timeout_s,
    )
    candidate = _two_opt_open_path(
      candidate,
      planner_deadline=planner_deadline,
      planner_timeout_s=waypoint_planner_timeout_s,
    )
    length = _path_length(candidate, start_xy=start_xy)
    if length < best_len:
      best_len = length
      best = candidate

  return points if best is None else best


def _waypoint_tangents(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
  if not points:
    return []
  if len(points) == 1:
    return [(1.0, 0.0)]

  tangents: list[tuple[float, float]] = []
  for i, p in enumerate(points):
    if i == 0:
      dx = points[1][0] - p[0]
      dy = points[1][1] - p[1]
      tangents.append(_normalize_xy(dx, dy))
      continue
    if i == len(points) - 1:
      dx = p[0] - points[i - 1][0]
      dy = p[1] - points[i - 1][1]
      tangents.append(_normalize_xy(dx, dy))
      continue

    in_dx = p[0] - points[i - 1][0]
    in_dy = p[1] - points[i - 1][1]
    out_dx = points[i + 1][0] - p[0]
    out_dy = points[i + 1][1] - p[1]
    in_v = _normalize_xy(in_dx, in_dy)
    out_v = _normalize_xy(out_dx, out_dy)
    sum_x = in_v[0] + out_v[0]
    sum_y = in_v[1] + out_v[1]
    if math.hypot(sum_x, sum_y) <= 1e-9:
      tangents.append(out_v)
    else:
      tangents.append(_normalize_xy(sum_x, sum_y))

  return tangents


def _point_within_bounds(
  x: float,
  y: float,
  bounds: tuple[float, float, float, float],
  eps: float = 1e-6,
) -> bool:
  x_min, x_max, y_min, y_max = bounds
  return (x_min - eps) <= x <= (x_max + eps) and (y_min - eps) <= y <= (y_max + eps)


def _segments_within_bounds(
  segments: list[MotionSegment],
  bounds: tuple[float, float, float, float],
) -> bool:
  if not segments:
    return True

  prev_x = float(segments[0].x)
  prev_y = float(segments[0].y)
  if not _point_within_bounds(prev_x, prev_y, bounds):
    return False

  for seg in segments[1:]:
    if seg.seg_type != SEG_TYPE_CIRCLE:
      if not _point_within_bounds(seg.x, seg.y, bounds):
        return False
      prev_x = float(seg.x)
      prev_y = float(seg.y)
      continue

    start = MotionSegment(seq=seg.seq - 1, x=prev_x, y=prev_y)
    center = circle_center_for_segment(start, seg)
    if center is None:
      if not _point_within_bounds(seg.x, seg.y, bounds):
        return False
      prev_x = float(seg.x)
      prev_y = float(seg.y)
      continue

    cx, cy = center
    r0 = math.hypot(prev_x - cx, prev_y - cy)
    r1 = math.hypot(seg.x - cx, seg.y - cy)
    if r0 <= 1e-9 or r1 <= 1e-9:
      if not _point_within_bounds(seg.x, seg.y, bounds):
        return False
      prev_x = float(seg.x)
      prev_y = float(seg.y)
      continue

    a0 = math.atan2(prev_y - cy, prev_x - cx)
    a1 = math.atan2(seg.y - cy, seg.x - cx)
    sweep = arc_sweep_rad(a0, a1, seg.direction)
    if sweep is None:
      if not _point_within_bounds(seg.x, seg.y, bounds):
        return False
      prev_x = float(seg.x)
      prev_y = float(seg.y)
      continue

    radius = 0.5 * (r0 + r1)
    steps = max(8, int(math.ceil(abs(sweep) / math.radians(4.0))))
    for i in range(1, steps + 1):
      angle = a0 + sweep * (i / steps)
      x = cx + radius * math.cos(angle)
      y = cy + radius * math.sin(angle)
      if not _point_within_bounds(x, y, bounds):
        return False

    prev_x = float(seg.x)
    prev_y = float(seg.y)

  return True


def _build_waypoint_stoppable_segments(
  points: list[tuple[float, float]],
  tangents: list[tuple[float, float]],
  start_seq: int,
  term_type: int,
  min_arc_radius: float,
  bounds: tuple[float, float, float, float],
) -> list[MotionSegment]:
  out: list[MotionSegment] = [
    MotionSegment(
      seq=start_seq,
      x=points[0][0],
      y=points[0][1],
      term_type=term_type,
      seg_type=SEG_TYPE_LINE,
    )
  ]
  next_seq = start_seq + 1

  for i in range(len(points) - 1):
    p0 = points[i]
    p1 = points[i + 1]
    edge_segments = _tangent_biarc_tessellation(
      [p0, p1],
      [tangents[i], tangents[i + 1]],
      start_seq=0,
      term_type=term_type,
    )
    edge_segments = _enforce_min_arc_radius(
      edge_segments,
      min_arc_radius=min_arc_radius,
    )

    if not _segments_within_bounds(edge_segments, bounds):
      edge_segments = [
        MotionSegment(
          seq=0,
          x=p0[0],
          y=p0[1],
          term_type=term_type,
          seg_type=SEG_TYPE_LINE,
        ),
        MotionSegment(
          seq=1,
          x=p1[0],
          y=p1[1],
          term_type=term_type,
          seg_type=SEG_TYPE_LINE,
        ),
      ]

    for seg in edge_segments[1:]:
      out.append(replace(seg, seq=next_seq))
      next_seq += 1

  return out


def _enforce_min_arc_radius(
  segments: list[MotionSegment],
  min_arc_radius: float,
) -> list[MotionSegment]:
  if min_arc_radius <= 0.0 or len(segments) <= 1:
    return segments

  out: list[MotionSegment] = [segments[0]]
  prev_x = float(segments[0].x)
  prev_y = float(segments[0].y)

  for seg in segments[1:]:
    rewritten = seg
    if seg.seg_type == SEG_TYPE_CIRCLE:
      start = MotionSegment(seq=seg.seq - 1, x=prev_x, y=prev_y)
      center = circle_center_for_segment(start, seg)
      if center is not None:
        cx, cy = center
        radius = math.hypot(prev_x - cx, prev_y - cy)
        if radius + 1e-9 < min_arc_radius:
          rewritten = replace(
            seg,
            seg_type=SEG_TYPE_LINE,
            circle_type=CIRCLE_TYPE_CENTER,
            via_center_x=0.0,
            via_center_y=0.0,
            direction=MCCM_DIR_2D_CCW,
          )
    out.append(rewritten)
    prev_x = float(rewritten.x)
    prev_y = float(rewritten.y)

  return out


def _tangent_biarc_tessellation(
  points: list[tuple[float, float]],
  tangents: list[tuple[float, float]],
  start_seq: int,
  term_type: int,
) -> list[MotionSegment]:
  if not points or len(points) != len(tangents):
    return []

  def circle_from_start_tangent_to_point(
    start: tuple[float, float],
    tangent: tuple[float, float],
    end: tuple[float, float],
  ) -> Optional[tuple[float, float, int]]:
    sx, sy = start
    ex, ey = end
    tx, ty = tangent
    dx = ex - sx
    dy = ey - sy
    chord2 = dx * dx + dy * dy
    if chord2 <= 1e-12:
      return None

    nx = -ty
    ny = tx
    denom = dx * nx + dy * ny
    if abs(denom) <= 1e-9:
      return None

    signed_radius = chord2 / (2.0 * denom)
    if abs(signed_radius) > 1e9:
      return None

    cx = sx + nx * signed_radius
    cy = sy + ny * signed_radius
    direction = MCCM_DIR_2D_CCW if signed_radius > 0 else MCCM_DIR_2D_CW
    return (cx, cy, direction)

  def invert_direction(direction: int) -> int:
    if direction == MCCM_DIR_2D_CCW:
      return MCCM_DIR_2D_CW
    if direction == MCCM_DIR_2D_CW:
      return MCCM_DIR_2D_CCW
    return direction

  def biarc_segments(
    p0: tuple[float, float],
    t0: tuple[float, float],
    p1: tuple[float, float],
    t1: tuple[float, float],
  ) -> list[tuple[str, float, float, float, float, int]]:
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    dy = y1 - y0
    chord2 = dx * dx + dy * dy
    if chord2 <= 1e-12:
      return []

    t0x, t0y = _normalize_xy(t0[0], t0[1])
    t1x, t1y = _normalize_xy(t1[0], t1[1])
    dot = max(-1.0, min(1.0, t0x * t1x + t0y * t1y))

    join: Optional[tuple[float, float]] = None
    a = 2.0 * (1.0 - dot)
    if a > 1e-9:
      b = dx * (t0x + t1x) + dy * (t0y + t1y)
      c = chord2
      disc = b * b + a * c
      if disc >= 0.0:
        sqrt_disc = math.sqrt(disc)
        d_candidates = [(-b + sqrt_disc) / a, (-b - sqrt_disc) / a]
        positive = [value for value in d_candidates if value >= 0.0]
        d = min(positive) if positive else max(d_candidates)
        jx = 0.5 * (x0 + x1 + d * (t0x - t1x))
        jy = 0.5 * (y0 + y1 + d * (t0y - t1y))
        if (
          math.hypot(jx - x0, jy - y0) > 1e-6
          and math.hypot(x1 - jx, y1 - jy) > 1e-6
        ):
          join = (jx, jy)

    if join is not None:
      arc0 = circle_from_start_tangent_to_point(p0, (t0x, t0y), join)
      arc1_rev = circle_from_start_tangent_to_point(p1, (-t1x, -t1y), join)
      if arc0 is not None and arc1_rev is not None:
        c0x, c0y, d0 = arc0
        c1x, c1y, d1_rev = arc1_rev
        return [
          ("arc", join[0], join[1], c0x, c0y, d0),
          ("arc", x1, y1, c1x, c1y, invert_direction(d1_rev)),
        ]

    arc = circle_from_start_tangent_to_point(p0, (t0x, t0y), p1)
    if arc is not None:
      cx, cy, direction = arc
      return [("arc", x1, y1, cx, cy, direction)]

    return [("line", x1, y1, 0.0, 0.0, 0)]

  seq = start_seq
  segments: list[MotionSegment] = [
    MotionSegment(
      seq=seq,
      x=points[0][0],
      y=points[0][1],
      term_type=term_type,
      seg_type=SEG_TYPE_LINE,
    )
  ]
  seq += 1

  for i in range(len(points) - 1):
    p0 = points[i]
    p1 = points[i + 1]
    t0 = tangents[i]
    t1 = tangents[i + 1]
    for seg_kind, ex, ey, cx, cy, direction in biarc_segments(p0, t0, p1, t1):
      if seg_kind == "arc":
        segments.append(
          MotionSegment(
            seq=seq,
            x=ex,
            y=ey,
            term_type=term_type,
            seg_type=SEG_TYPE_CIRCLE,
            circle_type=CIRCLE_TYPE_CENTER,
            via_center_x=cx,
            via_center_y=cy,
            direction=direction,
          )
        )
      else:
        segments.append(
          MotionSegment(
            seq=seq,
            x=ex,
            y=ey,
            term_type=term_type,
            seg_type=SEG_TYPE_LINE,
          )
        )
      seq += 1

  return segments


def square_segments(
  start_seq: int = 100,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  points = [
    (1000.0, 0.0),
    (1000.0, 1000.0),
    (2000.0, 1000.0),
    (2000.0, 0.0),
    (1000.0, 0.0),
  ]

  segments: list[MotionSegment] = []
  for i, (x, y) in enumerate(points):
    segments.append(
      MotionSegment(
        seq=start_seq + i,
        x=x,
        y=y,
        term_type=term_type,
      )
    )
  return segments


def lissajous_segments(
  start_seq: int = 100,
  tessellation_segments: int = LISSAJOUS_TESSELLATION_SEGMENTS,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
  x_min: float = 1000.0,
  x_max: float = 6000.0,
  y_min: float = 0.0,
  y_max: float = 2500.0,
  x_freq: int = 3,
  y_freq: int = 2,
  phase_rad: float = math.pi / 2.0,
  boundary_margin: float = 10.0,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  if tessellation_segments < 3:
    raise ValueError("tessellation_segments must be >= 3")
  if x_min >= x_max or y_min >= y_max:
    raise ValueError("invalid bounds")
  if boundary_margin < 0.0:
    raise ValueError("boundary_margin must be >= 0")

  x_center = (x_min + x_max) / 2.0
  y_center = (y_min + y_max) / 2.0
  x_amp = (x_max - x_min) / 2.0 - boundary_margin
  y_amp = (y_max - y_min) / 2.0 - boundary_margin

  if x_amp <= 0.0 or y_amp <= 0.0:
    raise ValueError("boundary_margin is too large for the requested box")

  def point_at_t(t: float) -> tuple[float, float]:
    x = x_center + x_amp * math.sin(x_freq * t + phase_rad)
    y = y_center + y_amp * math.sin(y_freq * t)
    return (x, y)

  def point_line_distance(
    p: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
  ) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    abx = bx - ax
    aby = by - ay
    ab2 = abx * abx + aby * aby
    if ab2 <= 1e-12:
      return math.hypot(px - ax, py - ay)
    t = ((px - ax) * abx + (py - ay) * aby) / ab2
    t = max(0.0, min(1.0, t))
    qx = ax + t * abx
    qy = ay + t * aby
    return math.hypot(px - qx, py - qy)

  def turn_angle(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
  ) -> float:
    v1x = b[0] - a[0]
    v1y = b[1] - a[1]
    v2x = c[0] - b[0]
    v2y = c[1] - b[1]
    m1 = math.hypot(v1x, v1y)
    m2 = math.hypot(v2x, v2y)
    if m1 <= 1e-9 or m2 <= 1e-9:
      return 0.0
    cos_theta = (v1x * v2x + v1y * v2y) / (m1 * m2)
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.acos(cos_theta)

  scale = min(x_amp, y_amp) * 2.0
  max_chord_error = max(0.25, scale / (2.0 * float(tessellation_segments)))
  max_turn_rad = math.radians(8.0)
  min_dt = (2.0 * math.pi) / max(4096.0, float(tessellation_segments) * 32.0)
  max_depth = 20
  seed_intervals = max(8, min(64, 2 * (x_freq + y_freq)))

  samples: list[tuple[float, tuple[float, float]]] = []

  def add_segment(
    t0: float,
    p0: tuple[float, float],
    t1: float,
    p1: tuple[float, float],
    depth: int,
  ) -> None:
    tm = (t0 + t1) * 0.5
    pm = point_at_t(tm)
    deviation = point_line_distance(pm, p0, p1)
    angle = turn_angle(p0, pm, p1)
    need_split = deviation > max_chord_error or angle > max_turn_rad

    if need_split and depth < max_depth and (t1 - t0) > min_dt:
      add_segment(t0, p0, tm, pm, depth + 1)
      add_segment(tm, pm, t1, p1, depth + 1)
      return

    samples.append((t1, p1))

  t_start = 0.0
  p_start = point_at_t(t_start)
  samples.append((t_start, p_start))

  for i in range(seed_intervals):
    t0 = (2.0 * math.pi * i) / seed_intervals
    t1 = (2.0 * math.pi * (i + 1)) / seed_intervals
    p0 = point_at_t(t0)
    p1 = point_at_t(t1)
    add_segment(t0, p0, t1, p1, depth=0)

  t_values = [t for t, _ in samples]
  points = [p for _, p in samples]
  if len(points) >= 2 and math.hypot(
    points[-1][0] - points[0][0], points[-1][1] - points[0][1]
  ) < 1e-6:
    points.pop()
    t_values.pop()

  if not points:
    return []

  def tangent_at_t(t: float) -> tuple[float, float]:
    tx = x_amp * x_freq * math.cos(x_freq * t + phase_rad)
    ty = y_amp * y_freq * math.cos(y_freq * t)
    mag = math.hypot(tx, ty)
    if mag > 1e-9:
      return (tx / mag, ty / mag)

    dt = 1e-4
    px1, py1 = point_at_t(t - dt)
    px2, py2 = point_at_t(t + dt)
    tx = px2 - px1
    ty = py2 - py1
    mag = math.hypot(tx, ty)
    if mag > 1e-9:
      return (tx / mag, ty / mag)
    return (1.0, 0.0)

  tangents = [tangent_at_t(t) for t in t_values]
  return _tangent_biarc_tessellation(points, tangents, start_seq, term_type)


def simple_two_segment_test(
  start_seq: int = 200,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  return [
    MotionSegment(seq=start_seq, x=1000.0, y=0.0, term_type=term_type),
    MotionSegment(seq=start_seq + 1, x=1000.0, y=1000.0, term_type=term_type),
  ]


def tangent_line_arc_segments(
  start_seq: int = 300,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
) -> list[MotionSegment]:
  validate_term_type(term_type)

  return [
    MotionSegment(
      seq=start_seq + 0,
      x=1000.0,
      y=0.0,
      term_type=term_type,
      seg_type=SEG_TYPE_LINE,
    ),
    MotionSegment(
      seq=start_seq + 1,
      x=1500.0,
      y=500.0,
      term_type=term_type,
      seg_type=SEG_TYPE_CIRCLE,
      circle_type=CIRCLE_TYPE_CENTER,
      via_center_x=1000.0,
      via_center_y=500.0,
      direction=MCCM_DIR_2D_CCW,
    ),
    MotionSegment(
      seq=start_seq + 2,
      x=1500.0,
      y=1200.0,
      term_type=term_type,
      seg_type=SEG_TYPE_LINE,
    ),
    MotionSegment(
      seq=start_seq + 3,
      x=2000.0,
      y=1700.0,
      term_type=term_type,
      seg_type=SEG_TYPE_CIRCLE,
      circle_type=CIRCLE_TYPE_CENTER,
      via_center_x=2000.0,
      via_center_y=1200.0,
      direction=MCCM_DIR_2D_CW,
    ),
    MotionSegment(
      seq=start_seq + 4,
      x=2600.0,
      y=1700.0,
      term_type=term_type,
      seg_type=SEG_TYPE_LINE,
    ),
  ]


def fibonacci_spiral_arc_segments(
  start_seq: int = 400,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
  arc_count: int = DEFAULT_FIBONACCI_ARC_COUNT,
  x_min: float = DEFAULT_FIBONACCI_X_MIN,
  x_max: float = DEFAULT_FIBONACCI_X_MAX,
  y_min: float = DEFAULT_FIBONACCI_Y_MIN,
  y_max: float = DEFAULT_FIBONACCI_Y_MAX,
  direction: str = DEFAULT_FIBONACCI_DIRECTION,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  if arc_count < 2:
    raise ValueError("arc_count must be >= 2")
  if x_min >= x_max or y_min >= y_max:
    raise ValueError("invalid bounds")

  direction_text = direction.strip().lower()
  if direction_text not in ("ccw", "cw"):
    raise ValueError("direction must be 'ccw' or 'cw'")
  ccw = direction_text == "ccw"
  mccm_direction = MCCM_DIR_2D_CCW if ccw else MCCM_DIR_2D_CW

  fib = [1, 1]
  while len(fib) < arc_count:
    fib.append(fib[-1] + fib[-2])

  x = 0.0
  y = 0.0
  tx = 1.0
  ty = 0.0
  raw_arcs: list[tuple[float, float, float, float, float, float]] = []

  for i in range(arc_count):
    r = float(fib[i])
    if ccw:
      nx, ny = -ty, tx
      cx = x + nx * r
      cy = y + ny * r
      rsx = x - cx
      rsy = y - cy
      rex = -rsy
      rey = rsx
      ex = cx + rex
      ey = cy + rey
      tx, ty = -ty, tx
    else:
      nx, ny = ty, -tx
      cx = x + nx * r
      cy = y + ny * r
      rsx = x - cx
      rsy = y - cy
      rex = rsy
      rey = -rsx
      ex = cx + rex
      ey = cy + rey
      tx, ty = ty, -tx

    raw_arcs.append((x, y, ex, ey, cx, cy))
    x, y = ex, ey

  def sample_arc_points(
    sx: float,
    sy: float,
    ex: float,
    ey: float,
    cx: float,
    cy: float,
    mccm_dir: int,
  ) -> list[tuple[float, float]]:
    a0 = math.atan2(sy - cy, sx - cx)
    a1 = math.atan2(ey - cy, ex - cx)
    sweep = arc_sweep_rad(a0, a1, mccm_dir)
    if sweep is None:
      return [(sx, sy), (ex, ey)]

    radius = math.hypot(sx - cx, sy - cy)
    steps = max(8, int(math.ceil(abs(sweep) / math.radians(5.0))))
    points: list[tuple[float, float]] = []
    for step in range(steps + 1):
      t = step / steps
      angle = a0 + sweep * t
      points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points

  sampled_points = [(0.0, 0.0)]
  for sx, sy, ex, ey, cx, cy in raw_arcs:
    sampled_points.extend(sample_arc_points(sx, sy, ex, ey, cx, cy, mccm_direction))

  raw_x_min = min(point[0] for point in sampled_points)
  raw_x_max = max(point[0] for point in sampled_points)
  raw_y_min = min(point[1] for point in sampled_points)
  raw_y_max = max(point[1] for point in sampled_points)
  raw_w = raw_x_max - raw_x_min
  raw_h = raw_y_max - raw_y_min
  if raw_w <= 0.0 or raw_h <= 0.0:
    raise ValueError("degenerate Fibonacci spiral geometry")

  bound_w = x_max - x_min
  bound_h = y_max - y_min
  scale = min(bound_w / raw_w, bound_h / raw_h)
  tx_out = x_min - raw_x_min * scale + 0.5 * (bound_w - raw_w * scale)
  ty_out = y_min - raw_y_min * scale + 0.5 * (bound_h - raw_h * scale)

  segments: list[MotionSegment] = []
  start_x = tx_out
  start_y = ty_out
  segments.append(
    MotionSegment(
      seq=start_seq,
      x=start_x,
      y=start_y,
      term_type=term_type,
      seg_type=SEG_TYPE_LINE,
    )
  )

  for i, (_, _, ex, ey, cx, cy) in enumerate(raw_arcs):
    segments.append(
      MotionSegment(
        seq=start_seq + i + 1,
        x=tx_out + ex * scale,
        y=ty_out + ey * scale,
        term_type=term_type,
        seg_type=SEG_TYPE_CIRCLE,
        circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=tx_out + cx * scale,
        via_center_y=ty_out + cy * scale,
        direction=mccm_direction,
      )
    )

  return segments


def apsidal_precessing_orbit_segments(
  start_seq: int = 500,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
  x_min: float = 1000.0,
  x_max: float = 6000.0,
  y_min: float = 0.0,
  y_max: float = 2500.0,
  revolutions: float = DEFAULT_ORBIT_REVOLUTIONS,
  points_per_revolution: int = DEFAULT_ORBIT_POINTS_PER_REVOLUTION,
  eccentricity: float = DEFAULT_ORBIT_ECCENTRICITY,
  precession_deg_per_revolution: float = DEFAULT_ORBIT_PRECESSION_DEG_PER_REVOLUTION,
  initial_apsis_deg: float = DEFAULT_ORBIT_INITIAL_APSIS_DEG,
  boundary_margin: float = DEFAULT_ORBIT_BOUNDARY_MARGIN,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  if x_min >= x_max or y_min >= y_max:
    raise ValueError("invalid bounds")
  if revolutions <= 0.0:
    raise ValueError("revolutions must be > 0")
  if points_per_revolution < 16:
    raise ValueError("points_per_revolution must be >= 16")
  if not (0.0 <= eccentricity < 1.0):
    raise ValueError("eccentricity must be in [0, 1)")
  if boundary_margin < 0.0:
    raise ValueError("boundary_margin must be >= 0")

  center_x = 0.5 * (x_min + x_max)
  center_y = 0.5 * (y_min + y_max)
  x_amp = 0.5 * (x_max - x_min) - boundary_margin
  y_amp = 0.5 * (y_max - y_min) - boundary_margin
  if x_amp <= 0.0 or y_amp <= 0.0:
    raise ValueError("boundary_margin is too large for the requested box")

  semi_major = min(x_amp, y_amp)
  semi_minor = semi_major * math.sqrt(max(0.0, 1.0 - eccentricity * eccentricity))
  if semi_minor <= 1e-9:
    raise ValueError("eccentricity is too close to 1 for stable interpolation")

  total_points = max(2, int(math.ceil(revolutions * points_per_revolution)) + 1)
  precession_rad_per_orbit = math.radians(precession_deg_per_revolution)
  initial_apsis_rad = math.radians(initial_apsis_deg)
  total_phase = 2.0 * math.pi * revolutions
  precession_rad_per_phase = precession_rad_per_orbit / (2.0 * math.pi)

  points: list[tuple[float, float]] = []
  tangents: list[tuple[float, float]] = []
  for i in range(total_points):
    phase = total_phase * (i / (total_points - 1))
    precession = initial_apsis_rad + precession_rad_per_phase * phase
    cos_p = math.cos(precession)
    sin_p = math.sin(precession)

    x_local = semi_major * math.cos(phase)
    y_local = semi_minor * math.sin(phase)
    x = center_x + cos_p * x_local - sin_p * y_local
    y = center_y + sin_p * x_local + cos_p * y_local
    points.append((x, y))

    dx_local = -semi_major * math.sin(phase)
    dy_local = semi_minor * math.cos(phase)

    # dR/dphase = dR/dprecession * dprecession/dphase
    # where dR/dprecession = [[-sin, -cos], [cos, -sin]]
    dR_x = precession_rad_per_phase * (-sin_p * x_local - cos_p * y_local)
    dR_y = precession_rad_per_phase * (cos_p * x_local - sin_p * y_local)

    dx = dR_x + (cos_p * dx_local - sin_p * dy_local)
    dy = dR_y + (sin_p * dx_local + cos_p * dy_local)
    tangents.append(_normalize_xy(dx, dy))

  return _tangent_biarc_tessellation(points, tangents, start_seq, term_type)


def archimedean_spiral_segments(
  start_seq: int = 600,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
  x_min: float = 1000.0,
  x_max: float = 6000.0,
  y_min: float = 0.0,
  y_max: float = 2500.0,
  turns: float = DEFAULT_ARCHIMEDEAN_TURNS,
  points_per_turn: int = DEFAULT_ARCHIMEDEAN_POINTS_PER_TURN,
  initial_angle_deg: float = DEFAULT_ARCHIMEDEAN_INITIAL_ANGLE_DEG,
  boundary_margin: float = DEFAULT_ARCHIMEDEAN_BOUNDARY_MARGIN,
  direction: str = DEFAULT_ARCHIMEDEAN_DIRECTION,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  if x_min >= x_max or y_min >= y_max:
    raise ValueError("invalid bounds")
  if turns <= 0.0:
    raise ValueError("turns must be > 0")
  if points_per_turn < 16:
    raise ValueError("points_per_turn must be >= 16")
  if boundary_margin < 0.0:
    raise ValueError("boundary_margin must be >= 0")

  direction_text = direction.strip().lower()
  if direction_text not in ("ccw", "cw"):
    raise ValueError("direction must be 'ccw' or 'cw'")

  center_x = 0.5 * (x_min + x_max)
  center_y = 0.5 * (y_min + y_max)
  x_amp = 0.5 * (x_max - x_min) - boundary_margin
  y_amp = 0.5 * (y_max - y_min) - boundary_margin
  if x_amp <= 0.0 or y_amp <= 0.0:
    raise ValueError("boundary_margin is too large for the requested box")

  theta_max = 2.0 * math.pi * turns
  if theta_max <= 1e-9:
    raise ValueError("turns must be large enough to form a spiral")
  dscale_dtheta = 1.0 / theta_max
  direction_sign = 1.0 if direction_text == "ccw" else -1.0
  phase0 = math.radians(initial_angle_deg)
  total_points = max(3, int(math.ceil(turns * points_per_turn)) + 1)

  points: list[tuple[float, float]] = []
  tangents: list[tuple[float, float]] = []
  for i in range(total_points):
    theta = theta_max * (i / (total_points - 1))
    scale = theta / theta_max
    phase = phase0 + direction_sign * theta
    cos_p = math.cos(phase)
    sin_p = math.sin(phase)

    x = center_x + x_amp * scale * cos_p
    y = center_y + y_amp * scale * sin_p
    points.append((x, y))

    dx = x_amp * (dscale_dtheta * cos_p - scale * sin_p * direction_sign)
    dy = y_amp * (dscale_dtheta * sin_p + scale * cos_p * direction_sign)
    tangents.append(_normalize_xy(dx, dy))

  return _tangent_biarc_tessellation(points, tangents, start_seq, term_type)


def waypoint_path_segments(
  start_seq: int = 700,
  term_type: int = DEFAULT_TEST_TERM_TYPE,
  waypoints: Optional[list[tuple[float, float]]] = None,
  min_arc_radius: float = DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  waypoint_order_mode: str = DEFAULT_WAYPOINT_ORDER_MODE,
  start_xy: Optional[tuple[float, float]] = None,
  waypoint_planner_timeout_s: float = DEFAULT_WAYPOINT_PLANNER_TIMEOUT_S,
  waypoint_bounds: Optional[tuple[float, float, float, float]] = None,
  waypoint_allow_stops: bool = DEFAULT_WAYPOINT_ALLOW_STOPS,
) -> list[MotionSegment]:
  validate_term_type(term_type)
  if waypoints is None or len(waypoints) < 2:
    raise ValueError("waypoints pattern requires at least 2 waypoints")
  if min_arc_radius < 0.0:
    raise ValueError("min_arc_radius must be >= 0")

  mode = waypoint_order_mode.strip().lower()
  if mode not in ("input", "shortest"):
    raise ValueError("waypoint_order_mode must be 'input' or 'shortest'")

  points: list[tuple[float, float]] = []
  for x, y in waypoints:
    px = float(x)
    py = float(y)
    if not points or _distance_xy(points[-1], (px, py)) > 1e-9:
      points.append((px, py))

  if len(points) < 2:
    raise ValueError("waypoints must contain at least 2 distinct points")

  if mode == "shortest":
    points = _order_waypoints_for_short_path(
      points,
      start_xy=start_xy,
      waypoint_planner_timeout_s=waypoint_planner_timeout_s,
    )

  filleted = filleted_polygon_segments(
    start_xy=points[0],
    waypoints=points[1:],
    radius=min_arc_radius,
    line_term_type=term_type,
    arc_term_type=term_type,
    final_term_type=term_type,
  )
  if filleted is not None:
    segments = [replace(seg, seq=start_seq + i) for i, seg in enumerate(filleted)]
    if waypoint_bounds is None or _segments_within_bounds(segments, waypoint_bounds):
      return segments

  stop_term_type = 0 if waypoint_allow_stops or filleted is None else term_type
  segments = [
    MotionSegment(
      seq=start_seq + index,
      x=point[0],
      y=point[1],
      term_type=stop_term_type,
      seg_type=SEG_TYPE_LINE,
    )
    for index, point in enumerate(points)
  ]
  return segments


def enforce_min_segment_length(
  segments: list[MotionSegment],
  min_segment_length: float,
) -> list[MotionSegment]:
  if min_segment_length <= 0.0 or len(segments) <= 2:
    return segments
  if has_circle_segments(segments):
    return segments

  filtered: list[MotionSegment] = [segments[0]]
  for seg in segments[1:-1]:
    prev = filtered[-1]
    if math.hypot(seg.x - prev.x, seg.y - prev.y) >= min_segment_length:
      filtered.append(seg)

  last = segments[-1]
  if len(filtered) >= 2:
    prev = filtered[-1]
    if math.hypot(last.x - prev.x, last.y - prev.y) < min_segment_length:
      prev_prev = filtered[-2]
      if math.hypot(last.x - prev_prev.x, last.y - prev_prev.y) >= min_segment_length:
        filtered[-1] = last
      else:
        filtered.append(last)
    else:
      filtered.append(last)
  else:
    filtered.append(last)

  base_seq = filtered[0].seq
  return [replace(seg, seq=base_seq + i) for i, seg in enumerate(filtered)]


def enforce_max_segment_length(
  segments: list[MotionSegment],
  max_segment_length: float,
) -> list[MotionSegment]:
  if max_segment_length <= 0.0 or len(segments) <= 1:
    return segments
  if has_circle_segments(segments):
    return segments

  out: list[MotionSegment] = [segments[0]]
  next_seq = segments[0].seq + 1

  for seg in segments[1:]:
    prev = out[-1]
    dx = seg.x - prev.x
    dy = seg.y - prev.y
    dist = math.hypot(dx, dy)

    if dist <= max_segment_length:
      out.append(replace(seg, seq=next_seq))
      next_seq += 1
      continue

    parts = int(math.ceil(dist / max_segment_length))
    for i in range(1, parts + 1):
      frac = i / parts
      out.append(
        replace(
          seg,
          seq=next_seq,
          x=prev.x + dx * frac,
          y=prev.y + dy * frac,
        )
      )
      next_seq += 1

  return out


def segment_lengths(segments: list[MotionSegment]) -> list[float]:
  return [
    segment_path_length(segments[i - 1], segments[i])
    for i in range(1, len(segments))
  ]


def _normalize_vector(x: float, y: float) -> Optional[tuple[float, float]]:
  mag = math.hypot(x, y)
  if mag <= 1e-9:
    return None
  return (x / mag, y / mag)


def _max_abs_sin_over_sweep(start_angle: float, sweep: float) -> float:
  end_angle = start_angle + sweep
  lo = min(start_angle, end_angle)
  hi = max(start_angle, end_angle)
  max_val = max(abs(math.sin(start_angle)), abs(math.sin(end_angle)))

  # |sin(theta)| reaches 1 at theta = pi/2 + k*pi
  k0 = math.ceil((lo - (0.5 * math.pi)) / math.pi)
  k1 = math.floor((hi - (0.5 * math.pi)) / math.pi)
  if k0 <= k1:
    return 1.0
  return max_val


def _max_abs_cos_over_sweep(start_angle: float, sweep: float) -> float:
  end_angle = start_angle + sweep
  lo = min(start_angle, end_angle)
  hi = max(start_angle, end_angle)
  max_val = max(abs(math.cos(start_angle)), abs(math.cos(end_angle)))

  # |cos(theta)| reaches 1 at theta = k*pi
  k0 = math.ceil(lo / math.pi)
  k1 = math.floor(hi / math.pi)
  if k0 <= k1:
    return 1.0
  return max_val


def _segment_tangent_component_bounds(
  start_x: float,
  start_y: float,
  seg: MotionSegment,
) -> tuple[float, float]:
  if seg.seg_type == SEG_TYPE_LINE:
    dx = seg.x - start_x
    dy = seg.y - start_y
    dist = math.hypot(dx, dy)
    if dist <= 1e-9:
      return (0.0, 0.0)
    return (abs(dx / dist), abs(dy / dist))

  if seg.seg_type == SEG_TYPE_CIRCLE:
    start = MotionSegment(seq=seg.seq - 1, x=start_x, y=start_y)
    center = circle_center_for_segment(start, seg)
    if center is not None:
      cx, cy = center
      r0 = math.hypot(start_x - cx, start_y - cy)
      r1 = math.hypot(seg.x - cx, seg.y - cy)
      if r0 > 1e-9 and r1 > 1e-9:
        a0 = math.atan2(start_y - cy, start_x - cx)
        a1 = math.atan2(seg.y - cy, seg.x - cx)
        sweep = arc_sweep_rad(a0, a1, seg.direction)
        if sweep is not None:
          # Tangent vector (up to sign) is (-sin(theta), cos(theta)),
          # so component maxima over sweep reduce to maxima of |sin| and |cos|.
          max_tx = _max_abs_sin_over_sweep(a0, sweep)
          max_ty = _max_abs_cos_over_sweep(a0, sweep)
          return (max_tx, max_ty)

  # Conservative fallback for unsupported/degenerate segment definitions.
  dx = seg.x - start_x
  dy = seg.y - start_y
  dist = math.hypot(dx, dy)
  if dist <= 1e-9:
    return (0.0, 0.0)
  return (abs(dx / dist), abs(dy / dist))


def cap_segments_speed_by_axis_velocity(
  segments: list[MotionSegment],
  v_x_max: float = DEFAULT_V_X_MAX,
  v_y_max: float = DEFAULT_V_Y_MAX,
  start_xy: Optional[tuple[float, float]] = None,
) -> list[MotionSegment]:
  if not segments:
    return segments
  if v_x_max <= 0.0 or v_y_max <= 0.0:
    raise ValueError("v_x_max and v_y_max must be > 0")
  if math.isinf(v_x_max) and math.isinf(v_y_max):
    return segments

  if start_xy is None:
    prev_x = float(segments[0].x)
    prev_y = float(segments[0].y)
    first_segment_start_unknown = True
  else:
    prev_x = float(start_xy[0])
    prev_y = float(start_xy[1])
    first_segment_start_unknown = False

  out: list[MotionSegment] = []
  for idx, seg in enumerate(segments):
    if idx == 0 and first_segment_start_unknown:
      # Without a known current position, the first segment direction is unknown.
      # Use a conservative cap that guarantees both component limits.
      speed_cap = min(v_x_max, v_y_max)
      max_tx = 1.0
      max_ty = 1.0
    else:
      max_tx, max_ty = _segment_tangent_component_bounds(prev_x, prev_y, seg)
      limit_x = float("inf") if max_tx <= 1e-9 else (v_x_max / max_tx)
      limit_y = float("inf") if max_ty <= 1e-9 else (v_y_max / max_ty)
      speed_cap = min(limit_x, limit_y)
    target_speed = min(float(seg.speed), speed_cap)

    if target_speed <= 0.0:
      raise ValueError(
        f"Computed non-positive speed for seq={seg.seq}. "
        f"Requested={seg.speed:.6f}, cap={speed_cap:.6f}, "
        f"v_x_max={v_x_max:.6f}, v_y_max={v_y_max:.6f}, "
        f"max_tx={max_tx:.6f}, max_ty={max_ty:.6f}"
      )

    out.append(replace(seg, speed=target_speed))
    prev_x = float(seg.x)
    prev_y = float(seg.y)

  return out


def check_segments_axis_velocities(
  segments: list[MotionSegment],
  speeds: list[float],
  v_x_max: float,
  v_y_max: float,
  start_xy: tuple[float, float],
) -> None:
  """Raise ValueError if any speed would produce an axis component exceeding its limit.

  Args:
    segments: Segment geometry (used to compute worst-case tangent components).
    speeds: Actual speed values to validate — e.g. read back from the PLC queue.
    v_x_max: Maximum permitted X-axis component velocity (mm/min).
    v_y_max: Maximum permitted Y-axis component velocity (mm/min).
    start_xy: Machine position at the start of the first segment.
  """
  if len(speeds) != len(segments):
    raise ValueError(
      f"speeds length {len(speeds)} does not match segments length {len(segments)}"
    )
  if v_x_max <= 0.0 or v_y_max <= 0.0:
    raise ValueError("v_x_max and v_y_max must be > 0")

  tolerance = 1e-6
  prev_x, prev_y = float(start_xy[0]), float(start_xy[1])
  for seg, speed in zip(segments, speeds):
    max_tx, max_ty = _segment_tangent_component_bounds(prev_x, prev_y, seg)
    v_x = speed * max_tx
    v_y = speed * max_ty
    if v_x > v_x_max + tolerance:
      raise ValueError(
        f"Segment seq={seg.seq}: X component {v_x:.4f} mm/min exceeds limit "
        f"{v_x_max:.4f} mm/min (speed={speed:.4f}, max_tx={max_tx:.6f})"
      )
    if v_y > v_y_max + tolerance:
      raise ValueError(
        f"Segment seq={seg.seq}: Y component {v_y:.4f} mm/min exceeds limit "
        f"{v_y_max:.4f} mm/min (speed={speed:.4f}, max_ty={max_ty:.6f})"
      )
    prev_x = float(seg.x)
    prev_y = float(seg.y)


def _segment_tangent_vector(
  start_x: float,
  start_y: float,
  seg: MotionSegment,
  at_end: bool,
) -> Optional[tuple[float, float]]:
  if seg.seg_type == SEG_TYPE_LINE:
    return _normalize_vector(seg.x - start_x, seg.y - start_y)

  if seg.seg_type == SEG_TYPE_CIRCLE:
    start = MotionSegment(seq=seg.seq - 1, x=start_x, y=start_y)
    center = circle_center_for_segment(start, seg)
    if center is not None:
      cx, cy = center
      point_x = seg.x if at_end else start_x
      point_y = seg.y if at_end else start_y
      radial_x = point_x - cx
      radial_y = point_y - cy
      direction = seg.direction
      if direction in (MCCM_DIR_2D_CCW, MCCM_DIR_2D_CCW_FULL):
        return _normalize_vector(-radial_y, radial_x)
      if direction in (MCCM_DIR_2D_CW, MCCM_DIR_2D_CW_FULL):
        return _normalize_vector(radial_y, -radial_x)

  return _normalize_vector(seg.x - start_x, seg.y - start_y)


def _merge_is_tangential(
  prev_start_x: float,
  prev_start_y: float,
  prev_seg: MotionSegment,
  next_seg: MotionSegment,
  tangency_angle_tolerance_deg: float,
) -> bool:
  prev_tangent = _segment_tangent_vector(prev_start_x, prev_start_y, prev_seg, at_end=True)
  next_tangent = _segment_tangent_vector(prev_seg.x, prev_seg.y, next_seg, at_end=False)
  if prev_tangent is None or next_tangent is None:
    return False

  dot = prev_tangent[0] * next_tangent[0] + prev_tangent[1] * next_tangent[1]
  dot = max(-1.0, min(1.0, dot))
  angle_deg = math.degrees(math.acos(dot))
  return angle_deg <= tangency_angle_tolerance_deg


def apply_merge_term_types(
  segments: list[MotionSegment],
  start_xy: Optional[tuple[float, float]] = None,
  tangential_term_type: int = 4,
  non_tangential_term_type: int = 0,
  final_term_type: Optional[int] = None,
  tangency_angle_tolerance_deg: float = DEFAULT_TANGENCY_ANGLE_TOLERANCE_DEG,
) -> list[MotionSegment]:
  if len(segments) <= 1:
    if final_term_type is None or not segments:
      return segments
    return [replace(segments[0], term_type=final_term_type)]

  out = list(segments)

  for i in range(len(out) - 1):
    if i == 0:
      if start_xy is None:
        is_tangent = False
      else:
        is_tangent = _merge_is_tangential(
          float(start_xy[0]),
          float(start_xy[1]),
          out[i],
          out[i + 1],
          tangency_angle_tolerance_deg,
        )
    else:
      is_tangent = _merge_is_tangential(
        out[i - 1].x,
        out[i - 1].y,
        out[i],
        out[i + 1],
        tangency_angle_tolerance_deg,
      )

    out[i] = replace(
      out[i],
      term_type=tangential_term_type if is_tangent else non_tangential_term_type,
    )

  if final_term_type is not None:
    out[-1] = replace(out[-1], term_type=final_term_type)

  return out


def estimate_max_curvature(segments: list[MotionSegment]) -> float:
  if len(segments) < 3:
    return 0.0

  kmax = 0.0
  for i in range(1, len(segments) - 1):
    x1, y1 = segments[i - 1].x, segments[i - 1].y
    x2, y2 = segments[i].x, segments[i].y
    x3, y3 = segments[i + 1].x, segments[i + 1].y
    a = math.hypot(x2 - x1, y2 - y1)
    b = math.hypot(x3 - x2, y3 - y2)
    c = math.hypot(x3 - x1, y3 - y1)
    if a <= 1e-9 or b <= 1e-9 or c <= 1e-9:
      continue

    area2 = abs((x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1))
    if area2 <= 1e-12:
      continue

    curvature = (2.0 * area2) / (a * b * c)
    if curvature > kmax:
      kmax = curvature

  return kmax


def tune_segments_for_constant_velocity(
  segments: list[MotionSegment],
  requested_min_segment_length: float,
  curvature_speed_safety: float,
  min_jerk_ratio: float,
  max_segment_factor: float,
) -> tuple[list[MotionSegment], float, float, float]:
  if not segments:
    return segments, requested_min_segment_length, 0.0, 0.0

  if not (0.1 <= curvature_speed_safety <= 1.0):
    raise ValueError("curvature_speed_safety must be in [0.1, 1.0]")
  if min_jerk_ratio < 0.0:
    raise ValueError("min_jerk_ratio must be >= 0")
  if max_segment_factor <= 1.0:
    raise ValueError("max_segment_factor must be > 1.0")

  base_speed = float(segments[0].speed)
  base_accel = max(1e-9, min(float(seg.accel) for seg in segments))
  base_decel = max(1e-9, min(float(seg.decel) for seg in segments))
  base_a = min(base_accel, base_decel)
  if has_circle_segments(segments):
    effective_min_length = requested_min_segment_length
    tuned = segments
    kmax = 0.0
    max_speed_for_curvature = float("inf")
    tuned_speed = base_speed
  else:
    required_min_length = (base_speed * base_speed) / (2.0 * base_a)
    effective_min_length = max(requested_min_segment_length, required_min_length)
    tuned = enforce_min_segment_length(segments, effective_min_length)
    tuned = enforce_max_segment_length(tuned, effective_min_length * max_segment_factor)

    kmax = estimate_max_curvature(tuned)
    if kmax > 0.0:
      max_speed_for_curvature = math.sqrt(base_a / kmax) * curvature_speed_safety
      tuned_speed = min(base_speed, max_speed_for_curvature)
    else:
      max_speed_for_curvature = float("inf")
      tuned_speed = base_speed

  tuned_segments: list[MotionSegment] = []
  for i, seg in enumerate(tuned):
    if min_jerk_ratio > 0.0:
      min_jerk = base_a * min_jerk_ratio
      jerk_accel = max(seg.jerk_accel, min_jerk)
      jerk_decel = max(seg.jerk_decel, min_jerk)
    else:
      jerk_accel = seg.jerk_accel
      jerk_decel = seg.jerk_decel
    tuned_segments.append(
      replace(
        seg,
        speed=tuned_speed,
        jerk_accel=jerk_accel,
        jerk_decel=jerk_decel,
      )
    )

  return tuned_segments, effective_min_length, max_speed_for_curvature, kmax


def build_segments(
  pattern: str,
  start_seq: int,
  term_type: int,
  lissajous_segments_count: int,
  min_segment_length: float,
  fibonacci_arc_count: int = DEFAULT_FIBONACCI_ARC_COUNT,
  fibonacci_x_min: float = DEFAULT_FIBONACCI_X_MIN,
  fibonacci_x_max: float = DEFAULT_FIBONACCI_X_MAX,
  fibonacci_y_min: float = DEFAULT_FIBONACCI_Y_MIN,
  fibonacci_y_max: float = DEFAULT_FIBONACCI_Y_MAX,
  fibonacci_direction: str = DEFAULT_FIBONACCI_DIRECTION,
  orbit_x_min: float = 1000.0,
  orbit_x_max: float = 6000.0,
  orbit_y_min: float = 0.0,
  orbit_y_max: float = 2500.0,
  orbit_revolutions: float = DEFAULT_ORBIT_REVOLUTIONS,
  orbit_points_per_revolution: int = DEFAULT_ORBIT_POINTS_PER_REVOLUTION,
  orbit_eccentricity: float = DEFAULT_ORBIT_ECCENTRICITY,
  orbit_precession_deg_per_revolution: float = DEFAULT_ORBIT_PRECESSION_DEG_PER_REVOLUTION,
  orbit_initial_apsis_deg: float = DEFAULT_ORBIT_INITIAL_APSIS_DEG,
  orbit_boundary_margin: float = DEFAULT_ORBIT_BOUNDARY_MARGIN,
  archimedean_x_min: float = 1000.0,
  archimedean_x_max: float = 6000.0,
  archimedean_y_min: float = 0.0,
  archimedean_y_max: float = 2500.0,
  archimedean_turns: float = DEFAULT_ARCHIMEDEAN_TURNS,
  archimedean_points_per_turn: int = DEFAULT_ARCHIMEDEAN_POINTS_PER_TURN,
  archimedean_initial_angle_deg: float = DEFAULT_ARCHIMEDEAN_INITIAL_ANGLE_DEG,
  archimedean_boundary_margin: float = DEFAULT_ARCHIMEDEAN_BOUNDARY_MARGIN,
  archimedean_direction: str = DEFAULT_ARCHIMEDEAN_DIRECTION,
  waypoint_points: Optional[list[tuple[float, float]]] = None,
  waypoint_min_arc_radius: float = DEFAULT_WAYPOINT_MIN_ARC_RADIUS,
  waypoint_order_mode: str = DEFAULT_WAYPOINT_ORDER_MODE,
  waypoint_start_xy: Optional[tuple[float, float]] = None,
  waypoint_planner_timeout_s: float = DEFAULT_WAYPOINT_PLANNER_TIMEOUT_S,
  waypoint_bounds: Optional[tuple[float, float, float, float]] = None,
  waypoint_allow_stops: bool = DEFAULT_WAYPOINT_ALLOW_STOPS,
) -> list[MotionSegment]:
  if min_segment_length < 0.0:
    raise ValueError("min_segment_length must be >= 0")

  if pattern == "lissajous":
    segments = lissajous_segments(
      start_seq=start_seq,
      tessellation_segments=lissajous_segments_count,
      term_type=term_type,
    )
  elif pattern == "square":
    segments = square_segments(start_seq=start_seq, term_type=term_type)
  elif pattern == "simple":
    segments = simple_two_segment_test(start_seq=start_seq, term_type=term_type)
  elif pattern == "tangent_mix":
    segments = tangent_line_arc_segments(start_seq=start_seq, term_type=term_type)
  elif pattern == "fibonacci_arcs":
    segments = fibonacci_spiral_arc_segments(
      start_seq=start_seq,
      term_type=term_type,
      arc_count=fibonacci_arc_count,
      x_min=fibonacci_x_min,
      x_max=fibonacci_x_max,
      y_min=fibonacci_y_min,
      y_max=fibonacci_y_max,
      direction=fibonacci_direction,
    )
  elif pattern == "apsidal_orbit":
    segments = apsidal_precessing_orbit_segments(
      start_seq=start_seq,
      term_type=term_type,
      x_min=orbit_x_min,
      x_max=orbit_x_max,
      y_min=orbit_y_min,
      y_max=orbit_y_max,
      revolutions=orbit_revolutions,
      points_per_revolution=orbit_points_per_revolution,
      eccentricity=orbit_eccentricity,
      precession_deg_per_revolution=orbit_precession_deg_per_revolution,
      initial_apsis_deg=orbit_initial_apsis_deg,
      boundary_margin=orbit_boundary_margin,
    )
  elif pattern == "archimedean_spiral":
    segments = archimedean_spiral_segments(
      start_seq=start_seq,
      term_type=term_type,
      x_min=archimedean_x_min,
      x_max=archimedean_x_max,
      y_min=archimedean_y_min,
      y_max=archimedean_y_max,
      turns=archimedean_turns,
      points_per_turn=archimedean_points_per_turn,
      initial_angle_deg=archimedean_initial_angle_deg,
      boundary_margin=archimedean_boundary_margin,
      direction=archimedean_direction,
    )
  elif pattern == "waypoint_path":
    segments = waypoint_path_segments(
      start_seq=start_seq,
      term_type=term_type,
      waypoints=waypoint_points,
      min_arc_radius=waypoint_min_arc_radius,
      waypoint_order_mode=waypoint_order_mode,
      start_xy=waypoint_start_xy,
      waypoint_planner_timeout_s=waypoint_planner_timeout_s,
      waypoint_bounds=waypoint_bounds,
      waypoint_allow_stops=waypoint_allow_stops,
    )
  else:
    raise ValueError(f"Unsupported pattern: {pattern}")

  if has_circle_segments(segments):
    return segments

  return enforce_min_segment_length(segments, min_segment_length=min_segment_length)


def print_pattern_summary(
  pattern: str,
  term_type: int,
  segments: list[MotionSegment],
  min_segment_length: float,
) -> None:
  xs = [seg.x for seg in segments]
  ys = [seg.y for seg in segments]
  lengths = segment_lengths(segments)
  min_len = min(lengths) if lengths else 0.0
  max_len = max(lengths) if lengths else 0.0
  avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0
  speeds = [seg.speed for seg in segments]
  min_speed = min(speeds) if speeds else 0.0
  max_speed = max(speeds) if speeds else 0.0
  accel = segments[0].accel if segments else 0.0
  jerk = segments[0].jerk_accel if segments else 0.0
  line_count = sum(1 for seg in segments if seg.seg_type == SEG_TYPE_LINE)
  circle_count = sum(1 for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE)
  term_counts: dict[int, int] = {}
  for seg in segments:
    term_counts[seg.term_type] = term_counts.get(seg.term_type, 0) + 1
  term_summary = ",".join(f"{tt}:{term_counts[tt]}" for tt in sorted(term_counts))
  kmax = estimate_max_curvature(segments)
  vmax_from_curvature = math.sqrt(accel / kmax) if (kmax > 0 and accel > 0) else float(
    "inf"
  )
  vmax_text = f"{vmax_from_curvature:.1f}" if math.isfinite(vmax_from_curvature) else "inf"
  print(
    f"{pattern} queue generated: "
    f"requested_term_type={term_type} "
    f"actual_term_types={term_summary} "
    f"min_segment_length={min_segment_length:.2f} "
    f"segments={len(segments)} "
    f"line/circle=({line_count}/{circle_count}) "
    f"x_range=({min(xs):.1f},{max(xs):.1f}) "
    f"y_range=({min(ys):.1f},{max(ys):.1f}) "
    f"segment_len[min/avg/max]=({min_len:.2f}/{avg_len:.2f}/{max_len:.2f}) "
    f"v[min/max]=({min_speed:.1f}/{max_speed:.1f}) a={accel:.1f} j={jerk:.1f} "
    f"kmax={kmax:.5f} vmax_from_a={vmax_text}"
  )


def write_segments_svg(
  segments: list[MotionSegment],
  output_path: str,
  title: str,
  position_seq: Optional[int] = None,
) -> None:
  if len(segments) < 2:
    raise ValueError("Need at least two segments to render SVG")

  xs = [seg.x for seg in segments]
  ys = [seg.y for seg in segments]
  min_x = min(xs)
  max_x = max(xs)
  min_y = min(ys)
  max_y = max(ys)

  width = 1200
  height = 900
  margin = 70.0
  plot_w = width - 2.0 * margin
  plot_h = height - 2.0 * margin

  span_x = max(max_x - min_x, 1e-9)
  span_y = max(max_y - min_y, 1e-9)
  scale = min(plot_w / span_x, plot_h / span_y)
  used_w = span_x * scale
  used_h = span_y * scale
  x_off = margin + (plot_w - used_w) * 0.5
  y_off = margin + (plot_h - used_h) * 0.5

  def to_svg(x: float, y: float) -> tuple[float, float]:
    px = x_off + (x - min_x) * scale
    py = y_off + used_h - (y - min_y) * scale
    return px, py

  seq_to_idx = {seg.seq: i for i, seg in enumerate(segments)}
  if position_seq is None:
    pos_idx = 0
  elif position_seq in seq_to_idx:
    pos_idx = seq_to_idx[position_seq]
  else:
    pos_idx = min(
      range(len(segments)),
      key=lambda i: abs(segments[i].seq - position_seq),
    )

  def rgb_hex(r: float, g: float, b: float) -> str:
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

  lines: list[str] = []
  lines.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
    f'viewBox="0 0 {width} {height}">'
  )
  lines.append('<rect width="100%" height="100%" fill="#0f172a"/>')
  lines.append(
    f'<rect x="{x_off:.2f}" y="{y_off:.2f}" width="{used_w:.2f}" height="{used_h:.2f}" '
    'fill="#111827" stroke="#334155" stroke-width="2"/>'
  )

  seg_count = len(segments) - 1
  denom = max(1, seg_count - 1)
  for i in range(seg_count):
    a = segments[i]
    b = segments[i + 1]
    x1, y1 = to_svg(a.x, a.y)
    x2, y2 = to_svg(b.x, b.y)
    t = i / denom
    r, g, bcol = colorsys.hsv_to_rgb((1.0 - t) * 0.65, 0.8, 0.95)
    color = rgb_hex(r, g, bcol)
    lines.append(
      f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
      f'stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>'
    )

  sx, sy = to_svg(segments[0].x, segments[0].y)
  ex, ey = to_svg(segments[-1].x, segments[-1].y)
  px, py = to_svg(segments[pos_idx].x, segments[pos_idx].y)

  lines.append(f'<circle cx="{sx:.2f}" cy="{sy:.2f}" r="7" fill="#22c55e"/>')
  lines.append(f'<circle cx="{ex:.2f}" cy="{ey:.2f}" r="7" fill="#ef4444"/>')
  lines.append(
    f'<circle cx="{px:.2f}" cy="{py:.2f}" r="9" fill="#f59e0b" stroke="#0b0f18" stroke-width="2"/>'
  )

  lines.append(
    f'<text x="{margin:.0f}" y="36" fill="#e5e7eb" '
    'font-family="Consolas, Menlo, monospace" font-size="24">'
    f"{title}</text>"
  )
  lines.append(
    f'<text x="{margin:.0f}" y="{height - 36}" fill="#cbd5e1" '
    'font-family="Consolas, Menlo, monospace" font-size="18">'
    f"Position seq={segments[pos_idx].seq} index={pos_idx}/{len(segments) - 1}</text>"
  )
  lines.append("</svg>")

  out = Path(output_path)
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text("\n".join(lines), encoding="utf-8")
