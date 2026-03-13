from __future__ import annotations

import colorsys
import math
from dataclasses import replace
from pathlib import Path
from typing import Optional

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


def validate_term_type(term_type: int) -> None:
  if term_type not in TESTABLE_TERM_TYPES:
    allowed = ", ".join(str(t) for t in TESTABLE_TERM_TYPES)
    raise ValueError(f"term_type must be one of: {allowed}")


def _normalize_xy(x: float, y: float) -> tuple[float, float]:
  mag = math.hypot(x, y)
  if mag <= 1e-9:
    return (1.0, 0.0)
  return (x / mag, y / mag)


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
    interior = i < len(tuned) - 1
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
        term_type=4 if interior else 1,
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
  speed = segments[0].speed if segments else 0.0
  accel = segments[0].accel if segments else 0.0
  jerk = segments[0].jerk_accel if segments else 0.0
  line_count = sum(1 for seg in segments if seg.seg_type == SEG_TYPE_LINE)
  circle_count = sum(1 for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE)
  kmax = estimate_max_curvature(segments)
  vmax_from_curvature = math.sqrt(accel / kmax) if (kmax > 0 and accel > 0) else float(
    "inf"
  )
  vmax_text = f"{vmax_from_curvature:.1f}" if math.isfinite(vmax_from_curvature) else "inf"
  print(
    f"{pattern} queue generated: "
    f"term_type={term_type} "
    f"min_segment_length={min_segment_length:.2f} "
    f"segments={len(segments)} "
    f"line/circle=({line_count}/{circle_count}) "
    f"x_range=({min(xs):.1f},{max(xs):.1f}) "
    f"y_range=({min(ys):.1f},{max(ys):.1f}) "
    f"segment_len[min/avg/max]=({min_len:.2f}/{avg_len:.2f}/{max_len:.2f}) "
    f"v={speed:.1f} a={accel:.1f} j={jerk:.1f} "
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
