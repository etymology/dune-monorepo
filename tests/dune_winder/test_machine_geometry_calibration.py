from __future__ import annotations

import json
import random
import threading
import time
from types import SimpleNamespace

import pytest

import dune_winder.core.machine_geometry_calibration as machine_geometry_module
import dune_winder.uv_head_target as uv_head_target_module
from dune_winder.core.machine_geometry_calibration import MachineGeometryCalibration
from dune_winder.paths import REPO_ROOT


class _Axis:
    def __init__(self, position):
        self._position = float(position)

    def getPosition(self):
        return self._position


class _IO:
    def __init__(self, x, y, z):
        self.xAxis = _Axis(x)
        self.yAxis = _Axis(y)
        self.zAxis = _Axis(z)


class _Backlash:
    def getEffectiveX(self, raw_x):
        return float(raw_x) - 2.0


class _Log:
    def __init__(self):
        self.entries = []

    def add(self, *args):
        self.entries.append(args)


class _TimeSource:
    def __init__(self):
        self.value = 0

    def get(self):
        self.value += 1
        return self.value


class _MachineCalibration:
    def __init__(self, root_directory):
        self.headRollerGap = 24.0
        self.headRollerRadius = 9.0
        self.headArmLength = 80.0
        self.cameraWireOffsetX = 10.0
        self.cameraWireOffsetY = -5.0
        self.rollerArmCalibration = SimpleNamespace(
            fitted_y_cals=(24.0, 23.0, 18.0, 17.0)
        )
        self._outputFilePath = str(root_directory)
        self._outputFileName = "machineCalibration.json"
        self.save_calls = 0

    def _to_dict(self):
        return {
            "headRollerGap": self.headRollerGap,
            "headRollerRadius": self.headRollerRadius,
            "headArmLength": self.headArmLength,
            "cameraWireOffsetX": self.cameraWireOffsetX,
            "cameraWireOffsetY": self.cameraWireOffsetY,
            "rollerArmCalibration": {
                "measurements": [],
                "fitted_y_cals": list(self.rollerArmCalibration.fitted_y_cals),
                "center_displacement": 0.0,
                "arm_tilt_rad": 0.0,
            },
        }

    def save(self):
        self.save_calls += 1


class _ControlStateMachine:
    def __init__(self, machine_calibration, *, active=False):
        state_name = "WindMode" if active else "StopMode"
        self.state = type(state_name, (), {})()
        self.machineCalibration = machine_calibration


class _Process:
    def __init__(self, root_directory, *, active=False):
        self._workspaceCalibrationDirectory = str(root_directory)
        self._systemTime = _TimeSource()
        self._log = _Log()
        self._io = _IO(110.0, 195.0, 30.0)
        self._xBacklash = _Backlash()
        self._machineCalibration = _MachineCalibration(root_directory)
        self.controlStateMachine = _ControlStateMachine(
            self._machineCalibration,
            active=active,
        )
        self.workspace = None
        self.uTemplateRecipe = SimpleNamespace(
            getState=lambda: {
                "lineOffsetOverrides": {},
                "lineOffsetOverrideItems": [],
            }
        )
        self.vTemplateRecipe = SimpleNamespace(
            getState=lambda: {
                "lineOffsetOverrides": {},
                "lineOffsetOverrideItems": [],
            }
        )
        self.manualCalibration = None
        self._lastTrace = None

    def getRecipeLayer(self):
        return "U"

    def getLastInstructionTrace(self):
        return self._lastTrace

    def isGCodeExecutionActive(self):
        return (
            getattr(self.controlStateMachine.state.__class__, "__name__", "")
            == "WindMode"
        )


def test_record_measurement_captures_last_trace_and_current_position(
    monkeypatch, tmp_path
):
    process = _Process(tmp_path)
    process._lastTrace = {
        "line": "N42 ~anchorToTarget(B1201,B2001,hover=True) (3,4)",
        "resultingWireTarget": {"x": 321.0, "y": 654.0},
    }
    service = MachineGeometryCalibration(process)

    monkeypatch.setattr(
        machine_geometry_module,
        "compute_pin_pair_tangent_geometry",
        lambda **kwargs: SimpleNamespace(roller_index=2),
    )

    measurement = service.recordMeasurement(capture_xy=True, capture_z=True)

    assert measurement["kind"] == "same_side"
    assert measurement["lineKey"] == "(3,4)"
    assert measurement["rollerIndex"] == 2
    assert measurement["actualWireX"] == pytest.approx(108.0, abs=1e-9)
    assert measurement["actualWireY"] == pytest.approx(195.0, abs=1e-9)
    assert measurement["actualZ"] == pytest.approx(30.0, abs=1e-9)
    assert measurement["projectedX"] == pytest.approx(321.0, abs=1e-9)
    assert measurement["projectedY"] == pytest.approx(654.0, abs=1e-9)


def test_machine_xy_solver_holds_roller_cals_fixed(monkeypatch, tmp_path):
    # The solver no longer fits roller-Y calibrations -- it minimizes the
    # per-line offsets by moving camera X/Y only, leaving roller cals
    # exactly as passed in.  The Z plane is fit separately (see
    # solveLayerZ).
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    real_random = random.Random
    monkeypatch.setattr(
        machine_geometry_module.random, "Random", lambda: real_random(0)
    )
    measurements = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
        {
            "id": "m2",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "gcodeLine": "~anchorToTarget(B1202,B2002) (1,2)",
            "effectiveCameraX": 120.0,
            "rawCameraY": 260.0,
            "actualWireX": 130.0,
            "actualWireY": 255.0,
        },
    ]

    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["actualWireX"]) - 10.0,
            "projectedY": float(measurement["actualWireY"]) + 5.0,
        },
    )

    evaluation = service._evaluateMachineXY(
        measurements,
        layer="U",
        operation_id="op-test-1",
        layer_path="layer.json",
        nominal_roller_y=21.0,
        current_camera_offset=(10.0, -5.0),
        initial_roller_y_cals=(24.0, 27.0, 18.0, 17.0),
    )

    # The projection mock embeds a constant +10/-5 bias that the starting
    # camera offset (10, -5) already cancels, so the optimum here is to
    # leave camera offset alone.  Roller cals are untouched regardless.
    assert evaluation["cameraOffsetX"] == pytest.approx(10.0, abs=1e-9)
    assert evaluation["cameraOffsetY"] == pytest.approx(-5.0, abs=0.2)
    assert evaluation["rollerYCals"] == [24.0, 27.0, 18.0, 17.0]
    assert any("m1" in item["measurementIds"] for item in evaluation["siteOffsetItems"])
    assert any("m2" in item["measurementIds"] for item in evaluation["siteOffsetItems"])


