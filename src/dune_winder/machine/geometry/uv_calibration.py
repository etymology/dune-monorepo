from __future__ import annotations

from dune_winder.geometry.primitives.location import Location
from dune_winder.geometry.serializable_location import SerializableLocation
from dune_winder.machine.calibration.defaults import (
    apply_layer_z_defaults,
    get_layer_z_defaults,
)
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.geometry.uv_layout import Point3D, UV_LAYERS, get_uv_layout


def calibration_absolute_location(
    calibration: LayerCalibration, pin_name: str
) -> Location:
    location = calibration.getPinLocation(pin_name)
    offset = calibration.offset
    if offset is None:
        offset = SerializableLocation()
    return Location(
        float(location.x + offset.x),
        float(location.y + offset.y),
        float(location.z + offset.z),
    )


def normalize_layer_calibration_to_absolute(
    calibration: LayerCalibration,
    layer: str,
) -> LayerCalibration:
    normalized = LayerCalibration(layer=layer)
    normalized.offset = SerializableLocation(0.0, 0.0, 0.0)
    normalized.coordinateSystem = getattr(calibration, "coordinateSystem", "raw")
    for pin_name in calibration.getPinNames():
        normalized.setPinLocation(
            pin_name, calibration_absolute_location(calibration, pin_name)
        )
    z_front, z_back = get_layer_z_defaults(layer)
    normalized.zFront = z_front
    normalized.zBack = z_back
    return normalized


def build_nominal_uv_calibration(
    layer: str,
    machine_calibration: MachineCalibration | None = None,
) -> LayerCalibration:
    """
    Build a nominal U/V calibration in raw coordinate space.

    Pin positions in `LayerCalibration` are stored as raw winder coordinates
    (no camera-wire offset baked in).  The geometric layout returns
    wire-space pin positions, so the camera-wire offset is subtracted here
    to produce raw values.  If `machine_calibration` is None the offset is
    treated as zero (nominal == raw); the caller is responsible for not
    persisting this calibration in that case, since it would not survive a
    later round-trip with a real camera offset.
    """
    requested_layer = str(layer).strip().upper()
    if requested_layer not in UV_LAYERS:
        raise ValueError(f"Unsupported U/V layer {layer!r}.")

    cam_x = 0.0
    cam_y = 0.0
    if machine_calibration is not None:
        cam_x = float(getattr(machine_calibration, "cameraWireOffsetX", None) or 0.0)
        cam_y = float(getattr(machine_calibration, "cameraWireOffsetY", None) or 0.0)

    layout = get_uv_layout(requested_layer)
    calibration = LayerCalibration(layer=requested_layer)
    calibration.offset = SerializableLocation(0.0, 0.0, 0.0)
    for pin_name, point in layout.nominal_positions().items():
        calibration.setPinLocation(
            pin_name,
            Location(
                float(point.x) - cam_x,
                float(point.y) - cam_y,
                float(point.z),
            ),
        )
    return apply_layer_z_defaults(calibration, requested_layer)


def absolute_pin_points(calibration: LayerCalibration) -> dict[str, Point3D]:
    return {
        pin_name: Point3D(
            float(location.x),
            float(location.y),
            float(location.z),
        )
        for pin_name in calibration.getPinNames()
        for location in [calibration_absolute_location(calibration, pin_name)]
    }


__all__ = [
    "absolute_pin_points",
    "build_nominal_uv_calibration",
    "calibration_absolute_location",
    "normalize_layer_calibration_to_absolute",
]
