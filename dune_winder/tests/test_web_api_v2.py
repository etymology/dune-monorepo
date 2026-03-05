import datetime
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer

from dune_winder.library.WebServerInterface import WebServerInterface
from tests._command_api_test_support import (
  build_registry_fixture,
)


class WebApiV2Tests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.registry, _, _, _, _, _ = build_registry_fixture()
    cls.registry.register(
      "test.fixed_datetime",
      lambda _args: datetime.datetime(2026, 3, 5, 20, 45, 4, 848085),
      False,
    )

    cls._originalRegistry = WebServerInterface.commandRegistry
    cls._originalLog = WebServerInterface.log

    WebServerInterface.commandRegistry = cls.registry
    WebServerInterface.log = None

    cls.server = HTTPServer(("127.0.0.1", 0), WebServerInterface)
    cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
    cls.thread.start()
    cls.baseUrl = "http://127.0.0.1:" + str(cls.server.server_port)

  @classmethod
  def tearDownClass(cls):
    cls.server.shutdown()
    cls.server.server_close()
    cls.thread.join(timeout=2)

    WebServerInterface.commandRegistry = cls._originalRegistry
    WebServerInterface.log = cls._originalLog

  def _post_json(self, path, payload):
    request = urllib.request.Request(
      self.baseUrl + path,
      data=json.dumps(payload).encode("utf-8"),
      method="POST",
      headers={"Content-Type": "application/json"},
    )

    try:
      with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
      return error.code, json.loads(error.read().decode("utf-8"))

  def test_command_endpoint_returns_json_envelope(self):
    status, payload = self._post_json(
      "/api/v2/command",
      {"name": "process.get_recipe_layer", "args": {}},
    )

    self.assertEqual(status, 200)
    self.assertTrue(payload["ok"])
    self.assertEqual(payload["data"], "V")
    self.assertIsNone(payload["error"])

  def test_unknown_command_returns_error_payload(self):
    status, payload = self._post_json(
      "/api/v2/command",
      {"name": "process.not_real", "args": {}},
    )

    self.assertEqual(status, 404)
    self.assertFalse(payload["ok"])
    self.assertEqual(payload["error"]["code"], "UNKNOWN_COMMAND")

  def test_batch_endpoint_returns_per_request_results(self):
    status, payload = self._post_json(
      "/api/v2/batch",
      {
        "requests": [
          {"id": "one", "name": "process.get_recipe_name", "args": {}},
          {"id": "two", "name": "process.bad", "args": {}},
          {"id": "three", "name": "configuration.get", "args": {"key": "maxVelocity"}},
        ]
      },
    )

    self.assertEqual(status, 200)
    self.assertTrue(payload["ok"])
    results = payload["data"]["results"]
    self.assertTrue(results["one"]["ok"])
    self.assertEqual(results["one"]["data"], "V-layer.gc")
    self.assertFalse(results["two"]["ok"])
    self.assertEqual(results["two"]["error"]["code"], "UNKNOWN_COMMAND")
    self.assertTrue(results["three"]["ok"])
    self.assertEqual(results["three"]["data"], "100")

  def test_post_to_unsupported_path_returns_json_error(self):
    request = urllib.request.Request(
      self.baseUrl + "/",
      data=json.dumps({"name": "process.get_recipe_layer", "args": {}}).encode("utf-8"),
      method="POST",
      headers={"Content-Type": "application/json"},
    )

    with self.assertRaises(urllib.error.HTTPError) as context:
      urllib.request.urlopen(request, timeout=5)

    self.assertEqual(context.exception.code, 404)
    payload = json.loads(context.exception.read().decode("utf-8"))
    self.assertFalse(payload["ok"])
    self.assertEqual(payload["error"]["code"], "BAD_REQUEST")

  def test_command_response_serializes_datetime_data(self):
    status, payload = self._post_json(
      "/api/v2/command",
      {"name": "test.fixed_datetime", "args": {}},
    )

    self.assertEqual(status, 200)
    self.assertTrue(payload["ok"])
    self.assertEqual(payload["data"], "2026-03-05 20:45:04.848085")
    self.assertIsNone(payload["error"])


if __name__ == "__main__":
  unittest.main()
