from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from dune_winder.library.Geometry.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration

from .constants import _DEFAULT_MACHINE_CALIBRATION_PATH
from .models import Point2D, Point3D, UvHeadTargetError
from .pin_layout import _default_layer_calibration_path


@lru_cache(maxsize=4)
def _load_machine_calibration(path: str | Path | None = None) -> MachineCalibration:
    resolved_path = (
        Path(path) if path is not None else _DEFAULT_MACHINE_CALIBRATION_PATH
    )
    calibration = MachineCalibration(str(resolved_path.parent), resolved_path.name)
    calibration.load()
    return calibration


@lru_cache(maxsize=8)
def _load_layer_calibration(
    layer: str, path: str | Path | None = None
) -> LayerCalibration:
    resolved_path = (
        Path(path) if path is not None else _default_layer_calibration_path(layer)
    )
    calibration = LayerCalibration(layer)
    calibration.load(
        str(resolved_path.parent), resolved_path.name, exceptionForMismatch=False
    )
    return calibration


def _location_to_point3(location: Location) -> Point3D:
    return Point3D(float(location.x), float(location.y), float(location.z))


def _location_to_point2(location: Location) -> Point2D:
    return Point2D(float(location.x), float(location.y))


def _wire_space_pin(layer_calibration: LayerCalibration, pin_name: str) -> Location:
    if not layer_calibration.getPinExists(pin_name):
        raise UvHeadTargetError(
            f"Pin {pin_name} is not present in {layer_calibration.getLayerNames()} calibration."
        )
    return layer_calibration.getPinLocation(pin_name).add(layer_calibration.offset)


@lru_cache(maxsize=8)
def _cached_all_wire_space_pins(
    layer_calibration_path: str,
) -> tuple[tuple[str, float, float, float], ...]:
    """Cached version - returns tuple of (pin_name, x, y, z) for hashability."""
    layer_cal = _load_layer_calibration(None, layer_calibration_path)
    return tuple(
        (pin_name,) + (float(loc.x), float(loc.y), float(loc.z))
        for pin_name, loc in (
            (name, layer_cal.getPinLocation(name).add(layer_cal.offset))
            for name in layer_cal.getPinNames()
        )
    )


def _all_wire_space_pins(layer_calibration: LayerCalibration) -> dict[str, Point3D]:
    """Get all wire space pins with caching by calibration path."""
    # Try to get the path from the calibration object
    cal_path = getattr(layer_calibration, "_fullFileName", None)
    if cal_path is not None and os.path.isfile(cal_path):
        points = _cached_all_wire_space_pins(cal_path)
        return {pin_name: Point3D(x, y, z) for pin_name, x, y, z in points}
    # Fallback to uncached if path not available
    return {
        pin_name: _location_to_point3(_wire_space_pin(layer_calibration, pin_name))
        for pin_name in layer_calibration.getPinNames()
    }
