from __future__ import annotations

import math


DEFAULT_QUEUED_MOTION_ACCEL_JERK = 1500.0
DEFAULT_QUEUED_MOTION_DECEL_JERK = 3000.0


def normalize_queued_motion_jerk(value, default: float = DEFAULT_QUEUED_MOTION_ACCEL_JERK) -> float:
  """Return a finite queued-motion jerk value in physical units/sec^3."""
  try:
    jerk = float(value)
  except Exception:
    return float(default)

  if not math.isfinite(jerk) or jerk <= 0.0:
    return float(default)
  return jerk


def is_valid_queued_motion_jerk(value) -> bool:
  try:
    jerk = float(value)
  except Exception:
    return False
  return math.isfinite(jerk) and jerk > 0.0
