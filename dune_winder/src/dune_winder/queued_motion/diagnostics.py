from __future__ import annotations

import math
from typing import Optional

from .segment_types import (
  MotionSegment,
  SEG_TYPE_CIRCLE,
  circle_center_for_segment,
  segment_kind,
  segment_path_length,
)


_DIRECTION_LABELS = {
  0: "CW",
  1: "CCW",
  2: "CW_FULL",
  3: "CCW_FULL",
}


def _point_dict(x: float, y: float) -> dict[str, float]:
  return {
    "x": float(x),
    "y": float(y),
  }


def _segment_circle_diagnostics(
  start_xy: tuple[float, float],
  seg: MotionSegment,
) -> Optional[dict[str, object]]:
  if seg.seg_type != SEG_TYPE_CIRCLE:
    return None

  start = MotionSegment(seq=seg.seq - 1, x=float(start_xy[0]), y=float(start_xy[1]))
  center = circle_center_for_segment(start, seg)
  if center is None:
    return None

  radius = math.hypot(float(start_xy[0]) - center[0], float(start_xy[1]) - center[1])
  return {
    "circleType": int(seg.circle_type),
    "center": _point_dict(center[0], center[1]),
    "radius": float(radius),
    "direction": int(seg.direction),
    "directionLabel": _DIRECTION_LABELS.get(int(seg.direction), str(int(seg.direction))),
  }


def serialize_segment_diagnostics(
  *,
  start_xy: tuple[float, float],
  segments: list[MotionSegment],
) -> tuple[list[dict[str, object]], dict[str, object]]:
  diagnostics: list[dict[str, object]] = []
  total_path_length = 0.0
  line_count = 0
  circle_count = 0
  cursor = (float(start_xy[0]), float(start_xy[1]))

  for index, seg in enumerate(segments):
    path_length = float(
      segment_path_length(MotionSegment(seq=seg.seq - 1, x=cursor[0], y=cursor[1]), seg)
    )
    total_path_length += path_length
    if seg.seg_type == SEG_TYPE_CIRCLE:
      circle_count += 1
    else:
      line_count += 1

    diagnostics.append(
      {
        "index": int(index),
        "seq": int(seg.seq),
        "kind": segment_kind(int(seg.seg_type)),
        "start": _point_dict(cursor[0], cursor[1]),
        "end": _point_dict(seg.x, seg.y),
        "pathLength": path_length,
        "speed": float(seg.speed),
        "accel": float(seg.accel),
        "decel": float(seg.decel),
        "jerkAccel": float(seg.jerk_accel),
        "jerkDecel": float(seg.jerk_decel),
        "termType": int(seg.term_type),
        "segType": int(seg.seg_type),
        "circle": _segment_circle_diagnostics(cursor, seg),
      }
    )
    cursor = (float(seg.x), float(seg.y))

  summary = {
    "segmentCount": int(len(segments)),
    "lineCount": int(line_count),
    "circleCount": int(circle_count),
    "totalPathLength": float(total_path_length),
  }
  return diagnostics, summary
