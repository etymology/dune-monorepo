from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dune_winder.machine.calibration.defaults import DefaultMachineCalibration
from dune_winder.machine.settings import Settings

from .segment_types import (
  MotionSegment,
  arc_sweep_rad,
  circle_center_for_segment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)


DEFAULT_TRANSFER_LEFT_MARGIN = 10.0
DEFAULT_TRANSFER_Y_THRESHOLD = 1000.0
DEFAULT_ARC_MAX_STEP_RAD = math.radians(3.0)
DEFAULT_ARC_MAX_CHORD = 5.0


@dataclass(frozen=True)
class MotionSafetyLimits:
  limit_left: float
  limit_right: float
  limit_bottom: float
  limit_top: float
  transfer_left: float
  transfer_right: float = 0.0
  transfer_left_margin: float = DEFAULT_TRANSFER_LEFT_MARGIN
  transfer_y_threshold: float = DEFAULT_TRANSFER_Y_THRESHOLD
  headward_pivot_x: float = 150.0
  headward_pivot_y: float = 1400.0
  headward_pivot_x_tolerance: float = 150.0
  headward_pivot_y_tolerance: float = 300.0


def _calibration_float(calibration, key: str, default: float) -> float:
  try:
    value = calibration.get(key)
  except Exception:
    value = None

  if value is None:
    value = default

  return float(value)


def motion_safety_limits_from_calibration(calibration) -> MotionSafetyLimits:
  return MotionSafetyLimits(
    limit_left=_calibration_float(calibration, "limitLeft", 0.0),
    limit_right=_calibration_float(calibration, "limitRight", 0.0),
    limit_bottom=_calibration_float(calibration, "limitBottom", 0.0),
    limit_top=_calibration_float(calibration, "limitTop", 0.0),
    transfer_left=_calibration_float(calibration, "transferLeft", 0.0),
    transfer_right=_calibration_float(calibration, "transferRight", 0.0),
    transfer_left_margin=_calibration_float(
      calibration,
      "transferLeftMargin",
      DEFAULT_TRANSFER_LEFT_MARGIN,
    ),
    transfer_y_threshold=_calibration_float(
      calibration,
      "transferYThreshold",
      DEFAULT_TRANSFER_Y_THRESHOLD,
    ),
    headward_pivot_x=_calibration_float(calibration, "headwardPivotX", 150.0),
    headward_pivot_y=_calibration_float(calibration, "headwardPivotY", 1400.0),
    headward_pivot_x_tolerance=_calibration_float(
      calibration, "headwardPivotXTolerance", 150.0
    ),
    headward_pivot_y_tolerance=_calibration_float(
      calibration, "headwardPivotYTolerance", 300.0
    ),
  )


def load_motion_safety_limits(calibration_path: Optional[str] = None) -> MotionSafetyLimits:
  if calibration_path:
    path = Path(calibration_path)
    if path.is_dir():
      output_path = str(path)
      output_name = Settings.MACHINE_CALIBRATION_FILE
    else:
      output_path = str(path.parent)
      output_name = path.name
  else:
    output_path = Settings.MACHINE_CALIBRATION_PATH
    output_name = Settings.MACHINE_CALIBRATION_FILE

  calibration = DefaultMachineCalibration(output_path, output_name)
  return motion_safety_limits_from_calibration(calibration)


def _line_intersects_rectangle(
  x1: float,
  y1: float,
  x2: float,
  y2: float,
  rect_x_center: float,
  rect_x_tolerance: float,
  rect_y_center: float,
  rect_y_tolerance: float,
) -> bool:
  x_min = rect_x_center - rect_x_tolerance
  x_max = rect_x_center + rect_x_tolerance
  y_min = rect_y_center - rect_y_tolerance
  y_max = rect_y_center + rect_y_tolerance

  def _line_intersect(p1, p2, q1, q2):
    def _ccw(a, b, c):
      return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    return _ccw(p1, q1, q2) != _ccw(p2, q1, q2) and _ccw(p1, p2, q1) != _ccw(p1, p2, q2)

  edges = [
    ((x_min, y_min), (x_max, y_min)),
    ((x_max, y_min), (x_max, y_max)),
    ((x_max, y_max), (x_min, y_max)),
    ((x_min, y_max), (x_min, y_min)),
  ]

  for edge in edges:
    if _line_intersect((x1, y1), (x2, y2), edge[0], edge[1]):
      return True

  return False


def _point_in_headward_pivot_keepout(x: float, y: float, limits: MotionSafetyLimits) -> bool:
  return (
    x < limits.headward_pivot_x + limits.headward_pivot_x_tolerance
    and x > limits.headward_pivot_x - limits.headward_pivot_x_tolerance
    and y < limits.headward_pivot_y + limits.headward_pivot_y_tolerance
    and y > limits.headward_pivot_y - limits.headward_pivot_y_tolerance
  )


