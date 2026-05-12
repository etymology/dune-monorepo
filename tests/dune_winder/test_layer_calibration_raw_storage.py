"""
Tests for raw-coordinate storage in LayerCalibration.

Pin positions in LayerCalibration are stored as raw winder coordinates
(no camera-wire offset baked in).  The offset is applied at runtime via
wire_space_pin_location.  Legacy "wire" files are auto-migrated on load.
"""

from __future__ import annotations

import json
import os
import tempfile

from dune_winder.geometry.primitives.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.calibration.pin_resolution import wire_space_pin_location


def _build_machine_calibration(*, cam_x: float = 65.0, cam_y: float = -108.2) -> MachineCalibration:
    machine = MachineCalibration()
    machine.cameraWireOffsetX = cam_x
    machine.cameraWireOffsetY = cam_y
    return machine


def test_new_calibration_defaults_to_raw_coordinate_system() -> None:
    cal = LayerCalibration("V")
    assert cal.coordinateSystem == "raw"


def test_save_round_trip_preserves_coordinate_system() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cal = LayerCalibration("V", archivePath=os.path.join(tmp, "Archive"))
        cal.zFront = 145.0
        cal.zBack = 275.0
        cal.setPinLocation("B400", Location(100.0, 200.0, 145.0))
        cal.save(tmp, "V_Calibration.json")

        with open(os.path.join(tmp, "V_Calibration.json")) as handle:
            data = json.load(handle)
        assert data["coordinateSystem"] == "raw"
        assert data["locations"]["B400"]["x"] == 100.0


def test_wire_space_pin_location_adds_camera_offset() -> None:
    cal = LayerCalibration("V")
    cal.setPinLocation("B400", Location(100.0, 200.0, 145.0))
    machine = _build_machine_calibration()

    wire = wire_space_pin_location(cal, machine, "B400")

    assert wire.x == 100.0 + 65.0
    assert abs(wire.y - (200.0 - 108.2)) < 1e-9
    assert wire.z == 145.0


def test_legacy_file_without_coordinate_system_is_migrated_to_raw() -> None:
    cam_x = 65.0
    cam_y = -108.2
    wire_x = 165.0  # raw 100 + cam 65
    wire_y = 91.8  # raw 200 + cam -108.2

    with tempfile.TemporaryDirectory() as tmp:
        legacy_data = {
            "layer": "V",
            "zFront": 145.0,
            "zBack": 275.0,
            "zPlaneCalibration": None,
            "hashValue": "",
            "offset": {"x": 0.0, "y": 0.0, "z": 0.0},
            "locations": {"B400": {"x": wire_x, "y": wire_y, "z": 145.0}},
        }
        # Compute hash on the legacy shape (no coordinateSystem field).
        helper = LayerCalibration("V")
        legacy_data["hashValue"] = helper._compute_hash(
            {k: v for k, v in legacy_data.items() if k != "hashValue"}
        )

        legacy_path = os.path.join(tmp, "V_Calibration.json")
        with open(legacy_path, "w") as handle:
            json.dump(legacy_data, handle)

        machine = _build_machine_calibration(cam_x=cam_x, cam_y=cam_y)
        cal = LayerCalibration(
            "V", archivePath=os.path.join(tmp, "Archive")
        )
        cal.load(
            tmp,
            "V_Calibration.json",
            machineCalibration=machine,
            exceptionForMismatch=False,
        )

        assert cal.coordinateSystem == "raw"
        # Storage now in raw form: original 100, 200.
        assert abs(cal.getPinLocation("B400").x - 100.0) < 1e-9
        assert abs(cal.getPinLocation("B400").y - 200.0) < 1e-9

        # The on-disk file was rewritten in the raw form.
        with open(legacy_path) as handle:
            persisted = json.load(handle)
        assert persisted["coordinateSystem"] == "raw"
        assert abs(persisted["locations"]["B400"]["x"] - 100.0) < 1e-9


def test_camera_offset_change_does_not_invalidate_pin_storage() -> None:
    """
    The whole point of decoupling: re-solving the camera-wire offset on the
    Machine Geometry tab should not silently drift pin calibrations.
    """
    with tempfile.TemporaryDirectory() as tmp:
        cal = LayerCalibration("V", archivePath=os.path.join(tmp, "Archive"))
        cal.zFront = 145.0
        cal.zBack = 275.0
        cal.setPinLocation("B400", Location(100.0, 200.0, 145.0))
        cal.save(tmp, "V_Calibration.json")

        # Reload with a different camera offset; raw values must not change.
        machine = _build_machine_calibration(cam_x=200.0, cam_y=-50.0)
        cal2 = LayerCalibration("V")
        cal2.load(
            tmp,
            "V_Calibration.json",
            machineCalibration=machine,
            exceptionForMismatch=False,
        )

        assert cal2.coordinateSystem == "raw"
        assert cal2.getPinLocation("B400").x == 100.0
        assert cal2.getPinLocation("B400").y == 200.0

        wire = wire_space_pin_location(cal2, machine, "B400")
        # Wire-space picks up the new offset at runtime.
        assert wire.x == 300.0
        assert wire.y == 150.0
