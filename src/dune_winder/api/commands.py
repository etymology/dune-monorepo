###############################################################################
# Name: commands.py
# Uses: Command catalog registration and argument validation.
###############################################################################

from .registry import CommandRegistry


def _validateArgs(args, required=(), optional=()):
  if not isinstance(args, dict):
    raise ValueError("Arguments must be a JSON object.")

  allowed = set(required) | set(optional)
  unknown = sorted([key for key in args.keys() if key not in allowed])
  if unknown:
    raise ValueError("Unknown argument(s): " + ", ".join(unknown))

  missing = [key for key in required if key not in args]
  if missing:
    raise ValueError("Missing argument(s): " + ", ".join(missing))


def _asInt(value, name):
  try:
    return int(value)
  except (TypeError, ValueError):
    raise ValueError("Argument '" + name + "' must be an integer.")


def _asFloat(value, name):
  try:
    return float(value)
  except (TypeError, ValueError):
    raise ValueError("Argument '" + name + "' must be a number.")


def _asString(value, name):
  if value is None:
    raise ValueError("Argument '" + name + "' must be a string.")
  return str(value)


def _asBool(value, name):
  if isinstance(value, bool):
    return value

  if isinstance(value, (int, float)):
    if value in (0, 1):
      return bool(value)
    raise ValueError("Argument '" + name + "' must be boolean.")

  text = str(value).strip().lower()
  if text in ("true", "1", "yes", "on"):
    return True
  if text in ("false", "0", "no", "off"):
    return False
  raise ValueError("Argument '" + name + "' must be boolean.")


