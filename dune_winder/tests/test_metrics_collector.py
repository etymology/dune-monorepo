import builtins
import importlib
import sys
import unittest
from unittest import mock


class MetricsCollectorTests(unittest.TestCase):
  def test_collector_degrades_gracefully_without_influx_dependency(self):
    moduleName = "dune_winder.core.metrics_collector"
    originalModule = sys.modules.pop(moduleName, None)
    originalImport = builtins.__import__

    def guardedImport(name, globals=None, locals=None, fromlist=(), level=0):
      if name == "influxdb_client" or name.startswith("influxdb_client."):
        raise ModuleNotFoundError("No module named 'influxdb_client'")
      return originalImport(name, globals, locals, fromlist, level)

    try:
      with mock.patch("builtins.__import__", side_effect=guardedImport):
        metricsCollectorModule = importlib.import_module(moduleName)

      collector = metricsCollectorModule.MetricsCollector(object())

      self.assertFalse(collector.isEnabled())
      self.assertEqual(
        collector.disableReason(),
        "Optional dependency 'influxdb-client' is not installed.",
      )

      collector.update()
      collector.close()
    finally:
      sys.modules.pop(moduleName, None)
      if originalModule is not None:
        sys.modules[moduleName] = originalModule


if __name__ == "__main__":
  unittest.main()
