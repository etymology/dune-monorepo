import unittest

from tests._command_api_test_support import build_registry_fixture


class SimPlcCommandTests(unittest.TestCase):
  def test_sim_commands_require_sim_mode(self):
    registry, _, _, _, _, _ = build_registry_fixture(sim_plc=False)

    response = registry.executeRequest({"name": "sim_plc.get_status", "args": {}})

    self.assertFalse(response["ok"])
    self.assertEqual(response["error"]["code"], "VALIDATION_ERROR")
    self.assertIn("SIM mode required", response["error"]["message"])

  def test_sim_commands_work_when_sim_backend_is_active(self):
    registry, _, _, _, _, _ = build_registry_fixture(sim_plc=True)

    statusResponse = registry.executeRequest({"name": "sim_plc.get_status", "args": {}})
    self.assertTrue(statusResponse["ok"])
    self.assertEqual(statusResponse["data"]["mode"], "SIM")

    setResponse = registry.executeRequest(
      {
        "name": "sim_plc.set_tag",
        "args": {"name": "STATE", "value": 4},
      },
    )
    self.assertTrue(setResponse["ok"])
    self.assertEqual(setResponse["data"], 4)

    getResponse = registry.executeRequest(
      {"name": "sim_plc.get_tag", "args": {"name": "STATE"}},
    )
    self.assertTrue(getResponse["ok"])
    self.assertEqual(getResponse["data"], 4)

    overrideResponse = registry.executeRequest(
      {
        "name": "sim_plc.set_tag",
        "args": {"name": "MACHINE_SW_STAT[6]", "value": 0, "override": True},
      },
    )
    self.assertTrue(overrideResponse["ok"])

    clearOverrideResponse = registry.executeRequest(
      {"name": "sim_plc.clear_override", "args": {"name": "MACHINE_SW_STAT[6]"}},
    )
    self.assertTrue(clearOverrideResponse["ok"])
    self.assertEqual(clearOverrideResponse["data"]["cleared"], 1)

    injectResponse = registry.executeRequest(
      {"name": "sim_plc.inject_error", "args": {"code": 5003}},
    )
    self.assertTrue(injectResponse["ok"])
    self.assertEqual(injectResponse["data"]["errorCode"], 5003)

    clearErrorResponse = registry.executeRequest(
      {"name": "sim_plc.clear_error", "args": {}},
    )
    self.assertTrue(clearErrorResponse["ok"])
    self.assertEqual(clearErrorResponse["data"]["errorCode"], 0)


if __name__ == "__main__":
  unittest.main()
