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

@dataclass(frozen=True)
class QueuedMotionCollisionState:
  z_actual_position: float = 0.0
  frame_lock_head_top: bool = False
  frame_lock_head_mid: bool = False
  frame_lock_head_btm: bool = False
  frame_lock_foot_top: bool = False
  frame_lock_foot_mid: bool = False
  frame_lock_foot_btm: bool = False


@dataclass(frozen=True)
class MotionSafetyLimits:
  limit_left: float
  limit_right: float
  limit_bottom: float
  limit_top: float
  transfer_left: float
  transfer_right: float = 0.0
  transfer_left_margin: float = 10.0
  transfer_y_threshold: float = 1000.0
  headward_pivot_x: float = 150.0
  headward_pivot_y: float = 1400.0
  headward_pivot_x_tolerance: float = 150.0
  headward_pivot_y_tolerance: float = 300.0
  queued_motion_z_collision_threshold: float = 0.0
  arc_max_step_rad: float = math.radians(3.0)
  arc_max_chord: float = 5.0
  apa_collision_bottom_y: float = 50.0
  apa_collision_top_y: float = 2250.0
  transfer_zone_head_min_x: float = 400.0
  transfer_zone_head_max_x: float = 500.0
  transfer_zone_foot_min_x: float = 7100.0
  transfer_zone_foot_max_x: float = 7200.0
  support_collision_bottom_min_y: float = 80.0
  support_collision_bottom_max_y: float = 450.0
  support_collision_middle_min_y: float = 1050.0
  support_collision_middle_max_y: float = 1550.0
  support_collision_top_min_y: float = 2200.0
  support_collision_top_max_y: float = 2650.0
  geometry_epsilon: float = 1e-9


def _calibration_float(
  calibration,
  key: str,
  default: float,
  *,
  persist_missing: bool = False,
) -> float:
  try:
    value = calibration.get(key)
  except Exception:
    value = None

  if value is None:
    value = default
    if persist_missing and hasattr(calibration, "set"):
      try:
        calibration.set(key, value)
      except Exception:
        pass

  return float(value)


