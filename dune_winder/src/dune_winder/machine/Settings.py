###############################################################################
# Name: Settings.py
# Uses: Structure for constant settings used in various systems.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import pathlib

from dune_winder.library.Configuration import Configuration

# src/dune_winder/machine/ -> src/dune_winder/ -> src/ -> project root
_ROOT = pathlib.Path(__file__).parent.parent.parent.parent


class Settings:
  SERVER_PORT = 6626  # Default TCP port number (plank's constant).
  WEB_SERVER_PORT = 8080  # Port for web server (80 is default).
  SERVER_MAX_DATA_SIZE = 1024  # Max data that can be read from server at once.
  SERVER_BACK_LOG = 5  # Default recommended by Python manual.
  CLIENT_MAX_DATA_SIZE = 1024  # Max data that can be read from client at once.
  IO_UPDATE_TIME = 0.1  # In seconds.  Currently 10 times/sec.

  # Path to configuration file.
  CONFIG_FILE = str(_ROOT / "configuration.xml")

  G_CODE_LOG_FILE = "_gCode.gc"

  # Directories — all derived from project root so they are always correct.
  CACHE_DIR = str(_ROOT / "cache")
  RECIPE_DIR = str(_ROOT / "gc_files")
  RECIPE_ARCHIVE_DIR = str(_ROOT / "cache" / "Recipes")
  MACHINE_CALIBRATION_PATH = str(_ROOT / "config") + "/"
  APA_CALIBRATION_DIR = str(_ROOT / "config" / "APA")

  # Files.
  IO_LOG = str(_ROOT / "cache" / "IO_log.csv")
  LOG_FILE = str(_ROOT / "cache" / "log.csv")
  MACHINE_CALIBRATION_FILE = "machineCalibration.xml"

  # Absolute path used by WebServerThread.os.chdir() — must be absolute so it
  # is CWD-independent regardless of how the process is launched.
  WEB_DIRECTORY = str(_ROOT / "web")

  # File making up the version for the control software.
  CONTROL_FILES = r".*\.py$"

  # File making up the version for the user interface.
  UI_FILES = r".*\.html$|.*\.css$|.*\.js$"

  # ---------------------------------------------------------------------
  @staticmethod
  def defaultConfig(configuration: Configuration):
    """
    Setup default values for configuration.
    """
    configuration.default("plcAddress", "192.168.140.13")

    # Location of camera's last captured image.
    configuration.default("cameraURL", "ftp://admin@192.168.140.19/image.bmp")
    configuration.default("pixelsPer_mm", 18)
    configuration.default("manualCalibrationOffsetUX", 65)
    configuration.default("manualCalibrationOffsetUY", -108.2)
    configuration.default("manualCalibrationOffsetVX", 65)
    configuration.default("manualCalibrationOffsetVY", -108.2)
    configuration.default("manualCalibrationOffsetXX", 65)
    configuration.default("manualCalibrationOffsetXY", -108.2)
    configuration.default("manualCalibrationOffsetGX", 65)
    configuration.default("manualCalibrationOffsetGY", -108.2)

    # Default for GUI server.
    configuration.default("serverAddress", "127.0.0.1")
    configuration.default("serverPort", Settings.SERVER_PORT)

    # Default for GUI server.
    configuration.default("webServerPort", 8080)

    configuration.default("machineCalibrationFile", Settings.MACHINE_CALIBRATION_FILE)

    # Velocity limits.
    configuration.default("maxVelocity", 1020)
    configuration.default("maxSlowVelocity", 1 * 25.4)  # 1 inches/second

    # Acceleration limits.
    configuration.default("maxAcceleration", 800)  # 8 inches/s^2
    configuration.default("maxDeceleration", 800)  # 2 inches/s^2
