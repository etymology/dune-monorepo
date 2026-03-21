###############################################################################
# Name: metrics_collector.py
# Uses: Collects PLC tag values and pushes them to InfluxDB.
#
# Reads directly from already-polled PLC.Tag caches — zero additional PLC
# network traffic.  Register update() as a BaseIO post_poll_callback so it
# snapshots consistent values immediately after each poll cycle.
#
# Data is pushed to InfluxDB asynchronously on every poll cycle (~10 Hz).
# Grafana queries InfluxDB directly using Flux, enabling sub-second display.
###############################################################################

try:
  from influxdb_client import InfluxDBClient, Point
  from influxdb_client.client.write_api import WriteOptions, WriteType
  _IMPORT_ERROR = None
except ModuleNotFoundError as importError:
  InfluxDBClient = None
  Point = None
  WriteOptions = None
  WriteType = None
  _IMPORT_ERROR = importError

# InfluxDB connection — must match docker-compose.yml
_URL    = "http://localhost:8086"
_TOKEN  = "dune-winder-token"
_ORG    = "dune"
_BUCKET = "winder"


def _safe_float(value) -> float:
  """Convert a tag value to float, returning 0.0 on None/error."""
  try:
    return float(value)
  except (TypeError, ValueError):
    return 0.0


class MetricsCollector:
  """
  Pushes monitored PLC tag values to InfluxDB after each poll cycle.

  All reads come from the PLC.Tag value cache populated by the existing
  PLC.Tag.pollAll() call — no extra PLC reads are performed.

  Writes are asynchronous (batch_size=1, flush_interval=200 ms) so the
  control-loop thread is never blocked by InfluxDB network latency or
  transient unavailability.
  """

  # -------------------------------------------------------------------------
  def __init__(self, io):
    """
    Args:
      io: BaseIO instance (already constructed with all tags registered).
    """
    self._io = io
    self._disabledReason = None
    self._client = None
    self._write_api = None

    if _IMPORT_ERROR is not None:
      self._disabledReason = (
        "Optional dependency 'influxdb-client' is not installed."
      )
      return

    self._client = InfluxDBClient(url=_URL, token=_TOKEN, org=_ORG)
    self._write_api = self._client.write_api(
      write_options=WriteOptions(
        write_type=WriteType.batching,
        batch_size=1,
        flush_interval=200,
      )
    )

  # -------------------------------------------------------------------------
  def isEnabled(self):
    return self._write_api is not None

  # -------------------------------------------------------------------------
  def disableReason(self):
    return self._disabledReason

  # -------------------------------------------------------------------------
  def update(self):
    """
    Build a data point from the current tag cache and queue it for InfluxDB.
    Call after each PLC poll cycle (register as a BaseIO.pollCallbacks entry).
    """
    if self._write_api is None:
      return

    point = (
      Point("plc_tags")
      .field("tension",          _safe_float(self._io.tension_tag.get()))
      .field("v_xyz",            _safe_float(self._io.v_xyz_tag.get()))
      .field("tension_motor_cv", _safe_float(self._io.tension_motor_cv_tag.get()))
      .field("x_position",       _safe_float(self._io.xAxis.getPosition()))
      .field("y_position",       _safe_float(self._io.yAxis.getPosition()))
      .field("z_position",       _safe_float(self._io.zAxis.getPosition()))
      .field("x_velocity",       _safe_float(self._io.xAxis.getVelocity()))
      .field("y_velocity",       _safe_float(self._io.yAxis.getVelocity()))
      .field("z_velocity",       _safe_float(self._io.zAxis.getVelocity()))
    )
    self._write_api.write(bucket=_BUCKET, record=point)

  # -------------------------------------------------------------------------
  def close(self):
    """Flush pending writes and release InfluxDB resources."""
    if self._write_api is not None:
      self._write_api.close()
    if self._client is not None:
      self._client.close()
