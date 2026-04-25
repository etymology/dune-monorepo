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
        self._io = _IO(100.0, 200.0, 30.0)
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


def test_machine_xy_solver_optimizes_measured_roller_and_keeps_others(
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
            "projectedY": (
                float(measurement["actualWireY"])
                + 5.0
                - (float(kwargs["roller_y_cals"][measurement["rollerIndex"]]) - 23.0)
                if measurement["id"] == "m1"
                else float(measurement["actualWireY"])
                + 5.0
                + (float(kwargs["roller_y_cals"][measurement["rollerIndex"]]) - 23.0)
            ),
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

    assert evaluation["rollerYCals"][1] == pytest.approx(23.0, abs=0.2)
    assert evaluation["rollerYCals"][0] == pytest.approx(24.0, abs=1e-9)
    assert evaluation["rollerYCals"][2] == pytest.approx(18.0, abs=1e-9)
    assert evaluation["rollerYCals"][3] == pytest.approx(17.0, abs=1e-9)
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
            "projectedY": (
                float(measurement["actualWireY"])
                + 5.0
                - (float(kwargs["roller_y_cals"][measurement["rollerIndex"]]) - 23.0)
                if measurement["id"] == "m1"
                else float(measurement["actualWireY"])
                + 5.0
                + (float(kwargs["roller_y_cals"][measurement["rollerIndex"]]) - 23.0)
            ),
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

    assert evaluation["rollerYCals"][1] == pytest.approx(23.0, abs=0.2)
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

    assert evaluation["cameraOffsetX"] == pytest.approx(10.0, abs=1e-9)
    assert evaluation["cameraOffsetY"] == pytest.approx(-1.5, abs=0.2)
    assert candidate_calls
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


def test_machine_xy_solver_clamps_camera_and_roller_bounds(monkeypatch, tmp_path):
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

    def project_measurement(measurement, **kwargs):
        roller = float(kwargs["roller_y_cals"][1])
        if measurement["id"] == "m0":
            return {
                "projectedX": float(measurement["actualWireX"]) - 20.0,
                "projectedY": float(measurement["actualWireY"]) - 5.0,
            }
        return {
            "projectedX": float(measurement["actualWireX"]) - 20.0,
            "projectedY": float(measurement["actualWireY"]) - 33.0 + roller,
        }

    monkeypatch.setattr(service, "_projectMeasurement", project_measurement)

    evaluation = service._evaluateMachineXY(
        measurements,
        layer="U",
        operation_id="op-bounds",
        layer_path="layer.json",
        nominal_roller_y=21.0,
        current_camera_offset=(10.0, -5.0),
        initial_roller_y_cals=(24.0, 23.0, 18.0, 17.0),
    )

    assert evaluation["cameraOffsetX"] == pytest.approx(20.0, abs=1e-9)
    assert evaluation["cameraOffsetY"] == pytest.approx(5.0, abs=0.2)
    assert evaluation["rollerYCals"][1] == pytest.approx(28.0, abs=1e-9)
    expected_camera_delta_norm = (
        ((evaluation["cameraOffsetX"] - 10.0) ** 2)
        + ((evaluation["cameraOffsetY"] - (-5.0)) ** 2)
    ) ** 0.5
    assert evaluation["score"]["cameraOffsetDeltaNorm"] == pytest.approx(
        expected_camera_delta_norm,
        abs=1e-9,
    )
    assert evaluation["score"]["rollerOffsetNorm"] == pytest.approx(5.0, abs=1e-9)


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
        layer_path=str(
            REPO_ROOT / "dune_winder" / "config" / "APA" / "U_Calibration.json"
        ),
        machine_path=str(
            REPO_ROOT / "dune_winder" / "config" / "machineCalibration.json"
        ),
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

    with pytest.raises(ValueError, match=r"\(1,1\).*offsetX="):
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

    tampered_overrides = {
        "(1,1)": {"x": 50.0, "y": -40.0},
    }

    result = service._sanityCheckLineOffsets("U", machine_draft, tampered_overrides)

    assert result["ok"] is False
    assert result["checkedCount"] == 1
    assert result["discrepancyCount"] == 1
    assert result["maxDiscrepancyX"] > 1.0
    assert result["maxDiscrepancyY"] > 1.0


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
