from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest

import dune_winder.core.machine_geometry_calibration as machine_geometry_module
from dune_winder.core.machine_geometry_calibration import MachineGeometryCalibration


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
    self.rollerArmCalibration = SimpleNamespace(fitted_y_cals=(24.0, 23.0, 18.0, 17.0))
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
    return getattr(self.controlStateMachine.state.__class__, "__name__", "") == "WindMode"


def test_record_measurement_captures_last_trace_and_current_position(monkeypatch, tmp_path):
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


def test_machine_xy_solver_relaxes_unmeasured_rollers_to_nominal(monkeypatch, tmp_path):
  process = _Process(tmp_path)
  service = MachineGeometryCalibration(process)
  nominal_roller_y = 21.0
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
      "projectedX": float(measurement["actualWireX"]),
      "projectedY": (
        float(measurement["actualWireY"])
        - (float(kwargs["roller_y_cals"][measurement["rollerIndex"]]) - 23.0)
        if measurement["id"] == "m1"
        else float(measurement["actualWireY"])
        + (float(kwargs["roller_y_cals"][measurement["rollerIndex"]]) - 23.0)
      ),
    },
  )

  evaluation = service._evaluateMachineXY(
    measurements,
    layer="U",
    operation_id="op-test-1",
    layer_path="layer.json",
    nominal_roller_y=nominal_roller_y,
    current_camera_offset=(10.0, -5.0),
    initial_roller_y_cals=(24.0, 27.0, 18.0, 17.0),
  )

  assert evaluation["rollerYCals"][0] == pytest.approx(nominal_roller_y, abs=1e-9)
  assert evaluation["rollerYCals"][1] == pytest.approx(23.0, abs=1e-3)
  assert evaluation["rollerYCals"][2] == pytest.approx(nominal_roller_y, abs=1e-9)
  assert evaluation["rollerYCals"][3] == pytest.approx(nominal_roller_y, abs=1e-9)


def test_machine_xy_solver_reports_bounded_progress(monkeypatch, tmp_path):
  process = _Process(tmp_path)
  service = MachineGeometryCalibration(process)
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

  monkeypatch.setattr(service, "_candidateMachineCalibrationPath", candidate_machine_path)
  monkeypatch.setattr(
    service,
    "_projectMeasurement",
    lambda measurement, **kwargs: {
      "projectedX": float(measurement["actualWireX"]),
      "projectedY": (
        float(measurement["actualWireY"])
        - (float(kwargs["roller_y_cals"][measurement["rollerIndex"]]) - 23.0)
        if measurement["id"] == "m1"
        else float(measurement["actualWireY"])
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
    progress_callback=lambda step, message, **fields: progress_events.append((step, message, fields)),
  )

  assert evaluation["rollerYCals"][1] == pytest.approx(23.0, abs=1e-3)
  assert projection_batches["count"] < 200
  assert any("totalEvaluations" in fields for _step, _message, fields in progress_events)
  assert any("percentComplete" in fields for _step, _message, fields in progress_events)


def test_machine_xy_solve_records_progress_and_success(monkeypatch, tmp_path):
  process = _Process(tmp_path)
  service = MachineGeometryCalibration(process)

  monkeypatch.setattr(service, "_candidateLayerCalibrationPath", lambda layer: "layer.json")

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
  assert any(entry[1] == "SOLVE_MACHINE_XY_PROGRESS" for entry in process._log.entries)
  assert any(entry[1] == "SOLVE_MACHINE_XY_DONE" for entry in process._log.entries)


def test_machine_xy_solve_records_failure(monkeypatch, tmp_path):
  process = _Process(tmp_path)
  service = MachineGeometryCalibration(process)

  monkeypatch.setattr(service, "_candidateLayerCalibrationPath", lambda layer: "layer.json")

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

  monkeypatch.setattr(service, "_candidateLayerCalibrationPath", lambda layer: "layer.json")
  monkeypatch.setattr(service, "_candidateMachineCalibrationPath", lambda roller_y_cals, camera_offset=None: "machine.json")
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
  assert any(entry[1] == "SOLVE_MACHINE_XY_CANCELED" for entry in process._log.entries)


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

  monkeypatch.setattr(service, "_candidateLayerCalibrationPath", lambda layer: "layer.json")
  monkeypatch.setattr(service, "_candidateMachineCalibrationPath", lambda roller_y_cals, camera_offset=None: "machine.json")
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

  with open(path, encoding="utf-8") as handle:
    data = json.load(handle)

  assert data["cameraWireOffsetX"] == pytest.approx(1.5, abs=1e-9)
  assert data["cameraWireOffsetY"] == pytest.approx(-2.5, abs=1e-9)
  assert data["rollerArmCalibration"]["fitted_y_cals"] == [21.0, 22.0, 23.0, 24.0]
  service._removeTemporaryCandidatePath(path)


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
