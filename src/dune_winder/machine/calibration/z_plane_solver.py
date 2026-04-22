from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from dune_winder.library.Geometry.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.z_plane import (
  LayerZPlaneCalibration,
  LayerZPlaneMeasurement,
  LayerZPlaneObservation,
  empty_layer_z_plane_calibration,
)
from dune_winder.uv_head_target import compute_uv_anchor_to_target_view


BOARD_WIDTH_MM = 130.0
TILT_SANITY_LIMIT_MM = 20.0
_FIT_RANK_ERROR = "Need at least 3 non-collinear projected-tangent measurements to fit a Z plane."


def _normalize_layer(layer: str) -> str:
  value = str(layer).strip().upper()
  if value not in {"U", "V"}:
    raise ValueError("Layer Z-plane calibration only supports U and V layers.")
  return value


def _normalized_path(path: str | Path | None) -> str | None:
  if path is None:
    return None
  return str(Path(path))


def evaluate_plane_z(
  coefficients: tuple[float, float, float],
  x: float,
  y: float,
  *,
  pin_family: str = "A",
  board_width: float = BOARD_WIDTH_MM,
) -> float:
  a, b, c = coefficients
  z = (float(a) * float(x)) + (float(b) * float(y)) + float(c)
  if str(pin_family).strip().upper() == "B":
    z += float(board_width)
  return float(z)


def has_valid_layer_z_plane_fit(calibration: LayerZPlaneCalibration | None) -> bool:
  return bool(
    calibration is not None
    and calibration.coefficients is not None
    and calibration.fit_error is None
  )


def build_layer_z_plane_observation(
  measurement: LayerZPlaneMeasurement,
  *,
  machine_calibration_path: str | Path | None = None,
  layer_calibration_path: str | Path | None = None,
  board_width: float = BOARD_WIDTH_MM,
) -> LayerZPlaneObservation:
  normalized_layer = _normalize_layer(measurement.layer)
  view = compute_uv_anchor_to_target_view(
    command_text=measurement.gcode_line,
    layer=normalized_layer,
    machine_calibration_path=_normalized_path(machine_calibration_path),
    layer_calibration_path=_normalized_path(layer_calibration_path),
  )
  pin_family = str(view.command.anchor_pin).strip().upper()[:1]
  target_family = str(view.command.target_pin).strip().upper()[:1]
  if pin_family != target_family or pin_family not in {"A", "B"}:
    raise ValueError(
      "Layer Z-plane calibration only supports same-side A-A or B-B measurements."
    )

  tangent_a = np.array(
    [float(view.raw_result.tangent_point_a.x), float(view.raw_result.tangent_point_a.y)],
    dtype=float,
  )
  tangent_b = np.array(
    [float(view.raw_result.tangent_point_b.x), float(view.raw_result.tangent_point_b.y)],
    dtype=float,
  )
  transfer = np.array(
    [
      float(view.raw_result.outbound_intercept.x),
      float(view.raw_result.outbound_intercept.y),
    ],
    dtype=float,
  )
  direction = tangent_b - tangent_a
  denominator = float(np.dot(direction, direction))
  if denominator <= 1e-12:
    raise ValueError("Projected tangent geometry is degenerate for this measurement.")
  lambda_value = float(np.dot(transfer - tangent_a, direction) / denominator)

  roller_tangent = view.raw_result.arm_corrected_outbound_point
  if roller_tangent is None:
    raise ValueError(
      "Layer Z-plane calibration requires a same-side roller tangent XY point."
    )
  normalized_z = float(measurement.actual_z)
  if pin_family == "B":
    normalized_z -= float(board_width)

  return LayerZPlaneObservation(
    gcode_line=str(measurement.gcode_line),
    layer=normalized_layer,
    anchor_pin=view.command.anchor_pin,
    target_pin=view.command.target_pin,
    pin_family=pin_family,
    actual_x=float(measurement.actual_x),
    actual_y=float(measurement.actual_y),
    actual_z=float(measurement.actual_z),
    tangent_point_a_x=float(tangent_a[0]),
    tangent_point_a_y=float(tangent_a[1]),
    tangent_point_b_x=float(tangent_b[0]),
    tangent_point_b_y=float(tangent_b[1]),
    transfer_point_x=float(transfer[0]),
    transfer_point_y=float(transfer[1]),
    lambda_value=lambda_value,
    effective_x=float(roller_tangent.x),
    effective_y=float(roller_tangent.y),
    normalized_z=normalized_z,
  )


def _load_layer_calibration_from_path(path: str | Path | None) -> LayerCalibration | None:
  if path is None:
    return None
  resolved = Path(path)
  calibration = LayerCalibration()
  calibration.load(str(resolved.parent), resolved.name, exceptionForMismatch=False)
  return calibration


def _fit_plane_from_observations(
  observations: list[LayerZPlaneObservation],
) -> tuple[tuple[float, float, float] | None, int, float | None]:
  if not observations:
    return (None, 0, None)
  points = np.asarray(
    [[obs.effective_x, obs.effective_y, 1.0] for obs in observations],
    dtype=float,
  )
  values = np.asarray([obs.normalized_z for obs in observations], dtype=float)
  rank = int(np.linalg.matrix_rank(points))
  if len(observations) < 3 or rank < 3:
    return (None, rank, None)
  coefficients, residuals, _rank, _singular = np.linalg.lstsq(points, values, rcond=None)
  residual_sum_squares = (
    float(residuals[0])
    if len(residuals) > 0
    else float(np.sum((points @ coefficients - values) ** 2))
  )
  return (
    (float(coefficients[0]), float(coefficients[1]), float(coefficients[2])),
    rank,
    residual_sum_squares,
  )


