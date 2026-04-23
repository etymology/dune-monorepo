from __future__ import annotations

import errno
import copy
import json
import multiprocessing
import os
import random
import pathlib
import queue
import threading
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
  _lookup_recipe_site,
  parse_anchor_to_target_command,
)


_SUPPORTED_LAYERS = ("U", "V")
_TRACE_LINE_REQUIRES = "~anchorToTarget("
_EPSILON = 1e-9
_SGD_MIN_LEARNING_RATE = 0.01
_SGD_MAX_LEARNING_RATE = 0.75
_SGD_MIN_PERTURBATION = 0.01
_SGD_MAX_PERTURBATION = 2.0
_SGD_MIN_BATCH_SIZE = 1
_SGD_MAX_BATCH_SIZE = 16
_SGD_MAX_ITERATIONS = 40
_SGD_BACKOFF_STEPS = 4
_CALIBRATION_PATH_CACHE: dict[tuple, str] = {}  # (roller_y_cals, camera_offset) -> path


def _normalize_layer(layer) -> str:
  normalized = str(layer).strip().upper()
  if normalized not in _SUPPORTED_LAYERS:
    raise ValueError("Machine geometry calibration only supports U and V layers.")
  return normalized


def _deep_copy_json(value):
  return json.loads(json.dumps(value))


def _nominal_roller_y(machine_calibration: MachineCalibration) -> float:
  return (float(machine_calibration.headRollerGap) / 2.0) + float(
    machine_calibration.headRollerRadius
  )


def _live_roller_y_cals(
  machine_calibration: MachineCalibration,
) -> tuple[float, float, float, float]:
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


def _machine_xy_rng():
  return random.Random()


def _clamp(value, minimum, maximum):
  return max(float(minimum), min(float(maximum), float(value)))


def _measurement_site_label(measurement) -> str | None:
  cached = measurement.get("siteLabel") or measurement.get("site_label")
  if cached:
    return str(cached)

  command_text = measurement.get("gcodeLine") or measurement.get("traceLine")
  layer = measurement.get("layer")
  if not command_text or not layer:
    return None

  try:
    command = parse_anchor_to_target_command(str(command_text))
    site = _lookup_recipe_site(str(layer), command.anchor_pin, command.target_pin)
    return str(site.site_label)
  except Exception:
    return None


def _measurement_site_key(measurement) -> str:
  label = _measurement_site_label(measurement)
  if label:
    return label
  line_key = measurement.get("lineKey")
  if line_key is not None:
    return str(line_key)
  measurement_id = measurement.get("id")
  return str(measurement_id)


def _group_measurements_by_site_label(measurements):
  grouped = {}
  for measurement in measurements:
    key = _measurement_site_key(measurement)
    grouped.setdefault(key, []).append(measurement)
  return grouped


def _parameter_vector_to_calibration(vector):
  vector = [float(value) for value in vector[:6]]
  return (
    (float(vector[0]), float(vector[1])),
    [float(value) for value in vector[2:6]],
  )


def _format_machine_xy_parameters(vector):
  return {
    "cameraOffsetX": float(vector[0]),
    "cameraOffsetY": float(vector[1]),
    "rollerYCals": [float(value) for value in vector[2:6]],
  }


def _mean(values):
  values = [float(value) for value in values]
  if not values:
    return 0.0
  return float(sum(values) / len(values))


class _MachineXYSolveCancelled(RuntimeError):
  pass


class _MachineXYSolveKilled(RuntimeError):
  pass


class _MachineXYEvaluationWorker:
  def __init__(self, process, result_queue):
    self._process = process
    self._result_queue = result_queue

  @property
  def exitcode(self):
    return self._process.exitcode

  def start(self):
    self._process.start()

  def is_alive(self):
    return self._process.is_alive()

  def poll(self, timeout=0.0):
    try:
      return self._result_queue.get(timeout=max(0.0, float(timeout)))
    except queue.Empty:
      return None

  def terminate(self):
    if self._process.is_alive():
      self._process.terminate()
      self._process.join(timeout=1.0)
    if self._process.is_alive() and hasattr(self._process, "kill"):
      self._process.kill()
      self._process.join(timeout=1.0)

  def close(self):
    try:
      if self._process.is_alive():
        self._process.join(timeout=0.1)
    except Exception:
      pass
    try:
      if hasattr(self._result_queue, "close"):
        self._result_queue.close()
    except Exception:
      pass
    try:
      if hasattr(self._result_queue, "join_thread"):
        self._result_queue.join_thread()
    except Exception:
      pass


def _project_machine_xy_measurements(
  group_measurements,
  *,
  layer_path,
  machine_path,
  roller_y_cals,
):
  # Batch projections with shared config; rely on compute_uv_anchor_to_target_view cache
  roller_offsets = tuple(float(value) for value in roller_y_cals[:4])
  results = []
  for measurement in group_measurements:
    view = compute_uv_anchor_to_target_view(
      command_text=str(measurement["gcodeLine"]),
      layer=str(measurement["layer"]),
      machine_calibration_path=machine_path,
      layer_calibration_path=layer_path,
      roller_arm_y_offsets=roller_offsets,
    )
    results.append(
      (
        measurement,
        {
          "projectedX": float(view.interpreter_wire_point.x),
          "projectedY": float(view.interpreter_wire_point.y),
        },
      )
    )
  return results


