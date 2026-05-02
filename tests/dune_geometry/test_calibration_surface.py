"""Surface tests for the Phase C calibration types in dune_geometry.

Covers PinCalibrationSnapshot/PinCalibrationFile (snapshot-based pin
storage) and CalibrationPoint/MachineCalibrationFile/
MachineCalibrationModel (machine-calibration capture and fitted model).
"""

from __future__ import annotations

import json

import pytest

dune_geometry = pytest.importorskip("dune_geometry")


def _ua(n: int) -> "dune_geometry.Pin":
    return dune_geometry.Pin("U", "A", n)


def _vb(n: int) -> "dune_geometry.Pin":
    return dune_geometry.Pin("V", "B", n)


def test_vec3_basic() -> None:
    v = dune_geometry.Vec3(1.0, 2.0, 3.0)
    assert (v.x, v.y, v.z) == (1.0, 2.0, 3.0)
    assert v.as_tuple() == (1.0, 2.0, 3.0)
    assert v == dune_geometry.Vec3(1.0, 2.0, 3.0)


def test_pin_coordinate_round_trip() -> None:
    pc = dune_geometry.PinCoordinate(_ua(1), dune_geometry.Vec3(10.0, 20.0, 30.0))
    assert pc.pin == _ua(1)
    assert pc.xyz == dune_geometry.Vec3(10.0, 20.0, 30.0)


def test_pin_calibration_file_to_from_json() -> None:
    file = dune_geometry.PinCalibrationFile("apa-stand-01")
    snapshot = dune_geometry.PinCalibrationSnapshot(
        taken_at="2026-05-02T12:00:00Z",
        calibration_camera_id="cam-A",
        pins=[
            dune_geometry.PinCoordinate(_ua(1), dune_geometry.Vec3(1.0, 2.0, 3.0)),
            dune_geometry.PinCoordinate(_vb(23), dune_geometry.Vec3(4.0, 5.0, 6.0)),
        ],
        operator="ben",
    )
    file.append_snapshot(snapshot)
    text = file.to_json()
    parsed = json.loads(text)
    # Pin serialises as object form.
    pin_obj = parsed["snapshots"][0]["pins"][0]["pin"]
    assert pin_obj == {"layer": "U", "side": "A", "number": 1}
    # Round-trip back through Rust restores the same data.
    restored = dune_geometry.PinCalibrationFile.from_json(text)
    assert restored.machine_id == "apa-stand-01"
    assert len(restored.snapshots) == 1
    assert restored.snapshots[0].pins[0].pin == _ua(1)


def test_effective_pin_coords_newest_wins() -> None:
    file = dune_geometry.PinCalibrationFile("apa")
    file.append_snapshot(
        dune_geometry.PinCalibrationSnapshot(
            taken_at="2026-05-01T00:00:00Z",
            calibration_camera_id="cam",
            pins=[
                dune_geometry.PinCoordinate(_ua(1), dune_geometry.Vec3(1.0, 0.0, 0.0)),
                dune_geometry.PinCoordinate(_ua(2), dune_geometry.Vec3(2.0, 0.0, 0.0)),
            ],
        )
    )
    file.append_snapshot(
        dune_geometry.PinCalibrationSnapshot(
            taken_at="2026-05-02T00:00:00Z",
            calibration_camera_id="cam",
            pins=[
                dune_geometry.PinCoordinate(_ua(1), dune_geometry.Vec3(99.0, 0.0, 0.0)),
            ],
        )
    )
    eff = dict(file.effective_pin_coords())
    # Newest snapshot's UA1 wins; UA2 still resolves from older.
    assert eff[_ua(1)].x == 99.0
    assert eff[_ua(2)].x == 2.0


def test_calibration_point_offset_helper() -> None:
    cp = dune_geometry.CalibrationPoint(
        captured_at="now",
        gcode_label="Top B Corner",
        gcode_line="~anchorToTarget(B1201,B2001)",
        calculated_xyz=dune_geometry.Vec3(1.0, 2.0, 3.0),
        recorded_xyz=dune_geometry.Vec3(1.5, 2.25, 3.75),
        head_side="stage",
    )
    off = cp.offset()
    assert (off.x, off.y, off.z) == (0.5, 0.25, 0.75)


def test_machine_calibration_model_effective_offset() -> None:
    model = dune_geometry.MachineCalibrationModel(
        base_camera_wire_offset_stage=dune_geometry.Vec3(1.0, 0.0, 0.0),
        base_camera_wire_offset_fixed=dune_geometry.Vec3(2.0, 0.0, 0.0),
        per_pin_camera_wire_offset=[
            dune_geometry.PerPinOffset(_ua(1), dune_geometry.Vec3(99.0, 0.0, 0.0)),
        ],
        arm_correction=dune_geometry.Vec3(0.0, 0.0, 0.0),
    )
    # Override wins for UA1.
    assert model.effective_offset(_ua(1), "stage").x == 99.0
    assert model.effective_offset(_ua(1), "fixed").x == 99.0
    # Other pins use head-side base.
    assert model.effective_offset(_ua(2), "stage").x == 1.0
    assert model.effective_offset(_ua(2), "fixed").x == 2.0


def test_machine_calibration_file_round_trip_with_roller_offsets() -> None:
    file = dune_geometry.MachineCalibrationFile("apa-stand-01")
    file.append_capture(
        dune_geometry.CalibrationPoint(
            captured_at="2026-05-02T12:00:00Z",
            gcode_label="Top B Corner",
            gcode_line="~anchorToTarget(B1201,B2001)",
            calculated_xyz=dune_geometry.Vec3(1.0, 2.0, 3.0),
            recorded_xyz=dune_geometry.Vec3(1.5, 2.25, 3.75),
            head_side="fixed",
            operator="ben",
            pin=dune_geometry.Pin("U", "B", 1201),
        )
    )
    file.set_roller_offsets({"stage": [1.0, 2.0], "fixed": [3.0, 4.0]})
    text = file.to_json()

    restored = dune_geometry.MachineCalibrationFile.from_json(text)
    assert restored.machine_id == "apa-stand-01"
    assert len(restored.capture_points) == 1
    cp = restored.capture_points[0]
    assert cp.gcode_label == "Top B Corner"
    assert cp.head_side == "fixed"
    assert cp.pin == dune_geometry.Pin("U", "B", 1201)
    assert restored.roller_offsets() == {"stage": [1.0, 2.0], "fixed": [3.0, 4.0]}


def test_invalid_head_side_rejected() -> None:
    with pytest.raises(ValueError):
        dune_geometry.CalibrationPoint(
            captured_at="now",
            gcode_label="X",
            gcode_line="X",
            calculated_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
            recorded_xyz=dune_geometry.Vec3(0.0, 0.0, 0.0),
            head_side="left",
        )