def test_machine_xy_solver_reports_bounded_progress(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    real_random = random.Random
    monkeypatch.setattr(
        machine_geometry_module.random, "Random", lambda: real_random(0)
    )
    measurements = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
        {
            "id": "m2",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "gcodeLine": "~anchorToTarget(B1202,B2002) (1,2)",
            "effectiveCameraX": 120.0,
            "rawCameraY": 260.0,
            "actualWireX": 130.0,
            "actualWireY": 255.0,
        },
    ]

    projection_batches = {"count": 0}
    progress_events = []

    def candidate_machine_path(roller_y_cals, camera_offset=None):
        projection_batches["count"] += 1
        return "machine.json"

    monkeypatch.setattr(
        service, "_candidateMachineCalibrationPath", candidate_machine_path
    )
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["actualWireX"]) - 10.0,
            "projectedY": float(measurement["actualWireY"]) + 5.0,
        },
    )

    evaluation = service._evaluateMachineXY(
        measurements,
        layer="U",
        operation_id="op-test-2",
        layer_path="layer.json",
        nominal_roller_y=21.0,
        current_camera_offset=(10.0, -5.0),
        initial_roller_y_cals=(24.0, 27.0, 18.0, 17.0),
        progress_callback=lambda step, message, **fields: progress_events.append(
            (step, message, fields)
        ),
    )

    assert evaluation["cameraOffsetX"] == pytest.approx(10.0, abs=1e-9)
    assert projection_batches["count"] < 200
    assert any(
        "totalEvaluations" in fields for _step, _message, fields in progress_events
    )
    assert any(
        "percentComplete" in fields for _step, _message, fields in progress_events
    )
    assert any("loss" in fields for _step, _message, fields in progress_events)
    assert any("siteLabel" in fields for _step, _message, fields in progress_events)


def test_machine_xy_solver_moves_camera_without_candidate_camera_paths(
    monkeypatch, tmp_path
):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    real_random = random.Random
    monkeypatch.setattr(
        machine_geometry_module.random, "Random", lambda: real_random(0)
    )
    measurements = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "alternating_side",
            "rollerIndex": None,
            "gcodeLine": "~anchorToTarget(A1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
    ]

    candidate_calls = []

    def candidate_machine_path(roller_y_cals, camera_offset=None):
        candidate_calls.append(
            {
                "roller_y_cals": tuple(float(value) for value in roller_y_cals[:4]),
                "camera_offset": camera_offset,
            }
        )
        return "machine.json"

    monkeypatch.setattr(
        service, "_candidateMachineCalibrationPath", candidate_machine_path
    )
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["actualWireX"]) - 10.0,
            "projectedY": float(measurement["actualWireY"]) + 1.5,
        },
    )

    evaluation = service._evaluateMachineXY(
        measurements,
        layer="U",
        operation_id="op-camera-only",
        layer_path="layer.json",
        nominal_roller_y=21.0,
        current_camera_offset=(0.0, 0.0),
        initial_roller_y_cals=(24.0, 23.0, 18.0, 17.0),
    )

    # B2001 is an X-natural (top/bottom) corner, so the camera absorbs the
    # on-axis X residual but leaves the off-axis Y residual alone -- a corner
    # offset cannot represent it, and pulling the camera off-axis to chase it
    # would shift that corner's commanded head (the command-target invariance
    # gate would then reject the apply).
    assert evaluation["cameraOffsetX"] == pytest.approx(10.0, abs=1e-9)
    assert evaluation["cameraOffsetY"] == pytest.approx(0.0, abs=1e-9)

    assert all(call["camera_offset"] is None for call in candidate_calls)


def test_machine_xy_solver_groups_site_label_offsets_across_line_keys(
    monkeypatch, tmp_path
):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    real_random = random.Random
    monkeypatch.setattr(
        machine_geometry_module.random, "Random", lambda: real_random(0)
    )
    measurements = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "siteLabel": "Foot A corner",
            "lineKey": "(1,1)",
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
        {
            "id": "m2",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "siteLabel": "Foot A corner",
            "lineKey": "(2,1)",
            "gcodeLine": "~anchorToTarget(B1202,B2002) (2,1)",
            "effectiveCameraX": 120.0,
            "rawCameraY": 260.0,
            "actualWireX": 130.0,
            "actualWireY": 255.0,
        },
    ]

    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["actualWireX"]) - 10.0,
            "projectedY": float(measurement["actualWireY"])
            + 5.0
            + (float(kwargs["roller_y_cals"][measurement["rollerIndex"]]) - 23.0),
        },
    )

    evaluation = service._evaluateMachineXY(
        measurements,
        layer="U",
        operation_id="op-test-3",
        layer_path="layer.json",
        nominal_roller_y=21.0,
        current_camera_offset=(10.0, -5.0),
        initial_roller_y_cals=(24.0, 27.0, 18.0, 17.0),
    )

    assert list(evaluation["siteOffsets"].keys()) == ["Foot A corner"]
    assert len(evaluation["lineOffsetOverrides"]) == 2
    line_offsets = list(evaluation["lineOffsetOverrides"].values())
    assert line_offsets[0]["x"] == pytest.approx(line_offsets[1]["x"], abs=1e-9)
    assert line_offsets[0]["y"] == pytest.approx(line_offsets[1]["y"], abs=1e-9)
    assert evaluation["siteOffsetItems"][0]["siteLabel"] == "Foot A corner"


def test_machine_xy_solver_clamps_camera_within_bounds(monkeypatch, tmp_path):
    # Roller calibrations are now held constant; the solver only clamps the
    # camera offset to its +/- bound.  This used to also clamp roller-Y.
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    real_random = random.Random
    monkeypatch.setattr(
        machine_geometry_module.random, "Random", lambda: real_random(0)
    )
    measurements = [
        {
            "id": "m0",
            "layer": "U",
            "kind": "alternating_side",
            "rollerIndex": None,
            "lineKey": "(1,0)",
            "gcodeLine": "~anchorToTarget(A1201,B2001) (1,0)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "lineKey": "(1,1)",
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
        {
            "id": "m2",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "lineKey": "(1,2)",
            "gcodeLine": "~anchorToTarget(B1202,B2002) (1,2)",
            "effectiveCameraX": 120.0,
            "rawCameraY": 230.0,
            "actualWireX": 130.0,
            "actualWireY": 225.0,
        },
    ]

    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["actualWireX"]) - 20.0,
            "projectedY": float(measurement["actualWireY"]) - 5.0,
        },
    )

    evaluation = service._evaluateMachineXY(
        measurements,
        layer="U",
        operation_id="op-bounds",
        layer_path="layer.json",
        nominal_roller_y=21.0,
        current_camera_offset=(10.0, -5.0),
        initial_roller_y_cals=(24.0, 23.0, 18.0, 17.0),
    )

    # Every measured corner here is X-natural (B2001/B2002), so only the X
    # residual drives the camera -- it clamps at the +10 mm bound (20.0).  The
    # off-axis Y residual is not absorbed (it stays at the starting -5.0): a
    # corner offset cannot represent it and moving the camera off-axis would
    # break command-target invariance for these corners.
    assert evaluation["cameraOffsetX"] == pytest.approx(20.0, abs=1e-9)
    assert evaluation["cameraOffsetY"] == pytest.approx(-5.0, abs=1e-9)
    # Roller cals untouched.
    assert evaluation["rollerYCals"] == [24.0, 23.0, 18.0, 17.0]
    expected_camera_delta_norm = (
        ((evaluation["cameraOffsetX"] - 10.0) ** 2)
        + ((evaluation["cameraOffsetY"] - (-5.0)) ** 2)
    ) ** 0.5
    assert evaluation["score"]["cameraOffsetDeltaNorm"] == pytest.approx(
        expected_camera_delta_norm,
        abs=1e-9,
    )
    assert evaluation["score"]["rollerOffsetNorm"] == pytest.approx(0.0, abs=1e-9)


