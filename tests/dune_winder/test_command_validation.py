import unittest

from _command_api_test_support import build_registry_fixture


class CommandValidationTests(unittest.TestCase):
  def test_v_template_transfer_pause_accepts_string_boolean(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.v_template.set_transfer_pause",
        "args": {"enabled": "True"},
      },
    )

    self.assertTrue(response["ok"])
    self.assertTrue(response["data"]["data"]["enabled"])

  def test_v_template_add_foot_pauses_accepts_string_boolean(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.v_template.set_add_foot_pauses",
        "args": {"enabled": "True"},
      },
    )

    self.assertTrue(response["ok"])
    self.assertTrue(response["data"]["data"]["enabled"])

  def test_v_template_pull_in_accepts_string_number(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.v_template.set_pull_in",
        "args": {"pull_in_id": "X_PULL_IN", "value": "91.5"},
      },
    )

    self.assertTrue(response["ok"])
    self.assertEqual(response["data"]["data"]["pullInId"], "X_PULL_IN")
    self.assertEqual(response["data"]["data"]["value"], 91.5)

  def test_u_template_pull_in_accepts_string_number(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.u_template.set_pull_in",
        "args": {"pull_in_id": "Y_PULL_IN", "value": "212.5"},
      },
    )

    self.assertTrue(response["ok"])
    self.assertEqual(response["data"]["data"]["pullInId"], "Y_PULL_IN")
    self.assertEqual(response["data"]["data"]["value"], 212.5)

  def test_machine_compute_roller_y_cal_accepts_hover_keyword(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "machine.compute_roller_y_cal",
        "args": {
          "gcode_line": "~anchorToTarget(B1201,B2001,hover=True)",
          "actual_x": 3297.0,
          "actual_y": 2683.0,
          "layer": "U",
        },
      },
    )

    self.assertTrue(response["ok"])
    self.assertEqual(response["data"]["anchor_pin"], "B1201")
    self.assertEqual(response["data"]["target_pin"], "B2001")

  def test_machine_compute_roller_y_cal_accepts_offset_and_hover_keywords(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "machine.compute_roller_y_cal",
        "args": {
          "gcode_line": "~anchorToTarget(B1201,B2001,offset=(1.5,-2),hover=True)",
          "actual_x": 3297.0,
          "actual_y": 2683.0,
          "layer": "U",
        },
      },
    )

    self.assertTrue(response["ok"])
    self.assertEqual(response["data"]["anchor_pin"], "B1201")
    self.assertEqual(response["data"]["target_pin"], "B2001")

  def test_v_template_xz_generate_command_is_registered(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.v_template.generate_recipe_file_xz",
        "args": {},
      },
    )

    self.assertTrue(response["ok"])
    self.assertEqual(response["data"]["data"]["scriptVariant"], "xz")

  def test_machine_geometry_record_measurement_accepts_string_booleans(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.machine_geometry.record_measurement",
        "args": {"capture_xy": "false", "capture_z": "true"},
      },
    )

    self.assertTrue(response["ok"])
    self.assertFalse(response["data"]["captureXY"])
    self.assertTrue(response["data"]["captureZ"])

  def test_machine_geometry_set_line_offset_override_accepts_string_numbers(self):
    registry, process, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.machine_geometry.set_line_offset_override",
        "args": {"line_key": "(12,7)", "x": "1.25", "y": "-2.5"},
      },
    )

    self.assertTrue(response["ok"])
    self.assertEqual(
      process.machineGeometryCalibration.lastSetLineOffset,
      ("V", "(12,7)", 1.25, -2.5),
    )

  def test_machine_geometry_cancel_machine_xy_is_registered(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.machine_geometry.cancel_machine_xy",
        "args": {},
      },
    )

    self.assertTrue(response["ok"])
    self.assertTrue(response["data"]["canceled"])

  def test_machine_geometry_kill_machine_xy_is_registered(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.machine_geometry.kill_machine_xy",
        "args": {},
      },
    )

    self.assertTrue(response["ok"])
    self.assertTrue(response["data"]["killed"])

  def test_unknown_arguments_are_rejected(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.seek_pin",
        "args": {"pin": "A1", "velocity": 10, "extra": 1},
      },
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
    self.assertIn("Unknown argument", response["error"]["message"])

  def test_missing_required_argument_is_rejected(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "configuration.get",
        "args": {},
      },
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
    self.assertIn("Missing argument", response["error"]["message"])

  def test_request_requires_name_field(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest({"args": {}})

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "BAD_REQUEST")

  def test_args_must_be_an_object(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.start",
        "args": ["not", "an", "object"],
      },
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")

  def test_execute_gcode_line_returns_validation_error_when_process_reports_failure(self):
    registry, process, _, _, _, _ = build_registry_fixture()
    process.executeG_CodeLine = lambda line: "Machine not ready: " + str(line)

    response = registry.executeRequest(
      {
        "name": "process.execute_gcode_line",
        "args": {"line": "G206 P0"},
      },
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
    self.assertIn("Machine not ready", response["error"]["message"])

  def test_find_uv_pin_segment_rejects_unknown_arguments(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.find_uv_pin_segment",
        "args": {
          "side": "B",
          "board_side": "head",
          "board_number": 1,
          "pin_number": 40,
          "extra": 1,
        },
      },
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
    self.assertIn("Unknown argument", response["error"]["message"])

  def test_jump_to_uv_pin_segment_requires_all_arguments(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.jump_to_uv_pin_segment",
        "args": {"side": "B", "board_side": "head", "board_number": 1},
      },
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
    self.assertIn("Missing argument", response["error"]["message"])


if __name__ == "__main__":
  unittest.main()
