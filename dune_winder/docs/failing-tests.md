Import errors (likely stale test files referencing renamed/moved modules):

test_g_code_handler_safety — imports dune_winder.core.g_code_handler (module doesn't exist)
test_manual_calibration — imports dune_winder.machine.layer_calibration (module doesn't exist)
test_motion_queue_test_gui — imports tkinter (not available in this WSL environment)
Data/schema mismatch:

test_tag_store_seeds_controller_and_program_values — KeyError: 'Z_AXIS_STAT' when calling tags.set("Z_AXIS_STAT[5].PC", ...) — tag not found in the store
Logic/simulation failures:

test_xy_seek_move_reaches_target_and_returns_ready — times out waiting for STATE == STATE_READY
test_xy_seek_move_reaches_target_with_imperative_backend — (same ladder sim, different backend)
test_xz_seek_respects_transfer_override — ladder sim failure
test_manual_mode_returns_to_stop_after_successful_z_seek — state machine Z move
test_z_seek_can_finish_motion_but_stay_in_state_5_if_gate_drops — Z move path
test_z_seek_reaches_target_and_returns_ready — Z move path
test_z_seek_stalls_when_axis_cannot_be_enabled — Z move path
test_xz_move_type_sets_error_when_y_transfer_not_ok — simulated PLC behavior
Codegen assertion mismatch:

test_generates_python_with_rockwell_mnemonics — generated Python doesn't match expected
test_imperative_codegen_compiles_for_movez_main — "if tag('trigger_z_move'):" not found in generated output
Want me to dig into any of these groups to help you assess whether they're real bugs or tests that need updating?