def test_translate_projection_payload_moves_same_side_transfer_edge():
    translated = machine_geometry_module._translate_projection_payload(
        {
            "sameSide": True,
            "projectedHeadX": 60.0,
            "projectedHeadY": 100.0,
            "projectedX": 55.0,
            "projectedY": 95.0,
            "anchorTangentX": 40.0,
            "anchorTangentY": 40.0,
            "targetTangentX": 80.0,
            "targetTangentY": 80.0,
            "anchorZ": 0.0,
            "headZ": 10.0,
            "headArmLength": 5.0,
            "headRollerRadius": 2.0,
            "headRollerGap": 1.0,
            "transferBounds": {
                "left": 0.0,
                "right": 120.0,
                "top": 100.0,
                "bottom": 0.0,
            },
            "transferEdge": "top",
        },
        (10.0, 5.0),
    )

    assert translated["projectedHeadX"] == pytest.approx(65.0, abs=1e-9)
    assert translated["projectedHeadY"] == pytest.approx(100.0, abs=1e-9)


def test_implied_pin_offset_falls_back_without_geometry():
    # A simplified projection (only wire XY) keeps the plain head-vs-wire
    # residual so legacy/test projections still behave.
    offset = machine_geometry_module._implied_pin_offset(
        100.0, 50.0, {"projectedX": 90.0, "projectedY": 45.0}
    )
    assert offset == pytest.approx((10.0, 5.0))


def test_implied_pin_offset_uses_head_not_wire_contact():
    # The observation is a head position; the wire-contact point sits far
    # away along the arm.  The residual must be measured against the head
    # target (then scaled), NOT the wire contact -- otherwise the arm
    # displacement leaks in as a bogus ~80 mm residual (the original bug).
    projection = {
        "sameSide": True,
        "projectedHeadX": 20.0,
        "projectedHeadY": 0.0,
        "projectedX": 100.0,  # wire contact, 80 mm off in X from the head
        "projectedY": 0.0,
        # anchor->target (100) == anchor->wire (100) => ratio 1.0, so the
        # head residual passes through unscaled and stays ~0.
        "anchorPinX": 0.0,
        "anchorPinY": 0.0,
        "anchorPinZ": 0.0,
        "targetPinX": 100.0,
        "targetPinY": 0.0,
        "targetPinZ": 0.0,
        "headZ": 0.0,
    }
    # Old (buggy) metric would be observed - projectedX = 20.3 - 100 = -79.7.
    offset_x, offset_y = machine_geometry_module._implied_pin_offset(
        20.3, 0.0, projection
    )
    assert offset_x == pytest.approx(0.3, abs=1e-6)
    assert offset_y == pytest.approx(0.0, abs=1e-6)


def test_implied_pin_offset_scales_same_side_by_lever_arm():
    # Head sweeps a longer lever arm than the pin: a 10 mm head error
    # becomes d_at/d_ah * 10 mm of pin shift.
    projection = {
        "sameSide": True,
        "projectedHeadX": 100.0,
        "projectedHeadY": 0.0,
        "projectedX": 100.0,  # anchor->head (wire target) distance = 100
        "projectedY": 0.0,
        "anchorPinX": 0.0,
        "anchorPinY": 0.0,
        "anchorPinZ": 0.0,
        "targetPinX": 25.0,  # anchor->target distance = 25 => ratio 0.25
        "targetPinY": 0.0,
        "targetPinZ": 0.0,
        "headZ": 0.0,
    }
    offset_x, offset_y = machine_geometry_module._implied_pin_offset(
        110.0, 4.0, projection
    )
    assert offset_x == pytest.approx(2.5, abs=1e-6)
    assert offset_y == pytest.approx(1.0, abs=1e-6)


def test_implied_pin_offset_scales_only_dominant_plane_cross_side():
    # Cross-side: the pin pair separates mainly in X, so only the X axis is
    # scaled (in the XZ plane); Y passes through unscaled.
    projection = {
        "sameSide": False,
        "projectedHeadX": 100.0,
        "projectedHeadY": 200.0,
        "projectedX": 0.0,
        "projectedY": 0.0,
        "anchorPinX": 0.0,
        "anchorPinY": 0.0,
        "anchorPinZ": 0.0,
        "targetPinX": 40.0,  # |dx| dominates => XZ plane
        "targetPinY": 5.0,
        "targetPinZ": 30.0,  # d_at = hypot(40, 30) = 50
        "headZ": 0.0,  # d_ah = hypot(100, 0) = 100 => ratio 0.5
    }
    offset_x, offset_y = machine_geometry_module._implied_pin_offset(
        110.0, 207.0, projection
    )
    assert offset_x == pytest.approx(5.0, abs=1e-6)  # (110-100) * 0.5
    assert offset_y == pytest.approx(7.0, abs=1e-6)  # (207-200), unscaled


def test_project_measurement_bypasses_uv_head_target_view(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    measurement = {
        "id": "m1",
        "layer": "U",
        "kind": "same_side",
        "rollerIndex": 1,
        "lineKey": "(1,1)",
        "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
    }

    monkeypatch.setattr(
        uv_head_target_module,
        "compute_uv_anchor_to_target_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy uv_head_target projection should not be used")
        ),
    )

    projection = service._projectMeasurement(
        measurement,
        layer_path=str(REPO_ROOT / "config" / "APA" / "U_Calibration.json"),
        machine_path=str(REPO_ROOT / "config" / "machineCalibration.json"),
        roller_y_cals=(24.0, 23.0, 18.0, 17.0),
    )

    assert isinstance(projection["projectedX"], float)
    assert isinstance(projection["projectedY"], float)


def test_machine_xy_solve_records_progress_and_success(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)

    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )

    def evaluate(measurements, *, progress_callback=None, **kwargs):
        assert progress_callback is not None
        progress_callback("test_step", "Test progress update.")
        return {
            "cameraOffsetX": 11.0,
            "cameraOffsetY": -6.0,
            "rollerYCals": [21.0, 21.0, 21.0, 21.0],
            "score": {
                "lineOffsetNorm": 0.0,
                "rollerOffsetNorm": 0.0,
                "cameraOffsetDeltaNorm": 2.0,
            },
            "summaries": [],
        }

    monkeypatch.setattr(service, "_evaluateMachineXY", evaluate)

    result = service.solveMachineXY()
    draft = service._layerDraft("U")
    status = draft["machineSolveStatus"]

    assert result["fitError"] is None
    assert status["status"] == "succeeded"
    assert status["step"] == "done"
    assert status["fitError"] is None
    assert any(entry[1] == "SOLVE_MACHINE_XY_START" for entry in process._log.entries)
    assert any(
        entry[1] == "SOLVE_MACHINE_XY_PROGRESS" for entry in process._log.entries
    )
    assert any(entry[1] == "SOLVE_MACHINE_XY_DONE" for entry in process._log.entries)


