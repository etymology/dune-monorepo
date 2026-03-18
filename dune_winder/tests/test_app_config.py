import pathlib
import tempfile
import unittest

from dune_winder.library.app_config import AppConfig


class AppConfigTests(unittest.TestCase):
  def test_defaults_max_jerk_to_full_percent(self):
    with tempfile.TemporaryDirectory() as tempDirectory:
      configPath = pathlib.Path(tempDirectory) / "configuration.toml"

      configuration = AppConfig.load(configPath)

      self.assertEqual(configuration.maxJerk, 100.0)

  def test_normalizes_max_jerk_to_percent_range(self):
    with tempfile.TemporaryDirectory() as tempDirectory:
      configPath = pathlib.Path(tempDirectory) / "configuration.toml"
      configPath.write_text("maxJerk = 5000.0\n", encoding="utf-8")

      configuration = AppConfig.load(configPath)
      self.assertEqual(configuration.maxJerk, 100.0)

      configuration.set("maxJerk", 25.0)
      self.assertEqual(configuration.maxJerk, 25.0)

      configuration.set("maxJerk", 250.0)
      self.assertEqual(configuration.maxJerk, 100.0)


if __name__ == "__main__":
  unittest.main()
