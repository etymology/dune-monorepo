from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


class Point2D(NamedTuple):
  x: float
  y: float


@dataclass(frozen=True)
class RollerArmMeasurement:
  gcode_line: str
  layer: str
  actual_x: float
  actual_y: float
  roller_index: int
  y_cal: float


@dataclass
class RollerArmCalibration:
  measurements: list[RollerArmMeasurement]
  fitted_y_cals: tuple[float, float, float, float]
  center_displacement: float
  arm_tilt_rad: float


def compute_roller_y_cal(
  *,
  actual_pos: Point2D,
  tangent_point_a: Point2D,
  unit_direction: Point2D,
  normal: Point2D,
  roller_index: int,
  head_arm_length: float,
  head_roller_radius: float,
  y_sign: int,
) -> float:
  """
  Back-solve the y-offset of a roller given its measured head position.

  Args:
    actual_pos: Measured head center (Px, Py)
    tangent_point_a: Point on the tangent line
    unit_direction: Unit direction vector along tangent line
    normal: Unit normal vector (perpendicular to tangent)
    roller_index: 0-3 (determines x_off)
    head_arm_length: Arm length (determines x_off)
    head_roller_radius: Roller radius
    y_sign: +1 or -1 (upper or lower roller)

  Returns:
    y_cal: Calibrated y-offset (distance from arm center to roller in y)

  Equation: normal · (roller_center - tangent_point_a) = roller_radius
    where roller_center = (actual_pos.x + x_off, actual_pos.y + y_sign*y_cal)

  Rearranged:
    y_cal = (roller_radius - n.x*(Px + x_off - ta.x) - n.y*(Py - ta.y)) / (n.y * y_sign)
  """
  x_off = _x_offset_for_index(roller_index, head_arm_length)
  numerator = (
    head_roller_radius
    - normal.x * (actual_pos.x + x_off - tangent_point_a.x)
    - normal.y * (actual_pos.y - tangent_point_a.y)
  )
  denominator = normal.y * y_sign

  if abs(denominator) < 1e-9:
    msg = f"Cannot solve y_cal: degenerate normal (n.y={normal.y}, y_sign={y_sign})"
    raise ValueError(msg)

  return numerator / denominator


def fit_roller_arm(
  measurements: list[RollerArmMeasurement],
  *,
  head_arm_length: float,
  nominal_y: float,
) -> tuple[tuple[float, float, float, float], float, float]:
  """
  Fit a rigid-body model to roller measurements.

  Model: y_cal[i] = nominal_y + dy[i]
    where dy[i] = -Δy + arm*θ * y_sign_factor[i]

  Returns:
    (fitted_y_cals, center_displacement, arm_tilt_rad)
  """
  if not measurements:
    return (nominal_y, nominal_y, nominal_y, nominal_y), 0.0, 0.0

  if len(measurements) == 1:
    m = measurements[0]
    roller_index = m.roller_index
    y_sign = _y_sign_for_index(roller_index)

    dy_meas = m.y_cal - nominal_y
    theta = dy_meas / (head_arm_length * y_sign) if head_arm_length != 0 else 0.0

    fitted_y_cals = _predict_all_rollers(nominal_y, 0.0, theta, head_arm_length)
    return fitted_y_cals, 0.0, theta

  if len(measurements) >= 2:
    indices = [m.roller_index for m in measurements]
    y_cals_meas = [m.y_cal for m in measurements]

    dy_meas = [y - nominal_y for y in y_cals_meas]

    A = []
    b = []
    for i, (roller_idx, dy) in enumerate(zip(indices, dy_meas)):
      y_sign = _y_sign_for_index(roller_idx)
      A.append([-1.0, head_arm_length * y_sign])
      b.append(dy)

    delta_y, theta = _least_squares_fit(A, b)
    fitted_y_cals = _predict_all_rollers(nominal_y, delta_y, theta, head_arm_length)
    return fitted_y_cals, delta_y, theta

  return (nominal_y, nominal_y, nominal_y, nominal_y), 0.0, 0.0