def test_machine_xy_solve_does_not_touch_live_recipe_or_calibration(
    monkeypatch, tmp_path
):
    """The solver must only ever write a *draft*.

    Regenerating the live recipe (G-code) and saving the live machine
    calibration are reserved for ``applyMachineXY`` -- the explicit
    "user tells it to" action.  This pins that contract so a future change
    cannot quietly let a solve mutate live state.
    """
    process = _Process(tmp_path)

    recipe_calls = {"generate": 0, "replace": 0}

    def _record_generate(*args, **kwargs):
        recipe_calls["generate"] += 1
        return {"ok": True, "data": {}}

    def _record_replace(*args, **kwargs):
        recipe_calls["replace"] += 1
        return {"ok": True}

    for recipe in (process.uTemplateRecipe, process.vTemplateRecipe):
        recipe.generateRecipeFile = _record_generate
        recipe.replaceLineOffsetOverrides = _record_replace

    service = MachineGeometryCalibration(process)
    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )

    def evaluate(measurements, *, progress_callback=None, **kwargs):
        if progress_callback is not None:
            progress_callback("test_step", "Test progress update.")
        return {
            "cameraOffsetX": 11.0,
            "cameraOffsetY": -6.0,
            "rollerYCals": [21.0, 21.0, 21.0, 21.0],
            "score": {
                "lineOffsetNorm": 0.0,
                "rollerOffsetNorm": 0.0,
                "cameraOffsetDeltaNorm": 2.0,
            },
            "summaries": [],
            "lineOffsetOverrides": {"(1,1)": {"x": 3.0, "y": -1.0}},
        }

    monkeypatch.setattr(service, "_evaluateMachineXY", evaluate)

    result = service.solveMachineXY()

    # The solve succeeded and staged its result in the draft...
    assert result["fitError"] is None
    draft = service._layerDraft("U")
    assert draft["lineOffsetOverrides"] == {"(1,1)": {"x": 3.0, "y": -1.0}}

    # ...but it must NOT have regenerated the live recipe or saved the live
    # machine calibration.  Those happen only on apply.
    assert recipe_calls == {"generate": 0, "replace": 0}
    assert process._machineCalibration.save_calls == 0


def test_machine_xy_solve_records_failure(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)

    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )

    def fail_evaluate(*args, **kwargs):
        raise RuntimeError("projection failed")

    monkeypatch.setattr(service, "_evaluateMachineXY", fail_evaluate)

    with pytest.raises(ValueError, match="Machine XY solve failed: projection failed"):
        service.solveMachineXY()

    draft = service._layerDraft("U")
    status = draft["machineSolveStatus"]
    solve = draft["machineSolve"]

    assert status["status"] == "failed"
    assert "projection failed" in status["fitError"]
    assert "projection failed" in solve["fitError"]
    assert any(entry[1] == "SOLVE_MACHINE_XY_FAILED" for entry in process._log.entries)


def test_machine_xy_cancel_request_marks_running_status(tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    draft = service._layerDraft("U", create=True)
    draft["machineSolveStatus"] = {
        "operationId": "op-1",
        "status": "running",
        "message": "Working.",
    }
    service._registerMachineSolveOperation("op-1")

    result = service.cancelMachineXY()

    status = service._layerDraft("U")["machineSolveStatus"]
    assert result["canceled"] is True
    assert status["status"] == "cancel_requested"
    assert status["cancelRequested"] is True
    assert "current evaluation batch" in status["message"]


def test_machine_xy_kill_request_marks_running_status(tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    draft = service._layerDraft("U", create=True)
    draft["machineSolveStatus"] = {
        "operationId": "op-1",
        "status": "running",
        "message": "Working.",
    }
    service._registerMachineSolveOperation("op-1")

    class _Evaluation:
        def __init__(self):
            self.terminated = False

        def terminate(self):
            self.terminated = True

    evaluation = _Evaluation()
    service._registerActiveMachineSolveEvaluation("op-1", evaluation)

    result = service.killMachineXY()

    status = service._layerDraft("U")["machineSolveStatus"]
    assert result["killed"] is True
    assert evaluation.terminated is True
    assert status["status"] == "kill_requested"
    assert status["killRequested"] is True
    assert status["terminatedEvaluations"] == 1


def test_machine_xy_reconcile_stale_running_status(tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    draft = service._layerDraft("U", create=True)
    draft["machineSolveStatus"] = {
        "operationId": "op-stale",
        "status": "kill_requested",
        "message": "Kill requested. Terminating all active evaluations.",
    }

    status = service._reconcileMachineSolveStatus("U")

    assert status["status"] == "interrupted"
    assert status["killRequested"] is False
    assert "no longer running" in status["message"]


def test_machine_xy_cancel_reconciles_stale_running_status(tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    draft = service._layerDraft("U", create=True)
    draft["machineSolveStatus"] = {
        "operationId": "op-stale",
        "status": "running",
        "message": "Working.",
    }

    result = service.cancelMachineXY()

    status = service._layerDraft("U")["machineSolveStatus"]
    assert result["canceled"] is False
    assert status["status"] == "interrupted"
    assert "No Machine XY solve is active." in result["message"]


def test_machine_xy_solve_can_be_canceled(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "lineKey": "(1,1)",
            "gcodeLine": "~anchorToTarget(B1201,B2001)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
    ]

    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )
    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    monkeypatch.setattr(service, "_removeTemporaryCandidatePath", lambda path: None)

    call_count = {"value": 0}

    def project_measurement(measurement, **kwargs):
        call_count["value"] += 1
        if call_count["value"] == 1:
            cancel_result = service.cancelMachineXY()
            assert cancel_result["canceled"] is True
        return {
            "projectedX": float(measurement["actualWireX"]),
            "projectedY": float(measurement["actualWireY"]),
        }

    monkeypatch.setattr(service, "_projectMeasurement", project_measurement)

    result = service.solveMachineXY()

    status = service._layerDraft("U")["machineSolveStatus"]
    assert result["canceled"] is True
    assert result["fitError"] is None
    assert status["status"] == "canceled"
    assert status["fitError"] is None
    assert any(
        entry[1] == "SOLVE_MACHINE_XY_CANCELED" for entry in process._log.entries
    )


def test_machine_xy_solve_can_be_killed(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "lineKey": "(1,1)",
            "gcodeLine": "~anchorToTarget(B1201,B2001)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
    ]

    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )
    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    monkeypatch.setattr(service, "_removeTemporaryCandidatePath", lambda path: None)

    started = threading.Event()

    class _FakeEvaluation:
        def __init__(self):
            self.terminated = False
            self.closed = False

        @property
        def exitcode(self):
            return -15 if self.terminated else None

        def start(self):
            started.set()

        def is_alive(self):
            return not self.terminated

        def poll(self, timeout=0.0):
            time.sleep(min(float(timeout), 0.02))
            return None

        def terminate(self):
            self.terminated = True

        def close(self):
            self.closed = True

    evaluation = _FakeEvaluation()
    monkeypatch.setattr(
        service,
        "_spawnMachineSolveEvaluation",
        lambda *args, **kwargs: evaluation,
    )

    solve_result = {}
    solve_thread = threading.Thread(
        target=lambda: solve_result.setdefault("value", service.solveMachineXY()),
        daemon=True,
    )
    solve_thread.start()
    assert started.wait(timeout=1.0)

    kill_result = service.killMachineXY()

    solve_thread.join(timeout=1.0)
    assert not solve_thread.is_alive()
    status = service._layerDraft("U")["machineSolveStatus"]
    assert kill_result["killed"] is True
    assert evaluation.terminated is True
    assert evaluation.closed is True
    assert solve_result["value"]["killed"] is True
    assert status["status"] == "killed"
    assert any(entry[1] == "SOLVE_MACHINE_XY_KILLED" for entry in process._log.entries)


def test_machine_xy_candidate_file_does_not_use_atomic_replace(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)

    def fail_save(self):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(machine_geometry_module.MachineCalibration, "save", fail_save)

    path = service._candidateMachineCalibrationPath(
        (21.0, 22.0, 23.0, 24.0),
        camera_offset=(1.5, -2.5),
    )
    second_path = service._candidateMachineCalibrationPath(
        (21.0, 22.0, 23.0, 24.0),
        camera_offset=(9.0, 8.0),
    )

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)

    assert second_path == path
    assert data["cameraWireOffsetX"] == pytest.approx(10.0, abs=1e-9)
    assert data["cameraWireOffsetY"] == pytest.approx(-5.0, abs=1e-9)
    assert data["rollerArmCalibration"]["fitted_y_cals"] == [21.0, 22.0, 23.0, 24.0]
    service._removeTemporaryCandidatePath(path)


def test_machine_xy_solve_rejects_invalid_line_offsets(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "lineKey": "(1,1)",
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
    ]

    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )
    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["effectiveCameraX"]) + 100.0,
            "projectedY": float(measurement["rawCameraY"]) + 4.0,
        },
    )

    with pytest.raises(ValueError, match=r"\(1,1\).*deltaX="):
        service.solveMachineXY()


