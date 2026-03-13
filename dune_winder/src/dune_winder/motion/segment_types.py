from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Optional


SEG_TYPE_LINE = 1
SEG_TYPE_CIRCLE = 2

CIRCLE_TYPE_VIA = 0
CIRCLE_TYPE_CENTER = 1
CIRCLE_TYPE_RADIUS = 2
CIRCLE_TYPE_CENTER_INCREMENTAL = 3

MCCM_DIR_2D_CW = 0
MCCM_DIR_2D_CCW = 1
MCCM_DIR_2D_CW_FULL = 2
MCCM_DIR_2D_CCW_FULL = 3

DEFAULT_TEST_TERM_TYPE = 4


@dataclass(frozen=True)
class MotionSegment:
  seq: int
  x: float
  y: float
  speed: float = 600.0
  accel: float = 1500.0
  decel: float = 1500.0
  jerk_accel: float = 100.0
  jerk_decel: float = 100.0
  term_type: int = DEFAULT_TEST_TERM_TYPE
  seg_type: int = SEG_TYPE_LINE
  circle_type: int = CIRCLE_TYPE_CENTER
  via_center_x: float = 0.0
  via_center_y: float = 0.0
  direction: int = MCCM_DIR_2D_CCW


def segment_kind(seg_type: int) -> str:
  if seg_type == SEG_TYPE_LINE:
    return "line"
  if seg_type == SEG_TYPE_CIRCLE:
    return "circle"
  return f"unknown({seg_type})"


def has_circle_segments(segments: Iterable[MotionSegment]) -> bool:
  return any(seg.seg_type == SEG_TYPE_CIRCLE for seg in segments)


def circle_center_for_segment(
  start: MotionSegment,
  seg: MotionSegment,
) -> Optional[tuple[float, float]]:
  if seg.circle_type == CIRCLE_TYPE_CENTER:
    return (seg.via_center_x, seg.via_center_y)
  if seg.circle_type == CIRCLE_TYPE_CENTER_INCREMENTAL:
    return (start.x + seg.via_center_x, start.y + seg.via_center_y)
  return None


def arc_sweep_rad(
  start_angle: float, end_angle: float, direction: int
) -> Optional[float]:
  tau = 2.0 * math.pi
  ccw = (end_angle - start_angle) % tau
  cw = (start_angle - end_angle) % tau

  if direction == MCCM_DIR_2D_CW:
    return -cw
  if direction == MCCM_DIR_2D_CCW:
    return ccw
  if direction == MCCM_DIR_2D_CW_FULL:
    return -(cw if cw > 1e-9 else tau)
  if direction == MCCM_DIR_2D_CCW_FULL:
    return ccw if ccw > 1e-9 else tau
  return None


def segment_path_length(start: MotionSegment, seg: MotionSegment) -> float:
  if seg.seg_type == SEG_TYPE_LINE:
    return math.hypot(seg.x - start.x, seg.y - start.y)

  if seg.seg_type != SEG_TYPE_CIRCLE:
    return math.hypot(seg.x - start.x, seg.y - start.y)

  center = circle_center_for_segment(start, seg)
  if center is None:
    return math.hypot(seg.x - start.x, seg.y - start.y)

  cx, cy = center
  r0 = math.hypot(start.x - cx, start.y - cy)
  r1 = math.hypot(seg.x - cx, seg.y - cy)
  if r0 <= 1e-9 or r1 <= 1e-9:
    return math.hypot(seg.x - start.x, seg.y - start.y)

  a0 = math.atan2(start.y - cy, start.x - cx)
  a1 = math.atan2(seg.y - cy, seg.x - cx)
  sweep = arc_sweep_rad(a0, a1, seg.direction)
  if sweep is None:
    return math.hypot(seg.x - start.x, seg.y - start.y)

  radius = 0.5 * (r0 + r1)
  return abs(radius * sweep)
