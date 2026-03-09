###############################################################################
# Name: main.py
# Uses: Initialize and start the control system.
# Date: 2016-02-03
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import signal
import sys
import traceback
import time
import json
import threading
import os

from dune_winder.library.system_time import SystemTime
from dune_winder.library.log import Log
from dune_winder.library.configuration import Configuration
from dune_winder.library.json import dumps as jsonDumps
from dune_winder.library.version import Version

from dune_winder.machine.settings import Settings

from dune_winder.core.low_level_io import LowLevelIO
from dune_winder.core.process import Process
from dune_winder.api.commands import build_command_registry

from dune_winder.threads.primary_thread import PrimaryThread
from dune_winder.threads.ui_server_thread import UICommandServerThread
from dune_winder.threads.control_thread import ControlThread
from dune_winder.threads.web_server_thread import WebServerThread
from dune_winder.threads.camera_thread import CameraThread

from dune_winder.io.Maps.production_io import ProductionIO

# $$$TEMPORARY - Temporary.
from dune_winder.machine.default_calibration import DefaultMachineCalibration

# ==============================================================================
# Debug settings.
# These should all be set to False for production.
# Can be overridden from the command-line.
# ==============================================================================

# True to use debug interface.
debugInterface = True

# True to echo log to screen.
isLogEchoed = True

# True to log I/O.
# CAUTION: Log file will get large very quickly.
isIO_Logged = False

# True to start APA automatically.
isStartAPA = False

# ==============================================================================

# Module-level references so command handler and runtime bootstrap can share
# object state regardless of which scope creates them.
log = None
io = None
process = None
systemTime = None
configuration = None
machineCalibration = None
commandRegistry = None
controlVersion = None
uiVersion = None


# -----------------------------------------------------------------------
def _normalizeCommand(command):
  if isinstance(command, bytes):
    return command.decode("utf-8", errors="replace")
  return str(command)


# -----------------------------------------------------------------------
def _describeCaller(source):
  if source is None:
    return {"type": "ui-socket", "address": None, "port": None}

  if hasattr(source, "client_address"):
    address = source.client_address
    host = None
    port = None
    if isinstance(address, tuple):
      if len(address) > 0:
        host = address[0]
      if len(address) > 1:
        port = address[1]
    return {"type": source.__class__.__name__, "address": host, "port": port}

  return {"type": source.__class__.__name__, "address": None, "port": None}


# -----------------------------------------------------------------------
def _getSignalName(signalNumber):
  try:
    return signal.Signals(signalNumber).name
  except ValueError:
    return str(signalNumber)


# -----------------------------------------------------------------------
def _describeFrame(frame):
  if frame is None:
    return "<unknown>"

  code = frame.f_code
  return code.co_filename + ":" + str(frame.f_lineno) + " in " + code.co_name


# -----------------------------------------------------------------------
def commandHandler(source, command):
  """
  Handle a remote command payload.
  This path now only accepts JSON API request envelopes.

  Args:
    command: JSON request payload (single command or batch envelope).

  Returns:
    JSON envelope string.
  """
  commandText = _normalizeCommand(command)
  caller = _describeCaller(source)

  if log:
    log.add(
      "Main",
      "REMOTE_COMMAND",
      "Remote command requested.",
      [threading.current_thread().name, caller, commandText],
    )

  try:
    payload = json.loads(commandText)
  except (TypeError, ValueError):
    payload = None

  if payload is None:
    response = {
      "ok": False,
      "data": None,
      "error": {"code": "BAD_REQUEST", "message": "Request body must be valid JSON."},
    }
    return jsonDumps(response)

  if commandRegistry is None:
    response = {
      "ok": False,
      "data": None,
      "error": {"code": "INTERNAL_ERROR", "message": "Command registry is not configured."},
    }
    return jsonDumps(response)

  if isinstance(payload, dict) and "requests" in payload:
    response = commandRegistry.executeBatchRequest(payload)
  else:
    response = commandRegistry.executeRequest(payload)

  return jsonDumps(response)


# -----------------------------------------------------------------------
def signalHandler(signalNumber, frame):
  """
  Keyboard interrupt handler. Used to shutdown system for Ctrl-C.

  Args:
    signal: Ignored.
    frame: Ignored.
  """
  signalName = _getSignalName(signalNumber)
  frameDescription = _describeFrame(frame)
  threadName = threading.current_thread().name

  if log:
    log.add(
      "Main",
      "SIGNAL",
      "Signal received; requesting shutdown.",
      [signalNumber, signalName, threadName, frameDescription],
    )

  PrimaryThread.stopAllThreads(
    "signal",
    [signalNumber, signalName, threadName, frameDescription],
  )


