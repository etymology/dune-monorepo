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
from dune_winder.library.app_config import AppConfig
from dune_winder.library.json import dumps as jsonDumps
from dune_winder.library.version import Version
from dune_winder.paths import CONTROL_VERSION_PATH, SRC_ROOT, UI_VERSION_PATH, WEB_ROOT

from dune_winder.machine.settings import Settings

from dune_winder.core.low_level_io import LowLevelIO
from dune_winder.core.process import Process
from dune_winder.api.commands import build_command_registry

from dune_winder.threads.primary_thread import PrimaryThread
from dune_winder.threads.control_thread import ControlThread
from dune_winder.threads.web_server_thread import WebServerThread
from dune_winder.threads.camera_thread import CameraThread
from dune_winder.core.metrics_collector import MetricsCollector

from dune_winder.io.maps.production_io import ProductionIO
from dune_winder.io.devices.plc_backend import resolve_plc_sim_engine

# $$$TEMPORARY - Temporary.
from dune_winder.machine.calibration.defaults import DefaultMachineCalibration

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
def _parseOption(argument):
    text = str(argument).strip()
    option = text
    value = "TRUE"
    if "=" in text:
        option, value = text.split("=", 1)

    return option.strip().upper(), value.strip()


# -----------------------------------------------------------------------
def _resolvePlcMode(configuredMode, cliOverride):
    source = cliOverride if cliOverride is not None else configuredMode
    return AppConfig.normalizePlcMode(source)


# -----------------------------------------------------------------------
def _resolvePlcSimEngine(configuredEngine, cliOverride):
    return resolve_plc_sim_engine(configuredEngine, envOverride=cliOverride)


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
    global \
        log, \
        io, \
        process, \
        systemTime, \
        configuration, \
        machineCalibration, \
        commandRegistry
    global controlVersion, uiVersion
    global isStartAPA, isLogEchoed, isIO_Logged

    # Handle command line.
    plcModeOverride = None
    plcSimEngineOverride = None
    for argument in sys.argv[1:]:
        option, value = _parseOption(argument)

        if "START" == option:
            isStartAPA = str(value).upper() == "TRUE"
        elif "LOG" == option:
            isLogEchoed = str(value).upper() == "TRUE"
        elif "LOG_IO" == option:
            isIO_Logged = str(value).upper() == "TRUE"
        elif "PLC_MODE" == option:
            plcModeOverride = value
        elif "PLC_SIM_ENGINE" == option:
            plcSimEngineOverride = value

    # Install signal handler for Ctrl-C shutdown.
    signal.signal(signal.SIGINT, signalHandler)

    #
    # Create various objects.
    #

    systemTime = SystemTime()

    startTime = systemTime.get()

    # Load configuration (creates with defaults if the file does not exist).
    import pathlib

    configuration = AppConfig.load(pathlib.Path(Settings.CONFIG_FILE))
    plcMode = _resolvePlcMode(configuration.plcMode, plcModeOverride)
    plcSimEngine = _resolvePlcSimEngine(
        configuration.plcSimEngine,
        plcSimEngineOverride,
    )

    # Persist on first run so the file exists for operators to inspect.
    configuration.save()

    # Ensure runtime directories exist on first run.
    os.makedirs(Settings.CACHE_DIR, exist_ok=True)
    os.makedirs(Settings.RECIPE_DIR, exist_ok=True)
    os.makedirs(Settings.RECIPE_ARCHIVE_DIR, exist_ok=True)

    # Setup log file.
    log = Log(systemTime, Settings.LOG_FILE, isLogEchoed)
    log.add("Main", "START", "Control system starts.")
    plcShadowMode = bool(configuration.plcShadowMode)
    # Check for environment variable override
    envShadowMode = os.environ.get("PLC_SHADOW_MODE", "").strip().upper()
    if envShadowMode in ("1", "TRUE", "YES"):
        plcShadowMode = True
    elif envShadowMode in ("0", "FALSE", "NO"):
        plcShadowMode = False
    log.add("Main", "PLC_MODE", "PLC backend mode selected.", [plcMode])
    log.add("Main", "PLC_SIM_ENGINE", "PLC simulator engine selected.", [plcSimEngine])
    log.add("Main", "PLC_SHADOW_MODE", "PLC shadow mode.", [plcShadowMode])

    try:
        io = ProductionIO(
            configuration.plcAddress,
            plcMode=plcMode,
            plcSimEngine=plcSimEngine,
            plcShadowMode=plcShadowMode,
        )

        # Use low-level I/O to avoid warning.
        # (Low-level I/O is needed by remote commands.)
        LowLevelIO.getTags()

        # $$$TEMPORARY
        machineCalibration = DefaultMachineCalibration(
            Settings.MACHINE_CALIBRATION_PATH,
            configuration.machineCalibrationFile,
        )

        # Primary control process.
        process = Process(io, log, configuration, systemTime, machineCalibration)
        controlVersion = Version(
            str(CONTROL_VERSION_PATH),
            str(SRC_ROOT),
            Settings.CONTROL_FILES,
        )
        uiVersion = Version(
            str(UI_VERSION_PATH),
            str(WEB_ROOT),
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

        metricsCollector = MetricsCollector(io)
        if metricsCollector.isEnabled():
            io.pollCallbacks.append(metricsCollector.update)
        else:
            log.add(
                "Main",
                "METRICS_DISABLED",
                "PLC metrics streaming disabled.",
                [metricsCollector.disableReason()],
            )

        _ = WebServerThread(log, commandRegistry, host=configuration.webServerHost)
        _ = ControlThread(io, log, process.controlStateMachine, systemTime, isIO_Logged)
        _ = CameraThread(io.camera, log, systemTime)

        # Also stop on SIGTERM (e.g. `kill <pid>` or terminal close on Linux/Mac).
        signal.signal(signal.SIGTERM, signalHandler)

        # Load the single active workspace before starting threads so the web
        # server cannot accept workspace-dependent requests while it is still
        # None.
        process.loadWorkspace()

        # Begin operation.
        PrimaryThread.startAllThreads()

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
            process.closeWorkspace()

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


