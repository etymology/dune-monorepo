import math
import pytest

from dune_winder.machine.calibration.roller_arm import (
  Point2D,
  compute_roller_y_cal,
  fit_roller_arm,
  RollerArmMeasurement,
  RollerArmCalibration,
  roller_arm_calibration_to_dict,
  roller_arm_calibration_from_dict,
)


def test_compute_roller_y_cal_returns_float():
  """compute_roller_y_cal returns a float."""
  tangent_point_a = Point2D(0.0, 0.0)
  unit_direction = Point2D(1.0, 0.0)
  normal = Point2D(0.0, 1.0)

  actual_pos = Point2D(0.0, 5.0)
  roller_index = 0
  y_sign = -1

  y_cal = compute_roller_y_cal(
    actual_pos=actual_pos,
    tangent_point_a=tangent_point_a,
    unit_direction=unit_direction,
    normal=normal,
    roller_index=roller_index,
    head_arm_length=77.0,
    head_roller_radius=6.5,
    y_sign=y_sign,
  )

  assert isinstance(y_cal, float)


def test_fit_roller_arm_single_measurement():
  """Fit with 1 measurement: solve theta, predict others."""
  nominal_y = 7.0
  head_arm_length = 77.0
  roller_radius = 6.5

  m1 = RollerArmMeasurement(
    gcode_line="~anchorToTarget(B1201,B2001)",
    layer="U",
    actual_x=3297.0,
    actual_y=2683.0,
    roller_index=2,
    y_cal=6.93,
  )

  fitted_y_cals, delta_y, theta = fit_roller_arm(
    [m1],
    head_arm_length=head_arm_length,
    nominal_y=nominal_y,
  )

  assert delta_y == 0.0
  assert len(fitted_y_cals) == 4
  assert fitted_y_cals[0] < fitted_y_cals[1]


def test_fit_roller_arm_two_measurements():
  """Fit with 2 measurements: least-squares (delta_y, theta)."""
  nominal_y = 7.0
  head_arm_length = 77.0

  m1 = RollerArmMeasurement(
    gcode_line="~anchorToTarget(B1201,B2001)",
    layer="U",
    actual_x=3297.0,
    actual_y=2683.0,
    roller_index=2,
    y_cal=6.93,
  )

  m2 = RollerArmMeasurement(
    gcode_line="~anchorToTarget(A801,A2401)",
    layer="U",
    actual_x=477.0,
    actual_y=0.0,
    roller_index=3,
    y_cal=6.81,
  )

  fitted_y_cals, delta_y, theta = fit_roller_arm(
    [m1, m2],
    head_arm_length=head_arm_length,
    nominal_y=nominal_y,
  )

  assert len(fitted_y_cals) == 4
  assert math.isclose(fitted_y_cals[2], m1.y_cal, abs_tol=0.1)
  assert math.isclose(fitted_y_cals[3], m2.y_cal, abs_tol=0.1)


def test_fit_roller_arm_four_measurements():
  """Fit with 4 measurements: use measured values directly."""
  m1 = RollerArmMeasurement(
    gcode_line="~anchorToTarget(B1201,B2001)",
    layer="U",
    actual_x=3297.0,
    actual_y=2683.0,
    roller_index=2,
    y_cal=6.93,
  )

  m2 = RollerArmMeasurement(
    gcode_line="~anchorToTarget(A801,A2401)",
    layer="U",
    actual_x=477.0,
    actual_y=0.0,
    roller_index=3,
    y_cal=6.81,
  )

  m3 = RollerArmMeasurement(
    gcode_line="~anchorToTarget(A1,A800)",
    layer="U",
    actual_x=4357.0,
    actual_y=2683.0,
    roller_index=0,
    y_cal=6.9,
  )

  m4 = RollerArmMeasurement(
    gcode_line="~anchorToTarget(B2003,B1200)",
    layer="U",
    actual_x=7174.0,
    actual_y=3.7,
    roller_index=0,
    y_cal=7.1,
  )

  fitted_y_cals, delta_y, theta = fit_roller_arm(
    [m1, m2, m3, m4],
    head_arm_length=77.0,
    nominal_y=7.0,
  )

  assert len(fitted_y_cals) == 4


def test_roller_arm_calibration_serialization():
  """Test to_dict / from_dict roundtrip."""
  cal = RollerArmCalibration(
    measurements=[
      RollerArmMeasurement(
        gcode_line="~anchorToTarget(B1201,B2001)",
        layer="U",
        actual_x=3297.0,
        actual_y=2683.0,
        roller_index=2,
        y_cal=6.93,
      ),
    ],
    fitted_y_cals=(6.9, 7.1, 6.93, 7.07),
    center_displacement=0.1,
    arm_tilt_rad=0.002,
  )

  d = roller_arm_calibration_to_dict(cal)
  cal2 = roller_arm_calibration_from_dict(d)

  assert len(cal2.measurements) == 1
  assert cal2.measurements[0].roller_index == 2
  assert cal2.center_displacement == 0.1
  assert cal2.arm_tilt_rad == 0.002
