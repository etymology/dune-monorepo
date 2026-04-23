from __future__ import annotations

import errno
import copy
import json
import os
import pathlib
import time
import uuid
import traceback

from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.calibration.roller_arm import (
  RollerArmCalibration,
  RollerArmMeasurement,
  roller_arm_calibration_to_dict,
)
from dune_winder.machine.calibration.z_plane import (
  LayerZPlaneMeasurement,
  empty_layer_z_plane_calibration,
  layer_z_plane_calibration_from_dict,
  layer_z_plane_calibration_to_dict,
)
from dune_winder.machine.calibration.z_plane_solver import (
  apply_layer_z_plane_calibration,
  fit_layer_z_plane,
  has_valid_layer_z_plane_fit,
)
from dune_winder.recipes.line_offset_overrides import (
  extract_line_key,
  line_offset_override_items,
  normalize_line_key,
)
from dune_winder.uv_head_target import (
  clear_uv_head_target_caches,
  compute_pin_pair_tangent_geometry,
  compute_uv_anchor_to_target_view,
  parse_anchor_to_target_command,
)


_SUPPORTED_LAYERS = ("U", "V")
_TRACE_LINE_REQUIRES = "~anchorToTarget("
_EPSILON = 1e-9
_SEARCH_MIN_STEP = 0.001
_SEARCH_BASE_STEP = 2.0
_SEARCH_MAX_STEP = 64.0


def _normalize_layer(layer) -> str:
  normalized = str(layer).strip().upper()
  if normalized not in _SUPPORTED_LAYERS:
    raise ValueError("Machine geometry calibration only supports U and V layers.")
  return normalized


def _deep_copy_json(value):
  return json.loads(json.dumps(value))


def _compare_score(candidate, incumbent) -> bool:
  if incumbent is None:
    return True
  for candidate_value, incumbent_value in zip(candidate, incumbent):
    if candidate_value < incumbent_value - 1e-9:
      return True
    if candidate_value > incumbent_value + 1e-9:
      return False
  return False


def _nominal_roller_y(machine_calibration: MachineCalibration) -> float:
  return (float(machine_calibration.headRollerGap) / 2.0) + float(
    machine_calibration.headRollerRadius
  )


def _live_roller_y_cals(machine_calibration: MachineCalibration) -> tuple[float, float, float, float]:
  nominal = _nominal_roller_y(machine_calibration)
  calibration = getattr(machine_calibration, "rollerArmCalibration", None)
  if calibration is None:
    return (nominal, nominal, nominal, nominal)
  return tuple(float(value) for value in calibration.fitted_y_cals[:4])


def _error_text(exception):
  text = str(exception).strip()
  if text:
    return text
  return repr(exception)


def _clamp(value, minimum, maximum):
  return max(float(minimum), min(float(maximum), float(value)))


def _search_level_count(initial_step, minimum_step=_SEARCH_MIN_STEP) -> int:
  step = max(float(initial_step), float(minimum_step))
  count = 0
  while step >= float(minimum_step):
    count += 1
    step /= 2.0
  return max(count, 1)


def _estimated_search_step(max_abs_error) -> float:
  if max_abs_error is None:
    return float(_SEARCH_BASE_STEP)
  return _clamp(max(float(max_abs_error), float(_SEARCH_BASE_STEP)), _SEARCH_BASE_STEP, _SEARCH_MAX_STEP)


class _MachineXYSolveCancelled(RuntimeError):
  pass


