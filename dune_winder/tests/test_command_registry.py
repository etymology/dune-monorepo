import unittest

from tests._command_api_test_support import build_registry_fixture


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

  def test_batch_returns_mixed_result_entries(self):
    registry, process, _, _, _, _ = build_registry_fixture()
    response = registry.executeBatchRequest(
      {
        "requests": [
          {"id": "a", "name": "process.start", "args": {}},
          {"id": "b", "name": "process.unknown", "args": {}},
          {"id": "c", "name": "process.set_gcode_line", "args": {"line": "bad"}},
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
      {"name": "process.set_queued_motion_use_max_speed", "args": {"enabled": True}},
    )

    self.assertTrue(get_response["ok"])
    self.assertFalse(get_response["data"])
    self.assertTrue(set_response["ok"])
    self.assertTrue(set_response["data"])
    self.assertTrue(process.queuedMotionUseMaxSpeed)


if __name__ == "__main__":
  unittest.main()