def test_machine_geometry_state_save_retries_permission_error(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    service._loadState()["measurementRevision"] = 7

    attempts = {"count": 0}
    real_replace = machine_geometry_module.os.replace

    def flaky_replace(src, dst):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise PermissionError(13, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(machine_geometry_module.os, "replace", flaky_replace)

    service._saveState()

    with open(service._statePath(), encoding="utf-8") as handle:
        data = json.load(handle)

    assert attempts["count"] >= 2
    assert data["measurementRevision"] == 7


def test_geometry_parameter_edits_are_blocked_during_active_gcode(tmp_path):
    process = _Process(tmp_path, active=True)
    service = MachineGeometryCalibration(process)

    with pytest.raises(ValueError, match="Cannot change machine geometry"):
        service.setLineOffsetOverride("U", "(1,1)", 1.0, 2.0)


def test_sanity_check_passes_with_consistent_line_offsets(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "lineKey": "(1,1)",
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
    ]

    machine_draft = {
        "layer": "U",
        "cameraWireOffsetX": 10.0,
        "cameraWireOffsetY": -5.0,
        "rollerYCals": [24.0, 23.0, 18.0, 17.0],
    }
    line_offset_overrides = {
        "(1,1)": {"x": 3.0, "y": -2.0},
    }

    def project_payload(
        measurement,
        *,
        layer_path,
        roller_y_cals,
        _layer_calibration=None,
        _machine_calibration=None,
        **kwargs,
    ):
        return {
            "projectedX": float(measurement["actualWireX"])
            - float(line_offset_overrides["(1,1)"]["x"])
            - 10.0,
            "projectedY": float(measurement["actualWireY"])
            - float(line_offset_overrides["(1,1)"]["y"])
            + 5.0,
        }

    monkeypatch.setattr(
        machine_geometry_module,
        "_project_machine_xy_measurement_payload",
        project_payload,
    )
    monkeypatch.setattr(
        machine_geometry_module,
        "_translate_projection_payload",
        lambda payload, camera_offset: {
            "projectedX": float(payload["projectedX"]) + float(camera_offset[0]),
            "projectedY": float(payload["projectedY"]) + float(camera_offset[1]),
        },
    )
    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )
    monkeypatch.setattr(
        service, "_candidateMachineCalibrationObject", lambda roller_y_cals: None
    )

    result = service._sanityCheckLineOffsets("U", machine_draft, line_offset_overrides)

    assert result["ok"] is True
    assert result["checkedCount"] == 1
    assert result["maxDiscrepancyX"] < 0.01
    assert result["maxDiscrepancyY"] < 0.01


def test_sanity_check_fails_with_tampered_line_offsets(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "lineKey": "(1,1)",
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
    ]

    machine_draft = {
        "layer": "U",
        "cameraWireOffsetX": 10.0,
        "cameraWireOffsetY": -5.0,
        "rollerYCals": [24.0, 23.0, 18.0, 17.0],
    }

    def project_payload(
        measurement,
        *,
        layer_path,
        roller_y_cals,
        _layer_calibration=None,
        _machine_calibration=None,
        **kwargs,
    ):
        return {
            "projectedX": float(measurement["actualWireX"]) - 3.0 - 10.0,
            "projectedY": float(measurement["actualWireY"]) - (-2.0) + 5.0,
        }

    monkeypatch.setattr(
        machine_geometry_module,
        "_project_machine_xy_measurement_payload",
        project_payload,
    )
    monkeypatch.setattr(
        machine_geometry_module,
        "_translate_projection_payload",
        lambda payload, camera_offset: {
            "projectedX": float(payload["projectedX"]) + float(camera_offset[0]),
            "projectedY": float(payload["projectedY"]) + float(camera_offset[1]),
        },
    )
    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )
    monkeypatch.setattr(
        service, "_candidateMachineCalibrationObject", lambda roller_y_cals: None
    )

    # B2001 is the "Top B corner - foot end" target, whose natural axis is X.
    # The X tamper (on-axis) must be caught; the Y tamper is off-axis and is
    # zeroed by the natural-axis policy on both sides, so it cannot register.
    tampered_overrides = {
        "(1,1)": {"x": 50.0, "y": -40.0},
    }

    result = service._sanityCheckLineOffsets("U", machine_draft, tampered_overrides)

    assert result["ok"] is False
    assert result["checkedCount"] == 1
    assert result["discrepancyCount"] == 1
    assert result["maxDiscrepancyX"] > 1.0
    assert result["maxDiscrepancyY"] < 0.01


