###############################################################################
# Name: pin_resolution.py
# Uses: Resolve a stored pin calibration into a wire-space location.
# Notes:
#   Pin calibrations are stored in *raw* winder coordinates (the XY the
#   winder was at when the camera was centred on the pin).  Wire-space is
#   raw + the machine camera-wire offset.  Keeping the offset out of the
#   stored pin location means re-solving cameraWireOffsetX/Y on the
#   Machine Geometry tab does not invalidate existing pin calibrations.
###############################################################################

from __future__ import annotations

from dune_winder.geometry.primitives.location import Location


def wire_space_pin_location(
    layer_calibration,
    machine_calibration,
    pin_name: str,
) -> Location:
    """
    Return the wire-space position of a pin: stored raw pin location plus
    the layer offset plus the machine camera-wire offset.
    """
    raw = layer_calibration.getPinLocation(pin_name)
    layer_offset = layer_calibration.offset
    cam_x, cam_y = _camera_wire_offset(machine_calibration)
    return Location(
        float(raw.x) + float(layer_offset.x) + cam_x,
        float(raw.y) + float(layer_offset.y) + cam_y,
        float(raw.z) + float(layer_offset.z),
    )


def wire_space_translate(layer_calibration, machine_calibration, location: Location) -> Location:
    """Add the layer offset and machine camera-wire offset to an arbitrary raw location."""
    layer_offset = layer_calibration.offset
    cam_x, cam_y = _camera_wire_offset(machine_calibration)
    return Location(
        float(location.x) + float(layer_offset.x) + cam_x,
        float(location.y) + float(layer_offset.y) + cam_y,
        float(location.z) + float(layer_offset.z),
    )


def _camera_wire_offset(machine_calibration) -> tuple[float, float]:
    if machine_calibration is None:
        return (0.0, 0.0)
    cam_x = getattr(machine_calibration, "cameraWireOffsetX", None)
    cam_y = getattr(machine_calibration, "cameraWireOffsetY", None)
    return (float(cam_x or 0.0), float(cam_y or 0.0))
