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

from dune_winder.library.SystemTime import SystemTime
from dune_winder.library.Log import Log
from dune_winder.library.Configuration import Configuration
from dune_winder.library.Json import dumps as jsonDumps
from dune_winder.library.RemoteCommand import isReadOnlyRemoteCommand

from dune_winder.machine.Settings import Settings

from dune_winder.core.LowLevelIO import LowLevelIO
from dune_winder.core.Process import Process

from dune_winder.threads.PrimaryThread import PrimaryThread
from dune_winder.threads.UI_ServerThread import UI_ServerThread
from dune_winder.threads.ControlThread import ControlThread
from dune_winder.threads.WebServerThread import WebServerThread
from dune_winder.threads.CameraThread import CameraThread

from dune_winder.io.Maps.ProductionIO import ProductionIO

# $$$TEMPORARY - Temporary.
from dune_winder.machine.DefaultCalibration import DefaultMachineCalibration

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

# Module-level references so commandHandler and eval'd UI commands can reach
# runtime objects regardless of which scope creates them.
log = None
io = None
process = None
systemTime = None
configuration = None
machineCalibration = None


# -----------------------------------------------------------------------
def _isReadOnlyRemoteCommand(command):
  return isReadOnlyRemoteCommand(command)


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
def commandHandler(_, command):
  """
  Handle a remote command.
  This is define in main so that is has the most global access possible.

  Args:
    command: A command to evaluate.

  Returns:
    The data returned from the command.
  """

  if log and not _isReadOnlyRemoteCommand(command):
    log.add(
      "Main",
      "REMOTE_ACTION",
      "Remote command requested.",
      [threading.current_thread().name, command],
    )

  try:
    result = eval(command)
  except Exception as exception:
    result = "Invalid request"

    exceptionTypeName, exceptionValues, tracebackValue = sys.exc_info()

    if debugInterface:
      traceback.print_tb(tracebackValue)

    tracebackAsString = repr(traceback.format_tb(tracebackValue))
    log.add(
      "Main",
      "commandHandler",
      "Invalid command issued from UI.",
      [command, exception, exceptionTypeName, exceptionValues, tracebackAsString],
    )

  # Try and make JSON object of result.
  # (Custom encoder escapes any invalid UTF-8 characters which would otherwise
  # raise an exception.)
  try:
    result = jsonDumps(result)
  except (TypeError, ValueError):
    # If it cannot be made JSON, just make it a string.
    result = json.dumps(str(result))

  return result


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
  global log, io, process, systemTime, configuration, machineCalibration
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

    #
    # Initialize threads.
    #

    uiServer = UI_ServerThread(commandHandler, log)
    webServerThread = WebServerThread(commandHandler, log)
    controlThread = ControlThread(
      io, log, process.controlStateMachine, systemTime, isIO_Logged
    )
    cameraThread = CameraThread(io.camera, log, systemTime)

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
