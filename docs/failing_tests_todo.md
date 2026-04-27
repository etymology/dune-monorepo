# Failing dune_winder Tests TODO

95 tests fail. Grouped by likely root cause.

## Uncommitted source changes (25 tests)

Source files `src/dune_winder/uv_head_target.py` and `src/dune_winder/uv_head_target_gui.py` have uncommitted changes; tests need updating to match.

- [ ] `test_uv_head_target.py::test_compute_uv_head_target_matches_runtime_for_known_v_case`
- [ ] `test_uv_head_target.py::test_compute_uv_head_target_matches_runtime_for_second_known_v_case`
- [ ] `test_uv_head_target.py::test_lookup_recipe_site_resolves_anchor_and_wrapped_pin`
- [ ] `test_uv_head_target.py::test_infer_pair_pin_from_wrap_side_matches_known_u_case`
- [ ] `test_uv_head_target.py::test_compute_uv_tangent_view_rejects_mixed_pair_on_different_faces`
- [ ] `test_uv_head_target.py::test_arm_correction_head_shift_signs_follow_anchor_to_target_direction` (x4 parametrized)
- [ ] `test_uv_head_target.py::test_compute_arm_corrected_outbound_returns_transfer_edge_point_for_selected_quarter_arc`
- [ ] `test_uv_head_target_gui.py::test_build_request_from_form`
- [ ] `test_uv_head_target_gui.py::test_calculate_and_render_updates_summary_and_canvas`
- [ ] `test_uv_head_target_gui.py::test_calculate_and_render_surfaces_validation_error`
- [ ] `test_uv_head_target_gui.py::test_build_request_from_wrap_segment_includes_alternating_side_segments`
- [ ] `test_uv_head_target_gui.py::test_build_request_from_wrap_segment_preserves_adjacent_pin_for_recipe_transfer`
- [ ] `test_uv_head_target_gui.py::test_build_request_from_v_wrap_segment_includes_alternating_side_segments`
- [ ] `test_uv_head_target_gui.py::test_build_request_from_v_wrap_segment_preserves_adjacent_pin_for_recipe_transfer`
- [ ] `test_uv_head_target_gui.py::test_build_request_from_wrap_segment_preserves_adjacent_pin_on_wrap_5_and_11`
- [ ] `test_uv_head_target_gui.py::test_calculate_and_render_draws_alternating_side_view`
- [ ] `test_uv_layout.py::test_uv_calibration_normalization_handles_relative_and_absolute_uv_styles`
- [ ] `test_uv_tangency_analysis.py::test_build_uv_tangency_report_returns_site_geometry_and_sensitivities`
- [ ] `test_uv_tangency_analysis.py::test_cli_main_emits_json_report`
- [ ] `test_uv_tangency_analysis.py::test_compare_uv_tangency_reports_returns_both_layers`
- [ ] `test_v_template_gcode.py::test_default_render_matches_expected_spec_edges`
- [ ] `test_v_template_gcode.py::test_xz_script_variant_uses_xz_base_script`
- [ ] `test_vscode_rll_syntax.py::test_grammar_covers_all_supported_parser_opcodes`

## Monoroutine equivalence (17 tests)

All monoroutine equivalence tests fail — likely a systematic code drift in the simulated PLC monoroutine.

- [ ] `test_monoroutine_equivalence.py::test_active_seq_advances_with_segment`
- [ ] `test_monoroutine_equivalence.py::test_arc_segment_enqueued_correctly`
- [ ] `test_monoroutine_equivalence.py::test_arc_segment_stream`
- [ ] `test_monoroutine_equivalence.py::test_error_clear_returns_to_ready`
- [ ] `test_monoroutine_equivalence.py::test_four_line_segment_stream`
- [ ] `test_monoroutine_equivalence.py::test_mixed_segment_stream`
- [ ] `test_monoroutine_equivalence.py::test_multiple_segments_queue_count_matches`
- [ ] `test_monoroutine_equivalence.py::test_next_issued_when_two_or_more_queued`
- [ ] `test_monoroutine_equivalence.py::test_queue_abort_clears_state`
- [ ] `test_monoroutine_equivalence.py::test_segment_enqueue_ack_matches`
- [ ] `test_monoroutine_equivalence.py::test_segment_speed_capping_identical`
- [ ] `test_monoroutine_equivalence.py::test_single_line_segment_stream`
- [ ] `test_monoroutine_equivalence.py::test_start_queued_path_activates_cur_issued`
- [ ] `test_monoroutine_equivalence.py::test_xy_seek_from_far`
- [ ] `test_monoroutine_equivalence.py::test_xy_seek_from_mid_range`
- [ ] `test_monoroutine_equivalence.py::test_xy_seek_from_origin`
- [ ] `test_monoroutine_equivalence.py::test_xy_seek_state_transition`

