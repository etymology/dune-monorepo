###############################################################################
# Name: GCodeHandler.py
# Uses: Hardware specific G-code handling.  Associates the G-code command to a
#       actual hardware.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import time
import math
from dataclasses import dataclass, replace

from dune_winder.gcode.runtime import GCodeExecutionError, GCodeProgramExecutor
from dune_winder.gcode.handler_base import GCodeHandlerBase
from dune_winder.io.maps.base_io import BaseIO
from dune_winder.queued_motion.diagnostics import serialize_segment_diagnostics
from dune_winder.queued_motion.merge_planner import MergeWaypoint, build_merge_path_segments
from dune_winder.queued_motion.plc_interface import PLC_QUEUE_DEPTH
from dune_winder.queued_motion.queue_session import QueuedMotionSession
from dune_winder.queued_motion.safety import (
  MotionSafetyLimits,
  motion_safety_limits_from_calibration,
  QueuedMotionCollisionState,
  validate_xy_move_within_safety_limits,
)
from dune_winder.queued_motion.segment_patterns import DEFAULT_WAYPOINT_MIN_ARC_RADIUS

_COMMAND_POSITION_RESOLUTION_MM = 0.1


@dataclass(frozen=True)
class _PreviewedQueuedLine:
  line_index: int
  line_text: str
  queueable: bool
  x: float
  y: float
  velocity: float
  merge_mode: str | None


@dataclass
class _QueuedMotionPreviewState:
  block: dict[str, object]
  preview: dict[str, object]
  decision: str | None = None


