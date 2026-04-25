import unittest

from _command_api_test_support import build_registry_fixture


class CommandRegistryTests(unittest.TestCase):
    def test_known_command_dispatch_succeeds(self):
        registry, process, _, _, _, _ = build_registry_fixture()
        response = registry.executeRequest(
            {"name": "process.start", "args": {}},
        )

        self.assertTrue(response["ok"])
        self.assertIsNone(response["error"])
        self.assertTrue(process.started)

    def test_unknown_command_returns_unknown_command_error(self):
        registry, _, _, _, _, _ = build_registry_fixture()
        response = registry.executeRequest(
            {"name": "process.does_not_exist", "args": {}},
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "UNKNOWN_COMMAND")

    def test_invalid_args_return_validation_error(self):
        registry, _, _, _, _, _ = build_registry_fixture()
        response = registry.executeRequest(
            {"name": "process.set_gcode_line", "args": {"line": "not-an-int"}},
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")

    def test_legacy_get_stage_returns_empty_string(self):
        registry, _, _, _, _, _ = build_registry_fixture()
        response = registry.executeRequest(
            {"name": "process.get_stage", "args": {}},
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"], "")
        self.assertIsNone(response["error"])

    def test_manual_seek_xy_allows_single_axis_requests(self):
        registry, process, _, _, _, _ = build_registry_fixture()

        response = registry.executeRequest(
            {"name": "process.manual_seek_xy", "args": {"y": 42.0}},
        )

        self.assertTrue(response["ok"])
        self.assertEqual(process.lastSeek, ("seekXY", None, 42.0, None, None, None))

    def test_batch_returns_mixed_result_entries(self):
        registry, process, _, _, _, _ = build_registry_fixture()
        response = registry.executeBatchRequest(
            {
                "requests": [
                    {"id": "a", "name": "process.start", "args": {}},
                    {"id": "b", "name": "process.unknown", "args": {}},
                    {
                        "id": "c",
                        "name": "process.set_gcode_line",
                        "args": {"line": "bad"},
                    },
                ]
            },
        )

        self.assertTrue(response["ok"])
        results = response["data"]["results"]
        self.assertTrue(results["a"]["ok"])
        self.assertFalse(results["b"]["ok"])
        self.assertEqual(results["b"]["error"]["code"], "UNKNOWN_COMMAND")
        self.assertFalse(results["c"]["ok"])
        self.assertEqual(results["c"]["error"]["code"], "VALIDATION_ERROR")
        self.assertTrue(process.started)

    def test_queued_motion_preview_commands_dispatch(self):
        registry, process, _, _, _, _ = build_registry_fixture()

        preview_response = registry.executeRequest(
            {"name": "process.get_queued_motion_preview", "args": {}},
        )
        continue_response = registry.executeRequest(
            {"name": "process.continue_queued_motion_preview", "args": {}},
        )
        cancel_response = registry.executeRequest(
            {"name": "process.cancel_queued_motion_preview", "args": {}},
        )

        self.assertTrue(preview_response["ok"])
        self.assertEqual(preview_response["data"]["previewId"], 7)
        self.assertTrue(continue_response["ok"])
        self.assertTrue(cancel_response["ok"])
        self.assertTrue(process.queuedPreviewContinued)
        self.assertTrue(process.queuedPreviewCancelled)

    def test_queued_motion_max_speed_commands_dispatch(self):
        registry, process, _, _, _, _ = build_registry_fixture()

        get_response = registry.executeRequest(
            {"name": "process.get_queued_motion_use_max_speed", "args": {}},
        )
        set_response = registry.executeRequest(
            {
                "name": "process.set_queued_motion_use_max_speed",
                "args": {"enabled": True},
            },
        )

        self.assertTrue(get_response["ok"])
        self.assertFalse(get_response["data"])
        self.assertTrue(set_response["ok"])
        self.assertTrue(set_response["data"])
        self.assertTrue(process.queuedMotionUseMaxSpeed)

    def test_u_wrapping_recipe_command_dispatches_script_variant(self):
        registry, process, _, _, _, _ = build_registry_fixture()

        response = registry.executeRequest(
            {"name": "process.u_template.generate_recipe_file_wrapping", "args": {}},
        )

        self.assertTrue(response["ok"])
        self.assertEqual(
            response["data"]["data"]["scriptVariant"],
            "wrapping",
        )

    def test_get_layer_calibration_command_dispatches(self):
        registry, _, _, _, _, _ = build_registry_fixture()

        response = registry.executeRequest(
            {"name": "process.get_layer_calibration", "args": {"layer": "v"}},
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["layer"], "V")
        self.assertEqual(response["data"]["activeLayer"], "V")
        self.assertIn("B400", response["data"]["locations"])

    def test_get_layer_calibration_command_defaults_to_active_layer(self):
        registry, _, _, _, _, _ = build_registry_fixture()

        response = registry.executeRequest(
            {"name": "process.get_layer_calibration", "args": {}},
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["layer"], "V")
        self.assertEqual(response["data"]["activeLayer"], "V")

    def test_get_layer_calibration_command_requires_layer_when_unset(self):
        registry, process, _, _, _, _ = build_registry_fixture()
        process.getRecipeLayer = lambda: None

        response = registry.executeRequest(
            {"name": "process.get_layer_calibration", "args": {}},
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("Missing argument(s): layer", response["error"]["message"])

    def test_get_layer_calibration_json_command_dispatches(self):
        registry, _, _, _, _, _ = build_registry_fixture()

        response = registry.executeRequest(
            {"name": "process.get_layer_calibration_json", "args": {"layer": "V"}},
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["calibrationFile"], "V_Calibration.json")
        self.assertTrue(response["data"]["contentHash"])
        self.assertIn('"layer": "V"', response["data"]["content"])

    def test_get_layer_calibration_json_command_defaults_to_active_layer(self):
        registry, _, _, _, _, _ = build_registry_fixture()

        response = registry.executeRequest(
            {"name": "process.get_layer_calibration_json", "args": {}},
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["calibrationFile"], "V_Calibration.json")

    def test_get_layer_calibration_json_command_requires_layer_when_unset(self):
        registry, process, _, _, _, _ = build_registry_fixture()
        process.getRecipeLayer = lambda: None

        response = registry.executeRequest(
            {"name": "process.get_layer_calibration_json", "args": {}},
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("Missing argument(s): layer", response["error"]["message"])

    def test_eot_recover_command_dispatch_succeeds(self):
        registry, process, _, _, _, _ = build_registry_fixture()
        process.eotRecovered = False

        def _recover():
            process.eotRecovered = True
            return None

        process.eotRecover = _recover

        response = registry.executeRequest(
            {"name": "process.eot_recover", "args": {}},
        )

        self.assertTrue(response["ok"])
        self.assertTrue(process.eotRecovered)

    def test_find_uv_pin_segment_dispatches_to_workspace(self):
        registry, process, _, _, _, _ = build_registry_fixture()

        response = registry.executeRequest(
            {
                "name": "process.find_uv_pin_segment",
                "args": {
                    "side": "B",
                    "board_side": "head",
                    "board_number": 1,
                    "pin_number": 40,
                },
            },
        )

        self.assertTrue(response["ok"])
        self.assertEqual(process.workspace.lastFindUvPinSegment, ("B", "head", 1, 40))
        self.assertEqual(response["data"]["pinName"], "PB40")
        self.assertEqual(response["data"]["segmentStartLine"], 12)

    def test_jump_to_uv_pin_segment_dispatches_to_workspace(self):
        registry, process, _, _, _, _ = build_registry_fixture()

        response = registry.executeRequest(
            {
                "name": "process.jump_to_uv_pin_segment",
                "args": {
                    "side": "A",
                    "board_side": "bottom",
                    "board_number": 1,
                    "pin_number": 1,
                },
            },
        )

        self.assertTrue(response["ok"])
        self.assertEqual(process.workspace.lastJumpUvPinSegment, ("A", "bottom", 1, 1))
        self.assertEqual(response["data"]["jumpedToLine"], 12)


if __name__ == "__main__":
    unittest.main()