class MachineGeometryCalibration:
  FILE_NAME = "machineGeometryCalibration.json"

  def __init__(self, process):
    self._process = process
    self._state = None
    self._loadedPath = None
    self._cancelRequestedMachineSolveOperationIds = set()

  # -------------------------------------------------------------------
  def _stateDirectory(self):
    workspace = getattr(self._process, "workspace", None)
    if workspace is not None and hasattr(workspace, "getPath"):
      return workspace.getPath()
    return self._process._workspaceCalibrationDirectory

  # -------------------------------------------------------------------
  def _statePath(self):
    return os.path.join(self._stateDirectory(), self.FILE_NAME)

  # -------------------------------------------------------------------
  def _tempDirectory(self):
    return os.path.join(self._stateDirectory(), "MachineGeometryTemp")

  # -------------------------------------------------------------------
  def _emptyState(self):
    return {
      "measurementRevision": 0,
      "measurements": [],
      "machineDraft": None,
      "layerDrafts": {},
    }

  # -------------------------------------------------------------------
  def _loadState(self):
    path = self._statePath()
    if self._loadedPath == path and self._state is not None:
      return self._state

    state = self._emptyState()
    if os.path.isfile(path):
      try:
        with open(path, "r", encoding="utf-8") as handle:
          loaded = json.load(handle)
        if isinstance(loaded, dict):
          state.update(loaded)
      except (OSError, ValueError, TypeError) as exception:
        self._process._log.add(
          "MachineGeometryCalibration",
          "DRAFT_LOAD",
          "Failed to load machine geometry calibration state.",
          [path, exception],
        )
    if not isinstance(state.get("layerDrafts"), dict):
      state["layerDrafts"] = {}
    if not isinstance(state.get("measurements"), list):
      state["measurements"] = []
    self._state = state
    self._loadedPath = path
    return self._state

  # -------------------------------------------------------------------
  def _log(self, event, message, details=None):
    log = getattr(self._process, "_log", None)
    if log is None or not hasattr(log, "add"):
      return
    log.add(
      "MachineGeometryCalibration",
      str(event),
      str(message),
      [] if details is None else details,
    )

  # -------------------------------------------------------------------
  def _timestamp(self):
    source = getattr(self._process, "_systemTime", None)
    if source is not None and hasattr(source, "get"):
      try:
        return str(source.get())
      except Exception:
        pass
    return str(time.time())

  # -------------------------------------------------------------------
  def _machineSolveStatus(self, layer, *, create=False):
    draft = self._layerDraft(layer, create=create)
    if draft is None:
      return None
    status = draft.get("machineSolveStatus")
    if status is None and create:
      status = {}
      draft["machineSolveStatus"] = status
    return status

  # -------------------------------------------------------------------
  def _updateMachineSolveStatus(self, layer, **fields):
    status = self._machineSolveStatus(layer, create=True)
    status.update(fields)
    status["updatedAt"] = self._timestamp()
    self._saveState()
    return dict(status)

  # -------------------------------------------------------------------
  def _isMachineSolveCancellationRequested(self, operation_id):
    return str(operation_id) in self._cancelRequestedMachineSolveOperationIds

  # -------------------------------------------------------------------
  def _raiseIfMachineSolveCancelled(self, layer, operation_id):
    if self._isMachineSolveCancellationRequested(operation_id):
      raise _MachineXYSolveCancelled(
        "Machine XY solve canceled at user request."
      )

  # -------------------------------------------------------------------
  def _saveState(self):
    state = self._loadState()
    path = self._statePath()
    directory = os.path.dirname(path)
    if directory and not os.path.isdir(directory):
      os.makedirs(directory)
    temporary_path = path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as handle:
      json.dump(state, handle, indent=2, sort_keys=True)
    last_error = None
    for attempt in range(6):
      try:
        os.replace(temporary_path, path)
        return
      except PermissionError as error:
        last_error = error
      except OSError as error:
        if getattr(error, "errno", None) not in (errno.EACCES, errno.EPERM):
          raise
        last_error = error
      if attempt < 5:
        time.sleep(0.05 * (attempt + 1))
    try:
      os.unlink(temporary_path)
    except OSError:
      pass
    if last_error is not None:
      raise last_error

  # -------------------------------------------------------------------
  def _measurementRevision(self):
    return int(self._loadState().get("measurementRevision", 0))

  # -------------------------------------------------------------------
  def _bumpMeasurementRevision(self):
    state = self._loadState()
    state["measurementRevision"] = int(state.get("measurementRevision", 0)) + 1

  # -------------------------------------------------------------------
  def _layerDraft(self, layer, *, create=False):
    layer_key = _normalize_layer(layer)
    state = self._loadState()
    drafts = state.setdefault("layerDrafts", {})
    draft = drafts.get(layer_key)
    if draft is None and create:
      draft = {
        "zPlaneCalibration": None,
        "zPlaneSolve": None,
        "machineSolve": None,
        "lineOffsetOverrides": {},
      }
      drafts[layer_key] = draft
    return draft

  # -------------------------------------------------------------------
  def _activeLayer(self):
    layer = self._process.getRecipeLayer()
    if layer is None:
      raise ValueError("Load an active U or V recipe first.")
    return _normalize_layer(layer)

  # -------------------------------------------------------------------
  def _resolvedLayer(self, layer):
    active_layer = self._activeLayer()
    if layer is None:
      return active_layer
    normalized = _normalize_layer(layer)
    if normalized != active_layer:
      raise ValueError(
        "Requested layer "
        + normalized
        + " does not match active loaded recipe layer "
        + active_layer
        + "."
      )
    return normalized

  # -------------------------------------------------------------------
  def _machineCalibration(self):
    calibration = getattr(self._process, "_machineCalibration", None)
    if calibration is None:
      calibration = getattr(
        getattr(self._process, "controlStateMachine", None),
        "machineCalibration",
        None,
      )
    if calibration is None:
      raise ValueError("Machine calibration is not available.")
    return calibration

  # -------------------------------------------------------------------
  def _machineCalibrationPath(self):
    calibration = self._machineCalibration()
    output_path = getattr(calibration, "_outputFilePath", None)
    output_name = getattr(calibration, "_outputFileName", None)
    if output_path is None or output_name is None:
      raise ValueError("Machine calibration file path is not configured.")
    return str(pathlib.Path(output_path) / output_name)

  # -------------------------------------------------------------------
  def _activeLayerCalibration(self, layer):
    if hasattr(self._process, "_getActiveLayerCalibration"):
      return self._process._getActiveLayerCalibration(layer)

    calibration = None
    workspace = getattr(self._process, "workspace", None)
    if workspace is not None:
      calibration = getattr(workspace, "_calibration", None)
    if calibration is None:
      handler = getattr(self._process, "gCodeHandler", None)
      if handler is not None and hasattr(handler, "getLayerCalibration"):
        calibration = handler.getLayerCalibration()
    if calibration is None:
      raise ValueError("No layer calibration is loaded for active layer " + str(layer) + ".")
    return calibration

  # -------------------------------------------------------------------
  def _syncLayerCalibrationHandlers(self, calibration):
    handlers = []
    direct_handler = getattr(self._process, "gCodeHandler", None)
    if direct_handler is not None:
      handlers.append(direct_handler)
    workspace_handler = getattr(getattr(self._process, "workspace", None), "_gCodeHandler", None)
    if workspace_handler is not None and workspace_handler not in handlers:
      handlers.append(workspace_handler)

    for handler in handlers:
      if not hasattr(handler, "useLayerCalibration"):
        continue
      loaded = handler.getLayerCalibration() if hasattr(handler, "getLayerCalibration") else None
      if loaded is calibration or loaded is None:
        handler.useLayerCalibration(calibration)
        continue
      if (
        str(getattr(loaded, "getLayerNames", lambda: None)()).strip().upper()
        == str(calibration.getLayerNames()).strip().upper()
      ):
        handler.useLayerCalibration(calibration)

  # -------------------------------------------------------------------
  def _templateService(self, layer):
    normalized = _normalize_layer(layer)
    if normalized == "U":
      return self._process.uTemplateRecipe
    return self._process.vTemplateRecipe

  # -------------------------------------------------------------------
  def _isGCodeExecutionActive(self):
    if hasattr(self._process, "isGCodeExecutionActive"):
      return bool(self._process.isGCodeExecutionActive())
    state = getattr(getattr(self._process, "controlStateMachine", None), "state", None)
    return getattr(state.__class__, "__name__", None) == "WindMode"

  # -------------------------------------------------------------------
  def _geometryMutationGuard(self):
    if self._isGCodeExecutionActive():
      raise ValueError("Cannot change machine geometry during active G-code execution.")

  # -------------------------------------------------------------------
  def _currentCameraOffset(self):
    calibration = self._machineCalibration()
    offset_x = getattr(calibration, "cameraWireOffsetX", None)
    offset_y = getattr(calibration, "cameraWireOffsetY", None)
    if offset_x is None or offset_y is None:
      manual = getattr(self._process, "manualCalibration", None)
      if manual is not None and hasattr(manual, "_sharedCameraOffset"):
        offset_x, offset_y = manual._sharedCameraOffset()
      else:
        offset_x = 0.0 if offset_x is None else offset_x
        offset_y = 0.0 if offset_y is None else offset_y
    return (float(offset_x), float(offset_y))

  # -------------------------------------------------------------------
  def _currentPositions(self):
    io = self._process._io
    raw_camera_x = float(io.xAxis.getPosition())
    raw_camera_y = float(io.yAxis.getPosition())
    current_z = float(io.zAxis.getPosition()) if hasattr(io, "zAxis") else None
    effective_camera_x = float(self._process._xBacklash.getEffectiveX(raw_camera_x))
    return {
      "rawCameraX": raw_camera_x,
      "rawCameraY": raw_camera_y,
      "effectiveCameraX": effective_camera_x,
      "currentZ": current_z,
    }

  # -------------------------------------------------------------------
  def _extractAnchorToTargetLine(self, trace_payload):
    line_text = str((trace_payload or {}).get("line", "")).strip()
    start = line_text.find(_TRACE_LINE_REQUIRES)
    if start < 0:
      raise ValueError(
        "The last traced line is not a ~anchorToTarget(...) wrap line. Use a wrapping trace line."
      )
    depth = 0
    for index in range(start, len(line_text)):
      char = line_text[index]
      if char == "(":
        depth += 1
      elif char == ")":
        depth -= 1
        if depth == 0:
          return line_text[start : index + 1]
    raise ValueError("Failed to parse the last traced ~anchorToTarget(...) line.")

  # -------------------------------------------------------------------
  def _measurementFromTrace(self, layer, *, capture_xy, capture_z):
    if not capture_xy and not capture_z:
      raise ValueError("Capture requires at least one observed channel.")

    trace_payload = getattr(self._process, "getLastInstructionTrace", lambda: None)()
    if not trace_payload:
      raise ValueError("No motion trace is available yet.")

    gcode_line = self._extractAnchorToTargetLine(trace_payload)
    command = parse_anchor_to_target_command(gcode_line)
    positions = self._currentPositions()
    camera_offset_x, camera_offset_y = self._currentCameraOffset()
    line_key = extract_line_key(trace_payload.get("line"))
    wrap_number = None
    wrap_line_number = None
    if line_key is not None:
      wrap_number, wrap_line_number = (
        int(line_key[1:-1].split(",")[0]),
        int(line_key[1:-1].split(",")[1]),
      )

    kind = (
      "same_side"
      if command.anchor_pin[:1] == command.target_pin[:1]
      else "alternating_side"
    )
    roller_index = None
    if kind == "same_side":
      geometry = compute_pin_pair_tangent_geometry(
        layer=layer,
        pin_a=command.anchor_pin,
        pin_b=command.target_pin,
      )
      roller_index = int(geometry.roller_index)

    measurement = {
      "id": uuid.uuid4().hex,
      "layer": layer,
      "timestamp": str(self._process._systemTime.get()),
      "kind": kind,
      "gcodeLine": gcode_line,
      "traceLine": str(trace_payload.get("line", "")),
      "lineKey": line_key,
      "wrapNumber": wrap_number,
      "wrapLineNumber": wrap_line_number,
      "tracePayload": _deep_copy_json(trace_payload),
      "rawCameraX": positions["rawCameraX"],
      "rawCameraY": positions["rawCameraY"],
      "effectiveCameraX": positions["effectiveCameraX"],
      "currentZ": positions["currentZ"],
      "cameraOffsetX": camera_offset_x,
      "cameraOffsetY": camera_offset_y,
      "actualWireX": (
        positions["effectiveCameraX"] + camera_offset_x if capture_xy else None
      ),
      "actualWireY": (
        positions["rawCameraY"] + camera_offset_y if capture_xy else None
      ),
      "actualZ": positions["currentZ"] if capture_z else None,
      "projectedX": (
        None
        if trace_payload.get("resultingWireTarget") is None
        else trace_payload["resultingWireTarget"].get("x")
      ),
      "projectedY": (
        None
        if trace_payload.get("resultingWireTarget") is None
        else trace_payload["resultingWireTarget"].get("y")
      ),
      "rollerIndex": roller_index,
    }
    return measurement

  # -------------------------------------------------------------------
  def recordMeasurement(self, *, layer=None, capture_xy=True, capture_z=False):
    target_layer = _normalize_layer(layer or self._activeLayer())
    measurement = self._measurementFromTrace(
      target_layer,
      capture_xy=bool(capture_xy),
      capture_z=bool(capture_z),
    )
    state = self._loadState()
    state["measurements"].append(measurement)
    self._bumpMeasurementRevision()
    self._saveState()
    return measurement

  # -------------------------------------------------------------------
  def deleteMeasurement(self, measurement_id):
    state = self._loadState()
    target_id = str(measurement_id)
    state["measurements"] = [
      measurement
      for measurement in state.get("measurements", [])
      if str(measurement.get("id")) != target_id
    ]
    self._bumpMeasurementRevision()
    self._saveState()
    return {"measurementId": target_id}

  # -------------------------------------------------------------------
  def _usableMeasurements(self, layer):
    normalized = _normalize_layer(layer)
    measurements = []
    for measurement in self._loadState().get("measurements", []):
      if str(measurement.get("layer")).strip().upper() != normalized:
        continue
      measurement = dict(measurement)
      measurement["usableForLayerZ"] = (
        measurement.get("kind") == "same_side"
        and measurement.get("actualZ") is not None
      )
      measurement["usableForMachineXY"] = (
        measurement.get("actualWireX") is not None
        and measurement.get("actualWireY") is not None
        and measurement.get("lineKey") is not None
        and measurement.get("gcodeLine")
      )
      measurements.append(measurement)
    return measurements

  # -------------------------------------------------------------------
  def solveLayerZ(self, layer=None):
    target_layer = self._resolvedLayer(layer)
    calibration = self._activeLayerCalibration(target_layer)
    measurements = []
    for measurement in self._usableMeasurements(target_layer):
      if not measurement["usableForLayerZ"]:
        continue
      measurements.append(
        LayerZPlaneMeasurement(
          gcode_line=str(measurement["gcodeLine"]),
          layer=target_layer,
          actual_x=float(measurement.get("actualWireX", 0.0) or 0.0),
          actual_y=float(measurement.get("actualWireY", 0.0) or 0.0),
          actual_z=float(measurement["actualZ"]),
        )
      )

    if measurements:
      fitted = fit_layer_z_plane(
        measurements,
        machine_calibration_path=self._machineCalibrationPath(),
        layer_calibration_path=calibration.getFullFileName(),
      )
    else:
      fitted = empty_layer_z_plane_calibration()

    draft = self._layerDraft(target_layer, create=True)
    draft["zPlaneCalibration"] = layer_z_plane_calibration_to_dict(fitted)
    draft["zPlaneSolve"] = {
      "measurementRevision": self._measurementRevision(),
      "measurementIds": [
        measurement["id"]
        for measurement in self._usableMeasurements(target_layer)
        if measurement["usableForLayerZ"]
      ],
    }
    self._saveState()
    return draft["zPlaneCalibration"]

  # -------------------------------------------------------------------
  def cancelMachineXY(self, layer=None):
    target_layer = self._resolvedLayer(layer)
    status = self._machineSolveStatus(target_layer, create=False)
    if status is None:
      return {
        "layer": target_layer,
        "canceled": False,
        "message": "No Machine XY solve is active.",
      }

    current_status = str(status.get("status", "")).strip().lower()
    operation_id = status.get("operationId")
    if current_status not in ("running", "cancel_requested") or not operation_id:
      return {
        "layer": target_layer,
        "canceled": False,
        "message": "No Machine XY solve is active.",
      }

    self._cancelRequestedMachineSolveOperationIds.add(str(operation_id))
    updated_status = self._updateMachineSolveStatus(
      target_layer,
      operationId=operation_id,
      status="cancel_requested",
      message="Cancel requested. Stopping after the current evaluation batch.",
      cancelRequested=True,
      cancelRequestedAt=self._timestamp(),
    )
    self._log(
      "SOLVE_MACHINE_XY_CANCEL_REQUESTED",
      "Machine XY solve cancel requested.",
      [operation_id, target_layer],
    )
    return {
      "layer": target_layer,
      "canceled": True,
      "message": "Cancel requested.",
      "status": updated_status,
    }

  # -------------------------------------------------------------------
  def applyLayerZ(self, layer=None):
    self._geometryMutationGuard()
    target_layer = self._resolvedLayer(layer)
    draft = self._layerDraft(target_layer)
    if draft is None or draft.get("zPlaneCalibration") is None:
      raise ValueError("Run layer Z solve before applying.")
    fitted = layer_z_plane_calibration_from_dict(draft["zPlaneCalibration"])
    if not has_valid_layer_z_plane_fit(fitted):
      raise ValueError("Current layer Z draft fit is not valid.")

    calibration = self._activeLayerCalibration(target_layer)
    calibration.zPlaneCalibration = fitted
    apply_layer_z_plane_calibration(calibration, fitted)
    calibration.save()
    clear_uv_head_target_caches(layer_calibration=True, machine_calibration=False)
    self._syncLayerCalibrationHandlers(calibration)
    return layer_z_plane_calibration_to_dict(fitted)

  # -------------------------------------------------------------------
  def _liveLayerCalibrationCopy(self, layer):
    calibration = self._activeLayerCalibration(layer)
    return calibration.copy()

  # -------------------------------------------------------------------
  def _candidateLayerCalibrationPath(self, layer):
    draft = self._layerDraft(layer)
    if draft is None or draft.get("zPlaneCalibration") is None:
      calibration = self._activeLayerCalibration(layer)
      return calibration.getFullFileName()

    fitted = layer_z_plane_calibration_from_dict(draft["zPlaneCalibration"])
    if not has_valid_layer_z_plane_fit(fitted):
      calibration = self._activeLayerCalibration(layer)
      return calibration.getFullFileName()

    temporary_directory = self._tempDirectory()
    if not os.path.isdir(temporary_directory):
      os.makedirs(temporary_directory)
    temporary_path = os.path.join(temporary_directory, f"{layer}_solve_layer.json")
    calibration = self._liveLayerCalibrationCopy(layer)
    calibration.zPlaneCalibration = fitted
    apply_layer_z_plane_calibration(calibration, fitted)
    calibration.save(temporary_directory, os.path.basename(temporary_path))
    clear_uv_head_target_caches(layer_calibration=True, machine_calibration=False)
    return temporary_path

  # -------------------------------------------------------------------
  def _candidateMachineCalibrationPath(self, roller_y_cals, *, camera_offset=None):
    live = self._machineCalibration()
    temporary_directory = self._tempDirectory()
    if not os.path.isdir(temporary_directory):
      os.makedirs(temporary_directory)
    temporary_name = "machine_geometry_solve_machine_" + uuid.uuid4().hex + ".json"
    candidate = MachineCalibration(temporary_directory, temporary_name)
    candidate._from_dict(copy.deepcopy(live._to_dict()))
    if camera_offset is not None:
      candidate.cameraWireOffsetX = float(camera_offset[0])
      candidate.cameraWireOffsetY = float(camera_offset[1])
    candidate.rollerArmCalibration = RollerArmCalibration(
      measurements=[],
      fitted_y_cals=tuple(float(value) for value in roller_y_cals[:4]),
      center_displacement=0.0,
      arm_tilt_rad=0.0,
    )
    temporary_path = os.path.join(temporary_directory, temporary_name)
    with open(temporary_path, "w", encoding="utf-8") as handle:
      json.dump(candidate._to_dict(), handle, indent=2)
    clear_uv_head_target_caches(layer_calibration=False, machine_calibration=True)
    return temporary_path

  # -------------------------------------------------------------------
  def _removeTemporaryCandidatePath(self, path):
    try:
      os.unlink(path)
    except OSError:
      pass

  # -------------------------------------------------------------------
  def _projectMeasurement(self, measurement, *, layer_path, machine_path, roller_y_cals):
    view = compute_uv_anchor_to_target_view(
      command_text=str(measurement["gcodeLine"]),
      layer=str(measurement["layer"]),
      machine_calibration_path=machine_path,
      layer_calibration_path=layer_path,
      roller_arm_y_offsets=tuple(float(value) for value in roller_y_cals[:4]),
    )
    return {
      "projectedX": float(view.interpreter_wire_point.x),
      "projectedY": float(view.interpreter_wire_point.y),
    }

  # -------------------------------------------------------------------
  def _xyConflictError(self, usable_measurements):
    by_line_key = {}
    for measurement in usable_measurements:
      line_key = str(measurement["lineKey"])
      entry = by_line_key.setdefault(line_key, measurement)
      if entry is measurement:
        continue
      delta = abs(float(entry["actualWireX"]) - float(measurement["actualWireX"])) + abs(
        float(entry["actualWireY"]) - float(measurement["actualWireY"])
      )
      if delta > 1e-6:
        return (
          "Multiple XY measurements target line "
          + line_key
          + ". Prune duplicates before solving machine XY."
        )
    return None

  # -------------------------------------------------------------------
  def _evaluateMachineXY(
    self,
    measurements,
    *,
    layer,
    operation_id,
    layer_path,
    nominal_roller_y,
    current_camera_offset,
    initial_roller_y_cals,
    progress_callback=None,
  ):
    same_side_by_roller = {index: [] for index in range(4)}
    for measurement in measurements:
      if measurement["kind"] == "same_side" and measurement.get("rollerIndex") is not None:
        same_side_by_roller[int(measurement["rollerIndex"])].append(measurement)

    measured_rollers = [
      roller_index
      for roller_index in range(4)
      if same_side_by_roller[roller_index]
    ]
    measurement_order = [str(measurement["id"]) for measurement in measurements]

    def project_group(group_measurements, roller_y_cals, camera_offset):
      if not group_measurements:
        return []
      self._raiseIfMachineSolveCancelled(layer, operation_id)
      machine_path = self._candidateMachineCalibrationPath(
        roller_y_cals,
        camera_offset=camera_offset,
      )
      results = []
      try:
        for measurement in group_measurements:
          self._raiseIfMachineSolveCancelled(layer, operation_id)
          projection = self._projectMeasurement(
            measurement,
            layer_path=layer_path,
            machine_path=machine_path,
            roller_y_cals=roller_y_cals,
          )
          results.append((measurement, projection))
      finally:
        self._removeTemporaryCandidatePath(machine_path)
      return results

    def summarize_results(results, camera_offset):
      camera_x = float(camera_offset[0])
      camera_y = float(camera_offset[1])
      by_measurement = {}
      primary = 0.0
      for measurement, projection in results:
        offset_x = (
          float(measurement["effectiveCameraX"]) + camera_x
        ) - float(projection["projectedX"])
        offset_y = (
          float(measurement["rawCameraY"]) + camera_y
        ) - float(projection["projectedY"])
        summary = (
          measurement,
          projection,
          float(offset_x),
          float(offset_y),
        )
        by_measurement[str(measurement["id"])] = summary
        primary += (offset_x * offset_x) + (offset_y * offset_y)
      return {
        "primary": float(primary),
        "by_measurement": by_measurement,
      }

    def ordered_summaries(summary_by_measurement):
      return [
        summary_by_measurement[measurement_id]
        for measurement_id in measurement_order
        if measurement_id in summary_by_measurement
      ]

    def primary_for_measurements(summary_by_measurement, group_measurements):
      primary = 0.0
      for measurement in group_measurements:
        summary = summary_by_measurement.get(str(measurement["id"]))
        if summary is None:
          continue
        primary += (float(summary[2]) * float(summary[2])) + (float(summary[3]) * float(summary[3]))
      return float(primary)

    def max_abs_offset(summary_by_measurement, group_measurements=None):
      values = []
      if group_measurements is None:
        source = summary_by_measurement.values()
      else:
        source = [
          summary_by_measurement.get(str(measurement["id"]))
          for measurement in group_measurements
        ]
      for summary in source:
        if summary is None:
          continue
        values.append(abs(float(summary[2])))
        values.append(abs(float(summary[3])))
      if not values:
        return None
      return max(values)

    progress_state = {
      "startedAt": time.time(),
      "completed": 0,
      "total": None,
    }

    def progress_fields(**fields):
      payload = dict(fields)
      total = progress_state["total"]
      completed = int(payload.get("completedEvaluations", progress_state["completed"]))
      if total is not None:
        payload["totalEvaluations"] = int(total)
        payload["completedEvaluations"] = completed
        payload["percentComplete"] = min(
          100.0,
          max(0.0, (float(completed) / float(total)) * 100.0),
        )
        elapsed = max(0.0, time.time() - float(progress_state["startedAt"]))
        payload["elapsedSeconds"] = float(elapsed)
        if completed > 0 and completed < total:
          remaining = int(total) - completed
          payload["estimatedSecondsRemaining"] = float(
            (elapsed / float(completed)) * float(remaining)
          )
        elif completed >= total:
          payload["estimatedSecondsRemaining"] = 0.0
      return payload

    def publish(step, message, **fields):
      if progress_callback is None:
        return
      self._raiseIfMachineSolveCancelled(layer, operation_id)
      progress_callback(step, message, **progress_fields(**fields))

    def project_with_status(
      group_measurements,
      roller_y_cals,
      camera_offset,
      *,
      step,
      message,
      phase,
      phase_index,
      phase_count,
      step_size=None,
      level_index=None,
      level_count=None,
      candidate_label=None,
    ):
      publish(
        step,
        message,
        phase=phase,
        phaseIndex=int(phase_index),
        phaseCount=int(phase_count),
        stepSize=(None if step_size is None else float(step_size)),
        levelIndex=(None if level_index is None else int(level_index)),
        levelCount=(None if level_count is None else int(level_count)),
        candidateLabel=candidate_label,
      )
      results = project_group(group_measurements, roller_y_cals, camera_offset)
      progress_state["completed"] += 1
      return results

    def build_full_score(primary, roller_y_cals, camera_offset):
      roller_secondary = sum(
        (float(value) - float(nominal_roller_y)) ** 2
        for value in roller_y_cals
      )
      camera_secondary = (
        (float(camera_offset[0]) - float(current_camera_offset[0])) ** 2
        + (float(camera_offset[1]) - float(current_camera_offset[1])) ** 2
      )
      return (
        float(primary),
        float(roller_secondary),
        float(camera_secondary),
      )

    phase_count = 4 + len(measured_rollers)
    current_phase_index = 1
    working_roller_y_cals = [float(nominal_roller_y)] * 4
    for roller_index in measured_rollers:
      working_roller_y_cals[roller_index] = float(initial_roller_y_cals[roller_index])

    camera_offset = (
      float(current_camera_offset[0]),
      float(current_camera_offset[1]),
    )

    if not measurements:
      score = build_full_score(0.0, working_roller_y_cals, camera_offset)
      publish(
        "done",
        "No machine XY measurements were available. Draft mirrors the current machine camera offset and nominal rollers.",
        completedEvaluations=0,
        totalEvaluations=0,
        percentComplete=100.0,
        phase="done",
        phaseIndex=phase_count,
        phaseCount=phase_count,
        elapsedSeconds=0.0,
        estimatedSecondsRemaining=0.0,
      )
      return {
        "cameraOffsetX": float(camera_offset[0]),
        "cameraOffsetY": float(camera_offset[1]),
        "rollerYCals": [float(value) for value in working_roller_y_cals],
        "score": {
          "lineOffsetNorm": float(score[0]),
          "rollerOffsetNorm": float(score[1]),
          "cameraOffsetDeltaNorm": float(score[2]),
        },
        "summaries": [],
      }

    baseline_results = project_with_status(
      measurements,
      working_roller_y_cals,
      camera_offset,
      step="baseline",
      message="Evaluating the current machine XY candidate.",
      phase="camera_coarse_x",
      phase_index=current_phase_index,
      phase_count=phase_count,
      candidate_label="baseline",
    )
    current_summary = summarize_results(baseline_results, camera_offset)
    current_score = build_full_score(
      current_summary["primary"],
      working_roller_y_cals,
      camera_offset,
    )

    camera_step = _estimated_search_step(
      max_abs_offset(current_summary["by_measurement"])
    )
    camera_levels = _search_level_count(camera_step)
    roller_steps = {
      roller_index: _estimated_search_step(
        max_abs_offset(
          current_summary["by_measurement"],
          same_side_by_roller[roller_index],
        )
      )
      for roller_index in measured_rollers
    }
    roller_levels = {
      roller_index: _search_level_count(roller_steps[roller_index])
      for roller_index in measured_rollers
    }
    progress_state["total"] = int(
      progress_state["completed"]
      + (4 * 2 * camera_levels)
      + sum(2 * roller_levels[roller_index] for roller_index in measured_rollers)
    )
    publish(
      "planning",
      "Machine XY solve projection budget established.",
      phase="planning",
      phaseIndex=0,
      phaseCount=phase_count,
      completedEvaluations=progress_state["completed"],
      cameraSearchLevels=int(camera_levels),
      measuredRollerCount=len(measured_rollers),
    )

    def optimize_camera_axis(axis_name, phase_name, phase_index):
      nonlocal camera_offset, current_summary, current_score
      step_size = float(camera_step)
      for level_index in range(camera_levels):
        self._raiseIfMachineSolveCancelled(layer, operation_id)
        candidate_specs = (
          ("lower", -step_size),
          ("upper", step_size),
        )
        for candidate_label, delta in candidate_specs:
          if axis_name == "x":
            candidate_camera_offset = (
              float(camera_offset[0]) + float(delta),
              float(camera_offset[1]),
            )
          else:
            candidate_camera_offset = (
              float(camera_offset[0]),
              float(camera_offset[1]) + float(delta),
            )
          candidate_results = project_with_status(
            measurements,
            working_roller_y_cals,
            candidate_camera_offset,
            step="optimizing_camera",
            message=(
              "Optimizing camera "
              + axis_name.upper()
              + " with step "
              + f"{step_size:.3f}"
              + " mm."
            ),
            phase=phase_name,
            phase_index=phase_index,
            phase_count=phase_count,
            step_size=step_size,
            level_index=level_index + 1,
            level_count=camera_levels,
            candidate_label=candidate_label,
          )
          candidate_summary = summarize_results(candidate_results, candidate_camera_offset)
          candidate_score = build_full_score(
            candidate_summary["primary"],
            working_roller_y_cals,
            candidate_camera_offset,
          )
          if _compare_score(candidate_score, current_score):
            camera_offset = candidate_camera_offset
            current_summary = candidate_summary
            current_score = candidate_score
        step_size /= 2.0

    optimize_camera_axis("x", "camera_coarse_x", current_phase_index)
    current_phase_index += 1
    optimize_camera_axis("y", "camera_coarse_y", current_phase_index)
    current_phase_index += 1

    total_primary = float(current_summary["primary"])
    total_roller_secondary = float(current_score[1])
    camera_secondary = float(current_score[2])
    summary_by_measurement = dict(current_summary["by_measurement"])

    for roller_index in measured_rollers:
      self._raiseIfMachineSolveCancelled(layer, operation_id)
      group_measurements = same_side_by_roller[roller_index]
      current_group_primary = primary_for_measurements(summary_by_measurement, group_measurements)
      other_primary = float(total_primary - current_group_primary)
      current_roller_secondary = (
        float(working_roller_y_cals[roller_index]) - float(nominal_roller_y)
      ) ** 2
      other_roller_secondary = float(total_roller_secondary - current_roller_secondary)
      best_y = float(working_roller_y_cals[roller_index])
      best_group_primary = float(current_group_primary)
      best_group_summaries = [
        summary_by_measurement[str(measurement["id"])]
        for measurement in group_measurements
        if str(measurement["id"]) in summary_by_measurement
      ]
      best_score = (
        float(total_primary),
        float(total_roller_secondary),
        float(camera_secondary),
      )
      step_size = float(roller_steps[roller_index])
      for level_index in range(roller_levels[roller_index]):
        self._raiseIfMachineSolveCancelled(layer, operation_id)
        for candidate_label, delta in (("lower", -step_size), ("upper", step_size)):
          candidate_y = float(best_y + delta)
          candidate_roller_y_cals = list(working_roller_y_cals)
          candidate_roller_y_cals[roller_index] = float(candidate_y)
          candidate_results = project_with_status(
            group_measurements,
            candidate_roller_y_cals,
            camera_offset,
            step="optimizing_roller",
            message=(
              "Optimizing roller "
              + str(roller_index)
              + " with step "
              + f"{step_size:.3f}"
              + " mm."
            ),
            phase="roller_" + str(roller_index),
            phase_index=current_phase_index,
            phase_count=phase_count,
            step_size=step_size,
            level_index=level_index + 1,
            level_count=roller_levels[roller_index],
            candidate_label=candidate_label,
          )
          candidate_summary = summarize_results(candidate_results, camera_offset)
          candidate_group_primary = float(candidate_summary["primary"])
          candidate_score = (
            float(other_primary + candidate_group_primary),
            float(
              other_roller_secondary
              + ((candidate_y - float(nominal_roller_y)) ** 2)
            ),
            float(camera_secondary),
          )
          if _compare_score(candidate_score, best_score):
            best_y = candidate_y
            best_group_primary = candidate_group_primary
            best_group_summaries = list(candidate_summary["by_measurement"].values())
            best_score = candidate_score
        step_size /= 2.0

      working_roller_y_cals[roller_index] = float(best_y)
      total_primary = float(best_score[0])
      total_roller_secondary = float(best_score[1])
      for summary in best_group_summaries:
        summary_by_measurement[str(summary[0]["id"])] = summary
      current_summary = {
        "primary": float(total_primary),
        "by_measurement": dict(summary_by_measurement),
      }
      current_score = (
        float(total_primary),
        float(total_roller_secondary),
        float(camera_secondary),
      )
      current_phase_index += 1

    optimize_camera_axis("x", "camera_refine_x", current_phase_index)
    current_phase_index += 1
    optimize_camera_axis("y", "camera_refine_y", current_phase_index)

    return {
      "cameraOffsetX": float(camera_offset[0]),
      "cameraOffsetY": float(camera_offset[1]),
      "rollerYCals": [float(value) for value in working_roller_y_cals],
      "score": {
        "lineOffsetNorm": float(current_score[0]),
        "rollerOffsetNorm": float(current_score[1]),
        "cameraOffsetDeltaNorm": float(current_score[2]),
      },
      "summaries": ordered_summaries(current_summary["by_measurement"]),
      "progress": {
        "completedEvaluations": int(progress_state["completed"]),
        "totalEvaluations": int(progress_state["total"] or progress_state["completed"]),
      },
    }

  # -------------------------------------------------------------------
  def solveMachineXY(self, layer=None):
    target_layer = self._resolvedLayer(layer)
    operation_id = uuid.uuid4().hex
    solve_started_at = time.time()
    self._cancelRequestedMachineSolveOperationIds.discard(str(operation_id))
    progress_checkpoint = {
      "time": 0.0,
      "step": None,
      "message": None,
      "completed": None,
      "total": None,
      "status": None,
    }

    def progress(step, message, **fields):
      now = time.time()
      completed = fields.get("completedEvaluations")
      total = fields.get("totalEvaluations")
      should_emit = (
        progress_checkpoint["step"] != step
        or progress_checkpoint["message"] != message
        or progress_checkpoint["completed"] != completed
        or progress_checkpoint["total"] != total
        or progress_checkpoint["status"] != "running"
        or progress_checkpoint["time"] <= 0.0
        or (now - progress_checkpoint["time"]) >= 0.25
      )
      if not should_emit:
        return
      progress_checkpoint["time"] = now
      progress_checkpoint["step"] = step
      progress_checkpoint["message"] = message
      progress_checkpoint["completed"] = completed
      progress_checkpoint["total"] = total
      progress_checkpoint["status"] = "running"
      status_fields = dict(fields)
      if (
        "elapsedSeconds" not in status_fields
        and progress_checkpoint["status"] == "running"
      ):
        status_fields["elapsedSeconds"] = float(max(0.0, now - solve_started_at))
      self._updateMachineSolveStatus(
        target_layer,
        operationId=operation_id,
        status="running",
        step=step,
        message=message,
        **status_fields,
      )
      self._log(
        "SOLVE_MACHINE_XY_PROGRESS",
        str(message),
        [operation_id, target_layer, step, fields],
      )

    try:
      usable_measurements = [
        measurement
        for measurement in self._usableMeasurements(target_layer)
        if measurement["usableForMachineXY"]
      ]
      self._log(
        "SOLVE_MACHINE_XY_START",
        "Machine XY solve started.",
        [operation_id, target_layer, len(usable_measurements)],
      )
      self._updateMachineSolveStatus(
        target_layer,
        operationId=operation_id,
        status="running",
        step="starting",
        message="Preparing machine XY solve.",
        startedAt=self._timestamp(),
        finishedAt=None,
        solveLayer=target_layer,
        measurementRevision=self._measurementRevision(),
        measurementCount=len(usable_measurements),
        fitError=None,
        cancelRequested=False,
        cancelRequestedAt=None,
        completedEvaluations=0,
        totalEvaluations=None,
        percentComplete=0.0,
        elapsedSeconds=0.0,
        estimatedSecondsRemaining=None,
      )

      conflict = self._xyConflictError(usable_measurements)
      draft = self._layerDraft(target_layer, create=True)
      state = self._loadState()
      current_camera_offset = self._currentCameraOffset()
      machine_calibration = self._machineCalibration()
      current_roller_y_cals = _live_roller_y_cals(machine_calibration)
      nominal_roller_y = _nominal_roller_y(machine_calibration)

      if conflict is not None:
        result = {
          "fitError": conflict,
          "measurementRevision": self._measurementRevision(),
        }
        draft["machineSolve"] = result
        draft["lineOffsetOverrides"] = {}
        state["machineDraft"] = None
        self._updateMachineSolveStatus(
          target_layer,
          operationId=operation_id,
          status="failed",
          step="validation",
          message=conflict,
          fitError=conflict,
          finishedAt=self._timestamp(),
          percentComplete=100.0,
          completedEvaluations=0,
          totalEvaluations=0,
          elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
          estimatedSecondsRemaining=0.0,
        )
        self._log(
          "SOLVE_MACHINE_XY_FAILED",
          "Machine XY solve failed validation.",
          [operation_id, target_layer, conflict],
        )
        self._cancelRequestedMachineSolveOperationIds.discard(str(operation_id))
        self._saveState()
        return result

      progress("layer_calibration", "Preparing layer calibration candidate.")
      layer_path = self._candidateLayerCalibrationPath(target_layer)
      evaluation = self._evaluateMachineXY(
        usable_measurements,
        layer=target_layer,
        operation_id=operation_id,
        layer_path=layer_path,
        nominal_roller_y=nominal_roller_y,
        current_camera_offset=current_camera_offset,
        initial_roller_y_cals=current_roller_y_cals,
        progress_callback=progress,
      )

      progress("building_draft", "Building line-offset draft and diagnostics.")
      overrides = {}
      diagnostics = []
      measurement_ids = []
      for measurement, projection, offset_x, offset_y in evaluation["summaries"]:
        line_key = normalize_line_key(measurement["lineKey"])
        measurement_ids.append(measurement["id"])
        existing_override = overrides.get(line_key)
        if existing_override is None:
          overrides[line_key] = {
            "x": float(offset_x),
            "y": float(offset_y),
            "gcodeLine": measurement["gcodeLine"],
            "measurementIds": [measurement["id"]],
            "kind": measurement["kind"],
          }
        else:
          existing_override.setdefault("measurementIds", []).append(measurement["id"])
        diagnostics.append(
          {
            "measurementId": measurement["id"],
            "lineKey": line_key,
            "kind": measurement["kind"],
            "rollerIndex": measurement.get("rollerIndex"),
            "projectedX": float(projection["projectedX"]),
            "projectedY": float(projection["projectedY"]),
            "actualWireX": float(measurement["actualWireX"]),
            "actualWireY": float(measurement["actualWireY"]),
            "offsetX": float(offset_x),
            "offsetY": float(offset_y),
          }
        )

      machine_draft = {
        "layer": target_layer,
        "cameraWireOffsetX": evaluation["cameraOffsetX"],
        "cameraWireOffsetY": evaluation["cameraOffsetY"],
        "rollerYCals": list(evaluation["rollerYCals"]),
        "nominalRollerY": float(nominal_roller_y),
        "measurementRevision": self._measurementRevision(),
        "measurementIds": measurement_ids,
        "objective": dict(evaluation["score"]),
      }
      machine_solve = {
        "fitError": None,
        "measurementRevision": self._measurementRevision(),
        "measurementIds": measurement_ids,
        "objective": dict(evaluation["score"]),
        "lineOffsetOverrides": dict(overrides),
        "lineOffsetOverrideItems": line_offset_override_items(overrides),
        "diagnostics": diagnostics,
      }
      draft["machineSolve"] = machine_solve
      draft["lineOffsetOverrides"] = dict(overrides)
      state["machineDraft"] = machine_draft
      self._updateMachineSolveStatus(
        target_layer,
        operationId=operation_id,
        status="succeeded",
        step="done",
        message=(
          "Machine XY solve completed with "
          + str(len(measurement_ids))
          + " measurement"
          + ("" if len(measurement_ids) == 1 else "s")
          + "."
        ),
        fitError=None,
        finishedAt=self._timestamp(),
        cancelRequested=False,
        completedEvaluations=int(
          evaluation.get("progress", {}).get("completedEvaluations", 0)
        ),
        totalEvaluations=int(
          evaluation.get("progress", {}).get("totalEvaluations", 0)
        ),
        percentComplete=100.0,
        elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
        estimatedSecondsRemaining=0.0,
      )
      self._cancelRequestedMachineSolveOperationIds.discard(str(operation_id))
      self._saveState()
      self._log(
        "SOLVE_MACHINE_XY_DONE",
        "Machine XY solve completed.",
        [
          operation_id,
          target_layer,
          len(measurement_ids),
          dict(evaluation["score"]),
        ],
      )
      return machine_solve
    except _MachineXYSolveCancelled:
      self._cancelRequestedMachineSolveOperationIds.discard(str(operation_id))
      self._updateMachineSolveStatus(
        target_layer,
        operationId=operation_id,
        status="canceled",
        step="canceled",
        message="Machine XY solve canceled.",
        fitError=None,
        finishedAt=self._timestamp(),
        cancelRequested=False,
        percentComplete=100.0,
        elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
        estimatedSecondsRemaining=0.0,
      )
      self._log(
        "SOLVE_MACHINE_XY_CANCELED",
        "Machine XY solve canceled.",
        [operation_id, target_layer],
      )
      return {
        "canceled": True,
        "fitError": None,
        "measurementRevision": self._measurementRevision(),
      }
    except Exception as exception:
      self._cancelRequestedMachineSolveOperationIds.discard(str(operation_id))
      message = "Machine XY solve failed: " + _error_text(exception)
      self._updateMachineSolveStatus(
        target_layer,
        operationId=operation_id,
        status="failed",
        step="failed",
        message=message,
        fitError=message,
        finishedAt=self._timestamp(),
        cancelRequested=False,
        percentComplete=100.0,
        elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
        estimatedSecondsRemaining=0.0,
      )
      draft = self._layerDraft(target_layer, create=True)
      draft["machineSolve"] = {
        "fitError": message,
        "measurementRevision": self._measurementRevision(),
      }
      self._saveState()
      self._log(
        "SOLVE_MACHINE_XY_FAILED",
        "Machine XY solve failed.",
        [operation_id, target_layer, repr(exception), traceback.format_exc()],
      )
      raise ValueError(message)

  # -------------------------------------------------------------------
  def applyMachineXY(self, layer=None):
    self._geometryMutationGuard()
    target_layer = self._resolvedLayer(layer)
    state = self._loadState()
    machine_draft = state.get("machineDraft")
    draft = self._layerDraft(target_layer)
    if machine_draft is None or str(machine_draft.get("layer")) != target_layer:
      raise ValueError("Run machine XY solve for the active layer before applying.")
    if draft is None or not draft.get("lineOffsetOverrides"):
      raise ValueError("No solved line offsets are available to apply.")

    machine_calibration = self._machineCalibration()
    camera_offset_x = float(machine_draft["cameraWireOffsetX"])
    camera_offset_y = float(machine_draft["cameraWireOffsetY"])
    manual = getattr(self._process, "manualCalibration", None)
    if manual is not None and hasattr(manual, "_applySharedCameraOffset"):
      manual._applySharedCameraOffset(camera_offset_x, camera_offset_y)
    else:
      machine_calibration.cameraWireOffsetX = camera_offset_x
      machine_calibration.cameraWireOffsetY = camera_offset_y
      machine_calibration.save()

    same_side_measurements = [
      measurement
      for measurement in self._usableMeasurements(target_layer)
      if measurement["kind"] == "same_side"
      and measurement["usableForMachineXY"]
        and measurement.get("rollerIndex") is not None
    ]
    roller_measurements = []
    for measurement in same_side_measurements:
      roller_index = int(measurement["rollerIndex"])
      roller_measurements.append(
        RollerArmMeasurement(
          gcode_line=str(measurement["gcodeLine"]),
          layer=target_layer,
          actual_x=float(measurement["actualWireX"]),
          actual_y=float(measurement["actualWireY"]),
          roller_index=roller_index,
          y_cal=float(machine_draft["rollerYCals"][roller_index]),
        )
      )

    machine_calibration.rollerArmCalibration = RollerArmCalibration(
      measurements=roller_measurements,
      fitted_y_cals=tuple(float(value) for value in machine_draft["rollerYCals"]),
      center_displacement=0.0,
      arm_tilt_rad=0.0,
    )
    machine_calibration.save()
    clear_uv_head_target_caches(layer_calibration=False, machine_calibration=True)

    template_service = self._templateService(target_layer)
    override_result = template_service.replaceLineOffsetOverrides(
      draft["lineOffsetOverrides"]
    )
    if not override_result.get("ok", False):
      raise ValueError(
        str(override_result.get("error", "Failed to apply line offset overrides."))
      )
    script_variant = getattr(template_service, "_lastGeneratedScriptVariant", None)
    generation_result = template_service.generateRecipeFile(scriptVariant=script_variant)
    if not generation_result.get("ok", False):
      raise ValueError(
        str(generation_result.get("error", "Failed to regenerate recipe file."))
      )
    return {
      "machineCalibration": {
        "cameraWireOffsetX": float(machine_calibration.cameraWireOffsetX),
        "cameraWireOffsetY": float(machine_calibration.cameraWireOffsetY),
        "rollerArmCalibration": roller_arm_calibration_to_dict(
          machine_calibration.rollerArmCalibration
        ),
      },
      "lineOffsetOverrideItems": line_offset_override_items(draft["lineOffsetOverrides"]),
      "scriptVariant": script_variant,
      "generation": generation_result.get("data"),
    }

  # -------------------------------------------------------------------
  def setLineOffsetOverride(self, layer, line_key, x_value, y_value):
    self._geometryMutationGuard()
    service = self._templateService(layer)
    return service.setLineOffsetOverride(line_key, x_value, y_value)

  # -------------------------------------------------------------------
  def deleteLineOffsetOverride(self, layer, line_key):
    self._geometryMutationGuard()
    service = self._templateService(layer)
    return service.deleteLineOffsetOverride(line_key)

  # -------------------------------------------------------------------
  def _liveLayerPlaneSummary(self, layer):
    calibration = self._activeLayerCalibration(layer)
    z_plane = getattr(calibration, "zPlaneCalibration", None)
    if z_plane is None:
      return None
    return layer_z_plane_calibration_to_dict(z_plane)

  # -------------------------------------------------------------------
  def getState(self):
    state = self._loadState()
    layer = self._process.getRecipeLayer()
    enabled = layer in _SUPPORTED_LAYERS
    disabled_reason = None
    if not enabled:
      if layer is None:
        disabled_reason = "Load an active U or V recipe first."
      else:
        disabled_reason = "Machine geometry calibration only supports U and V."

    last_trace = getattr(self._process, "getLastInstructionTrace", lambda: None)()
    machine_calibration = self._machineCalibration()
    machine_live = {
      "cameraWireOffsetX": self._currentCameraOffset()[0],
      "cameraWireOffsetY": self._currentCameraOffset()[1],
      "nominalRollerY": _nominal_roller_y(machine_calibration),
      "rollerYCals": list(_live_roller_y_cals(machine_calibration)),
    }

    layer_state = None
    if enabled:
      template_state = self._templateService(layer).getState()
      draft = self._layerDraft(layer, create=False) or {
        "zPlaneCalibration": None,
        "machineSolve": None,
        "lineOffsetOverrides": {},
      }
      layer_state = {
        "layer": layer,
        "liveZPlaneCalibration": self._liveLayerPlaneSummary(layer),
        "draftZPlaneCalibration": draft.get("zPlaneCalibration"),
        "draftZPlaneStale": (
          draft.get("zPlaneSolve", {}).get("measurementRevision")
          != self._measurementRevision()
          if draft.get("zPlaneSolve")
          else False
        ),
        "currentLineOffsetOverrides": template_state.get("lineOffsetOverrides", {}),
        "currentLineOffsetOverrideItems": template_state.get(
          "lineOffsetOverrideItems", []
        ),
        "draftLineOffsetOverrides": draft.get("lineOffsetOverrides", {}),
        "draftLineOffsetOverrideItems": line_offset_override_items(
          draft.get("lineOffsetOverrides", {})
        ),
        "machineSolve": draft.get("machineSolve"),
        "machineSolveStatus": draft.get("machineSolveStatus"),
      }

    measurements = []
    for measurement in self._loadState().get("measurements", []):
      item = dict(measurement)
      item["usableForLayerZ"] = (
        item.get("kind") == "same_side" and item.get("actualZ") is not None
      )
      item["usableForMachineXY"] = (
        item.get("actualWireX") is not None
        and item.get("actualWireY") is not None
        and item.get("lineKey") is not None
      )
      measurements.append(item)

    return {
      "enabled": enabled,
      "disabledReason": disabled_reason,
      "activeLayer": layer,
      "gcodeExecutionActive": self._isGCodeExecutionActive(),
      "measurementRevision": self._measurementRevision(),
      "lastMotionTrace": last_trace,
      "currentPositions": self._currentPositions(),
      "measurements": measurements,
      "machine": {
        "live": machine_live,
        "draft": state.get("machineDraft"),
        "draftStale": (
          state.get("machineDraft", {}).get("measurementRevision")
          != self._measurementRevision()
          if state.get("machineDraft")
          else False
        ),
      },
      "layerState": layer_state,
    }
