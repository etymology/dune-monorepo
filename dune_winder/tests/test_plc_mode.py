import builtins
import pathlib
import tempfile
import unittest
from unittest import mock

from dune_winder.io.Maps.production_io import create_plc_backend
from dune_winder.library.app_config import AppConfig
from dune_winder.main import _resolvePlcMode


class PlcModeTests(unittest.TestCase):
  def test_app_config_defaults_to_real_and_persists_sim(self):
    with tempfile.TemporaryDirectory() as tempDirectory:
      configPath = pathlib.Path(tempDirectory) / "configuration.toml"
      configuration = AppConfig.load(configPath)
      self.assertEqual(configuration.plcMode, "REAL")

      configuration.set("plcMode", "sim")
      self.assertEqual(configuration.plcMode, "SIM")

      reloaded = AppConfig.load(configPath)
      self.assertEqual(reloaded.plcMode, "SIM")

  def test_app_config_rejects_invalid_plc_mode(self):
    with tempfile.TemporaryDirectory() as tempDirectory:
      configPath = pathlib.Path(tempDirectory) / "configuration.toml"
      configPath.write_text('plcMode = "BROKEN"\n', encoding="utf-8")

      with self.assertRaises(ValueError):
        AppConfig.load(configPath)

  def test_resolve_plc_mode_uses_cli_override(self):
    self.assertEqual(_resolvePlcMode("REAL", None), "REAL")
    self.assertEqual(_resolvePlcMode("REAL", "SIM"), "SIM")

  def test_sim_backend_selection_does_not_require_pycomm3(self):
    originalImport = builtins.__import__

    def guardedImport(name, globals=None, locals=None, fromlist=(), level=0):
      if name == "pycomm3":
        raise ImportError("pycomm3 unavailable")
      return originalImport(name, globals, locals, fromlist, level)

    with mock.patch("builtins.__import__", side_effect=guardedImport):
      plc = create_plc_backend("127.0.0.1", "SIM")

    self.assertEqual(plc.__class__.__name__, "SimulatedPLC")


if __name__ == "__main__":
  unittest.main()
