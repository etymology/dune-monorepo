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


def build_command_registry(process, io, configuration, lowLevelIO, log, machineCalibration):
  registry = CommandRegistry(log=log)

  # ---------------------------------------------------------------------------
  # Process movement and run-control commands.
  # ---------------------------------------------------------------------------
  registry.register("process.start", lambda args: (_validateArgs(args), process.start())[1], True)
  registry.register("process.stop", lambda args: (_validateArgs(args), process.stop())[1], True)
  registry.register("process.step", lambda args: (_validateArgs(args), process.step())[1], True)
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
    return process.executeG_CodeLine(_asString(args["line"], "line"))

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
      required=("x", "y"),
      optional=("velocity", "acceleration", "deceleration"),
    )
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
      _asFloat(args["x"], "x"),
      _asFloat(args["y"], "y"),
      velocity=velocity,
      acceleration=acceleration,
      deceleration=deceleration,
    )

  registry.register("process.manual_seek_xy", process_manual_seek_xy, True)

  def process_manual_seek_xy_named(args):
    _validateArgs(args, optional=("x_name", "y_name", "velocity"))
    if process.apa is None or not hasattr(process.apa, "_gCodeHandler"):
      raise ValueError("No APA G-code handler is available.")

    gCodeHandler = process.apa._gCodeHandler
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
    return process.manualSeekZ(_asFloat(args["position"], "position"), velocity=velocity)

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

  def process_set_anchor_point(args):
    _validateArgs(args, required=("pin_a",), optional=("pin_b",))
    pinA = _asString(args["pin_a"], "pin_a").upper()
    pinB = args.get("pin_b")
    if pinB is not None:
      pinB = _asString(pinB, "pin_b").upper()
    return process.setAnchorPoint(pinA, pinB)

  registry.register("process.set_anchor_point", process_set_anchor_point, True)

  def process_snapshot_apa(args):
    _validateArgs(args)
    currentLine = None
    totalLines = None
    if process.gCodeHandler.isG_CodeLoaded():
      currentLine = process.gCodeHandler.getLine()
      totalLines = process.gCodeHandler.getTotalLines()

    return {
      "recipes": process.getRecipes(),
      "recipeName": process.getRecipeName(),
      "recipeLayer": process.getRecipeLayer(),
      "stage": process.getStage(),
      "gcodeLine": currentLine,
      "gcodeTotalLines": totalLines,
      "movementReady": process.controlStateMachine.isReadyForMovement(),
    }

  registry.register("process.snapshot_apa", process_snapshot_apa, False)

  registry.register(
    "process.get_camera_image_url",
    lambda args: (_validateArgs(args), process.getCameraImageURL())[1],
    False,
  )

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
    return process.manualCalibration.setTransferPause(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.manual_calibration.set_transfer_pause",
    manual_calibration_set_transfer_pause,
    True,
  )

  def manual_calibration_set_include_lead_mode(args):
    _validateArgs(args, required=("enabled",))
    return process.manualCalibration.setIncludeLeadMode(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.manual_calibration.set_include_lead_mode",
    manual_calibration_set_include_lead_mode,
    True,
  )

  registry.register(
    "process.manual_calibration.clear_gx_draft",
    lambda args: (_validateArgs(args), process.manualCalibration.clearGXDraft())[1],
    True,
  )
  registry.register(
    "process.manual_calibration.generate_recipe_file",
    lambda args: (_validateArgs(args), process.manualCalibration.generateRecipeFile())[1],
    True,
  )

  def v_template_set_offset(args):
    _validateArgs(args, required=("offset_id", "value"))
    return process.vTemplateRecipe.setOffset(
      _asString(args["offset_id"], "offset_id"), _asFloat(args["value"], "value")
    )

  registry.register("process.v_template.set_offset", v_template_set_offset, True)

  def v_template_set_transfer_pause(args):
    _validateArgs(args, required=("enabled",))
    return process.vTemplateRecipe.setTransferPause(_asBool(args["enabled"], "enabled"))

  registry.register("process.v_template.set_transfer_pause", v_template_set_transfer_pause, True)

  def v_template_set_include_lead_mode(args):
    _validateArgs(args, required=("enabled",))
    return process.vTemplateRecipe.setIncludeLeadMode(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.v_template.set_include_lead_mode", v_template_set_include_lead_mode, True
  )

  def v_template_reset_draft(args):
    _validateArgs(args, optional=("mark_dirty",))
    markDirty = args.get("mark_dirty", True)
    return process.vTemplateRecipe.resetDraft(markDirty=bool(_asBool(markDirty, "mark_dirty")))

  registry.register("process.v_template.reset_draft", v_template_reset_draft, True)

  registry.register(
    "process.v_template.generate_recipe_file",
    lambda args: (_validateArgs(args), process.vTemplateRecipe.generateRecipeFile())[1],
    True,
  )

  def u_template_set_offset(args):
    _validateArgs(args, required=("offset_id", "value"))
    return process.uTemplateRecipe.setOffset(
      _asString(args["offset_id"], "offset_id"), _asFloat(args["value"], "value")
    )

  registry.register("process.u_template.set_offset", u_template_set_offset, True)

  def u_template_set_transfer_pause(args):
    _validateArgs(args, required=("enabled",))
    return process.uTemplateRecipe.setTransferPause(_asBool(args["enabled"], "enabled"))

  registry.register("process.u_template.set_transfer_pause", u_template_set_transfer_pause, True)

  def u_template_set_include_lead_mode(args):
    _validateArgs(args, required=("enabled",))
    return process.uTemplateRecipe.setIncludeLeadMode(_asBool(args["enabled"], "enabled"))

  registry.register(
    "process.u_template.set_include_lead_mode", u_template_set_include_lead_mode, True
  )

  def u_template_reset_draft(args):
    _validateArgs(args, optional=("mark_dirty",))
    markDirty = args.get("mark_dirty", True)
    return process.uTemplateRecipe.resetDraft(markDirty=bool(_asBool(markDirty, "mark_dirty")))

  registry.register("process.u_template.reset_draft", u_template_reset_draft, True)

  registry.register(
    "process.u_template.generate_recipe_file",
    lambda args: (_validateArgs(args), process.uTemplateRecipe.generateRecipeFile())[1],
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

  def process_load_recipe(args):
    _validateArgs(args, required=("layer", "recipe"), optional=("line",))
    if process.apa is None:
      raise ValueError("No APA is loaded.")
    line = args.get("line", -1)
    return process.apa.loadRecipe(
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

  registry.register("process.open_recipe_in_editor", process_open_recipe_in_editor, True)
  registry.register(
    "process.open_calibration_in_editor",
    lambda args: (_validateArgs(args), process.openCalibrationInEditor())[1],
    True,
  )

  def process_set_gcode_run_to_line(args):
    _validateArgs(args, required=("line",))
    return process.setG_CodeRunToLine(_asInt(args["line"], "line"))

  registry.register("process.set_gcode_run_to_line", process_set_gcode_run_to_line, True)

  def process_set_stage(args):
    _validateArgs(args, required=("stage",), optional=("message",))
    message = _asString(args.get("message", "<unspecified>"), "message")
    return process.setStage(_asInt(args["stage"], "stage"), message=message)

  registry.register("process.set_stage", process_set_stage, True)

  def process_set_gcode_velocity_scale(args):
    _validateArgs(args, required=("scale_factor",))
    return process.setG_CodeVelocityScale(_asFloat(args["scale_factor"], "scale_factor"))

  registry.register("process.set_gcode_velocity_scale", process_set_gcode_velocity_scale, True)
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
    "process.get_stage",
    lambda args: (_validateArgs(args), process.getStage())[1],
    False,
  )
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
    lambda args: (_validateArgs(args), process.controlStateMachine.state.__class__.__name__)[1],
    False,
  )

  def log_get_all(args):
    _validateArgs(args, optional=("number_of_lines",))
    count = args.get("number_of_lines", -1)
    return log.getAll(_asInt(count, "number_of_lines"))

  registry.register("log.get_all", log_get_all, False)

  registry.register("io.move_latch", lambda args: (_validateArgs(args), io.plcLogic.move_latch())[1], True)
  registry.register("io.latch", lambda args: (_validateArgs(args), io.plcLogic.latch())[1], True)
  registry.register("io.latch_home", lambda args: (_validateArgs(args), io.plcLogic.latchHome())[1], True)
  registry.register(
    "io.latch_unlock", lambda args: (_validateArgs(args), io.plcLogic.latchUnlock())[1], True
  )

  registry.register(
    "machine.get_z_back", lambda args: (_validateArgs(args), machineCalibration.zBack)[1], False
  )

  def configuration_get(args):
    _validateArgs(args, required=("key",))
    return configuration.get(_asString(args["key"], "key"))

  registry.register("configuration.get", configuration_get, False)

  # Useful read-only utility command used by pages that still rely on this data.
  registry.register("low_level_io.get_tags", lambda args: (_validateArgs(args), lowLevelIO.getTags())[1], False)

  return registry