def test_apply_machine_xy_rejects_inconsistent_draft(monkeypatch, tmp_path):
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [
        {
            "id": "m1",
            "layer": "U",
            "kind": "same_side",
            "rollerIndex": 1,
            "lineKey": "(1,1)",
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
            "effectiveCameraX": 100.0,
            "rawCameraY": 200.0,
            "actualWireX": 110.0,
            "actualWireY": 195.0,
        },
    ]
    draft = service._layerDraft("U", create=True)
    draft["lineOffsetOverrides"] = {
        "(1,1)": {"x": 50.0, "y": -40.0},
    }
    state["machineDraft"] = {
        "layer": "U",
        "cameraWireOffsetX": 10.0,
        "cameraWireOffsetY": -5.0,
        "rollerYCals": [24.0, 23.0, 18.0, 17.0],
    }

    def project_payload(
        measurement,
        *,
        layer_path,
        roller_y_cals,
        _layer_calibration=None,
        _machine_calibration=None,
        **kwargs,
    ):
        return {
            "projectedX": float(measurement["actualWireX"]) - 3.0 - 10.0,
            "projectedY": float(measurement["actualWireY"]) - (-2.0) + 5.0,
        }

    monkeypatch.setattr(
        machine_geometry_module,
        "_project_machine_xy_measurement_payload",
        project_payload,
    )
    monkeypatch.setattr(
        machine_geometry_module,
        "_translate_projection_payload",
        lambda payload, camera_offset: {
            "projectedX": float(payload["projectedX"]) + float(camera_offset[0]),
            "projectedY": float(payload["projectedY"]) + float(camera_offset[1]),
        },
    )
    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )
    monkeypatch.setattr(
        service, "_candidateMachineCalibrationObject", lambda roller_y_cals: None
    )

    with pytest.raises(ValueError, match="Line offset sanity check failed"):
        service.applyMachineXY()


def _install_command_target_fakes(
    monkeypatch,
    service,
    *,
    live_offsets,
    site_label="Top B corner - foot end",
    offset_id="top_b_foot_end",
    natural_axis="x",
):
    """Stub projection + template so head command == cameraOffset + lineOffset.

    The fake projection reads the offset baked into the (synthetic) g-code line
    by ``_commandTargetHead`` and adds the candidate camera-wire offset, so the
    commanded head target is exactly ``camera_offset + corner_offset`` on each
    axis -- letting a test dial the live/drafted camera and corner offsets to
    engineer an exact match or a deliberate move.
    """
    import re

    offset_pattern = re.compile(r"offset=\((-?[0-9.]+),(-?[0-9.]+)\)")

    def project_payload(
        measurement,
        *,
        layer_path,
        roller_y_cals,
        cameraWireOffset=(0.0, 0.0),
        _layer_calibration=None,
        _machine_calibration=None,
        **kwargs,
    ):
        match = offset_pattern.search(str(measurement["gcodeLine"]))
        offset_x = float(match.group(1)) if match else 0.0
        offset_y = float(match.group(2)) if match else 0.0
        return {
            "projectedHeadX": float(cameraWireOffset[0]) + offset_x,
            "projectedHeadY": float(cameraWireOffset[1]) + offset_y,
        }

    monkeypatch.setattr(
        machine_geometry_module,
        "_project_machine_xy_measurement_payload",
        project_payload,
    )
    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )
    monkeypatch.setattr(
        service, "_candidateMachineCalibrationObject", lambda roller_y_cals: None
    )
    fake_template = SimpleNamespace(
        LABEL_TO_OFFSET_ID={site_label: offset_id},
        OFFSET_NATURAL_AXIS={offset_id: natural_axis},
        getState=lambda: {"offsets": dict(live_offsets)},
    )
    monkeypatch.setattr(service, "_templateService", lambda layer: fake_template)
    return fake_template


def _command_target_measurement():
    return {
        "id": "m1",
        "layer": "U",
        "kind": "alternating_side",
        "lineKey": "(1,1)",
        "siteLabel": "Top B corner - foot end",
        "gcodeLine": "~anchorToTarget(B1201,B2001) (1,1)",
        "effectiveCameraX": 100.0,
        "rawCameraY": 200.0,
        "actualWireX": 110.0,
        "actualWireY": 195.0,
    }


def test_command_target_check_passes_when_recalibration_preserves_target(
    monkeypatch, tmp_path
):
    # Live calibration: camera (10, -5), corner X = 3 -> head X = 13.
    # Drafted calibration: camera (11, -5), corner X = 2 -> head X = 13.
    # The +1 camera shift is cancelled by the -1 corner shift, so the commanded
    # head target is unchanged and the check passes.
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [_command_target_measurement()]

    _install_command_target_fakes(
        monkeypatch, service, live_offsets={"top_b_foot_end": {"x": 3.0, "y": 0.0}}
    )

    machine_draft = {"cameraWireOffsetX": 11.0, "cameraWireOffsetY": -5.0}
    overrides = {
        "(1,1)": {
            "x": 2.0,
            "y": 0.0,
            "siteLabel": "Top B corner - foot end",
            "measurementIds": ["m1"],
        }
    }

    result = service._checkCommandTargetInvariance("U", machine_draft, overrides)

    assert result["ok"] is True
    assert result["checkedCount"] == 1
    assert result["discrepancyCount"] == 0
    assert result["maxDiscrepancyX"] < 0.01
    assert result["maxDiscrepancyY"] < 0.01


def test_command_target_check_fails_when_target_moves(monkeypatch, tmp_path):
    # Same live calibration (head X = 13) but the drafted corner over-corrects to
    # 5 (head X = 16): the camera/corner shifts no longer cancel, so the commanded
    # head target moves 3 mm and the check fails.
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [_command_target_measurement()]

    _install_command_target_fakes(
        monkeypatch, service, live_offsets={"top_b_foot_end": {"x": 3.0, "y": 0.0}}
    )

    machine_draft = {"cameraWireOffsetX": 11.0, "cameraWireOffsetY": -5.0}
    overrides = {
        "(1,1)": {
            "x": 5.0,
            "y": 0.0,
            "siteLabel": "Top B corner - foot end",
            "measurementIds": ["m1"],
        }
    }

    result = service._checkCommandTargetInvariance("U", machine_draft, overrides)

    assert result["ok"] is False
    assert result["checkedCount"] == 1
    assert result["discrepancyCount"] == 1
    assert result["maxDiscrepancyX"] == pytest.approx(3.0, abs=1e-6)
    assert result["maxDiscrepancyY"] < 0.01
    assert result["discrepancies"][0]["lineKey"] == "(1,1)"


def test_apply_machine_xy_rejects_moved_command_target(monkeypatch, tmp_path):
    """Apply must hard-fail when the draft would move a commanded head target,
    even if the line-offset sanity check is satisfied."""
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["measurements"] = [_command_target_measurement()]
    state["machineDraft"] = {
        "layer": "U",
        "cameraWireOffsetX": 11.0,
        "cameraWireOffsetY": -5.0,
    }
    draft = service._layerDraft("U", create=True)
    draft["lineOffsetOverrides"] = {
        "(1,1)": {
            "x": 5.0,
            "y": 0.0,
            "siteLabel": "Top B corner - foot end",
            "measurementIds": ["m1"],
        }
    }

    # The line-offset sanity check is a separate gate; pass it so the test
    # isolates the command-target gate.
    monkeypatch.setattr(
        service,
        "_sanityCheckLineOffsets",
        lambda *args, **kwargs: {
            "ok": True,
            "checkedCount": 1,
            "maxDiscrepancyX": 0.0,
            "maxDiscrepancyY": 0.0,
        },
    )
    _install_command_target_fakes(
        monkeypatch, service, live_offsets={"top_b_foot_end": {"x": 3.0, "y": 0.0}}
    )

    with pytest.raises(ValueError, match="Command target invariance check failed"):
        service.applyMachineXY()


