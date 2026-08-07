import pathlib
import tempfile
import unittest

from dune_winder.library.app_config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_defaults_queued_motion_dynamics_to_physical_units(self):
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"

            configuration = AppConfig.load(configPath)

            self.assertEqual(configuration.maxAcceleration, 2000)
            self.assertEqual(configuration.maxDeceleration, 2000)
            self.assertEqual(configuration.maxJerkAccel, 1500.0)
            self.assertEqual(configuration.maxJerkDecel, 3000.0)

    def test_load_maps_legacy_max_jerk_to_both_physical_jerk_limits(self):
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"
            configPath.write_text("maxJerk = 5000.0\n", encoding="utf-8")

            configuration = AppConfig.load(configPath)
            self.assertEqual(configuration.maxJerkAccel, 5000.0)
            self.assertEqual(configuration.maxJerkDecel, 5000.0)

            configuration.set("maxJerk", 2500.0)
            self.assertEqual(configuration.maxJerkAccel, 2500.0)
            self.assertEqual(configuration.maxJerkDecel, 2500.0)

    def test_set_preserves_separate_physical_jerk_limits(self):
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"

            configuration = AppConfig.load(configPath)
            configuration.set("maxJerkAccel", 1750.0)
            configuration.set("maxJerkDecel", 3250.0)

            self.assertEqual(configuration.maxJerkAccel, 1750.0)
            self.assertEqual(configuration.maxJerkDecel, 3250.0)

    def test_plc_sim_engine_defaults_and_persists(self):
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"

            configuration = AppConfig.load(configPath)
            self.assertEqual(configuration.plcSimEngine, "LEGACY")

            configuration.set("plcSimEngine", "ladder")
            self.assertEqual(configuration.plcSimEngine, "LADDER")

            reloaded = AppConfig.load(configPath)
            self.assertEqual(reloaded.plcSimEngine, "LADDER")

    def test_x_backlash_compensation_defaults_and_persists(self):
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"

            configuration = AppConfig.load(configPath)
            self.assertEqual(configuration.xBacklashCompensationMm, 2.0)

            configuration.set("xBacklashCompensationMm", 3.5)
            reloaded = AppConfig.load(configPath)

            self.assertEqual(reloaded.xBacklashCompensationMm, 3.5)

    def test_xy_accel_jerk_profiles_default_to_the_three_documented_values(self):
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"

            configuration = AppConfig.load(configPath)

            self.assertEqual(configuration.xyRegulatedAccelJerkDefault, 1500.0)
            self.assertEqual(configuration.xyRegulatedAccelJerkGentle, 1000.0)
            self.assertEqual(configuration.xyRegulatedAccelJerkJerky, 2000.0)

    def test_xy_accel_jerk_profiles_persist(self):
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"

            configuration = AppConfig.load(configPath)
            configuration.set("xyRegulatedAccelJerkDefault", 1600.0)
            configuration.set("xyRegulatedAccelJerkGentle", 900.0)
            configuration.set("xyRegulatedAccelJerkJerky", 2400.0)

            reloaded = AppConfig.load(configPath)

            self.assertEqual(reloaded.xyRegulatedAccelJerkDefault, 1600.0)
            self.assertEqual(reloaded.xyRegulatedAccelJerkGentle, 900.0)
            self.assertEqual(reloaded.xyRegulatedAccelJerkJerky, 2400.0)

    def test_xy_accel_jerk_profiles_reject_non_positive_values(self):
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"

            configuration = AppConfig.load(configPath)
            configuration.set("xyRegulatedAccelJerkGentle", 0.0)
            self.assertEqual(configuration.xyRegulatedAccelJerkGentle, 1000.0)

            configuration.set("xyRegulatedAccelJerkJerky", -5.0)
            self.assertEqual(configuration.xyRegulatedAccelJerkJerky, 2000.0)

    def test_xy_accel_jerk_profiles_accept_the_stringified_api_values(self):
        # configuration.set arrives from the web API as a string, so a decimal
        # must survive the round trip rather than raising like an int field.
        with tempfile.TemporaryDirectory() as tempDirectory:
            configPath = pathlib.Path(tempDirectory) / "configuration.toml"

            configuration = AppConfig.load(configPath)
            configuration.set("xyRegulatedAccelJerkDefault", "1450.5")

            self.assertEqual(configuration.xyRegulatedAccelJerkDefault, 1450.5)


if __name__ == "__main__":
    unittest.main()
