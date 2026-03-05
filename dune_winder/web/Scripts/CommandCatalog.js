///////////////////////////////////////////////////////////////////////////////
// Name: CommandCatalog.js
// Uses: Central command names for API v2 calls.
///////////////////////////////////////////////////////////////////////////////

( function()
{
  var catalog =
  {
    process:
    {
      start: "process.start",
      stop: "process.stop",
      step: "process.step",
      stopNextLine: "process.stop_next_line",
      setGCodeLine: "process.set_gcode_line",
      executeGCodeLine: "process.execute_gcode_line",
      jogXY: "process.jog_xy",
      jogZ: "process.jog_z",
      manualSeekXY: "process.manual_seek_xy",
      manualSeekXYNamed: "process.manual_seek_xy_named",
      manualSeekZ: "process.manual_seek_z",
      manualHeadPosition: "process.manual_head_position",
      seekPin: "process.seek_pin",
      setAnchorPoint: "process.set_anchor_point",
      acknowledgeError: "process.acknowledge_error",
      servoDisable: "process.servo_disable",
      loadRecipe: "process.load_recipe",
      getRecipes: "process.get_recipes",
      getRecipeName: "process.get_recipe_name",
      getRecipeLayer: "process.get_recipe_layer",
      getRecipePeriod: "process.get_recipe_period",
      getWrapSeekLine: "process.get_wrap_seek_line",
      openRecipeInEditor: "process.open_recipe_in_editor",
      openCalibrationInEditor: "process.open_calibration_in_editor",
      setGCodeRunToLine: "process.set_gcode_run_to_line",
      setStage: "process.set_stage",
      setGCodeVelocityScale: "process.set_gcode_velocity_scale",
      getGCodeVelocityScale: "process.get_gcode_velocity_scale",
      setSpoolWire: "process.set_spool_wire",
      getGCodeLine: "process.get_gcode_line",
      getGCodeTotalLines: "process.get_gcode_total_lines",
      getControlStateName: "process.get_control_state_name",
      getStage: "process.get_stage",
      getCameraImageURL: "process.get_camera_image_url",
      vTemplateGetState: "process.v_template.get_state",
      vTemplateSetOffset: "process.v_template.set_offset",
      vTemplateSetTransferPause: "process.v_template.set_transfer_pause",
      vTemplateSetIncludeLeadMode: "process.v_template.set_include_lead_mode",
      vTemplateResetDraft: "process.v_template.reset_draft",
      vTemplateGenerateRecipeFile: "process.v_template.generate_recipe_file",
      uTemplateGetState: "process.u_template.get_state",
      uTemplateSetOffset: "process.u_template.set_offset",
      uTemplateSetTransferPause: "process.u_template.set_transfer_pause",
      uTemplateSetIncludeLeadMode: "process.u_template.set_include_lead_mode",
      uTemplateResetDraft: "process.u_template.reset_draft",
      uTemplateGenerateRecipeFile: "process.u_template.generate_recipe_file",
      manualCalibrationGetState: "process.manual_calibration.get_state",
      manualCalibrationSetCornerOffset: "process.manual_calibration.set_corner_offset",
      manualCalibrationSetTransferPause: "process.manual_calibration.set_transfer_pause",
      manualCalibrationSetIncludeLeadMode: "process.manual_calibration.set_include_lead_mode",
      manualCalibrationClearGXDraft: "process.manual_calibration.clear_gx_draft",
      manualCalibrationGenerateRecipeFile: "process.manual_calibration.generate_recipe_file",
    },
    io:
    {
      moveLatch: "io.move_latch",
      latch: "io.latch",
      latchHome: "io.latch_home",
      latchUnlock: "io.latch_unlock",
    },
    machine:
    {
      getZBack: "machine.get_z_back",
    },
    configuration:
    {
      get: "configuration.get",
    },
    log:
    {
      getAll: "log.get_all",
    },
  }

  window.CommandCatalog = catalog
} )()