def build_command_registry(
  process,
  io,
  configuration,
  lowLevelIO,
  log,
  machineCalibration,
  systemTime=None,
  version=None,
  uiVersion=None,
):
  registry = CommandRegistry(log=log)

  # ---------------------------------------------------------------------------
  # Process movement and run-control commands.
  # ---------------------------------------------------------------------------
  registry.register(
    "process.start", lambda args: (_validateArgs(args), process.start())[1], True
  )
  registry.register(
    "process.stop", lambda args: (_validateArgs(args), process.stop())[1], True
  )
  registry.register(
    "process.step", lambda args: (_validateArgs(args), process.step())[1], True
  )
  registry.register(
    "process.stop_next_line",
    lambda args: (_validateArgs(args), process.stopNextLine())[1],
    True,
  )

  def process_set_gcode_line(args):
    _validateArgs(args, required=("line",))
    return process.setG_CodeLine(_asInt(args["line"], "line"))

  registry.register("process.set_gcode_line", process_set_gcode_line, True)

  def process_execute_gcode_line(args):
    _validateArgs(args, required=("line",))
    error = process.executeG_CodeLine(_asString(args["line"], "line"))
    if error is not None:
      raise ValueError(str(error))
    return None

  registry.register("process.execute_gcode_line", process_execute_gcode_line, True)

  def process_jog_xy(args):
    _validateArgs(
      args,
      required=("x_velocity", "y_velocity"),
      optional=("acceleration", "deceleration"),
    )
    acceleration = args.get("acceleration")
    if acceleration is not None:
      acceleration = _asFloat(acceleration, "acceleration")

    deceleration = args.get("deceleration")
    if deceleration is not None:
      deceleration = _asFloat(deceleration, "deceleration")

    return process.jogXY(
      _asFloat(args["x_velocity"], "x_velocity"),
      _asFloat(args["y_velocity"], "y_velocity"),
      acceleration=acceleration,
      deceleration=deceleration,
    )

  registry.register("process.jog_xy", process_jog_xy, True)

  def process_jog_z(args):
    _validateArgs(args, required=("velocity",))
    return process.jogZ(_asFloat(args["velocity"], "velocity"))

  registry.register("process.jog_z", process_jog_z, True)

  def process_manual_seek_xy(args):
    _validateArgs(
      args,
      optional=("x", "y", "velocity", "acceleration", "deceleration"),
    )
    if "x" not in args and "y" not in args:
      raise ValueError("At least one of 'x' or 'y' is required.")

    xPosition = args.get("x")
    if xPosition is not None:
      xPosition = _asFloat(xPosition, "x")

    yPosition = args.get("y")
    if yPosition is not None:
      yPosition = _asFloat(yPosition, "y")

    velocity = args.get("velocity")
    if velocity is not None:
      velocity = _asFloat(velocity, "velocity")

    acceleration = args.get("acceleration")
    if acceleration is not None:
      acceleration = _asFloat(acceleration, "acceleration")

    deceleration = args.get("deceleration")
    if deceleration is not None:
      deceleration = _asFloat(deceleration, "deceleration")

    return process.manualSeekXY(
      xPosition,
      yPosition,
      velocity=velocity,
      acceleration=acceleration,
      deceleration=deceleration,
    )

  registry.register("process.manual_seek_xy", process_manual_seek_xy, True)

  registry.register(
    "process.get_real_x_position",
    lambda args: (_validateArgs(args), process.getRealXPosition())[1],
    False,
  )

  def process_manual_seek_xy_named(args):
    _validateArgs(args, optional=("x_name", "y_name", "velocity"))
    if process.workspace is None or not hasattr(process.workspace, "_gCodeHandler"):
      raise ValueError("No workspace G-code handler is available.")

    gCodeHandler = process.workspace._gCodeHandler
    xPosition = None
    yPosition = None

    if "x_name" in args and args["x_name"] is not None:
      xName = _asString(args["x_name"], "x_name")
      if not hasattr(gCodeHandler, xName):
        raise ValueError("Unknown X location key: " + xName)
      xPosition = getattr(gCodeHandler, xName)

    if "y_name" in args and args["y_name"] is not None:
      yName = _asString(args["y_name"], "y_name")
      if not hasattr(gCodeHandler, yName):
        raise ValueError("Unknown Y location key: " + yName)
      yPosition = getattr(gCodeHandler, yName)

    velocity = args.get("velocity")
    if velocity is not None:
      velocity = _asFloat(velocity, "velocity")

    return process.manualSeekXY(xPosition, yPosition, velocity=velocity)

  registry.register("process.manual_seek_xy_named", process_manual_seek_xy_named, True)

  def process_manual_seek_z(args):
    _validateArgs(args, required=("position",), optional=("velocity",))
    velocity = args.get("velocity")
    if velocity is not None:
      velocity = _asFloat(velocity, "velocity")
    return process.manualSeekZ(
      _asFloat(args["position"], "position"), velocity=velocity
    )

  registry.register("process.manual_seek_z", process_manual_seek_z, True)

  def process_manual_head_position(args):
    _validateArgs(args, required=("position", "velocity"))
    return process.manualHeadPosition(
      _asInt(args["position"], "position"), _asFloat(args["velocity"], "velocity")
    )

  registry.register("process.manual_head_position", process_manual_head_position, True)

  def process_seek_pin(args):
    _validateArgs(args, required=("pin", "velocity"))
    return process.seekPin(
      _asString(args["pin"], "pin").upper(), _asFloat(args["velocity"], "velocity")
    )

  registry.register("process.seek_pin", process_seek_pin, True)

  def process_get_layer_calibration(args):
    _validateArgs(args, optional=("layer",))
    layer = args.get("layer")
    if layer is None:
      layer = process.getRecipeLayer()
    if layer is None:
      raise ValueError("Missing argument(s): layer")
    return process.getLayerCalibration(_asString(layer, "layer"))

  registry.register(
    "process.get_layer_calibration", process_get_layer_calibration, False
  )

  def process_get_layer_calibration_json(args):
    _validateArgs(args, optional=("layer",))
    layer = args.get("layer")
    if layer is None:
      layer = process.getRecipeLayer()
    if layer is None:
      raise ValueError("Missing argument(s): layer")
    return process.getLayerCalibrationJson(_asString(layer, "layer"))

  registry.register(
    "process.get_layer_calibration_json",
    process_get_layer_calibration_json,
    False,
  )

  def _resolve_process_layer(args):
    layer = args.get("layer")
    if layer is None:
      layer = process.getRecipeLayer()
    if layer is None:
      raise ValueError("Missing argument(s): layer")
    return _asString(layer, "layer").upper()

  def _active_layer_calibration_or_raise(layer):
    if hasattr(process, "_getActiveLayerCalibration"):
      try:
        return process._getActiveLayerCalibration(layer)
      except Exception as exc:
        raise ValueError(str(exc)) from exc

    handler = getattr(process, "gCodeHandler", None)
    if handler is not None and hasattr(handler, "getLayerCalibration"):
      calibration = handler.getLayerCalibration()
      if calibration is not None and str(calibration.getLayerNames()).strip().upper() == layer:
        return calibration

    raise ValueError("No layer calibration is loaded for active layer " + str(layer) + ".")

  def _sync_layer_calibration_handlers(calibration):
    handlers = []
    direct_handler = getattr(process, "gCodeHandler", None)
    if direct_handler is not None:
      handlers.append(direct_handler)
    workspace_handler = getattr(getattr(process, "workspace", None), "_gCodeHandler", None)
    if workspace_handler is not None and workspace_handler not in handlers:
      handlers.append(workspace_handler)

    for handler in handlers:
      if not hasattr(handler, "useLayerCalibration"):
        continue
      loaded = None
      if hasattr(handler, "getLayerCalibration"):
        loaded = handler.getLayerCalibration()
      if loaded is calibration or (
        loaded is not None
        and str(loaded.getLayerNames()).strip().upper()
        == str(calibration.getLayerNames()).strip().upper()
      ):
        handler.useLayerCalibration(calibration)

  def _machine_calibration_path():
    output_path = getattr(machineCalibration, "_outputFilePath", None)
    output_name = getattr(machineCalibration, "_outputFileName", None)
    if output_path is None or output_name is None:
      return None
    import pathlib

    return str(pathlib.Path(output_path) / output_name)

  def process_get_layer_z_plane_calibration(args):
    from dune_winder.machine.calibration.z_plane import (
      empty_layer_z_plane_calibration,
      layer_z_plane_calibration_to_dict,
    )

    _validateArgs(args, optional=("layer",))
    layer = _resolve_process_layer(args)
    calibration = _active_layer_calibration_or_raise(layer)
    z_plane_calibration = getattr(calibration, "zPlaneCalibration", None)
    if z_plane_calibration is None:
      z_plane_calibration = empty_layer_z_plane_calibration()
    return layer_z_plane_calibration_to_dict(z_plane_calibration)

  registry.register(
    "process.get_layer_z_plane_calibration",
    process_get_layer_z_plane_calibration,
    False,
  )

  def process_add_layer_z_plane_measurement(args):
    from dune_winder.machine.calibration.z_plane import (
      LayerZPlaneMeasurement,
    )
    from dune_winder.machine.calibration.z_plane_solver import (
      apply_layer_z_plane_calibration,
      fit_layer_z_plane,
    )

    _validateArgs(
      args,
      required=("gcode_line", "actual_x", "actual_y", "actual_z"),
      optional=("layer",),
    )
    layer = _resolve_process_layer(args)
    calibration = _active_layer_calibration_or_raise(layer)

    measurement = LayerZPlaneMeasurement(
      gcode_line=_asString(args["gcode_line"], "gcode_line"),
      layer=layer,
      actual_x=_asFloat(args["actual_x"], "actual_x"),
      actual_y=_asFloat(args["actual_y"], "actual_y"),
      actual_z=_asFloat(args["actual_z"], "actual_z"),
    )
    current = getattr(calibration, "zPlaneCalibration", None)
    measurements = [] if current is None else list(current.measurements)
    measurements.append(measurement)

    fitted = fit_layer_z_plane(
      measurements,
      machine_calibration_path=_machine_calibration_path(),
      layer_calibration_path=calibration.getFullFileName(),
    )
    calibration.zPlaneCalibration = fitted
    apply_layer_z_plane_calibration(calibration, fitted)
    calibration.save()
    _sync_layer_calibration_handlers(calibration)
    return process_get_layer_z_plane_calibration({"layer": layer})

  registry.register(
    "process.add_layer_z_plane_measurement",
    process_add_layer_z_plane_measurement,
    True,
  )

  def process_clear_layer_z_plane_calibration(args):
    _validateArgs(args, optional=("layer",))
    layer = _resolve_process_layer(args)
    calibration = _active_layer_calibration_or_raise(layer)
    calibration.zPlaneCalibration = None
    calibration.save()
    _sync_layer_calibration_handlers(calibration)
    return process_get_layer_z_plane_calibration({"layer": layer})

  registry.register(
    "process.clear_layer_z_plane_calibration",
    process_clear_layer_z_plane_calibration,
    True,
  )

  registry.register(
    "process.machine_geometry.get_state",
    lambda args: (_validateArgs(args), process.machineGeometryCalibration.getState())[1],
    False,
  )

  def process_machine_geometry_record_measurement(args):
    _validateArgs(args, optional=("layer", "capture_xy", "capture_z"))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    capture_xy = args.get("capture_xy", True)
    capture_z = args.get("capture_z", False)
    return process.machineGeometryCalibration.recordMeasurement(
      layer=layer,
      capture_xy=_asBool(capture_xy, "capture_xy"),
      capture_z=_asBool(capture_z, "capture_z"),
    )

  registry.register(
    "process.machine_geometry.record_measurement",
    process_machine_geometry_record_measurement,
    True,
  )

  def process_machine_geometry_delete_measurement(args):
    _validateArgs(args, required=("measurement_id",))
    return process.machineGeometryCalibration.deleteMeasurement(
      _asString(args["measurement_id"], "measurement_id")
    )

  registry.register(
    "process.machine_geometry.delete_measurement",
    process_machine_geometry_delete_measurement,
    True,
  )

  def process_machine_geometry_solve_layer_z(args):
    _validateArgs(args, optional=("layer",))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    return process.machineGeometryCalibration.solveLayerZ(layer=layer)

  registry.register(
    "process.machine_geometry.solve_layer_z",
    process_machine_geometry_solve_layer_z,
    True,
  )

  def process_machine_geometry_apply_layer_z(args):
    _validateArgs(args, optional=("layer",))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    return process.machineGeometryCalibration.applyLayerZ(layer=layer)

  registry.register(
    "process.machine_geometry.apply_layer_z",
    process_machine_geometry_apply_layer_z,
    True,
  )

  def process_machine_geometry_solve_machine_xy(args):
    _validateArgs(args, optional=("layer",))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    return process.machineGeometryCalibration.solveMachineXY(layer=layer)

  registry.register(
    "process.machine_geometry.solve_machine_xy",
    process_machine_geometry_solve_machine_xy,
    True,
  )

  def process_machine_geometry_cancel_machine_xy(args):
    _validateArgs(args, optional=("layer",))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    return process.machineGeometryCalibration.cancelMachineXY(layer=layer)

  registry.register(
    "process.machine_geometry.cancel_machine_xy",
    process_machine_geometry_cancel_machine_xy,
    True,
  )

  def process_machine_geometry_kill_machine_xy(args):
    _validateArgs(args, optional=("layer",))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    return process.machineGeometryCalibration.killMachineXY(layer=layer)

  registry.register(
    "process.machine_geometry.kill_machine_xy",
    process_machine_geometry_kill_machine_xy,
    True,
  )

  def process_machine_geometry_apply_machine_xy(args):
    _validateArgs(args, optional=("layer",))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    return process.machineGeometryCalibration.applyMachineXY(layer=layer)

  registry.register(
    "process.machine_geometry.apply_machine_xy",
    process_machine_geometry_apply_machine_xy,
    True,
  )

  def process_machine_geometry_set_line_offset_override(args):
    _validateArgs(args, required=("line_key", "x", "y"), optional=("layer",))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    return process.machineGeometryCalibration.setLineOffsetOverride(
      layer or process.getRecipeLayer(),
      _asString(args["line_key"], "line_key"),
      _asFloat(args["x"], "x"),
      _asFloat(args["y"], "y"),
    )

  registry.register(
    "process.machine_geometry.set_line_offset_override",
    process_machine_geometry_set_line_offset_override,
    True,
  )

  def process_machine_geometry_delete_line_offset_override(args):
    _validateArgs(args, required=("line_key",), optional=("layer",))
    layer = args.get("layer")
    if layer is not None:
      layer = _asString(layer, "layer")
    return process.machineGeometryCalibration.deleteLineOffsetOverride(
      layer or process.getRecipeLayer(),
      _asString(args["line_key"], "line_key"),
    )

  registry.register(
    "process.machine_geometry.delete_line_offset_override",
    process_machine_geometry_delete_line_offset_override,
    True,
  )

  def process_set_anchor_point(args):
    _validateArgs(args, required=("pin_a",), optional=("pin_b",))
    pinA = _asString(args["pin_a"], "pin_a").upper()
    pinB = args.get("pin_b")
    if pinB is not None:
      pinB = _asString(pinB, "pin_b").upper()
    return process.setAnchorPoint(pinA, pinB)

  registry.register("process.set_anchor_point", process_set_anchor_point, True)

  # ---------------------------------------------------------------------------
  # Template generator commands.
  # ---------------------------------------------------------------------------
  registry.register(
    "process.v_template.get_state",
    lambda args: (_validateArgs(args), process.vTemplateRecipe.getState())[1],
    False,
  )
  registry.register(
    "process.u_template.get_state",
    lambda args: (_validateArgs(args), process.uTemplateRecipe.getState())[1],
    False,
  )
  registry.register(
    "process.manual_calibration.get_state",
    lambda args: (_validateArgs(args), process.manualCalibration.getState())[1],
    False,
  )

  def manual_calibration_set_corner_offset(args):
    _validateArgs(args, required=("offset_id", "value"))
    return process.manualCalibration.setCornerOffset(
      _asString(args["offset_id"], "offset_id"),
      _asFloat(args["value"], "value"),
    )

  registry.register(
    "process.manual_calibration.set_corner_offset",
    manual_calibration_set_corner_offset,
    True,
  )

  def manual_calibration_set_transfer_pause(args):
    _validateArgs(args, required=("enabled",))
    return process.manualCalibration.setTransferPause(
      _asBool(args["enabled"], "enabled")
    )

  registry.register(
    "process.manual_calibration.set_transfer_pause",
    manual_calibration_set_transfer_pause,
    True,
  )

  def manual_calibration_set_include_lead_mode(args):
    _validateArgs(args, required=("enabled",))
    return process.manualCalibration.setIncludeLeadMode(
      _asBool(args["enabled"], "enabled")
    )

  registry.register(
    "process.manual_calibration.set_include_lead_mode",
    manual_calibration_set_include_lead_mode,
    True,
  )

  def manual_calibration_set_strip_g113_params(args):
    _validateArgs(args, required=("enabled",))
    return process.manualCalibration.setStripG113Params(
      _asBool(args["enabled"], "enabled")
    )

  registry.register(
    "process.manual_calibration.set_strip_g113_params",
    manual_calibration_set_strip_g113_params,
    True,
  )

  registry.register(
    "process.manual_calibration.clear_gx_draft",
    lambda args: (_validateArgs(args), process.manualCalibration.clearGXDraft())[1],
    True,
  )
  registry.register(
    "process.manual_calibration.generate_recipe_file",
    lambda args: (_validateArgs(args), process.manualCalibration.generateRecipeFile())[
      1
    ],
    True,
  )
  registry.register(
    "process.manual_calibration.start_new",
    lambda args: (_validateArgs(args), process.manualCalibration.startNew())[1],
    True,
  )
  registry.register(
    "process.manual_calibration.load_previous",
    lambda args: (_validateArgs(args), process.manualCalibration.loadPrevious())[1],
    True,
  )
  registry.register(
    "process.manual_calibration.save_live",
    lambda args: (_validateArgs(args), process.manualCalibration.saveLive())[1],
    True,
  )

  def manual_calibration_goto_pin(args):
    _validateArgs(args, required=("pin",), optional=("velocity",))
    velocity = args.get("velocity")
    if velocity is not None:
      velocity = _asFloat(velocity, "velocity")
    return process.manualCalibration.gotoPin(_asInt(args["pin"], "pin"), velocity)

  registry.register(
    "process.manual_calibration.goto_pin", manual_calibration_goto_pin, True
  )

  def manual_calibration_capture_current_pin(args):
    _validateArgs(args, required=("pin",))
    return process.manualCalibration.captureCurrentPin(_asInt(args["pin"], "pin"))

  registry.register(
    "process.manual_calibration.capture_current_pin",
    manual_calibration_capture_current_pin,
    True,
  )

  def manual_calibration_mark_board_check(args):
    _validateArgs(args, required=("pin", "status"))
    return process.manualCalibration.markBoardCheck(
      _asInt(args["pin"], "pin"),
      _asString(args["status"], "status"),
    )

  registry.register(
    "process.manual_calibration.mark_board_check",
    manual_calibration_mark_board_check,
    True,
  )

  def manual_calibration_predict_pin(args):
    _validateArgs(args, required=("pin",))
    return process.manualCalibration.predictPin(_asInt(args["pin"], "pin"))

  registry.register(
    "process.manual_calibration.predict_pin", manual_calibration_predict_pin, False
  )

  def manual_calibration_set_camera_offset(args):
    _validateArgs(args, required=("x", "y"))
    return process.manualCalibration.setCameraOffset(
      _asFloat(args["x"], "x"),
      _asFloat(args["y"], "y"),
    )

  registry.register(
    "process.manual_calibration.set_camera_offset",
    manual_calibration_set_camera_offset,
    True,
  )

  def manual_calibration_set_x_backlash_compensation(args):
    _validateArgs(args, required=("value",))
    return process.manualCalibration.setXBacklashCompensation(
      _asFloat(args["value"], "value"),
    )

  registry.register(
    "process.manual_calibration.set_x_backlash_compensation",
    manual_calibration_set_x_backlash_compensation,
    True,
  )

  # ---------------------------------------------------------------------------
  def manual_calibration_set_skip_wrap_pins(args):
    _validateArgs(args, required=("value",))
    return process.manualCalibration.setSkipWrapPins(
      _asInt(args["value"], "value"),
    )

  registry.register(
    "process.manual_calibration.set_skip_wrap_pins",
    manual_calibration_set_skip_wrap_pins,
    True,
  )

  def manual_calibration_update_measured_pin(args):
    _validateArgs(args, required=("pin", "wire_x", "wire_y"))
    return process.manualCalibration.updateMeasuredPin(
      _asInt(args["pin"], "pin"),
      _asFloat(args["wire_x"], "wire_x"),
      _asFloat(args["wire_y"], "wire_y"),
    )

  registry.register(
    "process.manual_calibration.update_measured_pin",
    manual_calibration_update_measured_pin,
    True,
  )

  def manual_calibration_delete_measured_pin(args):
    _validateArgs(args, required=("pin",))
    return process.manualCalibration.deleteMeasuredPin(_asInt(args["pin"], "pin"))

  registry.register(
    "process.manual_calibration.delete_measured_pin",
    manual_calibration_delete_measured_pin,
    True,
  )

  def manual_calibration_capture_current_reference(args):
    _validateArgs(args, required=("reference_id",))
    return process.manualCalibration.captureCurrentReference(
      _asString(args["reference_id"], "reference_id"),
    )

  registry.register(
    "process.manual_calibration.capture_current_reference",
    manual_calibration_capture_current_reference,
    True,
  )

  def manual_calibration_goto_reference(args):
    _validateArgs(args, required=("reference_id",), optional=("velocity",))
    velocity = args.get("velocity")
    if velocity is not None:
      velocity = _asFloat(velocity, "velocity")
    return process.manualCalibration.gotoReference(
      _asString(args["reference_id"], "reference_id"),
      velocity,
    )

  registry.register(
    "process.manual_calibration.goto_reference",
    manual_calibration_goto_reference,
    True,
  )

  def manual_calibration_update_reference_point(args):
    _validateArgs(args, required=("reference_id", "wire_x", "wire_y"))
    return process.manualCalibration.updateReferencePoint(
      _asString(args["reference_id"], "reference_id"),
      _asFloat(args["wire_x"], "wire_x"),
      _asFloat(args["wire_y"], "wire_y"),
    )

  registry.register(
    "process.manual_calibration.update_reference_point",
    manual_calibration_update_reference_point,
    True,
  )

  def v_template_set_offset(args):
    _validateArgs(args, required=("offset_id", "value"))
    return process.vTemplateRecipe.setOffset(
      _asString(args["offset_id"], "offset_id"), _asFloat(args["value"], "value")
    )

  registry.register("process.v_template.set_offset", v_template_set_offset, True)

  def v_template_set_pull_in(args):
    _validateArgs(args, required=("pull_in_id", "value"))
    return process.vTemplateRecipe.setPullIn(
      _asString(args["pull_in_id"], "pull_in_id"),
      _asFloat(args["value"], "value"),
    )

  registry.register("process.v_template.set_pull_in", v_template_set_pull_in, True)

  def v_template_set_transfer_pause(args):
    _validateArgs(args, required=("enabled",))
    return process.vTemplateRecipe.setTransferPause(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.v_template.set_transfer_pause", v_template_set_transfer_pause, True
  )

  def v_template_set_add_foot_pauses(args):
    _validateArgs(args, required=("enabled",))
    return process.vTemplateRecipe.setAddFootPauses(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.v_template.set_add_foot_pauses", v_template_set_add_foot_pauses, True
  )

  def v_template_set_include_lead_mode(args):
    _validateArgs(args, required=("enabled",))
    return process.vTemplateRecipe.setIncludeLeadMode(
      _asBool(args["enabled"], "enabled")
    )

  registry.register(
    "process.v_template.set_include_lead_mode", v_template_set_include_lead_mode, True
  )

  def v_template_set_strip_g113_params(args):
    _validateArgs(args, required=("enabled",))
    return process.vTemplateRecipe.setStripG113Params(
      _asBool(args["enabled"], "enabled")
    )

  registry.register(
    "process.v_template.set_strip_g113_params", v_template_set_strip_g113_params, True
  )

  def v_template_reset_draft(args):
    _validateArgs(args, optional=("mark_dirty",))
    markDirty = args.get("mark_dirty", True)
    return process.vTemplateRecipe.resetDraft(
      markDirty=bool(_asBool(markDirty, "mark_dirty"))
    )

  registry.register("process.v_template.reset_draft", v_template_reset_draft, True)

  registry.register(
    "process.v_template.generate_recipe_file",
    lambda args: (_validateArgs(args), process.vTemplateRecipe.generateRecipeFile())[1],
    True,
  )

  registry.register(
    "process.v_template.generate_recipe_file_xz",
    lambda args: (
      _validateArgs(args),
      process.vTemplateRecipe.generateRecipeFile(scriptVariant="xz"),
    )[1],
    True,
  )

  def u_template_set_offset(args):
    _validateArgs(args, required=("offset_id", "value"))
    return process.uTemplateRecipe.setOffset(
      _asString(args["offset_id"], "offset_id"), _asFloat(args["value"], "value")
    )

  registry.register("process.u_template.set_offset", u_template_set_offset, True)

  def u_template_set_pull_in(args):
    _validateArgs(args, required=("pull_in_id", "value"))
    return process.uTemplateRecipe.setPullIn(
      _asString(args["pull_in_id"], "pull_in_id"),
      _asFloat(args["value"], "value"),
    )

  registry.register("process.u_template.set_pull_in", u_template_set_pull_in, True)

  def u_template_set_transfer_pause(args):
    _validateArgs(args, required=("enabled",))
    return process.uTemplateRecipe.setTransferPause(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.u_template.set_transfer_pause", u_template_set_transfer_pause, True
  )

  def u_template_set_add_foot_pauses(args):
    _validateArgs(args, required=("enabled",))
    return process.uTemplateRecipe.setAddFootPauses(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.u_template.set_add_foot_pauses", u_template_set_add_foot_pauses, True
  )

  def u_template_set_include_lead_mode(args):
    _validateArgs(args, required=("enabled",))
    return process.uTemplateRecipe.setIncludeLeadMode(
      _asBool(args["enabled"], "enabled")
    )

  registry.register(
    "process.u_template.set_include_lead_mode", u_template_set_include_lead_mode, True
  )

  def u_template_set_strip_g113_params(args):
    _validateArgs(args, required=("enabled",))
    return process.uTemplateRecipe.setStripG113Params(
      _asBool(args["enabled"], "enabled")
    )

  registry.register(
    "process.u_template.set_strip_g113_params", u_template_set_strip_g113_params, True
  )

  def u_template_reset_draft(args):
    _validateArgs(args, optional=("mark_dirty",))
    markDirty = args.get("mark_dirty", True)
    return process.uTemplateRecipe.resetDraft(
      markDirty=bool(_asBool(markDirty, "mark_dirty"))
    )

  registry.register("process.u_template.reset_draft", u_template_reset_draft, True)

  registry.register(
    "process.u_template.generate_recipe_file",
    lambda args: (_validateArgs(args), process.uTemplateRecipe.generateRecipeFile())[1],
    True,
  )
  registry.register(
    "process.u_template.generate_recipe_file_wrapping",
    lambda args: (
      _validateArgs(args),
      process.uTemplateRecipe.generateRecipeFile(scriptVariant="wrapping"),
    )[1],
    True,
  )

  # ---------------------------------------------------------------------------
  # Additional commands used by migrated UI pages.
  # ---------------------------------------------------------------------------
  registry.register(
    "process.acknowledge_error",
    lambda args: (_validateArgs(args), process.acknowledgeError())[1],
    True,
  )
  registry.register(
    "process.servo_disable",
    lambda args: (_validateArgs(args), process.servoDisable())[1],
    True,
  )
  registry.register(
    "process.eot_recover",
    lambda args: (_validateArgs(args), process.eotRecover())[1],
    True,
  )

  def process_load_recipe(args):
    _validateArgs(args, required=("layer", "recipe"), optional=("line",))
    if process.workspace is None:
      raise ValueError("No workspace is loaded.")
    line = args.get("line", -1)
    return process.workspace.loadRecipe(
      _asString(args["layer"], "layer"),
      _asString(args["recipe"], "recipe"),
      _asInt(line, "line"),
    )

  registry.register("process.load_recipe", process_load_recipe, True)

  registry.register(
    "process.get_recipes",
    lambda args: (_validateArgs(args), process.getRecipes())[1],
    False,
  )
  registry.register(
    "process.get_recipe_name",
    lambda args: (_validateArgs(args), process.getRecipeName())[1],
    False,
  )
  registry.register(
    "process.get_recipe_layer",
    lambda args: (_validateArgs(args), process.getRecipeLayer())[1],
    False,
  )
  registry.register(
    "process.get_recipe_period",
    lambda args: (_validateArgs(args), process.getRecipePeriod())[1],
    False,
  )

  def process_set_recipe_layer(args):
    _validateArgs(args, required=("layer",))
    if process.workspace is None:
      raise ValueError("No workspace is loaded.")
    layer = _asString(args["layer"], "layer")
    process.workspace.setLayer(layer)
    return None

  registry.register("process.set_recipe_layer", process_set_recipe_layer, True)

  registry.register(
    "process.get_workspace_state",
    lambda args: (_validateArgs(args), process.getWorkspaceState())[1],
    False,
  )

  def process_find_uv_pin_segment(args):
    _validateArgs(
      args,
      required=("side", "board_side", "board_number", "pin_number"),
    )
    if process.workspace is None:
      raise ValueError("No workspace is loaded.")
    return process.workspace.findUvPinSegment(
      _asString(args["side"], "side"),
      _asString(args["board_side"], "board_side"),
      _asInt(args["board_number"], "board_number"),
      _asInt(args["pin_number"], "pin_number"),
    )

  registry.register("process.find_uv_pin_segment", process_find_uv_pin_segment, False)

  def process_jump_to_uv_pin_segment(args):
    _validateArgs(
      args,
      required=("side", "board_side", "board_number", "pin_number"),
    )
    if process.workspace is None:
      raise ValueError("No workspace is loaded.")
    return process.workspace.jumpToUvPinSegment(
      _asString(args["side"], "side"),
      _asString(args["board_side"], "board_side"),
      _asInt(args["board_number"], "board_number"),
      _asInt(args["pin_number"], "pin_number"),
    )

  registry.register(
    "process.jump_to_uv_pin_segment", process_jump_to_uv_pin_segment, True
  )

  def process_get_wrap_seek_line(args):
    _validateArgs(args, required=("wrap",))
    return process.getWrapSeekLine(_asInt(args["wrap"], "wrap"))

  registry.register("process.get_wrap_seek_line", process_get_wrap_seek_line, False)

  def process_open_recipe_in_editor(args):
    _validateArgs(args, optional=("recipe_file",))
    recipeFile = args.get("recipe_file")
    if recipeFile is not None:
      recipeFile = _asString(recipeFile, "recipe_file")
    return process.openRecipeInEditor(recipeFile=recipeFile)

  registry.register(
    "process.open_recipe_in_editor", process_open_recipe_in_editor, True
  )
  registry.register(
    "process.open_calibration_in_editor",
    lambda args: (_validateArgs(args), process.openCalibrationInEditor())[1],
    True,
  )

  def process_set_gcode_run_to_line(args):
    _validateArgs(args, required=("line",))
    return process.setG_CodeRunToLine(_asInt(args["line"], "line"))

  registry.register(
    "process.set_gcode_run_to_line", process_set_gcode_run_to_line, True
  )

  def process_set_gcode_velocity_scale(args):
    _validateArgs(args, required=("scale_factor",))
    return process.setG_CodeVelocityScale(
      _asFloat(args["scale_factor"], "scale_factor")
    )

  registry.register(
    "process.set_gcode_velocity_scale", process_set_gcode_velocity_scale, True
  )
  registry.register(
    "process.get_gcode_velocity_scale",
    lambda args: (_validateArgs(args), process.gCodeHandler.getVelocityScale())[1],
    False,
  )

  def process_set_spool_wire(args):
    _validateArgs(args, required=("wire",))
    spool = getattr(process, "spool", None)
    if spool is None:
      raise ValueError("Spool control is not available.")
    return spool.setWire(_asFloat(args["wire"], "wire"))

  registry.register("process.set_spool_wire", process_set_spool_wire, True)

  registry.register(
    "process.get_gcode_line",
    lambda args: (_validateArgs(args), process.gCodeHandler.getLine())[1],
    False,
  )
  registry.register(
    "process.get_gcode_total_lines",
    lambda args: (_validateArgs(args), process.gCodeHandler.getTotalLines())[1],
    False,
  )
  registry.register(
    "process.get_control_state_name",
    lambda args: (
      _validateArgs(args),
      process.controlStateMachine.state.__class__.__name__,
    )[1],
    False,
  )
  registry.register(
    "process.get_stage",
    # Legacy APA stage polling has been removed; return the historical
    # "no APA loaded" sentinel so old clients degrade gracefully.
    lambda args: (_validateArgs(args), "")[1],
    False,
  )
  registry.register(
    "process.get_ui_snapshot",
    lambda args: (_validateArgs(args), process.getUiSnapshot())[1],
    False,
  )
  registry.register(
    "process.get_queued_motion_preview",
    lambda args: (_validateArgs(args), process.getQueuedMotionPreview())[1],
    False,
  )
  registry.register(
    "process.continue_queued_motion_preview",
    lambda args: (_validateArgs(args), process.continueQueuedMotionPreview())[1],
    True,
  )
  registry.register(
    "process.cancel_queued_motion_preview",
    lambda args: (_validateArgs(args), process.cancelQueuedMotionPreview())[1],
    True,
  )
  registry.register(
    "process.get_queued_motion_use_max_speed",
    lambda args: (_validateArgs(args), process.getQueuedMotionUseMaxSpeed())[1],
    False,
  )

  def process_set_queued_motion_use_max_speed(args):
    _validateArgs(args, required=("enabled",))
    return process.setQueuedMotionUseMaxSpeed(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.set_queued_motion_use_max_speed",
    process_set_queued_motion_use_max_speed,
    True,
  )

  def process_get_gcode_list(args):
    _validateArgs(args, required=("delta",), optional=("center",))
    center = args.get("center")
    if center is not None:
      center = _asInt(center, "center")
    return process.getG_CodeList(center, _asInt(args["delta"], "delta"))

  registry.register("process.get_gcode_list", process_get_gcode_list, False)
  registry.register(
    "process.get_position_logging",
    lambda args: (_validateArgs(args), process.getPositionLogging())[1],
    False,
  )

  def process_set_position_logging(args):
    _validateArgs(args, required=("enabled",))
    return process.setPositionLogging(_asBool(args["enabled"], "enabled"))

  registry.register("process.set_position_logging", process_set_position_logging, True)

  def process_max_velocity(args):
    _validateArgs(args, optional=("value", "max_velocity"))
    if "value" in args and "max_velocity" in args:
      raise ValueError("Provide only one of: value, max_velocity.")

    value = args.get("value")
    if value is None:
      value = args.get("max_velocity")
    if value is not None:
      value = _asFloat(value, "value")
    return process.maxVelocity(value)

  registry.register("process.max_velocity", process_max_velocity, True)
  registry.register(
    "process.acknowledge_plc_init",
    lambda args: (_validateArgs(args), process.acknowledgePLC_Init())[1],
    True,
  )

  def log_get_all(args):
    _validateArgs(args, optional=("number_of_lines",))
    count = args.get("number_of_lines", -1)
    return log.getAll(_asInt(count, "number_of_lines"))

  registry.register("log.get_all", log_get_all, False)
  registry.register(
    "log.get_recent",
    lambda args: (_validateArgs(args), log.getRecent())[1],
    False,
  )

  registry.register(
    "io.move_latch",
    lambda args: (_validateArgs(args), io.plcLogic.move_latch())[1],
    True,
  )
  registry.register(
    "io.latch", lambda args: (_validateArgs(args), io.plcLogic.latch())[1], True
  )
  registry.register(
    "io.latch_home",
    lambda args: (_validateArgs(args), io.plcLogic.latchHome())[1],
    True,
  )
  registry.register(
    "io.latch_unlock",
    lambda args: (_validateArgs(args), io.plcLogic.latchUnlock())[1],
    True,
  )
  registry.register(
    "io.get_state",
    lambda args: (_validateArgs(args), io.plcLogic.getState())[1],
    False,
  )
  registry.register(
    "io.get_error_code_string",
    lambda args: (_validateArgs(args), io.plcLogic.getErrorCodeString())[1],
    False,
  )

  def io_max_acceleration(args):
    _validateArgs(args, optional=("value", "max_acceleration"))
    if "value" in args and "max_acceleration" in args:
      raise ValueError("Provide only one of: value, max_acceleration.")

    value = args.get("value")
    if value is None:
      value = args.get("max_acceleration")
    if value is not None:
      value = _asFloat(value, "value")
    return io.plcLogic.maxAcceleration(value)

  registry.register("io.max_acceleration", io_max_acceleration, True)

  def io_max_deceleration(args):
    _validateArgs(args, optional=("value", "max_deceleration"))
    if "value" in args and "max_deceleration" in args:
      raise ValueError("Provide only one of: value, max_deceleration.")

    value = args.get("value")
    if value is None:
      value = args.get("max_deceleration")
    if value is not None:
      value = _asFloat(value, "value")
    return io.plcLogic.maxDeceleration(value)

  registry.register("io.max_deceleration", io_max_deceleration, True)

  registry.register(
    "machine.get_z_back",
    lambda args: (_validateArgs(args), machineCalibration.zBack)[1],
    False,
  )
  registry.register(
    "machine.get_calibration",
    lambda args: (
      _validateArgs(args),
      {
        key: value
        for key, value in machineCalibration.__dict__.items()
        if not key.startswith("_")
      },
    )[1],
    False,
  )

  def machine_set_calibration(args):
    _validateArgs(args, required=("key", "value"))
    return machineCalibration.set(
      _asString(args["key"], "key"),
      _asFloat(args["value"], "value"),
    )

  registry.register("machine.set_calibration", machine_set_calibration, True)
  registry.register(
    "machine.save_calibration",
    lambda args: (_validateArgs(args), machineCalibration.save())[1],
    True,
  )

  def machine_compute_roller_y_cal(args):
    from dune_winder.machine.geometry.uv_tangency import (
      compute_pin_pair_tangent_geometry,
      Point2D,
    )
    from dune_winder.machine.calibration.roller_arm import (
      compute_roller_y_cal as compute_y_cal,
    )
    import re

    _validateArgs(args, required=("gcode_line", "actual_x", "actual_y", "layer"))

    gcode_line = _asString(args["gcode_line"], "gcode_line")
    actual_x = _asFloat(args["actual_x"], "actual_x")
    actual_y = _asFloat(args["actual_y"], "actual_y")
    layer = _asString(args["layer"], "layer").upper()

    match = re.fullmatch(
      r"~anchorToTarget\("
      r"([A-B]\d+),([A-B]\d+)"
      r"(?:,(?:offset=\([^)]+\)|hover=(?:True|False|1|0|yes|no|on|off))){0,2}"
      r"\)",
      gcode_line,
      flags=re.IGNORECASE,
    )
    if not match:
      raise ValueError(
        f"gcode_line '{gcode_line}' does not match ~anchorToTarget(pinA,pinB[,offset=(x,y)][,hover=True])"
      )
    anchor_pin, target_pin = match.groups()

    geom = compute_pin_pair_tangent_geometry(
      layer=layer,
      pin_a=anchor_pin,
      pin_b=target_pin,
    )

    roller_index = geom.roller_index
    y_sign = -1 if roller_index in (0, 2) else 1

    y_cal = compute_y_cal(
      actual_pos=Point2D(actual_x, actual_y),
      tangent_point_a=geom.tangent_point_a,
      unit_direction=geom.unit_direction,
      normal=geom.normal,
      roller_index=roller_index,
      head_arm_length=float(machineCalibration.headArmLength),
      head_roller_radius=float(machineCalibration.headRollerRadius),
      y_sign=y_sign,
    )

    nominal_y = (float(machineCalibration.headRollerGap) / 2.0) + float(
      machineCalibration.headRollerRadius
    )
    y_cal_delta = y_cal - nominal_y

    quadrant_map = {
      (1, -1): "+x,-y",
      (1, 1): "+x,+y",
      (-1, -1): "-x,-y",
      (-1, 1): "-x,+y",
    }
    x_sign = -1 if roller_index in (0, 1) else 1
    quadrant = quadrant_map.get((x_sign, y_sign), "unknown")

    return {
      "roller_index": roller_index,
      "quadrant": quadrant,
      "y_cal": y_cal,
      "y_cal_delta": y_cal_delta,
      "y_sign": y_sign,
      "anchor_pin": anchor_pin,
      "target_pin": target_pin,
    }

  registry.register(
    "machine.compute_roller_y_cal",
    machine_compute_roller_y_cal,
    False,
  )

  def machine_add_roller_arm_measurement(args):
    from dune_winder.machine.calibration.roller_arm import (
      RollerArmMeasurement,
      fit_roller_arm,
      RollerArmCalibration,
    )

    result = machine_compute_roller_y_cal(args)
    gcode_line = _asString(args["gcode_line"], "gcode_line")
    layer = _asString(args["layer"], "layer").upper()

    measurement = RollerArmMeasurement(
      gcode_line=gcode_line,
      layer=layer,
      actual_x=_asFloat(args["actual_x"], "actual_x"),
      actual_y=_asFloat(args["actual_y"], "actual_y"),
      roller_index=result["roller_index"],
      y_cal=result["y_cal"],
    )

    current_cal = machineCalibration.rollerArmCalibration
    if current_cal is None:
      measurements = [measurement]
    else:
      measurements = list(current_cal.measurements) + [measurement]

    head_roller_radius = float(machineCalibration.headRollerRadius)
    head_roller_gap = float(machineCalibration.headRollerGap)
    nominal_y = (head_roller_gap / 2.0) + head_roller_radius
    fitted_y_cals, center_displacement, arm_tilt = fit_roller_arm(
      measurements,
      head_arm_length=float(machineCalibration.headArmLength),
      nominal_y=nominal_y,
    )

    new_cal = RollerArmCalibration(
      measurements=measurements,
      fitted_y_cals=fitted_y_cals,
      center_displacement=center_displacement,
      arm_tilt_rad=arm_tilt,
    )
    machineCalibration.rollerArmCalibration = new_cal
    machineCalibration.save()

    return machine_get_roller_arm_calibration({})

  registry.register(
    "machine.add_roller_arm_measurement",
    machine_add_roller_arm_measurement,
    True,
  )

  def machine_get_roller_arm_calibration(args):
    from dune_winder.machine.calibration.roller_arm import (
      roller_arm_calibration_to_dict,
    )

    _validateArgs(args)
    if machineCalibration.rollerArmCalibration is None:
      head_roller_radius = float(machineCalibration.headRollerRadius)
      head_roller_gap = float(machineCalibration.headRollerGap)
      nominal_y_offset = (head_roller_gap / 2.0) + head_roller_radius
      return {
        "measurements": [],
        "fitted_y_cals": [nominal_y_offset] * 4,
        "center_displacement": 0.0,
        "arm_tilt_rad": 0.0,
      }
    return roller_arm_calibration_to_dict(machineCalibration.rollerArmCalibration)

  registry.register(
    "machine.get_roller_arm_calibration",
    machine_get_roller_arm_calibration,
    False,
  )

  def machine_set_roller_arm_calibration(args):
    from dune_winder.machine.calibration.roller_arm import (
      RollerArmCalibration,
      roller_arm_calibration_from_dict,
    )

    _validateArgs(args, required=("calibration",))
    calibration = args["calibration"]
    if isinstance(calibration, RollerArmCalibration):
      machineCalibration.rollerArmCalibration = calibration
    elif isinstance(calibration, dict):
      machineCalibration.rollerArmCalibration = roller_arm_calibration_from_dict(
        calibration
      )
    else:
      raise TypeError("calibration must be a calibration dict")
    machineCalibration.save()
    return machine_get_roller_arm_calibration({})

  registry.register(
    "machine.set_roller_arm_calibration",
    machine_set_roller_arm_calibration,
    True,
  )

  def machine_clear_roller_arm_calibration(args):
    _validateArgs(args)
    machineCalibration.rollerArmCalibration = None
    machineCalibration.save()
    return machine_get_roller_arm_calibration(args)

  registry.register(
    "machine.clear_roller_arm_calibration",
    machine_clear_roller_arm_calibration,
    True,
  )

  def configuration_get(args):
    _validateArgs(args, required=("key",))
    return configuration.get(_asString(args["key"], "key"))

  registry.register("configuration.get", configuration_get, False)

  def configuration_set(args):
    _validateArgs(args, required=("key", "value"))
    return configuration.set(
      _asString(args["key"], "key"),
      _asString(args["value"], "value"),
    )

  registry.register("configuration.set", configuration_set, True)
  registry.register(
    "configuration.save",
    lambda args: (_validateArgs(args), configuration.save())[1],
    True,
  )

  # Useful read-only utility command used by pages that still rely on this data.
  registry.register(
    "low_level_io.get_tags",
    lambda args: (_validateArgs(args), lowLevelIO.getTags())[1],
    False,
  )
  registry.register(
    "low_level_io.get_inputs",
    lambda args: (_validateArgs(args), lowLevelIO.getInputs())[1],
    False,
  )
  registry.register(
    "low_level_io.get_outputs",
    lambda args: (_validateArgs(args), lowLevelIO.getOutputs())[1],
    False,
  )

  def low_level_io_get_input(args):
    _validateArgs(args, required=("name",))
    return lowLevelIO.getInput(_asString(args["name"], "name"))

  registry.register("low_level_io.get_input", low_level_io_get_input, False)

  def low_level_io_get_output(args):
    _validateArgs(args, required=("name",))
    return lowLevelIO.getOutput(_asString(args["name"], "name"))

  registry.register("low_level_io.get_output", low_level_io_get_output, False)

  def low_level_io_get_tag(args):
    _validateArgs(args, required=("name",))
    return lowLevelIO.getTag(_asString(args["name"], "name"))

  registry.register("low_level_io.get_tag", low_level_io_get_tag, False)

  def _require_sim_plc():
    plc = getattr(io, "plc", None)
    requiredMethods = (
      "get_status",
      "get_tag",
      "set_tag",
      "clear_override",
      "inject_error",
      "clear_error",
    )
    if plc is None or any(not hasattr(plc, name) for name in requiredMethods):
      raise ValueError("SIM mode required for sim_plc.* commands.")
    return plc

  def sim_plc_get_status(args):
    _validateArgs(args)
    return _require_sim_plc().get_status()

  registry.register("sim_plc.get_status", sim_plc_get_status, False)

  def sim_plc_get_tag(args):
    _validateArgs(args, required=("name",))
    return _require_sim_plc().get_tag(_asString(args["name"], "name"))

  registry.register("sim_plc.get_tag", sim_plc_get_tag, False)

  def sim_plc_set_tag(args):
    _validateArgs(args, required=("name", "value"), optional=("override",))
    override = args.get("override")
    if override is not None:
      override = _asBool(override, "override")

    return _require_sim_plc().set_tag(
      _asString(args["name"], "name"),
      args["value"],
      override=override,
    )

  registry.register("sim_plc.set_tag", sim_plc_set_tag, True)

  def sim_plc_clear_override(args):
    _validateArgs(args, optional=("name",))
    name = args.get("name")
    if name is not None:
      name = _asString(name, "name")
    return _require_sim_plc().clear_override(name)

  registry.register("sim_plc.clear_override", sim_plc_clear_override, True)

  def sim_plc_inject_error(args):
    _validateArgs(args, optional=("code", "state"))
    code = _asInt(args.get("code", 3003), "code")
    state = args.get("state")
    if state is not None:
      state = _asInt(state, "state")
    return _require_sim_plc().inject_error(code=code, state=state)

  registry.register("sim_plc.inject_error", sim_plc_inject_error, True)

  def sim_plc_clear_error(args):
    _validateArgs(args)
    return _require_sim_plc().clear_error()

  registry.register("sim_plc.clear_error", sim_plc_clear_error, True)

  if systemTime is not None:
    registry.register(
      "system.get_time",
      lambda args: (_validateArgs(args), systemTime.get())[1],
      False,
    )

  if version is not None:
    registry.register(
      "version.get_version",
      lambda args: (_validateArgs(args), version.getVersion())[1],
      False,
    )
    registry.register(
      "version.get_hash",
      lambda args: (_validateArgs(args), version.getHash())[1],
      False,
    )
    registry.register(
      "version.get_date",
      lambda args: (_validateArgs(args), version.getDate())[1],
      False,
    )
    registry.register(
      "version.verify",
      lambda args: (_validateArgs(args), version.verify())[1],
      False,
    )
    registry.register(
      "version.update",
      lambda args: (_validateArgs(args), version.update())[1],
      True,
    )

  if uiVersion is not None:
    registry.register(
      "ui_version.get_version",
      lambda args: (_validateArgs(args), uiVersion.getVersion())[1],
      False,
    )
    registry.register(
      "ui_version.get_hash",
      lambda args: (_validateArgs(args), uiVersion.getHash())[1],
      False,
    )
    registry.register(
      "ui_version.get_date",
      lambda args: (_validateArgs(args), uiVersion.getDate())[1],
      False,
    )
    registry.register(
      "ui_version.verify",
      lambda args: (_validateArgs(args), uiVersion.verify())[1],
      False,
    )
    registry.register(
      "ui_version.update",
      lambda args: (_validateArgs(args), uiVersion.update())[1],
      True,
    )

  return registry
