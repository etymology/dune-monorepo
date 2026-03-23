import json
import unittest

import dune_winder.main as main_module
from tests._command_api_test_support import build_registry_fixture


class MainCommandHandlerTests(unittest.TestCase):
  def setUp(self):
    self._originalLog = main_module.log
    self._originalCommandRegistry = main_module.commandRegistry

  def tearDown(self):
    main_module.log = self._originalLog
    main_module.commandRegistry = self._originalCommandRegistry

  def test_command_handler_accepts_legacy_raw_manual_gcode(self):
    registry, process, _, _, log, _ = build_registry_fixture()
    main_module.log = log
    main_module.commandRegistry = registry

    response = main_module.commandHandler(None, b"g106 p0\r\n")
    payload = json.loads(response)

    self.assertTrue(payload["ok"])
    self.assertIsNone(payload["data"])
    self.assertEqual(process.lastExecuted, "G106 P0")

  def test_command_handler_rejects_non_json_non_gcode_payload(self):
    registry, _, _, _, log, _ = build_registry_fixture()
    main_module.log = log
    main_module.commandRegistry = registry

    response = main_module.commandHandler(None, b"process.start")
    payload = json.loads(response)

    self.assertFalse(payload["ok"])
    self.assertEqual(payload["error"]["code"], "BAD_REQUEST")


if __name__ == "__main__":
  unittest.main()