def test_corner_offset_items_collapses_overrides_to_corners():
    """The solver fans one per-corner offset across several measured lines;
    the page helper must collapse them back to one row per corner, align
    Current (live) with Draft (solved), drop unmapped sites, and constrain each
    draft offset to the corner's natural axis (top/bottom -> X, head/foot -> Y,
    quantised to 0.1 mm) so Draft shows exactly what Apply will write."""
    template = SimpleNamespace(
        LABEL_TO_OFFSET_ID={
            "Top B corner - head end": "top_b_head_end",
            "Foot A corner": "foot_a_corner",
        },
        OFFSET_IDS=("foot_a_corner", "top_b_head_end"),
        # Top/bottom corners move along X; head/foot corners along Y.
        OFFSET_NATURAL_AXIS={"top_b_head_end": "x", "foot_a_corner": "y"},
    )
    overrides = {
        "(301,13)": {
            "x": 7.04,
            "y": -2.0,
            "siteLabel": "Top B corner - head end",
            "measurementIds": ["a"],
        },
        "(302,13)": {
            "x": 7.04,
            "y": -2.0,
            "siteLabel": "Top B corner - head end",
            "measurementIds": ["b"],
        },
        "(301,18)": {
            "x": 0.03,
            "y": 10.04,
            "siteLabel": "Foot A corner",
            "measurementIds": ["c"],
        },
        "(301,99)": {"x": 1.0, "y": 1.0, "siteLabel": "Unmapped corner"},
    }
    live_offsets = {
        "top_b_head_end": {"x": 1.1, "y": 0.0},
        "foot_a_corner": {"x": 0.0, "y": 0.0},
    }

    current, draft = machine_geometry_module._corner_offset_items(
        template, overrides, live_offsets
    )

    # One row per mapped corner, ordered by OFFSET_IDS, unmapped site dropped.
    assert [item["offsetId"] for item in draft] == ["foot_a_corner", "top_b_head_end"]

    # Top corner: on-axis X quantised to 0.1 mm, off-axis Y zeroed.
    top_b = next(item for item in draft if item["offsetId"] == "top_b_head_end")
    assert (top_b["x"], top_b["y"]) == (7.0, 0.0)
    assert sorted(top_b["measurementIds"]) == ["a", "b"]
    assert sorted(top_b["lineKeys"]) == ["(301,13)", "(302,13)"]

    # Foot corner: off-axis X zeroed, on-axis Y quantised to 0.1 mm.
    foot_a = next(item for item in draft if item["offsetId"] == "foot_a_corner")
    assert (foot_a["x"], foot_a["y"]) == (0.0, 10.0)

    # Current rows align row-for-row with Draft and carry the live offset.
    assert [item["offsetId"] for item in current] == ["foot_a_corner", "top_b_head_end"]
    current_top_b = next(
        item for item in current if item["offsetId"] == "top_b_head_end"
    )
    assert (current_top_b["x"], current_top_b["y"]) == (1.1, 0.0)


def test_apply_machine_xy_writes_per_corner_offsets(monkeypatch, tmp_path):
    """Apply must write the solved offset to each *corner* (so it lands on
    every corner of that kind at regeneration), not as per-line overrides."""
    process = _Process(tmp_path)

    class _RecordingTemplate:
        LABEL_TO_OFFSET_ID = {
            "Top B corner - head end": "top_b_head_end",
            "Foot A corner": "foot_a_corner",
        }
        OFFSET_IDS = ("top_b_head_end", "foot_a_corner")

        def __init__(self):
            self.offsets = {}
            self.set_calls = []
            self.replace_calls = 0
            self.generate_calls = 0
            self._lastGeneratedScriptVariant = "default"

        def getState(self):
            return {"offsets": dict(self.offsets)}

        def setOffset(self, offset_id, value=None, *, x=None, y=None):
            self.offsets[offset_id] = {"x": float(x), "y": float(y)}
            self.set_calls.append((offset_id, float(x), float(y)))
            return {"ok": True}

        def replaceLineOffsetOverrides(self, overrides):
            self.replace_calls += 1
            return {"ok": True}

        def generateRecipeFile(self, scriptVariant=None):
            self.generate_calls += 1
            return {"ok": True, "data": {}}

    template = _RecordingTemplate()
    process.uTemplateRecipe = template

    service = MachineGeometryCalibration(process)
    state = service._loadState()
    state["machineDraft"] = {
        "layer": "U",
        "cameraWireOffsetX": 11.0,
        "cameraWireOffsetY": -6.0,
        "siteOffsets": {},
        "siteOffsetItems": [],
    }
    draft = service._layerDraft("U", create=True)
    draft["lineOffsetOverrides"] = {
        "(301,13)": {
            "x": 7.0,
            "y": -2.0,
            "siteLabel": "Top B corner - head end",
            "measurementIds": ["a"],
        },
        "(302,13)": {
            "x": 7.0,
            "y": -2.0,
            "siteLabel": "Top B corner - head end",
            "measurementIds": ["b"],
        },
        "(301,18)": {
            "x": 0.0,
            "y": 10.0,
            "siteLabel": "Foot A corner",
            "measurementIds": ["c"],
        },
    }

    monkeypatch.setattr(
        service,
        "_sanityCheckLineOffsets",
        lambda *args, **kwargs: {
            "ok": True,
            "checkedCount": 3,
            "maxDiscrepancyX": 0.0,
            "maxDiscrepancyY": 0.0,
        },
    )
    monkeypatch.setattr(
        machine_geometry_module, "clear_uv_head_target_caches", lambda **kwargs: None
    )
    monkeypatch.setattr(
        machine_geometry_module,
        "roller_arm_calibration_to_dict",
        lambda _calibration: {},
    )

    service.applyMachineXY()

    # One setOffset per corner (collapsed across the measured lines); the live
    # per-line override store is left untouched; the recipe regenerates once.
    assert template.replace_calls == 0
    assert template.generate_calls == 1
    assert {
        offset_id: (x, y) for offset_id, x, y in template.set_calls
    } == {
        "top_b_head_end": (7.0, -2.0),
        "foot_a_corner": (0.0, 10.0),
    }
    assert process._machineCalibration.cameraWireOffsetX == 11.0