def roller_arm_calibration_to_dict(cal: RollerArmCalibration) -> dict:
  return {
    "measurements": [
      {
        "gcode_line": m.gcode_line,
        "layer": m.layer,
        "actual_x": m.actual_x,
        "actual_y": m.actual_y,
        "roller_index": m.roller_index,
        "y_cal": m.y_cal,
      }
      for m in cal.measurements
    ],
    "fitted_y_cals": list(cal.fitted_y_cals),
    "center_displacement": cal.center_displacement,
    "arm_tilt_rad": cal.arm_tilt_rad,
  }


def roller_arm_calibration_from_dict(data: dict) -> RollerArmCalibration:
  measurements = [
    RollerArmMeasurement(
      gcode_line=m["gcode_line"],
      layer=m["layer"],
      actual_x=float(m["actual_x"]),
      actual_y=float(m["actual_y"]),
      roller_index=int(m["roller_index"]),
      y_cal=float(m["y_cal"]),
    )
    for m in data.get("measurements", [])
  ]
  raw_y_cals = data.get("fitted_y_cals", [0.0, 0.0, 0.0, 0.0])
  fitted_y_cals_list = [float(y) for y in raw_y_cals]
  while len(fitted_y_cals_list) < 4:
    fitted_y_cals_list.append(0.0)
  fitted_y_cals = tuple(fitted_y_cals_list[:4])
  return RollerArmCalibration(
    measurements=measurements,
    fitted_y_cals=fitted_y_cals,
    center_displacement=float(data.get("center_displacement", 0.0)),
    arm_tilt_rad=float(data.get("arm_tilt_rad", 0.0)),
  )


def _x_offset_for_index(roller_index: int, head_arm_length: float) -> float:
  return -head_arm_length if roller_index in (0, 1) else head_arm_length


def _y_sign_for_index(roller_index: int) -> int:
  return -1 if roller_index in (0, 2) else 1


def _predict_all_rollers(
  nominal_y: float,
  delta_y: float,
  theta: float,
  head_arm_length: float,
) -> tuple[float, float, float, float]:
  """
  Predict y_cal for all 4 rollers given fitted (delta_y, theta).

  y_cal[i] = nominal_y + dy[i]
  dy[i] = -delta_y + head_arm_length * theta * y_sign[i]
  """
  y_cals: list[float] = []
  for roller_index in range(4):
    y_sign = _y_sign_for_index(roller_index)
    dy = -delta_y + head_arm_length * theta * y_sign
    y_cals.append(nominal_y + dy)
  return (y_cals[0], y_cals[1], y_cals[2], y_cals[3])


def _least_squares_fit(A: list[list[float]], b: list[float]) -> tuple[float, float]:
  """
  Solve A @ [delta_y, theta]^T = b using least-squares.
  A is Mx2, b is M.
  Returns (delta_y, theta).
  """
  if not A or not b:
    return 0.0, 0.0

  ATA_00 = sum(A[i][0] * A[i][0] for i in range(len(A)))
  ATA_01 = sum(A[i][0] * A[i][1] for i in range(len(A)))
  ATA_10 = ATA_01
  ATA_11 = sum(A[i][1] * A[i][1] for i in range(len(A)))

  ATb_0 = sum(A[i][0] * b[i] for i in range(len(A)))
  ATb_1 = sum(A[i][1] * b[i] for i in range(len(A)))

  det = ATA_00 * ATA_11 - ATA_01 * ATA_10
  if abs(det) < 1e-9:
    return 0.0, 0.0

  inv_00 = ATA_11 / det
  inv_01 = -ATA_01 / det
  inv_10 = -ATA_10 / det
  inv_11 = ATA_00 / det

  delta_y = inv_00 * ATb_0 + inv_01 * ATb_1
  theta = inv_10 * ATb_0 + inv_11 * ATb_1

  return delta_y, theta
