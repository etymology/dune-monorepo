import unittest

from tests._command_api_test_support import build_registry_fixture


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

  def test_unknown_arguments_are_rejected(self):
    registry, _, _, _, _, _ = build_registry_fixture()
    response = registry.executeRequest(
      {
        "name": "process.seek_pin",
        "args": {"pin": "F1", "velocity": 10, "extra": 1},
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


if __name__ == "__main__":
  unittest.main()