class GCodeHandler(GCodeHandlerBase):
  # ---------------------------------------------------------------------
  def _queued_motion_collision_state(self):
    def _input_enabled(name):
      io_point = getattr(self._io, name, None)
      if io_point is None or not hasattr(io_point, "get"):
        return False
      try:
        return bool(io_point.get())
      except Exception:
        return False

    try:
      z_actual = float(self._io.zAxis.getPosition())
    except Exception:
      z_actual = 0.0

    return QueuedMotionCollisionState(
      z_actual_position=z_actual,
      frame_lock_head_top=_input_enabled("FrameLockHeadTop"),
      frame_lock_head_mid=_input_enabled("FrameLockHeadMid"),
      frame_lock_head_btm=_input_enabled("FrameLockHeadBtm"),
      frame_lock_foot_top=_input_enabled("FrameLockFootTop"),
      frame_lock_foot_mid=_input_enabled("FrameLockFootMid"),
      frame_lock_foot_btm=_input_enabled("FrameLockFootBtm"),
    )

  # ---------------------------------------------------------------------
  def _getHeadPosition(self, headPosition):
    """
    Resolve head position, polling the PLC if it is currently unknown (None).
    """
    if headPosition is None:
      headPosition = self._io.head.readCurrentPosition()
      self._headPosition = headPosition
    return GCodeHandlerBase._getHeadPosition(self, headPosition)

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
  def _actual_xy(self):
    try:
      x = float(self._io.xAxis.getPosition())
    except Exception:
      x = float(self._x)

    try:
      y = float(self._io.yAxis.getPosition())
    except Exception:
      y = float(self._y)

    return (x, y)

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
      line_text=str(self._gCode.lines[line_index]),
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
  def _build_queued_block(self, line_index, *, single_step_queue: bool = False):
    if (
      self._gCode is None
      or self._direction != 1
      or not hasattr(self._io.plcLogic, "queuedMotion")
      or (self.singleStep and not single_step_queue)
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
          break
        next_preview = self._preview_loaded_line(cursor)
        if not next_preview.queueable:
          break
        previews.append(next_preview)
        if next_preview.merge_mode is None:
          break

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
        queued_motion_collision_state=self._queued_motion_collision_state(),
      )
      if not segments:
        return None
      resume_line = previews[-1].line_index + 1
      stop_after_block = False
      if single_step_queue:
        segments = [replace(segments[0], term_type=0)]
        resume_line = line_index + 1
        stop_after_block = True
      self._queued_sequence_id += len(segments) + 1
      return {
        "start_line": line_index,
        "resume_line": resume_line,
        "start_xy": start_xy,
        "segments": segments,
        "source_lines": [
          {
            "lineIndex": int(preview.line_index),
            "lineNumber": int(preview.line_index + 1),
            "text": str(preview.line_text),
            "mergeMode": preview.merge_mode,
            "target": {
              "x": float(preview.x),
              "y": float(preview.y),
            },
          }
          for preview in previews
        ],
        "safety_limits": safety_limits,
        "stop_after_block": stop_after_block,
      }
    finally:
      self._restore_interpreter_state(snapshot)

  # ---------------------------------------------------------------------
  def _build_queued_preview_payload(self, block):
    start_xy = tuple(block["start_xy"])
    segments = list(block["segments"])
    safety_limits = block["safety_limits"]
    segment_diagnostics, segment_summary = serialize_segment_diagnostics(
      start_xy=start_xy,
      segments=segments,
    )
    source_lines = list(block.get("source_lines", []))
    start_line = int(block["start_line"])
    resume_line = int(block["resume_line"])

    summary = dict(segment_summary)
    summary["g113Count"] = int(len(source_lines))
    summary["startLineNumber"] = int(start_line + 1)
    summary["resumeLineNumber"] = int(resume_line + 1)

    return {
      "previewId": int(self._queued_preview_id),
      "kind": "single" if len(source_lines) == 1 else "block",
      "startLine": int(start_line),
      "resumeLine": int(resume_line),
      "stopAfterBlock": bool(block.get("stop_after_block")),
      "start": {
        "x": float(start_xy[0]),
        "y": float(start_xy[1]),
      },
      "actualHead": {
        "x": float(self._actual_xy()[0]),
        "y": float(self._actual_xy()[1]),
      },
      "sourceLines": source_lines,
      "segments": segment_diagnostics,
      "summary": summary,
      "limits": {
        "limitLeft": float(safety_limits.limit_left),
        "limitRight": float(safety_limits.limit_right),
        "limitBottom": float(safety_limits.limit_bottom),
        "limitTop": float(safety_limits.limit_top),
        "transferZoneHeadMinX": float(safety_limits.transfer_zone_head_min_x),
        "transferZoneHeadMaxX": float(safety_limits.transfer_zone_head_max_x),
        "transferZoneFootMinX": float(safety_limits.transfer_zone_foot_min_x),
        "transferZoneFootMaxX": float(safety_limits.transfer_zone_foot_max_x),
        "supportCollisionBottomMinY": float(safety_limits.support_collision_bottom_min_y),
        "supportCollisionBottomMaxY": float(safety_limits.support_collision_bottom_max_y),
        "supportCollisionMiddleMinY": float(safety_limits.support_collision_middle_min_y),
        "supportCollisionMiddleMaxY": float(safety_limits.support_collision_middle_max_y),
        "supportCollisionTopMinY": float(safety_limits.support_collision_top_min_y),
        "supportCollisionTopMaxY": float(safety_limits.support_collision_top_max_y),
      },
    }

  # ---------------------------------------------------------------------
  def _set_queued_motion_preview(self, block):
    self._queued_preview_id += 1
    self._queued_preview = _QueuedMotionPreviewState(
      block=block,
      preview=self._build_queued_preview_payload(block),
    )

  # ---------------------------------------------------------------------
  def _launch_queued_block(self, block):
    self._queued_block_start_line = int(block["start_line"])
    self._queued_block_resume_line = int(block["resume_line"])
    self._queued_stop_mode = "single_step" if block.get("stop_after_block") else None
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

  # ---------------------------------------------------------------------
  def _advance_queued_preview(self):
    if self._queued_preview is None:
      return None

    if self._queued_preview.decision == "continue":
      block = self._queued_preview.block
      self._queued_preview = None
      self._launch_queued_block(block)
      return False

    if self._queued_preview.decision == "cancel":
      block = self._queued_preview.block
      self._queued_preview = None
      self._queued_stop_mode = None
      self._queued_block_start_line = int(block["start_line"])
      self._queued_block_resume_line = int(block["resume_line"])
      self._nextLine = self._queued_block_start_line - self._direction
      return True

    return False

  # ---------------------------------------------------------------------
  def _start_queued_block(self, line_index):
    try:
      block = self._build_queued_block(line_index, single_step_queue=self.singleStep)
    except ValueError:
      # If queued planning fails for this line, execute it through the legacy path.
      return False
    if block is None:
      return False

    self._set_queued_motion_preview(block)
    previous_line = self._currentLine
    self._currentLine = int(block["start_line"])
    if self._currentLine != previous_line and self._lineChangeCallback:
      self._lineChangeCallback()
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
      self._queued_stop_mode = None
      return True

    if self._queued_session.aborted:
      self._queued_session = None
      self._nextLine = self._queued_block_start_line - self._direction
      self._queued_stop_mode = None
      return True

    if self._queued_session.done:
      self._queued_session = None
      self._nextLine = self._queued_block_resume_line - self._direction
      if self._queued_stop_mode == "single_step":
        self._stopNextMove = True
      self._queued_stop_mode = None
      return False

    return False

  # ---------------------------------------------------------------------
  def stop(self):
    """
    Stop the running G-Code.  Call when interrupting G-Code sequence.
    """

    self._stopNextMove = False
    if self._queued_preview is not None:
      self._queued_block_start_line = int(self._queued_preview.block["start_line"])
      self._queued_block_resume_line = int(self._queued_preview.block["resume_line"])
      self._queued_preview = None
      self._queued_stop_mode = None
      self._nextLine = self._queued_block_start_line - self._direction
      return

    if self._queued_session is not None:
      if hasattr(self._io.plcLogic, "stopSeek"):
        self._io.plcLogic.stopSeek()
      else:
        self._io.plcLogic.queuedMotion.set_stop_request(True)
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
    if self._queued_preview is not None:
      self._queued_block_start_line = int(self._queued_preview.block["start_line"])
      self._queued_block_resume_line = int(self._queued_preview.block["resume_line"])
      self._queued_preview = None
      self._queued_stop_mode = None
      self._nextLine = self._queued_block_start_line - self._direction
      self._stopNextMove = True
      return

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

    preview_state = self._advance_queued_preview()
    if preview_state is not None:
      return preview_state

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
          target_xy = (float(self._x), float(self._y))
          is_noop_xy_move = (
            math.hypot(target_xy[0] - start_xy[0], target_xy[1] - start_xy[1])
            < _COMMAND_POSITION_RESOLUTION_MM
          )
          if is_noop_xy_move:
            # Sub-resolution XY command: already at target.
            moving = False
          else:
            try:
              validate_xy_move_within_safety_limits(
                start_xy,
                target_xy,
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
  def getQueuedMotionPreview(self):
    if self._queued_preview is None:
      return None
    return self._queued_preview.preview

  # ---------------------------------------------------------------------
  def continueQueuedMotionPreview(self):
    if self._queued_preview is None:
      return False
    self._queued_preview.decision = "continue"
    return True

  # ---------------------------------------------------------------------
  def cancelQueuedMotionPreview(self):
    if self._queued_preview is None:
      return False
    self._queued_preview.decision = "cancel"
    return True


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
    self._queued_preview = None
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
    self._queued_preview = None

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
    self._queued_preview = None

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
      headCompensation: Instance of WirePathModel.
    """
    GCodeHandlerBase.__init__(self, machineCalibration, headCompensation)

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
    self._queued_preview_id = 0
    self._queued_preview = None
    self._queued_stop_mode = None