def motion_safety_limits_from_calibration(calibration) -> MotionSafetyLimits:
  def calibration_geometry_float(key: str, default: float) -> float:
    return _calibration_float(calibration, key, default, persist_missing=True)

  z_extended_threshold = _calibration_float(
    calibration,
    "queuedMotionZCollisionThreshold",
    _calibration_float(calibration, "zBack", 0.0),
    persist_missing=True,
  )
  return MotionSafetyLimits(
    limit_left=_calibration_float(calibration, "limitLeft", 0.0),
    limit_right=_calibration_float(calibration, "limitRight", 0.0),
    limit_bottom=_calibration_float(calibration, "limitBottom", 0.0),
    limit_top=_calibration_float(calibration, "limitTop", 0.0),
    transfer_left=_calibration_float(calibration, "transferLeft", 0.0),
    transfer_right=_calibration_float(calibration, "transferRight", 0.0),
    transfer_left_margin=calibration_geometry_float("transferLeftMargin", 10.0),
    transfer_y_threshold=calibration_geometry_float("transferYThreshold", 1000.0),
    headward_pivot_x=_calibration_float(calibration, "headwardPivotX", 150.0),
    headward_pivot_y=_calibration_float(calibration, "headwardPivotY", 1400.0),
    headward_pivot_x_tolerance=_calibration_float(
      calibration, "headwardPivotXTolerance", 150.0
    ),
    headward_pivot_y_tolerance=_calibration_float(
      calibration, "headwardPivotYTolerance", 300.0
    ),
    queued_motion_z_collision_threshold=z_extended_threshold,
    arc_max_step_rad=calibration_geometry_float("arcMaxStepRad", math.radians(3.0)),
    arc_max_chord=calibration_geometry_float("arcMaxChord", 5.0),
    apa_collision_bottom_y=calibration_geometry_float("apaCollisionBottomY", 50.0),
    apa_collision_top_y=calibration_geometry_float("apaCollisionTopY", 2250.0),
    transfer_zone_head_min_x=calibration_geometry_float("transferZoneHeadMinX", 400.0),
    transfer_zone_head_max_x=calibration_geometry_float("transferZoneHeadMaxX", 500.0),
    transfer_zone_foot_min_x=calibration_geometry_float("transferZoneFootMinX", 7100.0),
    transfer_zone_foot_max_x=calibration_geometry_float("transferZoneFootMaxX", 7200.0),
    support_collision_bottom_min_y=calibration_geometry_float(
      "supportCollisionBottomMinY", 80.0
    ),
    support_collision_bottom_max_y=calibration_geometry_float(
      "supportCollisionBottomMaxY", 450.0
    ),
    support_collision_middle_min_y=calibration_geometry_float(
      "supportCollisionMiddleMinY", 1050.0
    ),
    support_collision_middle_max_y=calibration_geometry_float(
      "supportCollisionMiddleMaxY", 1550.0
    ),
    support_collision_top_min_y=calibration_geometry_float(
      "supportCollisionTopMinY", 2200.0
    ),
    support_collision_top_max_y=calibration_geometry_float(
      "supportCollisionTopMaxY", 2650.0
    ),
    geometry_epsilon=calibration_geometry_float("geometryEpsilon", 1e-9),
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


def _orientation(
  a: tuple[float, float],
  b: tuple[float, float],
  c: tuple[float, float],
  eps: float,
) -> int:
  value = ((b[1] - a[1]) * (c[0] - b[0])) - ((b[0] - a[0]) * (c[1] - b[1]))
  if abs(value) <= eps:
    return 0
  return 1 if value > 0.0 else 2


def _point_on_segment(
  a: tuple[float, float],
  b: tuple[float, float],
  c: tuple[float, float],
  eps: float,
) -> bool:
  return (
    min(a[0], c[0]) - eps <= b[0] <= max(a[0], c[0]) + eps
    and min(a[1], c[1]) - eps <= b[1] <= max(a[1], c[1]) + eps
  )


def _segments_intersect(
  p1: tuple[float, float],
  q1: tuple[float, float],
  p2: tuple[float, float],
  q2: tuple[float, float],
  eps: float,
) -> bool:
  o1 = _orientation(p1, q1, p2, eps)
  o2 = _orientation(p1, q1, q2, eps)
  o3 = _orientation(p2, q2, p1, eps)
  o4 = _orientation(p2, q2, q1, eps)

  if o1 != o2 and o3 != o4:
    return True

  if o1 == 0 and _point_on_segment(p1, p2, q1, eps):
    return True
  if o2 == 0 and _point_on_segment(p1, q2, q1, eps):
    return True
  if o3 == 0 and _point_on_segment(p2, p1, q2, eps):
    return True
  if o4 == 0 and _point_on_segment(p2, q1, q2, eps):
    return True

  return False


def _point_in_box(
  x: float,
  y: float,
  x_min: float,
  x_max: float,
  y_min: float,
  y_max: float,
  eps: float,
) -> bool:
  return (
    x_min - eps <= x <= x_max + eps
    and y_min - eps <= y <= y_max + eps
  )


def _line_intersects_box(
  x1: float,
  y1: float,
  x2: float,
  y2: float,
  x_min: float,
  x_max: float,
  y_min: float,
  y_max: float,
  eps: float,
) -> bool:
  if _point_in_box(x1, y1, x_min, x_max, y_min, y_max, eps):
    return True
  if _point_in_box(x2, y2, x_min, x_max, y_min, y_max, eps):
    return True

  edges = [
    ((x_min, y_min), (x_max, y_min)),
    ((x_max, y_min), (x_max, y_max)),
    ((x_max, y_max), (x_min, y_max)),
    ((x_min, y_max), (x_min, y_min)),
  ]

  for edge in edges:
    if _segments_intersect((x1, y1), (x2, y2), edge[0], edge[1], eps):
      return True

  return False


def _z_collision_is_active(
  limits: MotionSafetyLimits,
  collision_state: Optional[QueuedMotionCollisionState],
) -> bool:
  if collision_state is None:
    return False
  return (
    float(collision_state.z_actual_position)
    > float(limits.queued_motion_z_collision_threshold)
  )


def _queued_motion_forbidden_boxes(
  limits: MotionSafetyLimits,
  collision_state: Optional[QueuedMotionCollisionState],
) -> list[tuple[str, float, float, float, float]]:
  if not _z_collision_is_active(limits, collision_state):
    return []

  boxes = []
  if limits.limit_left < limits.transfer_zone_head_min_x:
    boxes.append(
      (
        "APA collision zone",
        float(limits.limit_left),
        limits.transfer_zone_head_min_x - limits.geometry_epsilon,
        limits.apa_collision_bottom_y,
        limits.apa_collision_top_y,
      )
    )
  boxes.append(
    (
      "APA collision zone",
      limits.transfer_zone_head_max_x + limits.geometry_epsilon,
      limits.transfer_zone_foot_min_x - limits.geometry_epsilon,
      limits.apa_collision_bottom_y,
      limits.apa_collision_top_y,
    )
  )
  if limits.transfer_zone_foot_max_x < limits.limit_right:
    boxes.append(
      (
        "APA collision zone",
        limits.transfer_zone_foot_max_x + limits.geometry_epsilon,
        float(limits.limit_right),
        limits.apa_collision_bottom_y,
        limits.apa_collision_top_y,
      )
    )

  if collision_state is None:
    return boxes

  support_boxes = (
    (
      "head bottom frame-support keepout",
      collision_state.frame_lock_head_btm,
      limits.transfer_zone_head_min_x,
      limits.transfer_zone_head_max_x,
      limits.support_collision_bottom_min_y,
      limits.support_collision_bottom_max_y,
    ),
    (
      "head middle frame-support keepout",
      collision_state.frame_lock_head_mid,
      limits.transfer_zone_head_min_x,
      limits.transfer_zone_head_max_x,
      limits.support_collision_middle_min_y,
      limits.support_collision_middle_max_y,
    ),
    (
      "head top frame-support keepout",
      collision_state.frame_lock_head_top,
      limits.transfer_zone_head_min_x,
      limits.transfer_zone_head_max_x,
      limits.support_collision_top_min_y,
      limits.support_collision_top_max_y,
    ),
    (
      "foot bottom frame-support keepout",
      collision_state.frame_lock_foot_btm,
      limits.transfer_zone_foot_min_x,
      limits.transfer_zone_foot_max_x,
      limits.support_collision_bottom_min_y,
      limits.support_collision_bottom_max_y,
    ),
    (
      "foot middle frame-support keepout",
      collision_state.frame_lock_foot_mid,
      limits.transfer_zone_foot_min_x,
      limits.transfer_zone_foot_max_x,
      limits.support_collision_middle_min_y,
      limits.support_collision_middle_max_y,
    ),
    (
      "foot top frame-support keepout",
      collision_state.frame_lock_foot_top,
      limits.transfer_zone_foot_min_x,
      limits.transfer_zone_foot_max_x,
      limits.support_collision_top_min_y,
      limits.support_collision_top_max_y,
    ),
  )

  for label, enabled, x_min, x_max, y_min, y_max in support_boxes:
    if enabled:
      boxes.append((label, x_min, x_max, y_min, y_max))

  return boxes


def _validate_queued_motion_point(
  x: float,
  y: float,
  limits: MotionSafetyLimits,
  collision_state: Optional[QueuedMotionCollisionState],
  seq: int,
  label: str,
) -> None:
  for region_label, x_min, x_max, y_min, y_max in _queued_motion_forbidden_boxes(
    limits, collision_state
  ):
    if _point_in_box(x, y, x_min, x_max, y_min, y_max, limits.geometry_epsilon):
      raise ValueError(
        f"{label} seq={seq} enters {region_label} with Z extended "
        f"(X={x:.3f}, Y={y:.3f})"
      )


def _validate_queued_motion_line(
  start_x: float,
  start_y: float,
  target_x: float,
  target_y: float,
  limits: MotionSafetyLimits,
  collision_state: Optional[QueuedMotionCollisionState],
  seq: int,
  label: str,
) -> None:
  for region_label, x_min, x_max, y_min, y_max in _queued_motion_forbidden_boxes(
    limits, collision_state
  ):
    if _line_intersects_box(
      start_x,
      start_y,
      target_x,
      target_y,
      x_min,
      x_max,
      y_min,
      y_max,
      limits.geometry_epsilon,
    ):
      raise ValueError(
        f"{label} seq={seq} intersects {region_label} with Z extended "
        f"from ({start_x:.3f}, {start_y:.3f}) to ({target_x:.3f}, {target_y:.3f})"
      )


def _point_in_headward_pivot_keepout(x: float, y: float, limits: MotionSafetyLimits) -> bool:
  return (
    x < limits.headward_pivot_x + limits.headward_pivot_x_tolerance
    and x > limits.headward_pivot_x - limits.headward_pivot_x_tolerance
    and y < limits.headward_pivot_y + limits.headward_pivot_y_tolerance
    and y > limits.headward_pivot_y - limits.headward_pivot_y_tolerance
  )


def _validate_point(
  x: float,
  y: float,
  limits: MotionSafetyLimits,
  seq: int,
  label: str,
  collision_state: Optional[QueuedMotionCollisionState] = None,
) -> None:
  if x < limits.limit_left-limits.geometry_epsilon or x > limits.limit_right+limits.geometry_epsilon:
    raise ValueError(
      f"{label} seq={seq} has X={x:.3f} outside "
      f"[{limits.limit_left:.3f}, {limits.limit_right:.3f}]"
    )

  if y < limits.limit_bottom-limits.geometry_epsilon or y > limits.limit_top+limits.geometry_epsilon:
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

  _validate_queued_motion_point(x, y, limits, collision_state, seq, label)


def _validate_line_step(
  start_x: float,
  start_y: float,
  target_x: float,
  target_y: float,
  limits: MotionSafetyLimits,
  seq: int,
  label: str,
  collision_state: Optional[QueuedMotionCollisionState] = None,
) -> None:
  _validate_point(target_x, target_y, limits, seq, label, collision_state)
  if _line_intersects_box(
    start_x,
    start_y,
    target_x,
    target_y,
    limits.headward_pivot_x - limits.headward_pivot_x_tolerance,
    limits.headward_pivot_x + limits.headward_pivot_x_tolerance,
    limits.headward_pivot_y - limits.headward_pivot_y_tolerance,
    limits.headward_pivot_y + limits.headward_pivot_y_tolerance,
    limits.geometry_epsilon,
  ):
    raise ValueError(
      f"{label} seq={seq} intersects winding-head pivot keepout "
      f"from ({start_x:.3f}, {start_y:.3f}) to ({target_x:.3f}, {target_y:.3f})"
    )
  _validate_queued_motion_line(
    start_x,
    start_y,
    target_x,
    target_y,
    limits,
    collision_state,
    seq,
    label,
  )


def _validate_arc_step(
  start_x: float,
  start_y: float,
  seg: MotionSegment,
  limits: MotionSafetyLimits,
  collision_state: Optional[QueuedMotionCollisionState] = None,
) -> None:
  start = MotionSegment(seq=seg.seq - 1, x=start_x, y=start_y)
  center = circle_center_for_segment(start, seg)
  if center is None:
    _validate_line_step(
      start_x,
      start_y,
      seg.x,
      seg.y,
      limits,
      seg.seq,
      "arc-fallback",
      collision_state,
    )
    return

  cx, cy = center
  r0 = math.hypot(start_x - cx, start_y - cy)
  r1 = math.hypot(seg.x - cx, seg.y - cy)
  if r0 <= 1e-9 or r1 <= 1e-9:
    _validate_line_step(
      start_x,
      start_y,
      seg.x,
      seg.y,
      limits,
      seg.seq,
      "arc-fallback",
      collision_state,
    )
    return

  a0 = math.atan2(start_y - cy, start_x - cx)
  a1 = math.atan2(seg.y - cy, seg.x - cx)
  sweep = arc_sweep_rad(a0, a1, seg.direction)
  if sweep is None:
    _validate_line_step(
      start_x,
      start_y,
      seg.x,
      seg.y,
      limits,
      seg.seq,
      "arc-fallback",
      collision_state,
    )
    return

  radius = 0.5 * (r0 + r1)
  arc_length = abs(radius * sweep)
  step_radians = max(abs(limits.arc_max_step_rad), limits.geometry_epsilon)
  chord_length = max(abs(limits.arc_max_chord), limits.geometry_epsilon)
  steps = max(
    1,
    int(math.ceil(abs(sweep) / step_radians)),
    int(math.ceil(arc_length / chord_length)),
  )

  prev_x = start_x
  prev_y = start_y
  for step in range(1, steps + 1):
    t = step / steps
    angle = a0 + sweep * t
    x = cx + radius * math.cos(angle)
    y = cy + radius * math.sin(angle)
    _validate_line_step(prev_x, prev_y, x, y, limits, seg.seq, "arc", collision_state)
    prev_x = x
    prev_y = y


def validate_segments_within_safety_limits(
  segments: list[MotionSegment],
  limits: MotionSafetyLimits,
  start_xy: Optional[tuple[float, float]] = None,
  queued_motion_collision_state: Optional[QueuedMotionCollisionState] = None,
) -> None:
  if not segments:
    return

  if start_xy is None:
    prev_x = float(segments[0].x)
    prev_y = float(segments[0].y)
  else:
    prev_x = float(start_xy[0])
    prev_y = float(start_xy[1])
    _validate_point(
      prev_x,
      prev_y,
      limits,
      segments[0].seq - 1,
      "start",
      queued_motion_collision_state,
    )

  for seg in segments:
    if seg.seg_type == SEG_TYPE_CIRCLE:
      _validate_arc_step(prev_x, prev_y, seg, limits, queued_motion_collision_state)
    elif seg.seg_type == SEG_TYPE_LINE:
      _validate_line_step(
        prev_x,
        prev_y,
        seg.x,
        seg.y,
        limits,
        seg.seq,
        "line",
        queued_motion_collision_state,
      )
    else:
      _validate_line_step(
        prev_x,
        prev_y,
        seg.x,
        seg.y,
        limits,
        seg.seq,
        "segment",
        queued_motion_collision_state,
      )

    prev_x = float(seg.x)
    prev_y = float(seg.y)


def validate_xy_move_within_safety_limits(
  start_xy: tuple[float, float],
  target_xy: tuple[float, float],
  limits: MotionSafetyLimits,
  *,
  seq: int = 0,
  label: str = "line",
  queued_motion_collision_state: Optional[QueuedMotionCollisionState] = None,
) -> None:
  _validate_line_step(
    float(start_xy[0]),
    float(start_xy[1]),
    float(target_xy[0]),
    float(target_xy[1]),
    limits,
    int(seq),
    str(label),
    queued_motion_collision_state,
  )
