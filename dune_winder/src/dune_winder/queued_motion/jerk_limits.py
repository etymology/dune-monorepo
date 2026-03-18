from __future__ import annotations

import math


DEFAULT_QUEUED_MOTION_JERK_PERCENT = 100.0
MAX_QUEUED_MOTION_JERK_PERCENT = 100.0


def normalize_queued_motion_jerk_percent(value, default: float = DEFAULT_QUEUED_MOTION_JERK_PERCENT) -> float:
  """Return a finite queued-motion jerk percentage in the PLC's `(0, 100]` range."""
  try:
    jerk = float(value)
  except Exception:
    return float(default)

  if not math.isfinite(jerk) or jerk <= 0.0:
    return float(default)
  return min(jerk, MAX_QUEUED_MOTION_JERK_PERCENT)


def is_valid_queued_motion_jerk_percent(value) -> bool:
  try:
    jerk = float(value)
  except Exception:
    return False
  return math.isfinite(jerk) and 0.0 < jerk <= MAX_QUEUED_MOTION_JERK_PERCENT
