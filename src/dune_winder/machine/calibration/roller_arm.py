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
    Build a per-roller calibration from the latest measurement for each roller.

    Measuring one roller does not change the stored calibration for the others.
    """
    if not measurements:
        return (nominal_y, nominal_y, nominal_y, nominal_y), 0.0, 0.0

    fitted_y_cals = [nominal_y, nominal_y, nominal_y, nominal_y]
    for measurement in measurements:
        fitted_y_cals[measurement.roller_index] = measurement.y_cal

    return tuple(fitted_y_cals), 0.0, 0.0


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
