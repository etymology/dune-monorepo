###############################################################################
# Name: G_CodeHandler.py
# Uses: Hardware specific G-code handling.  Associates the G-code command to a
#       actual hardware.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import time
from dataclasses import dataclass

from dune_winder.gcode.runtime import GCodeExecutionError, GCodeProgramExecutor
from dune_winder.machine.g_code_handler_base import G_CodeHandlerBase
from dune_winder.io.Maps.base_io import BaseIO
from dune_winder.queued_motion.merge_planner import MergeWaypoint, build_merge_path_segments
from dune_winder.queued_motion.plc_interface import PLC_QUEUE_DEPTH
from dune_winder.queued_motion.queue_session import QueuedMotionSession
from dune_winder.queued_motion.safety import (
  MotionSafetyLimits,
  motion_safety_limits_from_calibration,
  validate_xy_move_within_safety_limits,
)
from dune_winder.queued_motion.segment_patterns import DEFAULT_WAYPOINT_MIN_ARC_RADIUS


@dataclass(frozen=True)
class _PreviewedQueuedLine:
  line_index: int
  queueable: bool
  x: float
  y: float
  velocity: float
  merge_mode: str | None


class G_CodeHandler(G_CodeHandlerBase):
  # ---------------------------------------------------------------------
  def _getHeadPosition(self, headPosition):
    """
    Resolve head position, polling the PLC if it is currently unknown (None).
    """
    if headPosition is None:
      headPosition = self._io.head.readCurrentPosition()
      self._headPosition = headPosition
    return G_CodeHandlerBase._getHeadPosition(self, headPosition)

  # ---------------------------------------------------------------------
  def isDone(self):
    """
    Check to see if the G-Code execution has finished.

    Returns:
      True if finished, false if not.
    """

    isDone = True
    if self._gCode:
      startLine = 0
      endLine = self._gCode.getLineCount() - 1

      if -1 != self.runToLine:
        if 1 == self._direction:
          endLine = self.runToLine - 1
        else:
          startLine = self.runToLine - 1

      isDone = False
      isDone |= 1 == self._direction and self._nextLine >= endLine
      isDone |= 1 != self._direction and self._nextLine <= startLine
      isDone |= self._isG_CodeError

    return isDone

  # ---------------------------------------------------------------------
  def getTotalLines(self):
    """
    Return the total number of G-Code lines for the current G-Code file.

    Returns:
      Total number of G-Code lines for the current G-Code file.  None if there
      is no G-Code file currently loaded.
    """
    result = None
    if self._gCode:
      result = self._gCode.getLineCount()

    return result

  # ---------------------------------------------------------------------
  def getLine(self):
    """
    Get the current line number being executed/ready to execute.

    Returns:
      Line number being executed/ready to execute.  None if no G-Code is
      loaded.
    """

    result = None
    if self._gCode:
      result = self._currentLine

    return result

  # ---------------------------------------------------------------------
  def setLine(self, line):
    """
    Set the line number of G-Code to execute next.

    Args:
      line: New line number.
    """

    isError = True
    if line >= -1 and line < self._gCode.getLineCount():
      isError = False
      self._nextLine = line
      self._currentLine = line
      if self._lineChangeCallback:
        self._lineChangeCallback()

    return isError

  # ---------------------------------------------------------------------
  def setLineChangeCallback(self, callback):
    """
    Register a callback invoked whenever the current line number changes.

    Args:
      callback: Callable with no arguments, or None to clear.
    """
    self._lineChangeCallback = callback

  # ---------------------------------------------------------------------
  def setBeforeExecuteLineCallback(self, callback):
    """
    Register a callback invoked before interpreting any G-Code line.

    Args:
      callback: Callable with no arguments returning None on success, or an
        error string on failure.
    """
    self._beforeExecuteLineCallback = callback

  # ---------------------------------------------------------------------
  def setDirection(self, isForward):
    """
    Set the direction of G-Code execution.

    Args:
      isForward: True for normal direction, False to run in reverse.
    """
    if isForward:
      self._direction = 1
    else:
      self._direction = -1

  # ---------------------------------------------------------------------
  def getDirection(self):
    """
    Get the direction of G-Code execution.

    Returns
      True for normal direction, False to run in reverse.
    """
    return 1 == self._direction

  # ---------------------------------------------------------------------
  def setVelocityScale(self, scaleFactor=1.0):
    """
    Set the velocity scale factor that limits the speed of all motions.

    Args:
      scaleFactor: New scale factor (typically between 0.0-1.0, although > 1 is
                   allowed).
    """
    self._velocityScale = scaleFactor

  # ---------------------------------------------------------------------
  def getVelocityScale(self):
    """
    Get the velocity scale factor that limits the speed of all motions.

    Returns:
      Scale factor (typically between 0-1.0).
    """
    return self._velocityScale

  # ---------------------------------------------------------------------
  def _commanded_xy_velocity(self):
    velocity = min(self._velocity, self._maxVelocity)
    velocity *= self._velocityScale
    return max(1.0, float(velocity))

  # ---------------------------------------------------------------------
  def _queued_motion_min_turning_radius(self):
    try:
      value = self._machineCalibration.get("queuedMotionMinTurningRadius")
    except Exception:
      value = None
    if value is None:
      return float(DEFAULT_WAYPOINT_MIN_ARC_RADIUS)
    return max(0.0, float(value))

  # ---------------------------------------------------------------------
  def _motion_safety_limits(self):
    return motion_safety_limits_from_calibration(self._machineCalibration)

  # ---------------------------------------------------------------------
  def _set_xy_safety_error(self, message: str):
    self._isG_CodeError = True
    self._isG_CodeErrorMessage = str(message)
    if (
      self._gCode is not None
      and self._currentLine is not None
      and 0 <= self._currentLine < self._gCode.getLineCount()
    ):
      self._isG_CodeErrorData = [self._currentLine, self._gCode.lines[self._currentLine]]
    else:
      self._isG_CodeErrorData = []
    self._pending_actions = []
    self._pending_stop_request = False

  # ---------------------------------------------------------------------
  def _preview_loaded_line(self, line_index):
    self._line = None
    self._functions = []
    self._gCode.executeNextLine(line_index)

    queueable = (
      self._instruction_request_xy
      and not self._instruction_request_z
      and not self._instruction_request_head
      and not self._instruction_request_latch
      and not self._instruction_request_stop
    )

    preview = _PreviewedQueuedLine(
      line_index=line_index,
      queueable=queueable,
      x=float(self._x),
      y=float(self._y),
      velocity=self._commanded_xy_velocity(),
      merge_mode=self._instruction_queue_merge_mode,
    )
    self._pending_actions = []
    self._pending_stop_request = False
    return preview

  # ---------------------------------------------------------------------
  def _build_queued_block(self, line_index):
    if (
      self.singleStep
      or self._gCode is None
      or self._direction != 1
      or not hasattr(self._io.plcLogic, "queuedMotion")
    ):
      return None

    snapshot = self._snapshot_interpreter_state()
    start_xy = (float(snapshot["_x"]), float(snapshot["_y"]))
    previews: list[_PreviewedQueuedLine] = []
    try:
      current = self._preview_loaded_line(line_index)
      if not current.queueable or current.merge_mode is None:
        return None
      previews.append(current)

      cursor = line_index
      while True:
        cursor += 1
        if cursor >= self._gCode.getLineCount():
          if len(previews) < 2:
            return None
          break
        next_preview = self._preview_loaded_line(cursor)
        if not next_preview.queueable:
          if len(previews) < 2:
            return None
          break
        previews.append(next_preview)
        if next_preview.merge_mode is None:
          break

      if len(previews) < 2:
        return None

      speed = min(preview.velocity for preview in previews)
      accel = max(1.0, float(getattr(self._io.plcLogic, "_maxAcceleration", 0.0) or 0.0))
      decel = max(1.0, float(getattr(self._io.plcLogic, "_maxDeceleration", 0.0) or 0.0))
      safety_limits = self._motion_safety_limits()
      waypoints = [
        MergeWaypoint(
          line_index=preview.line_index,
          x=preview.x,
          y=preview.y,
          mode=preview.merge_mode,
        )
        for preview in previews
      ]
      segments = build_merge_path_segments(
        start_xy=start_xy,
        waypoints=waypoints,
        start_seq=self._queued_sequence_id,
        speed=speed,
        accel=accel,
        decel=decel,
        min_arc_radius=self._queued_motion_min_turning_radius(),
        safety_limits=safety_limits,
      )
      self._queued_sequence_id += len(segments) + 1
      return {
        "start_line": line_index,
        "resume_line": previews[-1].line_index + 1,
        "segments": segments,
      }
    finally:
      self._restore_interpreter_state(snapshot)

  # ---------------------------------------------------------------------
  def _start_queued_block(self, line_index):
    block = self._build_queued_block(line_index)
    if block is None:
      return False

    self._queued_block_start_line = int(block["start_line"])
    self._queued_block_resume_line = int(block["resume_line"])
    self._queued_session = QueuedMotionSession(
      self._io.plcLogic.queuedMotion,
      list(block["segments"]),
      queue_depth=PLC_QUEUE_DEPTH,
    )
    previous_line = self._currentLine
    self._currentLine = self._queued_block_start_line
    if self._currentLine != previous_line and self._lineChangeCallback:
      self._lineChangeCallback()
    self._queued_session.advance()
    return True

  # ---------------------------------------------------------------------
  def _advance_queued_motion(self):
    if self._queued_session is None:
      return False

    self._queued_session.advance()

    if self._queued_session.error:
      self._isG_CodeError = True
      self._isG_CodeErrorMessage = self._queued_session.error
      self._isG_CodeErrorData = [
        self._queued_block_start_line,
        self._gCode.lines[self._queued_block_start_line],
      ]
      self._queued_session = None
      return True

    if self._queued_session.aborted:
      self._queued_session = None
      self._nextLine = self._queued_block_start_line - self._direction
      self._queued_stop_mode = None
      return True

    if self._queued_session.done:
      self._queued_session = None
      self._nextLine = self._queued_block_resume_line - self._direction
      return False

    return False

  # ---------------------------------------------------------------------
  def stop(self):
    """
    Stop the running G-Code.  Call when interrupting G-Code sequence.
    """

    self._stopNextMove = False
    if self._queued_session is not None:
      self._io.plcLogic.queuedMotion.set_abort(True)
      time.sleep(0.10)
      self._io.plcLogic.queuedMotion.set_abort(False)
      self._queued_session = None
      self._queued_stop_mode = None
      self._nextLine = self._queued_block_start_line - self._direction
      return

    # If we are interrupting a running line, set it as the next line to run.
    if not self._io.plcLogic.isReady():
      self._nextLine -= self._direction

  # ---------------------------------------------------------------------
  def stopNext(self):
    """
    Stop the G-Code after completing the current move.
    """
    if self._queued_session is not None:
      self._io.plcLogic.queuedMotion.set_abort(True)
      time.sleep(0.10)
      self._io.plcLogic.queuedMotion.set_abort(False)
      self._queued_session = None
      self._queued_stop_mode = None
      self._nextLine = self._queued_block_start_line - self._direction
      self._stopNextMove = True
      return
    self._stopNextMove = True

  # ---------------------------------------------------------------------
  def poll(self):
    """
    Update the logic for executing this line of G-Code.

    Returns:
      True if the G-Code list has finished, False if not.
    """

    isDone = False

    if self._queued_session is not None:
      return self._advance_queued_motion()

    if self._io.plcLogic.isReady() and self._io.head.isReady():
      moving = False

      velocity = min(self._velocity, self._maxVelocity)
      velocity *= self._velocityScale

      if not moving and self._pending_actions:
        action = self._pending_actions.pop(0)
        if action == "xy":
          start_xy = (
            float(self._io.xAxis.getPosition()),
            float(self._io.yAxis.getPosition()),
          )
          try:
            validate_xy_move_within_safety_limits(
              start_xy,
              (float(self._x), float(self._y)),
              self._motion_safety_limits(),
              seq=int(self._line or 0),
              label="line",
            )
          except ValueError as exception:
            self._set_xy_safety_error(str(exception))
          else:
            self._io.plcLogic.setXY_Position(self._x, self._y, velocity)
            moving = True
        elif action == "z":
          self._io.plcLogic.setZ_Position(self._z, velocity)
          moving = True
        elif action == "head":
          self._io.head.setHeadPosition(self._headPosition, velocity)
          moving = True
        elif action == "latch":
          self._io.plcLogic.move_latch()
          moving = True

      if self._pending_stop_request:
        self._pending_stop_request = False
        self._stopNextMove = True

      # If there are no more moves, run the next line of G-Code.
      if not moving:
        _prevLine = self._currentLine
        self._currentLine = self._nextLine
        if self._currentLine != _prevLine and self._lineChangeCallback:
          self._lineChangeCallback()

        isDone = self.isDone() or self._stopNextMove
        self._stopNextMove = False

        if not isDone:
          if self._delay > 0:
            self._delay -= 1
          elif self._pauseCount < self._PAUSE:
            self._pauseCount += 1
          else:
            self._pauseCount = 0
            self._nextLine += self._direction

            if self._positionLog:
              x = self._io.xAxis.getPosition()
              y = self._io.yAxis.getPosition()
              z = self._io.zAxis.getPosition()
              self._z = self._io.head.getTargetAxisPosition()
              self._positionLog.write(
                str(self._x)
                + ","
                + str(self._y)
                + ","
                + str(self._z)
                + ","
                + str(x)
                + ","
                + str(y)
                + ","
                + str(z)
                + ","
                + str(self._x - x)
                + ","
                + str(self._y - y)
                + ","
                + str(self._z - z)
                + "\n"
              )

            self._isG_CodeError = False
            self._stopNextMove = self.singleStep
            queued_started = False
            if self._beforeExecuteLineCallback:
              error = self._beforeExecuteLineCallback()
              if error:
                self._isG_CodeErrorMessage = str(error)
                self._isG_CodeErrorData = [self._nextLine, self._gCode.lines[self._nextLine]]
                self._isG_CodeError = True
                return True
            queued_started = self._start_queued_block(self._nextLine)
            if not queued_started:
              self.runNextLine(skip_before_execute_callback=True)
            self.singleStep = False

    return isDone

  # ---------------------------------------------------------------------
  def isG_CodeError(self):
    """
    Check to see if there is an error with the G-Code.

    Returns:
      True if there is an error, False if not.
    """
    return self._isG_CodeError

  # ---------------------------------------------------------------------
  def clearCodeError(self):
    """
    Clear any existing G-Code error.  Call after error has been debt with.
    """
    self._isG_CodeError = False
    self._isG_CodeErrorMessage = ""
    self._isG_CodeErrorData = []

  # ---------------------------------------------------------------------
  def getG_CodeErrorMessage(self):
    """
    If there is an error, this function will return an error message detailing
    what is wrong with the G-Code.

    Returns:
      String with error message.
    """
    return self._isG_CodeErrorMessage

  # ---------------------------------------------------------------------
  def getG_CodeErrorData(self):
    """
    If there is an error, this function will return an error data detailing
    what is wrong with the G-Code.

    Returns:
      An array of data.
    """
    return self._isG_CodeErrorData


  # ---------------------------------------------------------------------
  def executeG_CodeLine(self, line: str):
    """
    Run a line of G-code.

    Args:
      line: G-Code to execute.

    Returns:
      Failure data.  None if there was no failure.
    """
    errorData = None
    gCode = GCodeProgramExecutor([], self._callbacks)
    try:
      if self._beforeExecuteLineCallback:
        error = self._beforeExecuteLineCallback()
        if error:
          return {"line": line, "message": str(error), "data": []}

      # Interpret the next line.
      gCode.execute(line)
      self.poll()
      if self._isG_CodeError:
        errorData = {
          "line": line,
          "message": self._isG_CodeErrorMessage,
          "data": list(self._isG_CodeErrorData),
        }
        self.clearCodeError()
    except GCodeExecutionError as exception:
      errorData = {"line": line, "message": str(exception), "data": exception.data}

    return errorData

  # ---------------------------------------------------------------------
  def runNextLine(self, skip_before_execute_callback: bool = False):
    """
    Interpret and execute the next line of G-Code.
    """

    # Reset all values so we know what has changed.
    self._line = None
    self._lastX = self._x
    self._lastY = self._y
    self._lastZ = self._z
    self._lastVelocity = self._velocity
    self._functions = []

    try:
      if self._beforeExecuteLineCallback and not skip_before_execute_callback:
        error = self._beforeExecuteLineCallback()
        if error:
          self._isG_CodeErrorMessage = str(error)
          self._isG_CodeErrorData = [self._nextLine, self._gCode.lines[self._nextLine]]
          self._isG_CodeError = True
          return

      # Interpret the next line.
      self._gCode.executeNextLine(self._nextLine)
    except GCodeExecutionError as exception:
      self._isG_CodeErrorMessage = str(exception)

      self._isG_CodeErrorData = [self._nextLine, self._gCode.lines[self._nextLine]]
      self._isG_CodeErrorData += exception.data

      self._isG_CodeError = True

    # Place adjusted line in G-Code output log.
    if self._gCodeLog:
      line = ""

      #
      # Only log what has changed since the self._last line.
      #

      if self._line is not None:
        line += "N" + str(self._line) + " "

      if self._lastX != self._x:
        line += "X" + str(self._x) + " "

      if self._lastY != self._y:
        line += "Y" + str(self._y) + " "

      if self._lastZ != self._z:
        line += "Z" + str(self._z) + " "

      if self._lastVelocity != self._velocity:
        line += "F" + str(self._velocity) + " "

      for function in self._functions:
        line += "G" + str(function[0]) + " "
        for parameter in function[1:]:
          line += "P" + str(parameter) + " "

      # Strip trailing space.
      line = line.strip()

      # Add line-feed.
      line += "\n"

      # Place in G-Code log.
      self._gCodeLog.write(line)

  # ---------------------------------------------------------------------
  def closeG_Code(self):
    """
    Close the loaded G-Code file.
    """
    self._gCode = None
    self._currentLine = -1
    self._nextLine = -1
    self._firstMove = True
    self._queued_session = None
    self.useLayerCalibration(None)

  # ---------------------------------------------------------------------
  def loadG_Code(self, lines, calibration):
    """
    Load G-Code file.

    Args:
      fileName: Full file name to G-Code to be loaded.
      calibration: Calibration for layer being loaded.
    """

    self._gCode = GCodeProgramExecutor(lines, self._callbacks)
    self._currentLine = -1
    self._nextLine = -1
    self._firstMove = True
    self._queued_session = None

    # Setup the front and back head locations.
    # self._io.head.setFrontAndBack(calibration.zFront, calibration.zBack)

    # Use current X/Y/Z position as starting points.
    # (These will be moved to self.lastN when the next line is executed.)
    self._x = self._io.xAxis.getPosition()
    self._y = self._io.yAxis.getPosition()
    self._z = self._io.zAxis.getPosition()

  # ---------------------------------------------------------------------
  def reloadG_Code(self, lines):
    """
    Replace the active G-Code program while preserving execution state.

    Args:
      lines: New G-Code lines to use.

    Raises:
      ValueError: Current execution pointers do not fit in the new file.
    """
    gCode = GCodeProgramExecutor(lines, self._callbacks)
    lineCount = gCode.getLineCount()

    currentLine = self._currentLine
    if currentLine is not None and not (-1 <= currentLine < lineCount):
      raise ValueError("Current G-Code line is outside the reloaded file.")

    nextLine = self._nextLine
    if nextLine is not None and not (-1 <= nextLine <= lineCount):
      raise ValueError("Next G-Code line is outside the reloaded file.")

    self._gCode = gCode
    self._queued_session = None

  # ---------------------------------------------------------------------
  def isG_CodeLoaded(self):
    """
    Check to see if there is G-Code loaded.

    Returns:
      True if G-Code is loaded, False if not.
    """
    return self._gCode is not None

  # ---------------------------------------------------------------------
  def fetchLines(self, center, delta):
    """
    Fetch a sub-set of the G-Code self.lines.  Useful for showing what has
    recently executed, and what is to come.

    Args:
      center: Where to center the list.
      delta: Number of entries to read +/- center.

    Returns:
      List of G-Code lines, padded with empty lines if needed.  Empty list if
      no G-Code is loaded.
    """
    result = []
    if self._gCode:
      result = self._gCode.fetchLines(center, delta)

    return result

  # ---------------------------------------------------------------------
  def setG_CodeLog(self, gCodeLogFile):
    """
    Set a file to output resulting G-Code.

    Args:
      gCodeLogFile: File name to log data.
    """
    self._gCodeLog = open(gCodeLogFile, "a")

  # ---------------------------------------------------------------------
  def closeG_CodeLog(self):
    """
    Close the open G-Code log file.
    """
    if self._gCodeLog:
      self._gCodeLog.close()
      self._gCodeLog = None

  # ---------------------------------------------------------------------
  def isPositionLogging(self):
    """
    Check to see if position logging is enabled.

    Returns:
      True if position logging is enabled.
    """
    return self._positionLog is not None

  # ---------------------------------------------------------------------
  def startPositionLogging(self, positionLogFileName):
    """
    Start/stop logging resulting positions after seek completion.
    Test function--not used in normal operation.

    Args:
      positionLogFileName: Name of file to log position data.  None to close
        current log file.
    """
    if positionLogFileName:
      self._positionLog = open(positionLogFileName, "a")
      self._positionLog.write(
        "Actual x,Actual y,Actual z,Desired x,Desired y,Desired z,Error x,Error y,Error z\n"
      )
    elif self._positionLog:
      self._positionLog.close()
      self._positionLog = None

  # ---------------------------------------------------------------------

  def __init__(self, io: BaseIO, machineCalibration, headCompensation):
    """
    Constructor.

    Args:
      io: Instance of I/O map.
      machineCalibration: Machine calibration instance.
      headCompensation: Instance of HeadCompensation.
    """
    G_CodeHandlerBase.__init__(self, machineCalibration, headCompensation)

    self._gCode = None

    self._io = io

    self._direction = 1
    self.runToLine = -1
    self._currentLine = None
    self._nextLine = None
    self._gCodeLog = None
    self._positionLog = None

    self._stopNextMove = False
    self.singleStep = False
    self._beforeExecuteLineCallback = None
    self._lineChangeCallback = None

    # Add a pause between every G-Code instructions by setting _PAUSE to
    # non-zero value.
    self._PAUSE = 0
    self._pauseCount = 0

    # Delay from G-Code file.
    self._delay = 0

    # Tension measurment system parameters
    self._layer = None
    self._apaSide = None
    # self._comPort = None
    # self._strummerSerial = None
    # self._tensionThreshold = None
    # self._tensionRun = None
    # self._tensionFile = None
    # self._frequency = 0
    # self._isTensionError = False
    # self._isTensionErrorMessage = ""
    # # self._isTensionErrorData = []
    self._velocityScale = 1.0

    self._firstMove = False
    self._isG_CodeError = False
    self._isG_CodeErrorMessage = ""
    self._isG_CodeErrorData = []
    self._queued_session = None
    self._queued_block_start_line = None
    self._queued_block_resume_line = None
    self._queued_sequence_id = 1000
    self._queued_stop_mode = None
