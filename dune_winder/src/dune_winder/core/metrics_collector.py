###############################################################################
# Name: metrics_collector.py
# Uses: Collects PLC tag values for Prometheus/Grafana export.
#
# Reads directly from already-polled PLC.Tag caches — zero additional PLC
# network traffic.  Register update() as a BaseIO post_poll_callback so it
# snapshots consistent values immediately after each poll cycle.
###############################################################################

import threading
import time


def _safe_float(value) -> float:
  """Convert a tag value to float, returning 0.0 on None/error."""
  try:
    return float(value)
  except (TypeError, ValueError):
    return 0.0


class MetricsCollector:
  """
  Thread-safe snapshot of monitored PLC tag values.

  All reads come from the PLC.Tag value cache, which is populated by the
  existing PLC.Tag.pollAll() call inside PLC_Logic.poll().  No extra PLC
  reads are performed.
  """

  # Metric metadata: (name, help_text, unit)
  METRICS = [
    ("plc_tension",          "Wire tension",              "N",     0,    10),
    ("plc_v_xyz",            "XYZ velocity setpoint",     "mm/s",  0,  1100),
    ("plc_tension_motor_cv", "Tension motor control var", "",      0,    10),
  ]

  AXIS_METRICS = [
    ("plc_axis_position", "Axis actual position", "mm"),
    ("plc_axis_velocity", "Axis actual velocity", "mm/s"),
  ]

  # Axis position/velocity ranges for info (min, max)
  AXIS_RANGES = {
    "X": {"position": (-10, 7200), "velocity": (-10, 7200)},
    "Y": {"position": (-10, 2700), "velocity": (-10, 2700)},
    "Z": {"position": (-10, 450),  "velocity": (-10, 450)},
  }

  # -------------------------------------------------------------------------
  def __init__(self, io):
    """
    Args:
      io: BaseIO instance (already constructed with all tags registered).
    """
    self._io = io
    self._lock = threading.Lock()
    self._snapshot: dict = {}
    self._timestamp: float = 0.0

  # -------------------------------------------------------------------------
  def update(self):
    """
    Snapshot the current tag values.  Call after each PLC poll cycle
    (e.g. register as a BaseIO.pollCallbacks entry).
    """
    snapshot = {
      "plc_tension":          _safe_float(self._io.tension_tag.get()),
      "plc_v_xyz":            _safe_float(self._io.v_xyz_tag.get()),
      "plc_tension_motor_cv": _safe_float(self._io.tension_motor_cv_tag.get()),
      "plc_axis_position_X":  _safe_float(self._io.xAxis.getPosition()),
      "plc_axis_position_Y":  _safe_float(self._io.yAxis.getPosition()),
      "plc_axis_position_Z":  _safe_float(self._io.zAxis.getPosition()),
      "plc_axis_velocity_X":  _safe_float(self._io.xAxis.getVelocity()),
      "plc_axis_velocity_Y":  _safe_float(self._io.yAxis.getVelocity()),
      "plc_axis_velocity_Z":  _safe_float(self._io.zAxis.getVelocity()),
    }
    with self._lock:
      self._snapshot = snapshot
      self._timestamp = time.time()

  # -------------------------------------------------------------------------
  def render_prometheus(self) -> str:
    """
    Return a Prometheus text exposition (format 0.0.4) of the latest snapshot.
    """
    with self._lock:
      snap = dict(self._snapshot)

    lines: list[str] = []

    # Scalar process metrics
    for name, help_text, unit, _lo, _hi in self.METRICS:
      label = f" ({unit})" if unit else ""
      lines.append(f"# HELP {name} {help_text}{label}")
      lines.append(f"# TYPE {name} gauge")
      lines.append(f"{name} {snap.get(name, 0.0):.6g}")

    # Axis metrics with labels
    for base, help_text, unit in self.AXIS_METRICS:
      lines.append(f"# HELP {base} {help_text} ({unit})")
      lines.append(f"# TYPE {base} gauge")
      for axis in ("X", "Y", "Z"):
        key = f"{base}_{axis}"
        lines.append(f'{base}{{axis="{axis}"}} {snap.get(key, 0.0):.6g}')

    lines.append("")  # trailing newline
    return "\n".join(lines)