## Ladder simulated PLC (11 tests)

- [ ] `test_ladder_simulated_plc.py::test_gui_latch_pulse_advances_stub_and_auto_clears`
- [ ] `test_ladder_simulated_plc.py::test_hmi_stop_request_interrupts_queued_motion_and_aborts_queue`
- [ ] `test_ladder_simulated_plc.py::test_latch_stub_cycles_positions_without_stalling_state_machine`
- [ ] `test_ladder_simulated_plc.py::test_queue_circle_segment_is_capped_before_start_pulse`
- [ ] `test_ladder_simulated_plc.py::test_queue_segment_is_capped_before_start_pulse`
- [ ] `test_ladder_simulated_plc.py::test_queue_start_caps_arc_segment_to_axis_component_limits`
- [ ] `test_ladder_simulated_plc.py::test_queue_start_caps_diagonal_segment_before_cmd_a_issue`
- [ ] `test_ladder_simulated_plc.py::test_queue_start_caps_pending_segment_before_cmd_b_issue`
- [ ] `test_ladder_simulated_plc.py::test_xy_seek_move_reaches_target_and_returns_ready`
- [ ] `test_ladder_simulated_plc.py::test_xy_seek_move_reaches_target_with_imperative_backend`
- [ ] `test_ladder_simulated_plc.py::test_xz_seek_respects_transfer_override`

## PLC ladder runtime (7 tests)

- [ ] `test_plc_ladder_runtime.py::test_coordinate_motion_tracks_pending_status_scan_by_scan`
- [ ] `test_plc_ladder_runtime.py::test_ffl_and_ffu_update_queue_control_and_payload`
- [ ] `test_plc_ladder_runtime.py::test_generated_python_matches_ast_execution_for_movexy_main`
- [ ] `test_plc_ladder_runtime.py::test_generated_python_matches_ast_execution_for_movez_main`
- [ ] `test_plc_ladder_runtime.py::test_generated_python_matches_ast_for_coordinate_motion_scan_by_scan`
- [ ] `test_plc_ladder_runtime.py::test_generated_python_matches_ast_for_ffl_and_ffu`
- [ ] `test_plc_ladder_runtime.py::test_mccm_uses_arc_speed_and_accel_operands`

## PLC ladder parser (5 tests + 15 subtests)

- [ ] `test_plc_ladder_parser.py::test_generates_python_with_rockwell_mnemonics`
- [ ] `test_plc_ladder_parser.py::test_imperative_codegen_compiles_for_movez_main`
- [ ] `test_plc_ladder_parser.py::test_imperative_codegen_compiles_jump_label_routines`
- [ ] `test_plc_ladder_parser.py::test_imperative_codegen_sanitizes_invalid_root_names`
- [ ] `test_plc_ladder_parser.py::test_round_trips_movez_main_routine`
- [ ] `test_plc_ladder_parser.py::test_parses_all_targeted_acceptance_routines` (8 subtest failures)
- [ ] `test_plc_ladder_parser.py::test_round_trips_motion_queue_helpers_through_structured_python` (6 subtest failures)

## PLC ladder metadata (3 tests)

- [ ] `test_plc_ladder_metadata.py::test_loads_controller_program_tags_and_udts`
- [ ] `test_plc_ladder_metadata.py::test_program_tags_shadow_controller_tags`
- [ ] `test_plc_ladder_metadata.py::test_tag_store_seeds_controller_and_program_values`

## Manual calibration (4 tests)

Likely related to `z_plane`/layer calibration changes.

- [ ] `test_manual_calibration.py::test_hashless_calibration_refreshes_runtime_calibration_when_file_changes`
- [ ] `test_manual_calibration.py::test_nominal_calibration_uses_layer_specific_z_defaults`
- [ ] `test_manual_calibration.py::test_save_live_keeps_zero_file_offset_and_reloads_runtime_calibration`
- [ ] `test_manual_calibration.py::test_save_live_rewrites_loaded_live_z_values_to_layer_defaults`

## Misc (5 tests)

- [ ] `test_embedded_module_tests.py::test_default_layer_calibration_uses_layer_specific_z_defaults`
- [ ] `test_generate_plc_monoroutine.py::test_generated_monoroutine_contains_no_jsr_and_unique_program_tags`
- [ ] `test_hmi_stop_request_generation.py::test_generated_rll_matches_checked_in_pasteable`
- [ ] `test_process.py::test_execute_manual_gcode_accepts_four_digit_feed`
- [ ] `test_process.py::test_execute_manual_gcode_rejects_feed_above_max_velocity`
- [ ] `test_roller_arm_calibration.py::test_fit_roller_arm_single_measurement`
- [ ] `test_sync_monoroutine_tag_values.py::test_monoroutine_source_resolution_is_unambiguous_for_current_export`