def _machine_xy_evaluation_worker(
  result_queue,
  group_measurements,
  *,
  layer_path,
  machine_path,
  roller_y_cals,
):
  try:
    result_queue.put(
      {
        "ok": True,
        "results": _project_machine_xy_measurements(
          group_measurements,
          layer_path=layer_path,
          machine_path=machine_path,
          roller_y_cals=roller_y_cals,
        ),
      }
    )
  except Exception as exception:
    result_queue.put(
      {
        "ok": False,
        "error": _error_text(exception),
        "traceback": traceback.format_exc(),
      }
    )


class MachineGeometryCalibration:
  FILE_NAME = "machineGeometryCalibration.json"

  def __init__(self, process):
    self._process = process
    self._state = None
    self._loadedPath = None
    self._cancelRequestedMachineSolveOperationIds = set()
    self._killRequestedMachineSolveOperationIds = set()
    self._activeMachineSolveOperationIds = set()
    self._activeMachineSolveEvaluations = {}
    self._machineSolveEvaluationLock = threading.RLock()

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
  def _isMachineSolveKillRequested(self, operation_id):
    return str(operation_id) in self._killRequestedMachineSolveOperationIds

  # -------------------------------------------------------------------
  def _raiseIfMachineSolveCancelled(self, layer, operation_id):
    if self._isMachineSolveCancellationRequested(operation_id):
      raise _MachineXYSolveCancelled("Machine XY solve canceled at user request.")

  # -------------------------------------------------------------------
  def _raiseIfMachineSolveKilled(self, operation_id):
    if self._isMachineSolveKillRequested(operation_id):
      raise _MachineXYSolveKilled("Machine XY solve killed at user request.")

  # -------------------------------------------------------------------
  def _clearMachineSolveRequests(self, operation_id):
    self._cancelRequestedMachineSolveOperationIds.discard(str(operation_id))
    self._killRequestedMachineSolveOperationIds.discard(str(operation_id))

  # -------------------------------------------------------------------
  def _registerMachineSolveOperation(self, operation_id):
    with self._machineSolveEvaluationLock:
      self._activeMachineSolveOperationIds.add(str(operation_id))

  # -------------------------------------------------------------------
  def _unregisterMachineSolveOperation(self, operation_id):
    with self._machineSolveEvaluationLock:
      self._activeMachineSolveOperationIds.discard(str(operation_id))
      self._activeMachineSolveEvaluations.pop(str(operation_id), None)

  # -------------------------------------------------------------------
  def _isMachineSolveOperationActive(self, operation_id):
    with self._machineSolveEvaluationLock:
      return str(operation_id) in self._activeMachineSolveOperationIds

  # -------------------------------------------------------------------
  def _reconcileMachineSolveStatus(self, layer, status=None):
    resolved_layer = self._resolvedLayer(layer)
    current_status = status
    if current_status is None:
      current_status = self._machineSolveStatus(resolved_layer, create=False)
    if current_status is None:
      return None

    state_name = str(current_status.get("status", "")).strip().lower()
    operation_id = current_status.get("operationId")
    if state_name not in ("running", "cancel_requested", "kill_requested"):
      return current_status
    if operation_id and self._isMachineSolveOperationActive(operation_id):
      return current_status

    message = str(current_status.get("message") or "").strip()
    if not message:
      message = "Machine XY solve is no longer running."
    else:
      message = message.rstrip(".") + ". Machine XY solve is no longer running."
    reconciled = self._updateMachineSolveStatus(
      resolved_layer,
      operationId=operation_id,
      status="interrupted",
      step="interrupted",
      message=message,
      cancelRequested=False,
      killRequested=False,
      finishedAt=self._timestamp(),
      estimatedSecondsRemaining=0.0,
    )
    self._clearMachineSolveRequests(operation_id)
    self._log(
      "SOLVE_MACHINE_XY_RECONCILED",
      "Reconciled stale Machine XY solve status.",
      [operation_id, resolved_layer, state_name],
    )
    return reconciled

  # -------------------------------------------------------------------
  def _registerActiveMachineSolveEvaluation(self, operation_id, evaluation):
    with self._machineSolveEvaluationLock:
      operation_key = str(operation_id)
      active = self._activeMachineSolveEvaluations.setdefault(operation_key, set())
      active.add(evaluation)

  # -------------------------------------------------------------------
  def _unregisterActiveMachineSolveEvaluation(self, operation_id, evaluation):
    with self._machineSolveEvaluationLock:
      operation_key = str(operation_id)
      active = self._activeMachineSolveEvaluations.get(operation_key)
      if not active:
        return
      active.discard(evaluation)
      if not active:
        self._activeMachineSolveEvaluations.pop(operation_key, None)

  # -------------------------------------------------------------------
  def _terminateActiveMachineSolveEvaluations(self, operation_id):
    with self._machineSolveEvaluationLock:
      active = list(self._activeMachineSolveEvaluations.get(str(operation_id), ()))
    for evaluation in active:
      try:
        evaluation.terminate()
      except Exception:
        pass
    return len(active)

  # -------------------------------------------------------------------
  def _spawnMachineSolveEvaluation(
    self,
    group_measurements,
    *,
    layer_path,
    machine_path,
    roller_y_cals,
  ):
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(
      target=_machine_xy_evaluation_worker,
      args=(result_queue, group_measurements),
      kwargs={
        "layer_path": layer_path,
        "machine_path": machine_path,
        "roller_y_cals": tuple(float(value) for value in roller_y_cals[:4]),
      },
    )
    return _MachineXYEvaluationWorker(process, result_queue)

  # -------------------------------------------------------------------
  def _useIsolatedMachineSolveEvaluation(self):
    bound_method = getattr(self._projectMeasurement, "__func__", None)
    return bound_method is MachineGeometryCalibration._projectMeasurement

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
      raise ValueError(
        "No layer calibration is loaded for active layer " + str(layer) + "."
      )
    return calibration

  # -------------------------------------------------------------------
  def _syncLayerCalibrationHandlers(self, calibration):
    handlers = []
    direct_handler = getattr(self._process, "gCodeHandler", None)
    if direct_handler is not None:
      handlers.append(direct_handler)
    workspace_handler = getattr(
      getattr(self._process, "workspace", None), "_gCodeHandler", None
    )
    if workspace_handler is not None and workspace_handler not in handlers:
      handlers.append(workspace_handler)

    for handler in handlers:
      if not hasattr(handler, "useLayerCalibration"):
        continue
      loaded = (
        handler.getLayerCalibration()
        if hasattr(handler, "getLayerCalibration")
        else None
      )
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
    site_label = None
    try:
      site_label = _lookup_recipe_site(layer, command.anchor_pin, command.target_pin).site_label
    except Exception:
      site_label = None
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
      "siteLabel": site_label,
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
    status = self._reconcileMachineSolveStatus(target_layer)
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
  def killMachineXY(self, layer=None):
    target_layer = self._resolvedLayer(layer)
    status = self._reconcileMachineSolveStatus(target_layer)
    if status is None:
      return {
        "layer": target_layer,
        "killed": False,
        "message": "No Machine XY solve is active.",
      }

    current_status = str(status.get("status", "")).strip().lower()
    operation_id = status.get("operationId")
    if (
      current_status not in ("running", "cancel_requested", "kill_requested")
      or not operation_id
    ):
      return {
        "layer": target_layer,
        "killed": False,
        "message": "No Machine XY solve is active.",
      }

    self._killRequestedMachineSolveOperationIds.add(str(operation_id))
    terminated_evaluations = self._terminateActiveMachineSolveEvaluations(operation_id)
    updated_status = self._updateMachineSolveStatus(
      target_layer,
      operationId=operation_id,
      status="kill_requested",
      message="Kill requested. Terminating all active evaluations.",
      cancelRequested=True,
      cancelRequestedAt=self._timestamp(),
      killRequested=True,
      killRequestedAt=self._timestamp(),
      terminatedEvaluations=int(terminated_evaluations),
    )
    self._log(
      "SOLVE_MACHINE_XY_KILL_REQUESTED",
      "Machine XY solve kill requested.",
      [operation_id, target_layer, terminated_evaluations],
    )
    return {
      "layer": target_layer,
      "killed": True,
      "message": "Kill requested.",
      "terminatedEvaluations": int(terminated_evaluations),
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
    roller_tuple = tuple(float(value) for value in roller_y_cals[:4])
    cache_key = (roller_tuple, None)
    if camera_offset is not None:
      cache_key = (roller_tuple, (float(camera_offset[0]), float(camera_offset[1])))
    if cache_key in _CALIBRATION_PATH_CACHE:
      cached_path = _CALIBRATION_PATH_CACHE[cache_key]
      if os.path.isfile(cached_path):
        return cached_path
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
      fitted_y_cals=roller_tuple,
      center_displacement=0.0,
      arm_tilt_rad=0.0,
    )
    temporary_path = os.path.join(temporary_directory, temporary_name)
    with open(temporary_path, "w", encoding="utf-8") as handle:
      json.dump(candidate._to_dict(), handle, indent=2)
    _CALIBRATION_PATH_CACHE[cache_key] = temporary_path
    clear_uv_head_target_caches(layer_calibration=False, machine_calibration=True)
    return temporary_path

  # -------------------------------------------------------------------
  def _removeTemporaryCandidatePath(self, path):
    # Remove from cache if present
    keys_to_remove = [k for k, v in _CALIBRATION_PATH_CACHE.items() if v == path]
    for key in keys_to_remove:
      del _CALIBRATION_PATH_CACHE[key]
    try:
      os.unlink(path)
    except OSError:
      pass

  # -------------------------------------------------------------------
  def _projectMeasurement(
    self, measurement, *, layer_path, machine_path, roller_y_cals
  ):
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
      delta = abs(
        float(entry["actualWireX"]) - float(measurement["actualWireX"])
      ) + abs(float(entry["actualWireY"]) - float(measurement["actualWireY"]))
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
    measurements = list(measurements)
    measurement_order = [str(measurement["id"]) for measurement in measurements]
    measurement_site_labels = {}
    site_order = []
    same_side_by_roller = {index: [] for index in range(4)}
    for measurement in measurements:
      if (
        measurement["kind"] == "same_side"
        and measurement.get("rollerIndex") is not None
      ):
        same_side_by_roller[int(measurement["rollerIndex"])].append(measurement)
      site_label = _measurement_site_label(measurement)
      if not site_label:
        site_label = str(measurement.get("lineKey") or measurement.get("id"))
      measurement_site_labels[str(measurement["id"])] = site_label
      if site_label not in site_order:
        site_order.append(site_label)

    projection_cache: dict[
      tuple[str, tuple[float, ...], tuple[float, float]], dict
    ] = {}

    def _cached_project(measurement, roller_y_cals, camera_offset):
      cache_key = (
        str(measurement["gcodeLine"]),
        tuple(float(v) for v in roller_y_cals[:4]),
        (float(camera_offset[0]), float(camera_offset[1])),
      )
      if cache_key in projection_cache:
        return projection_cache[cache_key]
      machine_path = self._candidateMachineCalibrationPath(
        roller_y_cals,
        camera_offset=camera_offset,
      )
      try:
        result = self._projectMeasurement(
          measurement,
          layer_path=layer_path,
          machine_path=machine_path,
          roller_y_cals=roller_y_cals,
        )
      finally:
        self._removeTemporaryCandidatePath(machine_path)
      projection_cache[cache_key] = result
      return result

    def project_group(group_measurements, roller_y_cals, camera_offset):
      if not group_measurements:
        return []
      self._raiseIfMachineSolveCancelled(layer, operation_id)
      self._raiseIfMachineSolveKilled(operation_id)
      if not self._useIsolatedMachineSolveEvaluation():
        results = []
        for measurement in group_measurements:
          self._raiseIfMachineSolveCancelled(layer, operation_id)
          self._raiseIfMachineSolveKilled(operation_id)
          projection = _cached_project(measurement, roller_y_cals, camera_offset)
          results.append((measurement, projection))
        return results
      machine_path = self._candidateMachineCalibrationPath(
        roller_y_cals,
        camera_offset=camera_offset,
      )
      try:
        evaluation = self._spawnMachineSolveEvaluation(
          group_measurements,
          layer_path=layer_path,
          machine_path=machine_path,
          roller_y_cals=roller_y_cals,
        )
        self._registerActiveMachineSolveEvaluation(operation_id, evaluation)
        evaluation.start()
        payload = None
        try:
          while payload is None:
            self._raiseIfMachineSolveKilled(operation_id)
            payload = evaluation.poll(timeout=0.1)
            if payload is not None:
              break
            if not evaluation.is_alive():
              payload = evaluation.poll(timeout=0.0)
              break
          self._raiseIfMachineSolveKilled(operation_id)
          self._raiseIfMachineSolveCancelled(layer, operation_id)
          if payload is None:
            raise RuntimeError(
              "Machine XY evaluation exited before returning a result."
            )
          if not bool(payload.get("ok")):
            raise RuntimeError(
              "Machine XY evaluation failed: "
              + str(payload.get("error") or "unknown error")
            )
          return list(payload.get("results") or [])
        finally:
          self._unregisterActiveMachineSolveEvaluation(operation_id, evaluation)
          evaluation.close()
      finally:
        self._removeTemporaryCandidatePath(machine_path)

    def summarize_results(results, camera_offset):
      camera_x = float(camera_offset[0])
      camera_y = float(camera_offset[1])
      by_measurement = {}
      by_site_label = {}
      total_loss = 0.0
      for measurement, projection in results:
        site_label = measurement_site_labels.get(str(measurement["id"]))
        if not site_label:
          site_label = str(measurement.get("lineKey") or measurement.get("id"))
        line_key = measurement.get("lineKey")
        if line_key is not None:
          try:
            line_key = normalize_line_key(line_key)
          except Exception:
            line_key = str(line_key)
        offset_x = (float(measurement["effectiveCameraX"]) + camera_x) - float(
          projection["projectedX"]
        )
        offset_y = (float(measurement["rawCameraY"]) + camera_y) - float(
          projection["projectedY"]
        )
        summary = {
          "measurementId": str(measurement["id"]),
          "siteLabel": site_label,
          "lineKey": line_key,
          "measurement": measurement,
          "projection": projection,
          "offsetX": float(offset_x),
          "offsetY": float(offset_y),
        }
        by_measurement[str(measurement["id"])] = summary
        by_site_label.setdefault(site_label, []).append(summary)
        total_loss += (offset_x * offset_x) + (offset_y * offset_y)
      return {
        "loss": float(total_loss),
        "by_measurement": by_measurement,
        "by_site_label": by_site_label,
      }

    def ordered_summaries(summary_by_measurement):
      return [
        summary_by_measurement[measurement_id]
        for measurement_id in measurement_order
        if measurement_id in summary_by_measurement
      ]

    def build_site_offset_items(by_site_label):
      items = []
      for site_label in site_order:
        site_summaries = by_site_label.get(site_label)
        if not site_summaries:
          continue
        offsets_x = [float(summary["offsetX"]) for summary in site_summaries]
        offsets_y = [float(summary["offsetY"]) for summary in site_summaries]
        measurement_ids = [str(summary["measurementId"]) for summary in site_summaries]
        line_keys = [
          str(summary["lineKey"])
          for summary in site_summaries
          if summary.get("lineKey") is not None
        ]
        item = {
          "siteLabel": site_label,
          "x": _mean(offsets_x),
          "y": _mean(offsets_y),
          "measurementIds": measurement_ids,
          "lineKeys": line_keys,
          "measurementCount": len(site_summaries),
          "loss": float(
            sum((float(summary["offsetX"]) ** 2) + (float(summary["offsetY"]) ** 2) for summary in site_summaries)
          ),
        }
        items.append(item)
      return items

    def build_site_offsets(by_site_label):
      items = build_site_offset_items(by_site_label)
      offsets = {item["siteLabel"]: dict(item) for item in items}
      return offsets, items

    def build_line_offset_overrides(summary_by_measurement, site_offsets):
      overrides = {}
      for measurement_id in measurement_order:
        summary = summary_by_measurement.get(measurement_id)
        if summary is None:
          continue
        site_label = summary["siteLabel"]
        site_offset = site_offsets.get(site_label)
        if site_offset is None:
          continue
        line_key = summary.get("lineKey")
        if line_key is None:
          continue
        line_key = normalize_line_key(line_key)
        override = overrides.setdefault(
          line_key,
          {
            "x": float(site_offset["x"]),
            "y": float(site_offset["y"]),
            "siteLabel": site_label,
            "measurementIds": [],
          },
        )
        override.setdefault("measurementIds", []).append(measurement_id)
      return overrides

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

    progress_state = {
      "startedAt": time.time(),
      "completed": 0,
      "total": None,
    }

    progress_checkpoint = {
      "time": 0.0,
      "step": None,
      "message": None,
      "completed": None,
      "total": None,
      "status": None,
      "signature": None,
    }

    def publish(step, message, **fields):
      if progress_callback is None:
        return
      progress_callback(step, message, **progress_fields(**fields))

    def evaluate_batch(
      vector,
      group_measurements,
      *,
      step,
      message,
      epoch,
      batch_index,
      batch_count,
      candidate_label,
      learning_rate,
      perturbation,
      best_loss,
      gradient_norm=None,
      current_loss=None,
      site_label=None,
    ):
      camera_offset = (float(vector[0]), float(vector[1]))
      roller_y_cals = [float(value) for value in vector[2:6]]
      publish(
        step,
        message,
        epoch=int(epoch),
        batchIndex=int(batch_index),
        batchCount=int(batch_count),
        batchSize=len(group_measurements),
        candidateLabel=candidate_label,
        learningRate=float(learning_rate),
        perturbation=float(perturbation),
        bestLoss=(None if best_loss is None else float(best_loss)),
        loss=(None if current_loss is None else float(current_loss)),
        gradientNorm=(
          None if gradient_norm is None else float(gradient_norm)
        ),
        parameters=_format_machine_xy_parameters(vector),
        bestParameters=None,
        siteLabel=site_label,
      )
      results = project_group(group_measurements, roller_y_cals, camera_offset)
      progress_state["completed"] += 1
      summary = summarize_results(results, camera_offset)
      return summary

    def gradient_from_finite_differences(
      vector,
      group_measurements,
      *,
      epoch,
      batch_index,
      batch_count,
      candidate_label,
      learning_rate,
      perturbation,
      best_loss,
      site_label,
    ):
      gradient = []
      for axis_index in range(6):
        plus_vector = [float(value) for value in vector]
        minus_vector = [float(value) for value in vector]
        plus_vector[axis_index] += float(perturbation)
        minus_vector[axis_index] -= float(perturbation)
        plus_summary = evaluate_batch(
          plus_vector,
          group_measurements,
          step="optimizing_sgd",
          message="Evaluating a positive finite-difference perturbation.",
          epoch=epoch,
          batch_index=batch_index,
          batch_count=batch_count,
          candidate_label=f"{candidate_label}_axis_{axis_index}_plus",
          learning_rate=learning_rate,
          perturbation=perturbation,
          best_loss=best_loss,
          site_label=site_label,
        )
        minus_summary = evaluate_batch(
          minus_vector,
          group_measurements,
          step="optimizing_sgd",
          message="Evaluating a negative finite-difference perturbation.",
          epoch=epoch,
          batch_index=batch_index,
          batch_count=batch_count,
          candidate_label=f"{candidate_label}_axis_{axis_index}_minus",
          learning_rate=learning_rate,
          perturbation=perturbation,
          best_loss=best_loss,
          site_label=site_label,
        )
        plus_loss = float(plus_summary["loss"]) / max(len(group_measurements), 1)
        minus_loss = float(minus_summary["loss"]) / max(len(group_measurements), 1)
        gradient.append((plus_loss - minus_loss) / (2.0 * float(perturbation)))
      gradient_norm = float(sum(component * component for component in gradient) ** 0.5)
      return gradient, gradient_norm

    if not measurements:
      camera_offset = (
        float(current_camera_offset[0]),
        float(current_camera_offset[1]),
      )
      roller_y_cals = [float(value) for value in initial_roller_y_cals[:4]]
      publish(
        "done",
        "No machine XY measurements were available. Draft mirrors the current machine camera offset and roller values.",
        completedEvaluations=0,
        totalEvaluations=0,
        percentComplete=100.0,
        phase="done",
        elapsedSeconds=0.0,
        estimatedSecondsRemaining=0.0,
      )
      return {
        "cameraOffsetX": float(camera_offset[0]),
        "cameraOffsetY": float(camera_offset[1]),
        "rollerYCals": roller_y_cals,
        "siteOffsets": {},
        "siteOffsetItems": [],
        "lineOffsetOverrides": {},
        "lineOffsetOverrideItems": [],
        "score": {
          "lineOffsetNorm": 0.0,
          "rollerOffsetNorm": 0.0,
          "cameraOffsetDeltaNorm": 0.0,
          "loss": 0.0,
        },
        "summaries": [],
        "diagnostics": [],
        "progress": {
          "completedEvaluations": 0,
          "totalEvaluations": 0,
        },
      }

    working_vector = [
      float(current_camera_offset[0]),
      float(current_camera_offset[1]),
      *[float(value) for value in initial_roller_y_cals[:4]],
    ]
    batch_size = min(
      len(measurements),
      max(
        _SGD_MIN_BATCH_SIZE,
        min(_SGD_MAX_BATCH_SIZE, max(1, int(round(len(measurements) ** 0.5)))),
      ),
    )
    batch_count = max(1, min(_SGD_MAX_ITERATIONS, max(12, len(measurements))))
    progress_state["total"] = int(
      2 + (batch_count * ((2 * 6) + 1 + _SGD_BACKOFF_STEPS)) + 2
    )

    baseline_summary = evaluate_batch(
      working_vector,
      measurements,
      step="baseline",
      message="Evaluating the current machine XY candidate.",
      epoch=0,
      batch_index=0,
      batch_count=batch_count,
      candidate_label="baseline",
      learning_rate=0.0,
      perturbation=_SGD_MIN_PERTURBATION,
      best_loss=None,
      current_loss=None,
    )
    current_loss = float(baseline_summary["loss"]) / max(len(measurements), 1)
    best_loss = float(current_loss)
    best_vector = list(working_vector)

    baseline_max_abs = max(
      [abs(float(summary["offsetX"])) for summary in baseline_summary["by_measurement"].values()]
      + [abs(float(summary["offsetY"])) for summary in baseline_summary["by_measurement"].values()]
    )
    learning_rate = _clamp(
      max(0.05, baseline_max_abs * 0.05),
      _SGD_MIN_LEARNING_RATE,
      _SGD_MAX_LEARNING_RATE,
    )
    perturbation = _clamp(
      max(_SGD_MIN_PERTURBATION, baseline_max_abs * 0.1),
      _SGD_MIN_PERTURBATION,
      _SGD_MAX_PERTURBATION,
    )

    rng = _machine_xy_rng()
    last_gradient_norm = 0.0

    for epoch in range(1, batch_count + 1):
      self._raiseIfMachineSolveCancelled(layer, operation_id)
      batch_measurements = (
        list(measurements)
        if batch_size >= len(measurements)
        else rng.sample(measurements, batch_size)
      )
      if not batch_measurements:
        continue
      batch_site_labels = sorted(
        {
          _measurement_site_key(measurement)
          for measurement in batch_measurements
        }
      )
      dominant_site_label = batch_site_labels[0] if batch_site_labels else None
      batch_index = epoch
      gradient, gradient_norm = gradient_from_finite_differences(
        working_vector,
        batch_measurements,
        epoch=epoch,
        batch_index=batch_index,
        batch_count=batch_count,
        candidate_label="batch",
        learning_rate=learning_rate,
        perturbation=perturbation,
        best_loss=best_loss,
        site_label=dominant_site_label,
      )
      last_gradient_norm = float(gradient_norm)
      current_batch_summary = evaluate_batch(
        working_vector,
        batch_measurements,
        step="optimizing_sgd",
        message="Evaluating the current machine XY batch.",
        epoch=epoch,
        batch_index=batch_index,
        batch_count=batch_count,
        candidate_label="current",
        learning_rate=learning_rate,
        perturbation=perturbation,
        best_loss=best_loss,
        gradient_norm=gradient_norm,
        current_loss=current_loss,
        site_label=dominant_site_label,
      )
      current_batch_loss = float(current_batch_summary["loss"]) / max(
        len(batch_measurements), 1
      )
      accepted = False
      candidate_loss = current_batch_loss
      candidate_summary = current_batch_summary
      candidate_learning_rate = float(learning_rate)
      for backoff_index in range(_SGD_BACKOFF_STEPS):
        self._raiseIfMachineSolveCancelled(layer, operation_id)
        trial_vector = [
          float(value) - (float(candidate_learning_rate) * float(component))
          for value, component in zip(working_vector, gradient)
        ]
        trial_summary = evaluate_batch(
          trial_vector,
          batch_measurements,
          step="optimizing_sgd",
          message="Testing an SGD update step.",
          epoch=epoch,
          batch_index=batch_index,
          batch_count=batch_count,
          candidate_label=f"update_{backoff_index}",
          learning_rate=candidate_learning_rate,
          perturbation=perturbation,
          best_loss=best_loss,
          gradient_norm=gradient_norm,
          current_loss=current_batch_loss,
          site_label=dominant_site_label,
        )
        trial_loss = float(trial_summary["loss"]) / max(len(batch_measurements), 1)
        if trial_loss < candidate_loss - 1e-12:
          working_vector = list(trial_vector)
          current_loss = float(trial_loss)
          candidate_loss = float(trial_loss)
          candidate_summary = trial_summary
          learning_rate = _clamp(
            candidate_learning_rate * 1.05,
            _SGD_MIN_LEARNING_RATE,
            _SGD_MAX_LEARNING_RATE,
          )
          accepted = True
          break
        candidate_learning_rate *= 0.5

      if not accepted:
        learning_rate = _clamp(
          learning_rate * 0.5,
          _SGD_MIN_LEARNING_RATE,
          _SGD_MAX_LEARNING_RATE,
        )
      if candidate_loss < best_loss - 1e-12:
        best_loss = float(candidate_loss)
        best_vector = list(working_vector)
      publish(
        "optimizing",
        "Running stochastic gradient descent for Machine XY.",
        epoch=epoch,
        batchIndex=batch_index,
        batchCount=batch_count,
        batchSize=len(batch_measurements),
        candidateLabel="accepted" if accepted else "rejected",
        learningRate=learning_rate,
        perturbation=perturbation,
        loss=current_loss,
        bestLoss=best_loss,
        gradientNorm=last_gradient_norm,
        parameters=_format_machine_xy_parameters(working_vector),
        bestParameters=_format_machine_xy_parameters(best_vector),
        siteLabel=dominant_site_label,
      )

      perturbation = _clamp(
        perturbation * 0.98,
        _SGD_MIN_PERTURBATION,
        _SGD_MAX_PERTURBATION,
      )

    full_summary_current = evaluate_batch(
      working_vector,
      measurements,
      step="finalizing",
      message="Evaluating the final current Machine XY parameters.",
      epoch=batch_count + 1,
      batch_index=batch_count + 1,
      batch_count=batch_count,
      candidate_label="current_final",
      learning_rate=learning_rate,
      perturbation=perturbation,
      best_loss=best_loss,
      gradient_norm=last_gradient_norm,
      current_loss=current_loss,
      site_label=None,
    )
    full_summary_best = full_summary_current
    best_full_vector = list(working_vector)
    if any(abs(float(a) - float(b)) > 1e-12 for a, b in zip(best_vector, working_vector)):
      candidate_full_summary = evaluate_batch(
        best_vector,
        measurements,
        step="finalizing",
        message="Evaluating the best tracked Machine XY parameters.",
        epoch=batch_count + 1,
        batch_index=batch_count + 2,
        batch_count=batch_count,
        candidate_label="best_final",
        learning_rate=learning_rate,
        perturbation=perturbation,
        best_loss=best_loss,
        gradient_norm=last_gradient_norm,
        current_loss=current_loss,
        site_label=None,
      )
      if float(candidate_full_summary["loss"]) < float(full_summary_best["loss"]):
        full_summary_best = candidate_full_summary
        best_full_vector = list(best_vector)

    site_offsets, site_offset_items = build_site_offsets(full_summary_best["by_site_label"])
    line_offset_overrides = build_line_offset_overrides(
      full_summary_best["by_measurement"], site_offsets
    )

    diagnostics = []
    for site_label in site_order:
      site_summary = full_summary_best["by_site_label"].get(site_label)
      if not site_summary:
        continue
      diagnostics.append(
        {
          "siteLabel": site_label,
          "measurementIds": [str(summary["measurementId"]) for summary in site_summary],
          "lineKeys": [str(summary["lineKey"]) for summary in site_summary if summary.get("lineKey") is not None],
          "meanOffsetX": _mean(summary["offsetX"] for summary in site_summary),
          "meanOffsetY": _mean(summary["offsetY"] for summary in site_summary),
          "loss": float(
            sum((float(summary["offsetX"]) ** 2) + (float(summary["offsetY"]) ** 2) for summary in site_summary)
          ),
          "measurementCount": len(site_summary),
        }
      )

    selected_vector = best_full_vector
    selected_summary = full_summary_best
    selected_loss = float(selected_summary["loss"])
    camera_offset = (float(selected_vector[0]), float(selected_vector[1]))
    roller_y_cals = [float(value) for value in selected_vector[2:6]]

    return {
      "cameraOffsetX": float(camera_offset[0]),
      "cameraOffsetY": float(camera_offset[1]),
      "rollerYCals": roller_y_cals,
      "siteOffsets": site_offsets,
      "siteOffsetItems": site_offset_items,
      "lineOffsetOverrides": line_offset_overrides,
      "lineOffsetOverrideItems": line_offset_override_items(line_offset_overrides),
      "score": {
        "lineOffsetNorm": float(selected_loss),
        "rollerOffsetNorm": 0.0,
        "cameraOffsetDeltaNorm": 0.0,
        "loss": float(selected_loss),
      },
      "summaries": ordered_summaries(selected_summary["by_measurement"]),
      "diagnostics": diagnostics,
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
    self._clearMachineSolveRequests(operation_id)
    self._registerMachineSolveOperation(operation_id)
    progress_checkpoint = {
      "time": 0.0,
      "step": None,
      "message": None,
      "completed": None,
      "total": None,
      "status": None,
      "signature": None,
    }

    def progress(step, message, **fields):
      now = time.time()
      payload = dict(fields)
      completed = payload.get("completedEvaluations")
      total = payload.get("totalEvaluations")
      signature = json.dumps(
        {
          "loss": payload.get("loss"),
          "bestLoss": payload.get("bestLoss"),
          "gradientNorm": payload.get("gradientNorm"),
          "learningRate": payload.get("learningRate"),
          "batchIndex": payload.get("batchIndex"),
          "epoch": payload.get("epoch"),
          "candidateLabel": payload.get("candidateLabel"),
          "siteLabel": payload.get("siteLabel"),
          "parameters": payload.get("parameters"),
          "bestParameters": payload.get("bestParameters"),
        },
        sort_keys=True,
        default=str,
      )
      should_emit = (
        progress_checkpoint["step"] != step
        or progress_checkpoint["message"] != message
        or progress_checkpoint["completed"] != completed
        or progress_checkpoint["total"] != total
        or progress_checkpoint["status"] != "running"
        or progress_checkpoint["signature"] != signature
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
      progress_checkpoint["signature"] = signature
      status_fields = dict(payload)
      if "elapsedSeconds" not in status_fields:
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
        [operation_id, target_layer, step, status_fields],
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
        killRequested=False,
        killRequestedAt=None,
        terminatedEvaluations=0,
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
        self._clearMachineSolveRequests(operation_id)
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
      overrides = dict(evaluation.get("lineOffsetOverrides", {}))
      diagnostics = list(evaluation.get("diagnostics", []))
      measurement_ids = [
        str(summary["measurementId"]) for summary in evaluation.get("summaries", [])
      ]

      machine_draft = {
        "layer": target_layer,
        "cameraWireOffsetX": evaluation["cameraOffsetX"],
        "cameraWireOffsetY": evaluation["cameraOffsetY"],
        "rollerYCals": list(evaluation["rollerYCals"]),
        "siteOffsets": dict(evaluation.get("siteOffsets", {})),
        "siteOffsetItems": list(evaluation.get("siteOffsetItems", [])),
        "nominalRollerY": float(nominal_roller_y),
        "measurementRevision": self._measurementRevision(),
        "measurementIds": measurement_ids,
        "objective": dict(evaluation["score"]),
        "diagnostics": diagnostics,
      }
      machine_solve = {
        "fitError": None,
        "measurementRevision": self._measurementRevision(),
        "measurementIds": measurement_ids,
        "objective": dict(evaluation["score"]),
        "siteOffsets": dict(evaluation.get("siteOffsets", {})),
        "siteOffsetItems": list(evaluation.get("siteOffsetItems", [])),
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
        totalEvaluations=int(evaluation.get("progress", {}).get("totalEvaluations", 0)),
        percentComplete=100.0,
        elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
        estimatedSecondsRemaining=0.0,
        siteOffsets=dict(evaluation.get("siteOffsets", {})),
        siteOffsetItems=list(evaluation.get("siteOffsetItems", [])),
      )
      self._clearMachineSolveRequests(operation_id)
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
    except _MachineXYSolveKilled:
      self._terminateActiveMachineSolveEvaluations(operation_id)
      self._clearMachineSolveRequests(operation_id)
      self._updateMachineSolveStatus(
        target_layer,
        operationId=operation_id,
        status="killed",
        step="killed",
        message="Machine XY solve killed. Active evaluation terminated.",
        fitError=None,
        finishedAt=self._timestamp(),
        cancelRequested=False,
        killRequested=False,
        percentComplete=100.0,
        elapsedSeconds=float(max(0.0, time.time() - solve_started_at)),
        estimatedSecondsRemaining=0.0,
      )
      self._log(
        "SOLVE_MACHINE_XY_KILLED",
        "Machine XY solve killed.",
        [operation_id, target_layer],
      )
      return {
        "canceled": True,
        "killed": True,
        "fitError": None,
        "measurementRevision": self._measurementRevision(),
      }
    except _MachineXYSolveCancelled:
      self._clearMachineSolveRequests(operation_id)
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
      self._terminateActiveMachineSolveEvaluations(operation_id)
      self._clearMachineSolveRequests(operation_id)
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
    finally:
      self._unregisterMachineSolveOperation(operation_id)
      self._clearMachineSolveRequests(operation_id)

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
    machine_calibration.cameraWireOffsetX = camera_offset_x
    machine_calibration.cameraWireOffsetY = camera_offset_y
    if manual is not None and hasattr(manual, "_applySharedCameraOffset"):
      manual._applySharedCameraOffset(camera_offset_x, camera_offset_y)

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
    generation_result = template_service.generateRecipeFile(
      scriptVariant=script_variant
    )
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
      "siteOffsets": dict(machine_draft.get("siteOffsets", {})),
      "siteOffsetItems": list(machine_draft.get("siteOffsetItems", [])),
      "lineOffsetOverrideItems": line_offset_override_items(
        draft["lineOffsetOverrides"]
      ),
      "lineOffsetOverrides": dict(draft["lineOffsetOverrides"]),
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
      machine_solve_status = self._reconcileMachineSolveStatus(
        layer,
        draft.get("machineSolveStatus"),
      )
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
        "machineSolveStatus": machine_solve_status,
      }

    measurements = []
    for measurement in self._loadState().get("measurements", []):
      item = dict(measurement)
      item["siteLabel"] = item.get("siteLabel") or _measurement_site_label(item)
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
