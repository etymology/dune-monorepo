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
      acknowledgePLCInit: "process.acknowledge_plc_init",
      servoDisable: "process.servo_disable",
      maxVelocity: "process.max_velocity",
      loadRecipe: "process.load_recipe",
      getRecipes: "process.get_recipes",
      getRecipeName: "process.get_recipe_name",
      getRecipeLayer: "process.get_recipe_layer",
      getRecipePeriod: "process.get_recipe_period",
      getAPADetailedList: "process.get_apa_detailed_list",
      getAPADetails: "process.get_apa_details",
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
      getGCodeList: "process.get_gcode_list",
      getControlStateName: "process.get_control_state_name",
      getUISnapshot: "process.get_ui_snapshot",
      getQueuedMotionPreview: "process.get_queued_motion_preview",
      continueQueuedMotionPreview: "process.continue_queued_motion_preview",
      cancelQueuedMotionPreview: "process.cancel_queued_motion_preview",
      getQueuedMotionUseMaxSpeed: "process.get_queued_motion_use_max_speed",
      setQueuedMotionUseMaxSpeed: "process.set_queued_motion_use_max_speed",
      getPositionLogging: "process.get_position_logging",
      setPositionLogging: "process.set_position_logging",
      getStage: "process.get_stage",
      getCameraImageURL: "process.get_camera_image_url",
      vTemplateGetState: "process.v_template.get_state",
      vTemplateSetOffset: "process.v_template.set_offset",
      vTemplateSetPullIn: "process.v_template.set_pull_in",
      vTemplateSetTransferPause: "process.v_template.set_transfer_pause",
      vTemplateSetIncludeLeadMode: "process.v_template.set_include_lead_mode",
      vTemplateSetStripG113Params: "process.v_template.set_strip_g113_params",
      vTemplateResetDraft: "process.v_template.reset_draft",
      vTemplateGenerateRecipeFile: "process.v_template.generate_recipe_file",
      uTemplateGetState: "process.u_template.get_state",
      uTemplateSetOffset: "process.u_template.set_offset",
      uTemplateSetPullIn: "process.u_template.set_pull_in",
      uTemplateSetTransferPause: "process.u_template.set_transfer_pause",
      uTemplateSetIncludeLeadMode: "process.u_template.set_include_lead_mode",
      uTemplateSetStripG113Params: "process.u_template.set_strip_g113_params",
      uTemplateResetDraft: "process.u_template.reset_draft",
      uTemplateGenerateRecipeFile: "process.u_template.generate_recipe_file",
      manualCalibrationGetState: "process.manual_calibration.get_state",
      manualCalibrationSetCornerOffset: "process.manual_calibration.set_corner_offset",
      manualCalibrationSetTransferPause: "process.manual_calibration.set_transfer_pause",
      manualCalibrationSetIncludeLeadMode: "process.manual_calibration.set_include_lead_mode",
      manualCalibrationClearGXDraft: "process.manual_calibration.clear_gx_draft",
      manualCalibrationGenerateRecipeFile: "process.manual_calibration.generate_recipe_file",
      manualCalibrationStartNew: "process.manual_calibration.start_new",
      manualCalibrationLoadPrevious: "process.manual_calibration.load_previous",
      manualCalibrationSaveLive: "process.manual_calibration.save_live",
      manualCalibrationGotoPin: "process.manual_calibration.goto_pin",
      manualCalibrationCaptureCurrentPin: "process.manual_calibration.capture_current_pin",
      manualCalibrationMarkBoardCheck: "process.manual_calibration.mark_board_check",
      manualCalibrationPredictPin: "process.manual_calibration.predict_pin",
      manualCalibrationSetCameraOffset: "process.manual_calibration.set_camera_offset",
      manualCalibrationUpdateMeasuredPin: "process.manual_calibration.update_measured_pin",
      manualCalibrationDeleteMeasuredPin: "process.manual_calibration.delete_measured_pin",
      manualCalibrationCaptureCurrentReference: "process.manual_calibration.capture_current_reference",
      manualCalibrationGotoReference: "process.manual_calibration.goto_reference",
      manualCalibrationUpdateReferencePoint: "process.manual_calibration.update_reference_point",
    },
    io:
    {
      moveLatch: "io.move_latch",
      latch: "io.latch",
      latchHome: "io.latch_home",
      latchUnlock: "io.latch_unlock",
      getState: "io.get_state",
      getErrorCodeString: "io.get_error_code_string",
      maxAcceleration: "io.max_acceleration",
      maxDeceleration: "io.max_deceleration",
    },
    machine:
    {
      getZBack: "machine.get_z_back",
      getCalibration: "machine.get_calibration",
      setCalibration: "machine.set_calibration",
      saveCalibration: "machine.save_calibration",
    },
    configuration:
    {
      get: "configuration.get",
      set: "configuration.set",
      save: "configuration.save",
    },
    log:
    {
      getAll: "log.get_all",
      getRecent: "log.get_recent",
    },
    lowLevelIO:
    {
      getInputs: "low_level_io.get_inputs",
      getOutputs: "low_level_io.get_outputs",
      getTags: "low_level_io.get_tags",
      getInput: "low_level_io.get_input",
      getOutput: "low_level_io.get_output",
      getTag: "low_level_io.get_tag",
    },
    system:
    {
      getTime: "system.get_time",
    },
    version:
    {
      getVersion: "version.get_version",
      getHash: "version.get_hash",
      getDate: "version.get_date",
      verify: "version.verify",
      update: "version.update",
    },
    uiVersion:
    {
      getVersion: "ui_version.get_version",
      getHash: "ui_version.get_hash",
      getDate: "ui_version.get_date",
      verify: "ui_version.verify",
      update: "ui_version.update",
    },
  }

  window.CommandCatalog = catalog
} )()