def test_machine_xy_solver_attributes_uniform_shift_to_camera_offset_x(
    monkeypatch, tmp_path
):
    # Every synthetic observation sits exactly (2, 0) away from its
    # projection at the starting camera offset, regardless of which wrap
    # or which line within a wrap it belongs to.  The only satisfying
    # change is to bump cameraOffsetX by +2; per-line overrides must
    # stay at (0, 0) because there is nothing line-specific to explain.
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    real_random = random.Random
    monkeypatch.setattr(
        machine_geometry_module.random, "Random", lambda: real_random(0)
    )

    line_specs = [
        ("(1,0)", 100.0, 200.0, 1),
        ("(1,3)", 140.0, 230.0, 2),
        ("(2,1)", 175.0, 260.0, 3),
        ("(3,2)", 215.0, 290.0, 1),
        ("(3,4)", 250.0, 315.0, 2),
        ("(5,0)", 295.0, 345.0, 3),
    ]
    measurements = []
    for index, (line_key, actual_x, actual_y, roller_index) in enumerate(line_specs):
        measurements.append(
            {
                "id": "m" + str(index + 1),
                "layer": "U",
                "kind": "same_side",
                "rollerIndex": roller_index,
                "gcodeLine": "~anchorToTarget(B1201,B2001) " + line_key,
                "lineKey": line_key,
                "siteLabel": line_key,
                "effectiveCameraX": actual_x,
                "rawCameraY": actual_y,
                "actualWireX": actual_x,
                "actualWireY": actual_y,
            }
        )

    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    # The projection sits 12 mm below the observed X (10 mm absorbed by
    # the starting camera offset + 2 mm uniform residual) and 5 mm above
    # the observed Y (cancelled exactly by the starting camera offset).
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["actualWireX"]) - 12.0,
            "projectedY": float(measurement["actualWireY"]) + 5.0,
        },
    )

    evaluation = service._evaluateMachineXY(
        measurements,
        layer="U",
        operation_id="op-uniform-shift",
        layer_path="layer.json",
        nominal_roller_y=21.0,
        current_camera_offset=(10.0, -5.0),
        initial_roller_y_cals=(24.0, 27.0, 18.0, 17.0),
    )

    assert evaluation["cameraOffsetX"] == pytest.approx(12.0, abs=0.1)
    assert evaluation["cameraOffsetY"] == pytest.approx(-5.0, abs=0.1)
    assert evaluation["rollerYCals"] == [24.0, 27.0, 18.0, 17.0]
    assert evaluation["valid"] is True

    overrides = evaluation["lineOffsetOverrides"]
    expected_keys = {spec[0] for spec in line_specs}
    assert set(overrides.keys()) == expected_keys
    for line_key, override in overrides.items():
        assert override["x"] == pytest.approx(0.0, abs=0.1), line_key
        assert override["y"] == pytest.approx(0.0, abs=0.1), line_key


def test_machine_xy_solver_accepts_reproduction_of_large_live_override(
    monkeypatch, tmp_path
):
    # Cross-side anchor sites carry per-line overrides that are tens to
    # hundreds of mm wide; the solver writes the full residual back out
    # as the new override.  When a re-solve reproduces the existing
    # overrides almost exactly (delta == 0), it must NOT trip the bound
    # check -- the bound is on the *change* in override, not its size.
    # Use overrides whose mean is zero so the camera-offset SGD has no
    # incentive to drift, which keeps the test focused on the validation
    # gate rather than the optimizer's bound-clamping behavior.
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    real_random = random.Random
    monkeypatch.setattr(
        machine_geometry_module.random, "Random", lambda: real_random(0)
    )

    line_specs = [
        ("(1,16)", "Head A corner", 200.0, +140.0),
        ("(2,16)", "Head B corner", 250.0, -140.0),
        ("(79,12)", "Top A corner - head end", 300.0, +95.0),
        ("(80,12)", "Top B corner - head end", 350.0, -95.0),
    ]
    measurements = [
        {
            "id": "m" + str(index),
            "layer": "U",
            "kind": "cross_side",
            "rollerIndex": 1 + (index % 4),
            "gcodeLine": "~anchorToTarget(B1201,B2001) " + line_key,
            "lineKey": line_key,
            "siteLabel": site,
            "effectiveCameraX": x,
            "rawCameraY": 100.0,
            "actualWireX": x,
            "actualWireY": 100.0,
        }
        for index, (line_key, site, x, _override_x) in enumerate(line_specs)
    ]
    live_line_offsets = {
        line_key: {"x": override_x, "y": 0.0}
        for line_key, _site, _x, override_x in line_specs
    }

    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["actualWireX"])
            - float(live_line_offsets[measurement["lineKey"]]["x"]),
            "projectedY": float(measurement["actualWireY"]),
        },
    )

    evaluation = service._evaluateMachineXY(
        measurements,
        layer="U",
        operation_id="op-large-live",
        layer_path="layer.json",
        nominal_roller_y=21.0,
        current_camera_offset=(0.0, 0.0),
        initial_roller_y_cals=(24.0, 27.0, 18.0, 17.0),
        live_line_offsets=live_line_offsets,
    )

    assert evaluation["valid"] is True
    assert evaluation["violationCount"] == 0
    overrides = evaluation["lineOffsetOverrides"]
    for line_key, _site, _x, override_x in line_specs:
        assert overrides[line_key]["x"] == pytest.approx(
            override_x, abs=machine_geometry_module._MAX_LINE_OFFSET_DELTA_X_MM
        ), line_key


def test_machine_xy_solver_rejects_excessive_change_from_live_override(
    monkeypatch, tmp_path
):
    # If the residual disagrees with the live override by more than the
    # delta bound, the solver must raise -- that's a meaningful change
    # the operator should review, even though the absolute override is
    # in the same ballpark as the previous one.
    process = _Process(tmp_path)
    service = MachineGeometryCalibration(process)
    real_random = random.Random
    monkeypatch.setattr(
        machine_geometry_module.random, "Random", lambda: real_random(0)
    )

    state = service._loadState()
    state["measurements"] = [
        {
            "id": "m_drifted",
            "layer": "U",
            "kind": "cross_side",
            "rollerIndex": 1,
            "lineKey": "(1,16)",
            "gcodeLine": "~anchorToTarget(B1201,B2001) (1,16)",
            "siteLabel": "Head A corner",
            "effectiveCameraX": 200.0,
            "rawCameraY": 100.0,
            "actualWireX": 200.0,
            "actualWireY": 100.0,
        },
    ]

    monkeypatch.setattr(
        service, "_candidateLayerCalibrationPath", lambda layer: "layer.json"
    )
    monkeypatch.setattr(
        service,
        "_candidateMachineCalibrationPath",
        lambda roller_y_cals, camera_offset=None: "machine.json",
    )
    # Residual is +140 mm in X but the live override is only +100 mm;
    # the +40 mm delta blows the 8 mm cap.
    monkeypatch.setattr(
        service,
        "_projectMeasurement",
        lambda measurement, **kwargs: {
            "projectedX": float(measurement["actualWireX"]) - 140.0,
            "projectedY": float(measurement["actualWireY"]),
        },
    )

    fake_template_state = {
        "lineOffsetOverrides": {"(1,16)": {"x": 100.0, "y": 0.0}}
    }

    class _FakeTemplate:
        def getState(self):
            return fake_template_state

    monkeypatch.setattr(
        service, "_templateService", lambda layer: _FakeTemplate()
    )
    # The active sanity check would otherwise re-project against a real
    # layer calibration that doesn't carry this fixture's synthetic
    # pins; stub it so the test stays focused on the bound check.
    monkeypatch.setattr(
        service,
        "_sanityCheckLineOffsets",
        lambda *args, **kwargs: {
            "ok": True,
            "checkedCount": 0,
            "maxDiscrepancyX": 0.0,
            "maxDiscrepancyY": 0.0,
            "discrepancyCount": 0,
            "discrepancies": [],
        },
    )

    with pytest.raises(ValueError, match=r"\(1,16\).*deltaX="):
        service.solveMachineXY()
