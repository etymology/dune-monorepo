from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerZPlaneMeasurement:
  gcode_line: str
  layer: str
  actual_x: float
  actual_y: float
  actual_z: float


@dataclass(frozen=True)
class LayerZPlaneObservation:
  gcode_line: str
  layer: str
  anchor_pin: str
  target_pin: str
  pin_family: str
  actual_x: float
  actual_y: float
  actual_z: float
  tangent_point_a_x: float
  tangent_point_a_y: float
  tangent_point_b_x: float
  tangent_point_b_y: float
  transfer_point_x: float
  transfer_point_y: float
  lambda_value: float
  effective_x: float
  effective_y: float
  normalized_z: float
  residual: float | None = None


@dataclass
class LayerZPlaneCalibration:
  measurements: list[LayerZPlaneMeasurement]
  observations: list[LayerZPlaneObservation]
  board_width: float
  coefficients: tuple[float, float, float] | None = None
  rank: int | None = None
  residual_sum_squares: float | None = None
  max_abs_side_deviation_mm: float | None = None
  z_front_mean: float | None = None
  z_back_mean: float | None = None
  fit_error: str | None = None


def layer_z_plane_measurement_to_dict(measurement: LayerZPlaneMeasurement) -> dict:
  return {
    "gcode_line": measurement.gcode_line,
    "layer": measurement.layer,
    "actual_x": float(measurement.actual_x),
    "actual_y": float(measurement.actual_y),
    "actual_z": float(measurement.actual_z),
  }


def layer_z_plane_measurement_from_dict(data: dict) -> LayerZPlaneMeasurement:
  return LayerZPlaneMeasurement(
    gcode_line=str(data["gcode_line"]),
    layer=str(data["layer"]),
    actual_x=float(data["actual_x"]),
    actual_y=float(data["actual_y"]),
    actual_z=float(data["actual_z"]),
  )


def layer_z_plane_observation_to_dict(observation: LayerZPlaneObservation) -> dict:
  return {
    "gcode_line": observation.gcode_line,
    "layer": observation.layer,
    "anchor_pin": observation.anchor_pin,
    "target_pin": observation.target_pin,
    "pin_family": observation.pin_family,
    "actual_x": float(observation.actual_x),
    "actual_y": float(observation.actual_y),
    "actual_z": float(observation.actual_z),
    "tangent_point_a_x": float(observation.tangent_point_a_x),
    "tangent_point_a_y": float(observation.tangent_point_a_y),
    "tangent_point_b_x": float(observation.tangent_point_b_x),
    "tangent_point_b_y": float(observation.tangent_point_b_y),
    "transfer_point_x": float(observation.transfer_point_x),
    "transfer_point_y": float(observation.transfer_point_y),
    "lambda_value": float(observation.lambda_value),
    "effective_x": float(observation.effective_x),
    "effective_y": float(observation.effective_y),
    "normalized_z": float(observation.normalized_z),
    "residual": None if observation.residual is None else float(observation.residual),
  }


def layer_z_plane_observation_from_dict(data: dict) -> LayerZPlaneObservation:
  return LayerZPlaneObservation(
    gcode_line=str(data["gcode_line"]),
    layer=str(data["layer"]),
    anchor_pin=str(data["anchor_pin"]),
    target_pin=str(data["target_pin"]),
    pin_family=str(data["pin_family"]),
    actual_x=float(data["actual_x"]),
    actual_y=float(data["actual_y"]),
    actual_z=float(data["actual_z"]),
    tangent_point_a_x=float(data["tangent_point_a_x"]),
    tangent_point_a_y=float(data["tangent_point_a_y"]),
    tangent_point_b_x=float(data["tangent_point_b_x"]),
    tangent_point_b_y=float(data["tangent_point_b_y"]),
    transfer_point_x=float(data["transfer_point_x"]),
    transfer_point_y=float(data["transfer_point_y"]),
    lambda_value=float(data["lambda_value"]),
    effective_x=float(data["effective_x"]),
    effective_y=float(data["effective_y"]),
    normalized_z=float(data["normalized_z"]),
    residual=(
      None if data.get("residual") is None else float(data["residual"])
    ),
  )


def layer_z_plane_calibration_to_dict(calibration: LayerZPlaneCalibration) -> dict:
  return {
    "measurements": [
      layer_z_plane_measurement_to_dict(measurement)
      for measurement in calibration.measurements
    ],
    "observations": [
      layer_z_plane_observation_to_dict(observation)
      for observation in calibration.observations
    ],
    "board_width": float(calibration.board_width),
    "coefficients": (
      None
      if calibration.coefficients is None
      else [float(value) for value in calibration.coefficients]
    ),
    "rank": calibration.rank,
    "residual_sum_squares": (
      None
      if calibration.residual_sum_squares is None
      else float(calibration.residual_sum_squares)
    ),
    "max_abs_side_deviation_mm": (
      None
      if calibration.max_abs_side_deviation_mm is None
      else float(calibration.max_abs_side_deviation_mm)
    ),
    "z_front_mean": (
      None if calibration.z_front_mean is None else float(calibration.z_front_mean)
    ),
    "z_back_mean": (
      None if calibration.z_back_mean is None else float(calibration.z_back_mean)
    ),
    "fit_error": calibration.fit_error,
  }


def layer_z_plane_calibration_from_dict(data: dict) -> LayerZPlaneCalibration:
  coefficients = data.get("coefficients")
  return LayerZPlaneCalibration(
    measurements=[
      layer_z_plane_measurement_from_dict(item)
      for item in data.get("measurements", [])
    ],
    observations=[
      layer_z_plane_observation_from_dict(item)
      for item in data.get("observations", [])
    ],
    board_width=float(data.get("board_width", 130.0)),
    coefficients=(
      None
      if coefficients is None
      else tuple(float(value) for value in coefficients[:3])
    ),
    rank=None if data.get("rank") is None else int(data["rank"]),
    residual_sum_squares=(
      None
      if data.get("residual_sum_squares") is None
      else float(data["residual_sum_squares"])
    ),
    max_abs_side_deviation_mm=(
      None
      if data.get("max_abs_side_deviation_mm") is None
      else float(data["max_abs_side_deviation_mm"])
    ),
    z_front_mean=(
      None if data.get("z_front_mean") is None else float(data["z_front_mean"])
    ),
    z_back_mean=(
      None if data.get("z_back_mean") is None else float(data["z_back_mean"])
    ),
    fit_error=data.get("fit_error"),
  )


def empty_layer_z_plane_calibration(
  *,
  board_width: float = 130.0,
) -> LayerZPlaneCalibration:
  return LayerZPlaneCalibration(
    measurements=[],
    observations=[],
    board_width=float(board_width),
  )


__all__ = [
  "LayerZPlaneCalibration",
  "LayerZPlaneMeasurement",
  "LayerZPlaneObservation",
  "empty_layer_z_plane_calibration",
  "layer_z_plane_calibration_from_dict",
  "layer_z_plane_calibration_to_dict",
  "layer_z_plane_measurement_from_dict",
  "layer_z_plane_measurement_to_dict",
  "layer_z_plane_observation_from_dict",
  "layer_z_plane_observation_to_dict",
]