def _validate_point(x: float, y: float, limits: MotionSafetyLimits, seq: int, label: str) -> None:
  if x < limits.limit_left or x > limits.limit_right:
    raise ValueError(
      f"{label} seq={seq} has X={x:.3f} outside "
      f"[{limits.limit_left:.3f}, {limits.limit_right:.3f}]"
    )

  if y < limits.limit_bottom or y > limits.limit_top:
    raise ValueError(
      f"{label} seq={seq} has Y={y:.3f} outside "
      f"[{limits.limit_bottom:.3f}, {limits.limit_top:.3f}]"
    )

  if (
    x < limits.transfer_left - limits.transfer_left_margin
    and y > limits.transfer_y_threshold
  ):
    raise ValueError(
      f"{label} seq={seq} enters forbidden transfer region "
      f"(X={x:.3f}, Y={y:.3f})"
    )

  if _point_in_headward_pivot_keepout(x, y, limits):
    raise ValueError(
      f"{label} seq={seq} enters winding-head pivot keepout "
      f"(X={x:.3f}, Y={y:.3f})"
    )


def _validate_line_step(
  start_x: float,
  start_y: float,
  target_x: float,
  target_y: float,
  limits: MotionSafetyLimits,
  seq: int,
  label: str,
) -> None:
  _validate_point(target_x, target_y, limits, seq, label)
  if _line_intersects_rectangle(
    start_x,
    start_y,
    target_x,
    target_y,
    limits.headward_pivot_x,
    limits.headward_pivot_x_tolerance,
    limits.headward_pivot_y,
    limits.headward_pivot_y_tolerance,
  ):
    raise ValueError(
      f"{label} seq={seq} intersects winding-head pivot keepout "
      f"from ({start_x:.3f}, {start_y:.3f}) to ({target_x:.3f}, {target_y:.3f})"
    )


def _validate_arc_step(
  start_x: float,
  start_y: float,
  seg: MotionSegment,
  limits: MotionSafetyLimits,
) -> None:
  start = MotionSegment(seq=seg.seq - 1, x=start_x, y=start_y)
  center = circle_center_for_segment(start, seg)
  if center is None:
    _validate_line_step(start_x, start_y, seg.x, seg.y, limits, seg.seq, "arc-fallback")
    return

  cx, cy = center
  r0 = math.hypot(start_x - cx, start_y - cy)
  r1 = math.hypot(seg.x - cx, seg.y - cy)
  if r0 <= 1e-9 or r1 <= 1e-9:
    _validate_line_step(start_x, start_y, seg.x, seg.y, limits, seg.seq, "arc-fallback")
    return

  a0 = math.atan2(start_y - cy, start_x - cx)
  a1 = math.atan2(seg.y - cy, seg.x - cx)
  sweep = arc_sweep_rad(a0, a1, seg.direction)
  if sweep is None:
    _validate_line_step(start_x, start_y, seg.x, seg.y, limits, seg.seq, "arc-fallback")
    return

  radius = 0.5 * (r0 + r1)
  arc_length = abs(radius * sweep)
  steps = max(
    1,
    int(math.ceil(abs(sweep) / DEFAULT_ARC_MAX_STEP_RAD)),
    int(math.ceil(arc_length / DEFAULT_ARC_MAX_CHORD)),
  )

  prev_x = start_x
  prev_y = start_y
  for step in range(1, steps + 1):
    t = step / steps
    angle = a0 + sweep * t
    x = cx + radius * math.cos(angle)
    y = cy + radius * math.sin(angle)
    _validate_line_step(prev_x, prev_y, x, y, limits, seg.seq, "arc")
    prev_x = x
    prev_y = y


def validate_segments_within_safety_limits(
  segments: list[MotionSegment],
  limits: MotionSafetyLimits,
  start_xy: Optional[tuple[float, float]] = None,
) -> None:
  if not segments:
    return

  if start_xy is None:
    prev_x = float(segments[0].x)
    prev_y = float(segments[0].y)
  else:
    prev_x = float(start_xy[0])
    prev_y = float(start_xy[1])
    _validate_point(prev_x, prev_y, limits, segments[0].seq - 1, "start")

  for seg in segments:
    if seg.seg_type == SEG_TYPE_CIRCLE:
      _validate_arc_step(prev_x, prev_y, seg, limits)
    elif seg.seg_type == SEG_TYPE_LINE:
      _validate_line_step(prev_x, prev_y, seg.x, seg.y, limits, seg.seq, "line")
    else:
      _validate_line_step(prev_x, prev_y, seg.x, seg.y, limits, seg.seq, "segment")

    prev_x = float(seg.x)
    prev_y = float(seg.y)


def validate_xy_move_within_safety_limits(
  start_xy: tuple[float, float],
  target_xy: tuple[float, float],
  limits: MotionSafetyLimits,
  *,
  seq: int = 0,
  label: str = "line",
) -> None:
  _validate_line_step(
    float(start_xy[0]),
    float(start_xy[1]),
    float(target_xy[0]),
    float(target_xy[1]),
    limits,
    int(seq),
    str(label),
  )
