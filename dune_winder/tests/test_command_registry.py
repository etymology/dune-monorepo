import unittest

from tests._command_api_test_support import build_registry_fixture


class CommandRegistryTests(unittest.TestCase):
  def test_known_command_dispatch_succeeds(self):
    registry, process, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {"name": "process.start", "args": {}},
      isAuthenticated=True,
    )

    self.assertTrue(response["ok"])
    self.assertIsNone(response["error"])
    self.assertTrue(process.started)

  def test_unknown_command_returns_unknown_command_error(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {"name": "process.does_not_exist", "args": {}},
      isAuthenticated=True,
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "UNKNOWN_COMMAND")

  def test_invalid_args_return_validation_error(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {"name": "process.set_gcode_line", "args": {"line": "not-an-int"}},
      isAuthenticated=True,
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")

  def test_mutating_command_requires_authentication(self):
    registry, process, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {"name": "process.stop", "args": {}},
      isAuthenticated=False,
    )

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "UNAUTHORIZED")
    self.assertFalse(process.stopped)

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
      isAuthenticated=True,
    )

    self.assertTrue(response["ok"])
    results = response["data"]["results"]
    self.assertTrue(results["a"]["ok"])
    self.assertFalse(results["b"]["ok"])
    self.assertEqual(results["b"]["error"]["code"], "UNKNOWN_COMMAND")
    self.assertFalse(results["c"]["ok"])
    self.assertEqual(results["c"]["error"]["code"], "VALIDATION_ERROR")
    self.assertTrue(process.started)


if __name__ == "__main__":
  unittest.main()