# -----------------------------------------------------------------------
def main():
  global log, io, process, systemTime, configuration, machineCalibration, commandRegistry
  global controlVersion, uiVersion
  global isStartAPA, isLogEchoed, isIO_Logged

  # Handle command line.
  for argument in sys.argv[1:]:
    argument = argument.upper()
    option = argument
    value = "TRUE"
    if -1 != argument.find("="):
      option, value = argument.split("=")

    if "START" == option:
      isStartAPA = "TRUE" == value
    elif "LOG" == option:
      isLogEchoed = "TRUE" == value
    elif "LOG_IO" == option:
      isIO_Logged = "TRUE" == value

  # Install signal handler for Ctrl-C shutdown.
  signal.signal(signal.SIGINT, signalHandler)

  #
  # Create various objects.
  #

  systemTime = SystemTime()

  startTime = systemTime.get()

  # Load configuration and setup default values.
  configuration = Configuration(Settings.CONFIG_FILE)
  Settings.defaultConfig(configuration)

  # Save configuration (just in case it had not been created or new default
  # values added).
  configuration.save()

  # Setup log file.
  log = Log(systemTime, Settings.LOG_FILE, isLogEchoed)
  log.add("Main", "START", "Control system starts.")

  try:
    io = ProductionIO(configuration.get("plcAddress"))

    # Use low-level I/O to avoid warning.
    # (Low-level I/O is needed by remote commands.)
    LowLevelIO.getTags()

    # $$$TEMPORARY
    machineCalibration = DefaultMachineCalibration(
      Settings.MACHINE_CALIBRATION_PATH,
      configuration.get("machineCalibrationFile"),
    )

    # Primary control process.
    process = Process(io, log, configuration, systemTime, machineCalibration)
    projectRoot = os.path.dirname(Settings.CONFIG_FILE)
    controlVersion = Version(
      os.path.join(projectRoot, "src", "version.xml"),
      os.path.join(projectRoot, "src"),
      Settings.CONTROL_FILES,
    )
    uiVersion = Version(
      os.path.join(projectRoot, "web", "version.xml"),
      os.path.join(projectRoot, "web"),
      Settings.UI_FILES,
    )
    commandRegistry = build_command_registry(
      process,
      io,
      configuration,
      LowLevelIO,
      log,
      machineCalibration,
      systemTime=systemTime,
      version=controlVersion,
      uiVersion=uiVersion,
    )

    #
    # Initialize threads.
    #

    _ = UICommandServerThread(commandHandler, log)
    _ = WebServerThread(log, commandRegistry)
    _ = ControlThread(
      io, log, process.controlStateMachine, systemTime, isIO_Logged
    )
    _ = CameraThread(io.camera, log, systemTime)

    # Also stop on SIGTERM (e.g. `kill <pid>` or terminal close on Linux/Mac).
    signal.signal(signal.SIGTERM, signalHandler)

    # Begin operation.
    PrimaryThread.startAllThreads()

    # Load the single active APA.
    process.loadLatestAPA()

    if isStartAPA:
      process.start()

    try:
      # While the program is running...
      while PrimaryThread.isRunning:
        time.sleep(0.1)
    finally:
      PrimaryThread.stopAllThreads()
      log.add(
        "Main",
        "SHUTDOWN",
        "Main loop exited; beginning shutdown sequence.",
        [PrimaryThread.getStopContext(), PrimaryThread.getThreadStatus()],
      )

      # Shutdown the current processes.  In a finally block so state is always
      # persisted regardless of how the loop exits (normal stop, exception,
      # or signal).
      process.closeAPA()

      # Save configuration.
      configuration.save()

  except Exception as exception:
    exceptionType, exceptionValue, exceptionTraceback = sys.exc_info()
    tracebackString = repr(traceback.format_tb(exceptionTraceback))
    if debugInterface:
      traceback.print_tb(exceptionTraceback)
      raise exception
    else:
      log.add(
        "Main",
        "FAILURE",
        "Caught an exception.",
        [exception, exceptionType, exceptionValue, tracebackString],
      )

  elapsedTime = systemTime.getDelta(startTime)
  deltaString = systemTime.getElapsedString(elapsedTime)

  # Log run-time of this operation.
  log.add("Main", "RUN_TIME", "Ran for " + deltaString + ".", [elapsedTime])

  # Sign off.
  log.add("Main", "END", "Control system stops.")


# "If you think you understand quantum mechanics, you don't understand quantum
# mechanics." -- Richard Feynman
if __name__ == "__main__":
  main()
