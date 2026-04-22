from dataclasses import dataclass, field
import logging
from typing import Any, Optional, Callable, Sequence
import math
from typing import List, Tuple
from threading import Event

import numpy as np
import pandas as pd

from dune_tension.config import LAYER_LAYOUTS
from dune_tension.data_cache import select_dataframe
from dune_tension.geometry import refine_position
from dune_tension.paths import tension_data_db_path
from dune_tension.plc_io import is_in_measurable_area
from dune_winder.machine.geometry.uv_layout import get_uv_layout

LOGGER = logging.getLogger(__name__)
CONFIDENCE_SOURCES = ("neural_net", "signal_amplitude")


def normalize_confidence_source(value: str | None) -> str:
  """Normalize persisted/UI confidence-source values."""

  normalized = str(value or "neural_net").strip().lower().replace(" ", "_")
  if normalized not in CONFIDENCE_SOURCES:
    raise ValueError(
      f"Invalid confidence source {value!r}. Expected one of {CONFIDENCE_SOURCES}."
    )
  return normalized


def check_stop_event(
  stop_event: Event, message: str = "Measurement interrupted."
) -> bool:
  """Print a message and return True if the stop event is set."""
  if stop_event is not None and stop_event.is_set():
    LOGGER.info(message)
    return True
  return False


@dataclass
class TensiometerConfig:
  apa_name: str
  layer: str
  side: str
  dx: float
  dy: float
  wire_min: int
  wire_max: int
  flipped: bool
  samples_per_wire: int
  confidence_threshold: float
  confidence_source: str
  save_audio: bool
  spoof: bool
  plot_audio: bool = False
  record_duration: float = 0.5
  measuring_duration: float = 10.0

  data_path: str = field(init=False)

  def __post_init__(self):
    # All tension measurements are now stored in a single SQLite file
    # rather than separate files for each APA/layer pair.
    self.data_path = str(tension_data_db_path())


def make_config(
  apa_name: str,
  layer: str,
  side: str,
  flipped: bool = False,
  samples_per_wire: int = 3,
  confidence_threshold: float = 0.7,
  confidence_source: str = "neural_net",
  save_audio: bool = True,
  spoof: bool = False,
  plot_audio: bool = False,
  record_duration: float = 0.5,
  measuring_duration: float = 10.0,
) -> TensiometerConfig:
  try:
    layer_layout = LAYER_LAYOUTS[layer]
  except KeyError as exc:
    raise ValueError(f"Invalid layer {layer!r}") from exc

  dx = layer_layout.dx
  dy = layer_layout.dy
  wire_min = layer_layout.wire_min
  wire_max = layer_layout.wire_max

  if layer in ["U", "V"]:
    _dx, dy = get_uv_layout(layer).measurement_pitch(side)
  if flipped:
    dy = -dy
  return TensiometerConfig(
    apa_name,
    layer,
    side,
    dx,
    dy,
    wire_min,
    wire_max,
    flipped,
    samples_per_wire,
    confidence_threshold,
    normalize_confidence_source(confidence_source),
    save_audio,
    spoof,
    plot_audio,
    record_duration,
    measuring_duration,
  )


@dataclass(frozen=True)
class _WirePositionSnapshot:
  wire_numbers: Any
  xs: Any
  ys: Any
  focus_ys: Any
  focus_positions: Any
  focus_fit_slope: float | None
  focus_fit_intercept: float | None


@dataclass(frozen=True)
class PlannedWirePose:
  wire_number: int
  x: float
  y: float
  focus_position: int | None = None
  zone: int | None = None


def _weighted_focus_fit(
  ys: Sequence[float],
  focus_positions: Sequence[float],
  weights: Sequence[float],
) -> tuple[float | None, float | None]:
  if len(ys) < 2:
    return None, None

  y_values = [float(value) for value in ys]
  if len({round(value, 9) for value in y_values}) < 2:
    return None, None

  focus_values = [float(value) for value in focus_positions]
  weight_values = [float(value) for value in weights]
  total_weight = sum(weight_values)
  if total_weight <= 0:
    return None, None

  y_mean = sum(weight * y for weight, y in zip(weight_values, y_values)) / total_weight
  focus_mean = (
    sum(weight * focus for weight, focus in zip(weight_values, focus_values))
    / total_weight
  )
  variance = sum(
    weight * (y - y_mean) ** 2 for weight, y in zip(weight_values, y_values)
  )
  if variance <= 0:
    return None, None

  covariance = sum(
    weight * (y - y_mean) * (focus - focus_mean)
    for weight, y, focus in zip(weight_values, y_values, focus_values)
  )
  slope = covariance / variance
  intercept = focus_mean - slope * y_mean
  return float(slope), float(intercept)