def _side_plane_stats(
  coefficients: tuple[float, float, float],
  *,
  layer_calibration: LayerCalibration,
  board_width: float,
) -> tuple[float | None, float | None, float | None]:
  side_values: dict[str, list[float]] = {"A": [], "B": []}
  for pin_name in layer_calibration.getPinNames():
    family = str(pin_name).strip().upper()[:1]
    if family not in side_values:
      continue
    location = layer_calibration.getPinLocation(pin_name)
    side_values[family].append(
      evaluate_plane_z(
        coefficients,
        float(location.x),
        float(location.y),
        pin_family=family,
        board_width=board_width,
      )
    )

  front_values = side_values["A"]
  back_values = side_values["B"]
  z_front_mean = (
    float(sum(front_values) / len(front_values)) if front_values else None
  )
  z_back_mean = float(sum(back_values) / len(back_values)) if back_values else None

  max_abs_deviation = None
  for values, mean in ((front_values, z_front_mean), (back_values, z_back_mean)):
    if not values or mean is None:
      continue
    deviation = max(abs(value - mean) for value in values)
    max_abs_deviation = (
      deviation
      if max_abs_deviation is None
      else max(max_abs_deviation, deviation)
    )
  return (z_front_mean, z_back_mean, max_abs_deviation)


def fit_layer_z_plane_from_observations(
  measurements: list[LayerZPlaneMeasurement],
  observations: list[LayerZPlaneObservation],
  *,
  layer_calibration_path: str | Path | None = None,
  board_width: float = BOARD_WIDTH_MM,
  tilt_limit_mm: float = TILT_SANITY_LIMIT_MM,
) -> LayerZPlaneCalibration:
  result = LayerZPlaneCalibration(
    measurements=list(measurements),
    observations=list(observations),
    board_width=float(board_width),
  )
  coefficients, rank, residual_sum_squares = _fit_plane_from_observations(observations)
  result.rank = rank
  result.residual_sum_squares = residual_sum_squares
  if coefficients is None:
    result.fit_error = _FIT_RANK_ERROR
    return result

  result.coefficients = coefficients
  updated_observations = []
  for observation in observations:
    predicted = evaluate_plane_z(
      coefficients,
      observation.effective_x,
      observation.effective_y,
      pin_family="A",
      board_width=board_width,
    )
    updated_observations.append(
      replace(observation, residual=float(predicted - observation.normalized_z))
    )
  result.observations = updated_observations

  layer_calibration = _load_layer_calibration_from_path(layer_calibration_path)
  if layer_calibration is None:
    return result

  z_front_mean, z_back_mean, max_abs_deviation = _side_plane_stats(
    coefficients,
    layer_calibration=layer_calibration,
    board_width=board_width,
  )
  result.z_front_mean = z_front_mean
  result.z_back_mean = z_back_mean
  result.max_abs_side_deviation_mm = max_abs_deviation
  if max_abs_deviation is not None and max_abs_deviation > float(tilt_limit_mm):
    result.fit_error = (
      "Fitted Z plane deviates from the side mean by more than "
      f"{float(tilt_limit_mm):.1f} mm."
    )
  return result


def fit_layer_z_plane(
  measurements: list[LayerZPlaneMeasurement],
  *,
  machine_calibration_path: str | Path | None = None,
  layer_calibration_path: str | Path | None = None,
  board_width: float = BOARD_WIDTH_MM,
  tilt_limit_mm: float = TILT_SANITY_LIMIT_MM,
) -> LayerZPlaneCalibration:
  if not measurements:
    return empty_layer_z_plane_calibration(board_width=float(board_width))

  normalized_layers = {_normalize_layer(measurement.layer) for measurement in measurements}
  if len(normalized_layers) != 1:
    raise ValueError("Layer Z-plane measurements must all target the same layer.")

  observations = [
    build_layer_z_plane_observation(
      measurement,
      machine_calibration_path=machine_calibration_path,
      layer_calibration_path=layer_calibration_path,
      board_width=board_width,
    )
    for measurement in measurements
  ]
  return fit_layer_z_plane_from_observations(
    measurements,
    observations,
    layer_calibration_path=layer_calibration_path,
    board_width=board_width,
    tilt_limit_mm=tilt_limit_mm,
  )


def apply_layer_z_plane_calibration(
  layer_calibration: LayerCalibration,
  z_plane_calibration: LayerZPlaneCalibration,
) -> bool:
  if not has_valid_layer_z_plane_fit(z_plane_calibration):
    return False

  coefficients = z_plane_calibration.coefficients
  assert coefficients is not None

  side_values: dict[str, list[float]] = {"A": [], "B": []}
  for pin_name in layer_calibration.getPinNames():
    location = layer_calibration.getPinLocation(pin_name)
    family = str(pin_name).strip().upper()[:1]
    if family not in side_values:
      continue
    z_value = evaluate_plane_z(
      coefficients,
      float(location.x),
      float(location.y),
      pin_family=family,
      board_width=z_plane_calibration.board_width,
    )
    side_values[family].append(z_value)
    layer_calibration.setPinLocation(
      pin_name,
      Location(float(location.x), float(location.y), float(z_value)),
    )

  if side_values["A"]:
    layer_calibration.zFront = float(sum(side_values["A"]) / len(side_values["A"]))
  if side_values["B"]:
    layer_calibration.zBack = float(sum(side_values["B"]) / len(side_values["B"]))
  return True


__all__ = [
  "BOARD_WIDTH_MM",
  "TILT_SANITY_LIMIT_MM",
  "apply_layer_z_plane_calibration",
  "build_layer_z_plane_observation",
  "evaluate_plane_z",
  "fit_layer_z_plane",
  "fit_layer_z_plane_from_observations",
  "has_valid_layer_z_plane_fit",
]