class WirePositionProvider:
  """Cache normalized per-wire coordinates for repeated measurement planning."""

  def __init__(
    self,
    dataframe_loader: Callable[..., Any] = select_dataframe,
  ) -> None:
    self._dataframe_loader = dataframe_loader
    self._snapshots: dict[tuple[str, str, str, str], _WirePositionSnapshot | None] = {}

  def _snapshot_key(self, config: TensiometerConfig) -> tuple[str, str, str, str]:
    return (
      config.data_path,
      config.apa_name,
      config.layer,
      f"{config.side.upper()}:{int(bool(config.flipped))}",
    )

  def invalidate(self) -> None:
    self._snapshots.clear()

  def _build_snapshot(
    self,
    config: TensiometerConfig,
  ) -> _WirePositionSnapshot | None:
    _data_path, apa_name, layer, _cache_side = self._snapshot_key(config)
    virtual_side = (
      {"A": "B", "B": "A"}[config.side.upper()]
      if config.flipped
      else config.side.upper()
    )

    df = self._dataframe_loader(
      config.data_path,
      where_clause="apa_name = ? AND layer = ? AND side = ?",
      params=(apa_name, layer, virtual_side),
    )
    if getattr(df, "empty", True):
      return None

    if "measurement_mode" not in df.columns:
      df["measurement_mode"] = ""
    df["measurement_mode"] = (
      df["measurement_mode"].fillna("").astype(str).str.strip().str.lower()
    )
    df = df[df["measurement_mode"].isin({"", "legacy"})]
    if df.empty:
      return None

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df["wire_number"] = pd.to_numeric(df["wire_number"], errors="coerce")
    df["x"] = pd.to_numeric(df["x"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df["focus_position"] = pd.to_numeric(df["focus_position"], errors="coerce")
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")

    df_side = (
      df.sort_values("time")
      .drop_duplicates(subset="wire_number", keep="last")
      .sort_values("wire_number")
      .reset_index(drop=True)
    )
    if df_side.empty:
      return None

    df_side = df_side.dropna(subset=["wire_number", "x", "y"]).copy()
    if df_side.empty:
      return None

    focus_rows = df_side.dropna(subset=["y", "focus_position"]).copy()
    fit_rows = focus_rows[
      np.isfinite(focus_rows["confidence"].to_numpy(dtype=float))
      & (focus_rows["confidence"].to_numpy(dtype=float) > 0.0)
    ].copy()
    slope, intercept = _weighted_focus_fit(
      fit_rows["y"].tolist(),
      fit_rows["focus_position"].tolist(),
      fit_rows["confidence"].tolist(),
    )

    return _WirePositionSnapshot(
      wire_numbers=df_side["wire_number"].astype(int).values,
      xs=df_side["x"].astype(float).values,
      ys=df_side["y"].astype(float).values,
      focus_ys=focus_rows["y"].astype(float).values,
      focus_positions=focus_rows["focus_position"].astype(float).values,
      focus_fit_slope=slope,
      focus_fit_intercept=intercept,
    )

  def _get_snapshot(
    self,
    config: TensiometerConfig,
  ) -> _WirePositionSnapshot | None:
    key = self._snapshot_key(config)
    if key not in self._snapshots:
      self._snapshots[key] = self._build_snapshot(config)
    return self._snapshots[key]

  def _resolve_xy(
    self,
    config: TensiometerConfig,
    wire_number: int,
    snapshot: _WirePositionSnapshot,
  ) -> tuple[float, float]:
    lookup_wire_number = int(wire_number)
    if config.flipped and config.layer in ["X", "G"]:
      lookup_wire_number = config.wire_max - lookup_wire_number
      LOGGER.info("Flipped wire number: %s", lookup_wire_number)

    idx_closest = np.argmin(np.abs(snapshot.wire_numbers - lookup_wire_number))
    closest_wire = snapshot.wire_numbers[idx_closest]
    dy_offset = (lookup_wire_number - closest_wire) * config.dy
    x = float(snapshot.xs[idx_closest])
    y = float(snapshot.ys[idx_closest] + dy_offset)

    return (
      refine_position(x, y, config.dx, config.dy)
      if config.layer in ["V", "U"]
      else (x, y)
    )

  def _resolve_focus_position(
    self,
    snapshot: _WirePositionSnapshot,
    y: float,
    *,
    current_focus_position: int | None = None,
  ) -> int | None:
    if (
      snapshot.focus_fit_slope is not None and snapshot.focus_fit_intercept is not None
    ):
      predicted = snapshot.focus_fit_slope * float(y) + snapshot.focus_fit_intercept
      if math.isfinite(predicted):
        return int(round(predicted))

    if len(snapshot.focus_positions) > 0:
      idx_closest = np.argmin(np.abs(snapshot.focus_ys - float(y)))
      return int(round(float(snapshot.focus_positions[idx_closest])))

    if current_focus_position is None:
      return None
    return int(current_focus_position)

  def get_pose(
    self,
    config: TensiometerConfig,
    wire_number: int,
    current_focus_position: int | None = None,
  ) -> Optional[PlannedWirePose]:
    snapshot = self._get_snapshot(config)
    if snapshot is None:
      LOGGER.warning(
        "No data found for side %s in layer %s.",
        config.side,
        config.layer,
      )
      return None

    x, y = self._resolve_xy(config, wire_number, snapshot)
    focus_position = self._resolve_focus_position(
      snapshot,
      y,
      current_focus_position=current_focus_position,
    )
    return PlannedWirePose(
      wire_number=int(wire_number),
      x=float(x),
      y=float(y),
      focus_position=focus_position,
    )

  def get_xy(
    self,
    config: TensiometerConfig,
    wire_number: int,
  ) -> Optional[tuple[float, float]]:
    pose = self.get_pose(config, wire_number)
    if pose is None:
      return None
    return (pose.x, pose.y)


_DEFAULT_WIRE_POSITION_PROVIDER = WirePositionProvider()


def get_xy_from_file(
  config: TensiometerConfig,
  wire_number: int,
  provider: WirePositionProvider | None = None,
) -> Optional[tuple[float, float]]:
  active_provider = provider or _DEFAULT_WIRE_POSITION_PROVIDER
  return active_provider.get_xy(config, wire_number)


def greedy_order_triplets(
  startxy: tuple[float, float], triplets: List[Tuple[int, float, float]]
) -> List[Tuple[int, float, float]]:
  """
  Order triplets by greedy nearest-neighbor distance.

  Args:
      startxy: (x, y) starting coordinates.
      triplets: List of (wire_number, x, y) tuples.

  Returns:
      List of triplets that starts with the target closest to ``startxy``
      and then repeatedly adds the closest remaining target.
  """
  remaining = triplets.copy()
  ordered: list[tuple[int, float, float]] = []
  current_x, current_y = startxy

  while remaining:
    next_triplet = min(
      remaining,
      key=lambda triplet: math.hypot(triplet[1] - current_x, triplet[2] - current_y),
    )
    ordered.append(next_triplet)
    remaining.remove(next_triplet)
    current_x, current_y = next_triplet[1], next_triplet[2]

  return ordered


def greedy_order_poses(
  startxy: tuple[float, float], poses: list[PlannedWirePose]
) -> list[PlannedWirePose]:
  """Order planned poses by greedy nearest-neighbor distance."""

  remaining = poses.copy()
  ordered: list[PlannedWirePose] = []
  current_x, current_y = startxy

  while remaining:
    next_pose = min(
      remaining,
      key=lambda pose: math.hypot(pose.x - current_x, pose.y - current_y),
    )
    ordered.append(next_pose)
    remaining.remove(next_pose)
    current_x, current_y = next_pose.x, next_pose.y

  return ordered


def plan_measurement_poses(
  config: TensiometerConfig,
  wire_list: list[int],
  get_pose_from_file_func: Callable[
    [TensiometerConfig, int, int | None], Optional[PlannedWirePose]
  ],
  get_current_xy_func: Callable[[], tuple[float, float]],
  preserve_order: bool = False,
  current_focus_position: int | None = None,
) -> list[PlannedWirePose]:
  """Resolve, validate, and order motion targets with optional focus targets."""

  LOGGER.info("Loading wire coordinates...")
  poses: list[PlannedWirePose] = []
  for wire_number in wire_list:
    pose = get_pose_from_file_func(config, wire_number, current_focus_position)
    if pose is None:
      LOGGER.warning("No position data found for wire %s", wire_number)
      continue

    if not is_in_measurable_area(pose.x, pose.y):
      LOGGER.warning(
        "Skipping wire %s because position %s,%s is outside the measurable area.",
        wire_number,
        pose.x,
        pose.y,
      )
      continue

    poses.append(pose)

  if not poses:
    LOGGER.warning("No valid wires with legal coordinates.")
    return []

  if preserve_order:
    LOGGER.info("Preserving requested wire order...")
    return poses

  LOGGER.info("Getting current position...")
  start_xy = get_current_xy_func()
  LOGGER.info("Reordering wires...")
  return greedy_order_poses(start_xy, poses)


def plan_measurement_triplets(
  config: TensiometerConfig,
  wire_list: list[int],
  get_xy_from_file_func: Callable[
    [TensiometerConfig, int], Optional[tuple[float, float]]
  ],
  get_current_xy_func: Callable[[], tuple[float, float]],
  preserve_order: bool = False,
) -> list[tuple[int, float, float]]:
  """Resolve, validate, and order motion targets for wire measurements."""

  poses = plan_measurement_poses(
    config=config,
    wire_list=wire_list,
    get_pose_from_file_func=lambda cfg, wire, _current_focus: (
      None
      if (xy := get_xy_from_file_func(cfg, wire)) is None
      else PlannedWirePose(
        wire_number=int(wire),
        x=float(xy[0]),
        y=float(xy[1]),
      )
    ),
    get_current_xy_func=get_current_xy_func,
    preserve_order=preserve_order,
  )
  return [(pose.wire_number, pose.x, pose.y) for pose in poses]


def measure_list(
  config: TensiometerConfig,
  wire_list: list[int],
  get_pose_from_file_func: Callable[
    [TensiometerConfig, int, int | None], Optional[PlannedWirePose]
  ],
  get_current_xy_func: Callable[[], tuple[float, float]],
  collect_func: Callable[[int, float, float, int | None], Optional[float]],
  stop_event: Optional[object] = None,
  preserve_order: bool = False,
  profile: bool = True,
  current_focus_position: int | None = None,
):
  if profile:
    import cProfile
    import pstats
    import io

    profiler = cProfile.Profile()
    profiler.enable()

  ordered_poses = plan_measurement_poses(
    config=config,
    wire_list=wire_list,
    get_pose_from_file_func=get_pose_from_file_func,
    get_current_xy_func=get_current_xy_func,
    preserve_order=preserve_order,
    current_focus_position=current_focus_position,
  )
  if not ordered_poses:
    if profile:
      profiler.disable()
    return

  for pose in ordered_poses:
    LOGGER.info(
      "Measuring wire %s at %s,%s focus=%s",
      pose.wire_number,
      pose.x,
      pose.y,
      pose.focus_position,
    )
    if check_stop_event(stop_event):
      if profile:
        profiler.disable()
        s = io.StringIO()
        pstats.Stats(profiler, stream=s).sort_stats("cumulative").print_stats()
        LOGGER.info("Profiling stats:\n%s", s.getvalue())
      return
    collect_func(pose.wire_number, pose.x, pose.y, pose.focus_position)

  if profile:
    profiler.disable()
    s = io.StringIO()
    pstats.Stats(profiler, stream=s).sort_stats("cumulative").print_stats()
    LOGGER.info("Profiling stats:\n%s", s.getvalue())

  LOGGER.info("Done measuring wires %s", wire_list)
