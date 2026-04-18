###############################################################################
# Name: GCodeHandlerBase.py
# Uses: Base class to handle G-Code execution.
# Date: 2016-03-30
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   This class handles all the machine specific G-Code functions, but not the
# execution of the motions.  That is, it knows how to decode and handle
# specific G-Code functions that modify X/Y or signal other functions.
###############################################################################

import copy
import json
import logging
import os

from dune_winder.library.math_extra import MathExtra
from dune_winder.gcode.model import CommandWord, Comment, FunctionCall, Opcode, ProgramLine
from dune_winder.gcode.renderer import render_line
from dune_winder.gcode.runtime import (
  GCodeCallbacks,
  GCodeExecutionError,
  GCodeProgramExecutor,
)

from dune_winder.library.Geometry.location import Location
from dune_winder.library.Geometry.line import Line
from dune_winder.library.Geometry.box import Box
from dune_winder.library.Geometry.segment import Segment

from dune_winder.machine.calibration.layer import LayerCalibration
from dune_winder.machine.calibration.machine import MachineCalibration
from dune_winder.machine.settings import Settings


LOGGER = logging.getLogger(__name__)
_MOTION_TRACE_LOG_ENV = "DUNE_GCODE_MOTION_TRACE_LOG"
_MOTION_TRACE_LOG_DEFAULT = os.path.join(Settings.CACHE_DIR, "gcode_motion_trace.log")
_MOTION_TRACE_FILE_HANDLER = None
_MOTION_TRACE_FILE_PATH = None


def _motion_trace_log_path():
  configured = os.environ.get(_MOTION_TRACE_LOG_ENV)
  if configured:
    return os.path.abspath(configured)
  return os.path.abspath(_MOTION_TRACE_LOG_DEFAULT)


def _ensure_motion_trace_file_handler():
  global _MOTION_TRACE_FILE_HANDLER, _MOTION_TRACE_FILE_PATH

  file_path = _motion_trace_log_path()
  if _MOTION_TRACE_FILE_HANDLER is not None and _MOTION_TRACE_FILE_PATH == file_path:
    return

  if _MOTION_TRACE_FILE_HANDLER is not None:
    try:
      LOGGER.removeHandler(_MOTION_TRACE_FILE_HANDLER)
    except Exception:
      pass
    try:
      _MOTION_TRACE_FILE_HANDLER.close()
    except Exception:
      pass
    _MOTION_TRACE_FILE_HANDLER = None
    _MOTION_TRACE_FILE_PATH = None

  os.makedirs(os.path.dirname(file_path), exist_ok=True)
  handler = logging.FileHandler(file_path, encoding="utf-8")
  handler.setLevel(logging.INFO)
  handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
  LOGGER.addHandler(handler)
  if LOGGER.level in (logging.NOTSET, 0) or LOGGER.level > logging.INFO:
    LOGGER.setLevel(logging.INFO)
  _MOTION_TRACE_FILE_HANDLER = handler
  _MOTION_TRACE_FILE_PATH = file_path


class GCodeHandlerBase:
  DEBUG_UNIT = False

  # ---------------------------------------------------------------------
  @staticmethod
  def _location_to_dict(location):
    if location is None:
      return None
    return {
      "x": float(location.x),
      "y": float(location.y),
      "z": float(location.z),
    }

  # ---------------------------------------------------------------------
  def _wire_space_location(self, location):
    if location is None:
      return None
    offset = getattr(self._layerCalibration, "offset", None)
    if offset is None:
      return location.copy()
    return location.add(offset)

  # ---------------------------------------------------------------------
  def _build_pin_trace(self, *, role, pin_name, location, extra=None):
    payload = {
      "role": str(role),
      "pin": str(pin_name),
      "calibrationSpace": self._location_to_dict(location),
      "wireSpace": self._location_to_dict(self._wire_space_location(location)),
    }
    if extra:
      payload.update(extra)
    return payload

  # ---------------------------------------------------------------------
  def _record_instruction_trace_pin(self, *, role, pin_name, location, extra=None):
    if self._instruction_trace is None:
      return
    self._instruction_trace["pins"].append(
      self._build_pin_trace(
        role=role,
        pin_name=pin_name,
        location=location,
        extra=extra,
      )
    )

  # ---------------------------------------------------------------------
  def _resolve_head_target_z(self):
    head_position = getattr(self, "_headPosition", None)
    if head_position is None or head_position == -1:
      return None
    try:
      return float(self._getHeadPosition(head_position))
    except GCodeExecutionError:
      return None

  # ---------------------------------------------------------------------
  def _log_instruction_trace(self, line: ProgramLine):
    if not self._instruction_trace or not self._instruction_trace["enabled"]:
      return

    _ensure_motion_trace_file_handler()
    rendered_line = render_line(line)
    head_z = self._resolve_head_target_z()
    resulting_wire_target = None
    if head_z is not None and self._x is not None and self._y is not None:
      try:
        resulting_wire_target = self._headCompensation.getActualLocation(
          Location(self._x, self._y, head_z)
        )
      except Exception:
        resulting_wire_target = None

    payload = {
      "line": rendered_line,
      "resultingTarget": {
        "x": float(self._x) if self._x is not None else None,
        "y": float(self._y) if self._y is not None else None,
        "pinZ": float(self._z) if self._z is not None else None,
        "headZ": head_z,
      },
      "resultingWireTarget": self._location_to_dict(resulting_wire_target),
      "pins": list(self._instruction_trace["pins"]),
      "pinCenter": self._instruction_trace.get("pinCenter"),
      "anchorOrientation": self._instruction_trace.get("anchorOrientation"),
    }
    LOGGER.info("GCODE_MOTION_TRACE %s", json.dumps(payload, sort_keys=True))
    if self._instruction_trace_callback is not None:
      self._instruction_trace_callback(dict(payload))

  # ---------------------------------------------------------------------
  def _setVelocity(self, velocity):
    """Set commanded velocity, capped to the configured maximum."""
    if velocity < self._maxVelocity:
      self._velocity = velocity
    else:
      self._velocity = self._maxVelocity

  # ---------------------------------------------------------------------
  def _request_xy_move(self):
    self._instruction_request_xy = True

  # ---------------------------------------------------------------------
  def _request_z_move(self):
    self._instruction_request_z = True

  # ---------------------------------------------------------------------
  def _request_head_move(self):
    self._instruction_request_head = True

  # ---------------------------------------------------------------------
  def _request_head_transfer(self):
    self._instruction_request_head_transfer = True

  # ---------------------------------------------------------------------
  def _request_latch(self):
    self._instruction_request_latch = True

  # ---------------------------------------------------------------------
  def _request_stop(self):
    self._instruction_request_stop = True

  # ---------------------------------------------------------------------
  def _snapshot_interpreter_state(self):
    return {
      "_x": self._x,
      "_y": self._y,
      "_z": self._z,
      "_headPosition": self._headPosition,
      "_lastX": self._lastX,
      "_lastY": self._lastY,
      "_lastZ": self._lastZ,
      "_pending_actions": list(self._pending_actions),
      "_pending_stop_request": self._pending_stop_request,
      "_instruction_request_xy": self._instruction_request_xy,
      "_instruction_request_z": self._instruction_request_z,
      "_instruction_request_head": self._instruction_request_head,
      "_instruction_request_head_transfer": self._instruction_request_head_transfer,
      "_instruction_request_latch": self._instruction_request_latch,
      "_instruction_request_stop": self._instruction_request_stop,
      "_instruction_contains_x": self._instruction_contains_x,
      "_instruction_contains_y": self._instruction_contains_y,
      "_instruction_contains_z": self._instruction_contains_z,
      "_instruction_force_xz": self._instruction_force_xz,
      "_instruction_queue_merge_mode": self._instruction_queue_merge_mode,
      "_line": self._line,
      "_delay": self._delay,
      "_wireTension": self._wireTension,
      "_tensionTesting": self._tensionTesting,
      "_wireLength": self._wireLength,
      "_maxVelocity": self._maxVelocity,
      "_velocity": self._velocity,
      "_functions": list(self._functions),
      "_headCompensation": copy.deepcopy(self._headCompensation),
    }

  # ---------------------------------------------------------------------
  def _restore_interpreter_state(self, snapshot):
    for key, value in snapshot.items():
      setattr(self, key, value)

  # ---------------------------------------------------------------------
  def _consume_command_word(self, command: CommandWord):
    if command.letter == "X":
      self._instruction_contains_x = True
      self._x = float(command.value)
      self._request_xy_move()
      return

    if command.letter == "Y":
      self._instruction_contains_y = True
      self._y = float(command.value)
      self._request_xy_move()
      return

    if command.letter == "Z":
      self._instruction_contains_z = True
      self._z = self._resolve_z_target(command.value)
      if any(str(parameter).strip().upper() == "XZ" for parameter in command.parameters):
        self._instruction_force_xz = True
      self._request_z_move()
      return

    if command.letter == "F":
      self._setVelocity(float(command.value))
      return

    if command.letter == "N":
      self._line = int(command.value)
      if GCodeHandlerBase.DEBUG_UNIT:
        print("Line", self._line)
      return

  # ---------------------------------------------------------------------
  def _queue_instruction_actions(self):
    if (
      self._instruction_request_xy
      and self._instruction_request_z
      and (self._instruction_contains_x or self._instruction_force_xz)
      and not self._instruction_contains_y
      and self._instruction_contains_z
    ):
      self._pending_actions.append("xz")
      return

    if (
      self._instruction_request_xy
      and self._instruction_request_z
      and self._instruction_contains_y
      and not self._instruction_contains_x
      and self._instruction_contains_z
    ):
      self._pending_actions.append("yz")
      return

    if self._instruction_request_xy:
      self._pending_actions.append("xy")

    if self._instruction_request_z:
      self._pending_actions.append("z")

    if self._instruction_request_head:
      self._pending_actions.append("head")

    if self._instruction_request_head_transfer:
      self._pending_actions.append("head_transfer")

    if self._instruction_request_latch:
      self._pending_actions.append("latch")

    if self._instruction_request_stop:
      self._pending_stop_request = True

  # ---------------------------------------------------------------------
  def handle_instruction(self, line: ProgramLine):
    """Handle one complete parsed G-code instruction line atomically."""
    self._instruction_trace = {"enabled": False, "pins": []}
    self._instruction_request_xy = False
    self._instruction_request_z = False
    self._instruction_request_head = False
    self._instruction_request_head_transfer = False
    self._instruction_request_latch = False
    self._instruction_request_stop = False
    self._instruction_contains_x = False
    self._instruction_contains_y = False
    self._instruction_contains_z = False
    self._instruction_force_xz = False
    self._instruction_queue_merge_mode = None

    for item in line.items:
      if isinstance(item, Comment):
        continue
      if isinstance(item, CommandWord):
        self._consume_command_word(item)
        continue
      if isinstance(item, FunctionCall):
        self._runFunction(item.as_legacy_parameter_list())

    self._queue_instruction_actions()
    self._log_instruction_trace(line)

  # ---------------------------------------------------------------------
  def _resolve_z_target(self, value):
    if isinstance(value, (int, float)):
      return float(value)

    text = str(value).strip()
    try:
      return float(text)
    except ValueError:
      pass

    if text.upper() == "EXTEND":
      return float(self._machineCalibration.zBack)

    data = [str(value)]
    raise GCodeExecutionError("Unknown Z target " + str(value) + ".", data)

  # ---------------------------------------------------------------------
  def _parameterExtract(self, parameters, start, finish, newType, errorMessage):
    """
    Extract the parameters and format them, raising an exception if they are
    incorrect.  Internal function.

    Args:
      parameters: String with parameters.
      start: Start location in string.
      end: End location in string (None to use end of line).
      newType: Type to cast (int, float, str, ect.)
      errorMessage: Error message to append if an incorrect format is encountered.

    Returns:
      An instance of 'newType' with data.

    Throws:
      GCodeExecutionError if formatting is incorrect.
    """

    try:
      if finish is None:
        value = newType(parameters[start])
      elif finish == start:
        value = newType(parameters[start:])
      else:
        value = newType(parameters[start:finish])
    except (IndexError, AttributeError, ValueError):
      data = [str(parameters)]

      raise GCodeExecutionError(
        "G-Code " + errorMessage + " function incorrectly formatted.", data
      )

    return value

  # ---------------------------------------------------------------------
  def _getHeadPosition(self, headPosition):
    """
    Use the head position to determine the Z position.

    Args:
      headPosition - 0-3

    Returns:
      What Z will be at the requested head position.

    Throws:
      GCodeExecutionError if formatting is incorrect.
    """

    # $$$DEBUG - Get rid of constants.
    if 0 == headPosition:
      z = self._machineCalibration.zFront
    elif 1 == headPosition:
      z = self._layerCalibration.zFront
    elif 2 == headPosition:
      z = self._layerCalibration.zBack
    elif 3 == headPosition:
      z = self._machineCalibration.zBack
    else:
      data = [str(headPosition)]

      raise GCodeExecutionError("Unknown head position " + str(headPosition) + ".", data)

    return z

  # ---------------------------------------------------------------------
  def _getPin(self, pinName):
    """
    Function to fetch specific pin location.

    Args:
      pinName: Name of pin to fetch.

    Returns:
      Instance of Location.

    Throws:
      GCodeExecutionError if pin is not found.
    """
    try:
      result = self._layerCalibration.getPinLocation(pinName)
    except KeyError:
      data = [str(pinName)]

      raise GCodeExecutionError("Unknown pin " + str(pinName) + ".", data)

    return result

  # ---------------------------------------------------------------------
  def _latch(self, function):
    """
    Toggle spool latch.
    """
    self._request_latch()

  # ---------------------------------------------------------------------
  def _wireLength(self, function):
    """
    Consumed wire for line.
    """

    # Get the length from the parameter.
    length = self._parameterExtract(function, 1, None, float, "wire length")

    # Account for direction of travel.
    self._wireLength = length

  # ---------------------------------------------------------------------
  def _seekTransfer(self, function):
    """
    Seek to transfer area
    This will maintain the slope of the path between where the wire is
    anchored and where the G-Code position is at present.
    """

    # The position thus far.
    endLocation = Location(self._x, self._y, self._z)

    if GCodeHandlerBase.DEBUG_UNIT:
      print("  SEEK_TRANSFER starting at", endLocation, end=" ")

    # Starting location based on anchor point.  Actual location has compensation
    # for pin diameter.
    startLocation = self._headCompensation.pinCompensation(endLocation)

    if GCodeHandlerBase.DEBUG_UNIT:
      print("Pin correction", startLocation, end=" ")

    if startLocation is None:
      data = [
        str(self._headCompensation.anchorPoint()),
        str(self._headCompensation.orientation()),
        str(endLocation),
      ]

      raise GCodeExecutionError(
        "G-Code seek transfer could not establish an anchor point.", data
      )

    segment = Segment(startLocation, endLocation)

    # Box that defines the Z hand-off edges.
    edges = Box(
      self._machineCalibration.transferLeft,
      self._machineCalibration.transferTop,
      self._machineCalibration.transferRight,
      self._machineCalibration.transferBottom,
    )

    location = edges.intersectSegment(segment)
    if GCodeHandlerBase.DEBUG_UNIT:
      print("Finial location", location)

    if location is None:
      data = [str(edges), str(segment)]

      raise GCodeExecutionError(
        "G-Code seek transfer could not establish a finial location.", data
      )

    self._x = location.x
    self._y = location.y
    self._request_xy_move()

  # ---------------------------------------------------------------------
  def _pinCenter(self, function):
    """
    Seek between pins.
    """

    pinNumberA = self._parameterExtract(function, 1, None, str, "pin center")
    pinNumberB = self._parameterExtract(function, 2, None, str, "pin center")
    axies = self._parameterExtract(function, 3, None, str, "pin center")

    if GCodeHandlerBase.DEBUG_UNIT:
      print("  PIN_CENTER", pinNumberA, pinNumberB, end=" ")

    if not self._layerCalibration:
      raise GCodeExecutionError(
        "G-Code request for calibrated move, but no layer calibration to use."
      )

    pinA = self._getPin(pinNumberA)
    pinB = self._getPin(pinNumberB)
    center = pinA.center(pinB)
    wire_center = center.add(self._layerCalibration.offset)
    self._instruction_trace["enabled"] = True
    self._record_instruction_trace_pin(role="pinA", pin_name=pinNumberA, location=pinA)
    self._record_instruction_trace_pin(role="pinB", pin_name=pinNumberB, location=pinB)
    self._instruction_trace["pinCenter"] = {
      "axes": str(axies),
      "calibrationSpace": self._location_to_dict(center),
      "wireSpace": self._location_to_dict(wire_center),
    }
    center = wire_center
    if GCodeHandlerBase.DEBUG_UNIT:
      print(pinA, pinB, center)

    if "X" in axies:
      self._x = center.x
      self._instruction_contains_x = True
      self._request_xy_move()

    if "Y" in axies:
      self._y = center.y
      self._instruction_contains_y = True
      self._request_xy_move()

    # Save the Z center location (but don't act on it).
    self._z = center.z

  # ---------------------------------------------------------------------
  def _clip(self, function):
    # Clip coordinates.

    oldX = self._x
    oldY = self._y

    self._y = max(self._y, self._machineCalibration.transferBottom)
    self._y = min(self._y, self._machineCalibration.transferTop)
    self._x = max(self._x, self._machineCalibration.transferLeft)
    self._x = min(self._x, self._machineCalibration.transferRight)

    if GCodeHandlerBase.DEBUG_UNIT:
      print("  CLIP", oldX, oldY, "->", self._x, self._y)

    if (oldX != self._x) or (oldY != self._y):
      self._request_xy_move()

  def _offset(self, function):
    # Offset coordinates.

    if GCodeHandlerBase.DEBUG_UNIT:
      print("  OFFSET", end=" ")

    parameters = function[1:]
    for parameter in parameters:
      axis = self._parameterExtract(parameter, 0, None, str, "offset")
      offset = self._parameterExtract(parameter, 1, 1, float, "offset")

      if "X" == axis:
        if GCodeHandlerBase.DEBUG_UNIT:
          print("x", offset, end=" ")

        self._x += offset
        self._instruction_contains_x = True
        self._request_xy_move()

      if "Y" == axis:
        if GCodeHandlerBase.DEBUG_UNIT:
          print("y", offset, end=" ")

        self._y += offset
        self._instruction_contains_y = True
        self._request_xy_move()

      if GCodeHandlerBase.DEBUG_UNIT:
        print()

  # ---------------------------------------------------------------------
  def _headLocation(self, function):
    """
    Head position.
    """

    self._headPosition = self._parameterExtract(function, 1, None, int, "head location")
    if -1 == self._headPosition:
      return
    self._request_head_move()

    if GCodeHandlerBase.DEBUG_UNIT:
      print("  HEAD_LOCATION", self._headPosition)

  # ---------------------------------------------------------------------
  def _headTransfer(self, function):
    """
    Head transfer position.
    """
    self._headPosition = self._parameterExtract(function, 1, None, int, "head transfer")
    self._request_head_transfer()

    if GCodeHandlerBase.DEBUG_UNIT:
      print("  HEAD_TRANSFER", self._headPosition)

  # ---------------------------------------------------------------------
  def _delay(self, function):
    """
    Delay.
    """
    if GCodeHandlerBase.DEBUG_UNIT:
      print("  DELAY", self._delay)

    self._delay = self._parameterExtract(function, 1, None, int, "delay")

  # ---------------------------------------------------------------------
  def _tensionTesting(self, function):
    """
    Wire tension testing.
    """
    self._wireTension = self._parameterExtract(function, 1, None, int, "tensionTesting")
    if self._wireTension > 0:
      self._tensionTesting = True

    if GCodeHandlerBase.DEBUG_UNIT:
      print(f"  TENSION_TESTING {self._tensionTesting} on wire {self._wireTension}")

  # ---------------------------------------------------------------------
  def _anchorPoint(self, function):
    """
    Correct for the arm on the winder head.
    """

    # Get anchor point.
    pinNumber = self._parameterExtract(function, 1, None, str, "anchor point")
    orientation = self._parameterExtract(function, 2, None, str, "anchor point")

    # Get pin center.
    pin = self._getPin(pinNumber)
    self._instruction_trace["enabled"] = True
    self._instruction_trace["anchorOrientation"] = orientation
    self._record_instruction_trace_pin(
      role="anchor",
      pin_name=pinNumber,
      location=pin,
      extra={"orientation": str(orientation)},
    )
    pin = pin.add(self._layerCalibration.offset)

    if "0" == orientation:
      orientation = None

    self._headCompensation.anchorPoint(pin)
    self._headCompensation.orientation(orientation)

    if GCodeHandlerBase.DEBUG_UNIT:
      print("  ANCHOR_POINT", pinNumber, pin, orientation)

  # ---------------------------------------------------------------------
  def _armCorrect(self, function):
    """
    Correct for the arm on the winder head.
    """

    z = self._getHeadPosition(self._headPosition)
    if z is None:
      return

    currentLocation = Location(self._x, self._y, z)
    if GCodeHandlerBase.DEBUG_UNIT:
      print("  ARM_CORRECT", currentLocation, end=" ")

    if MathExtra.isclose(
      self._y, self._machineCalibration.transferTop, abs_tol=1e-3
    ) or MathExtra.isclose(self._y, self._machineCalibration.transferBottom, abs_tol=1e-3):
      self._x = self._headCompensation.correctX(currentLocation)
      if GCodeHandlerBase.DEBUG_UNIT:
        print("new X", self._x, end=" ")

      edge = None

      # Check to see if the adjusted position shifted past the right/left
      # transfer area.
      if self._x > self._machineCalibration.transferRight:
        edge = Line(Line.VERTICLE_SLOPE, self._machineCalibration.transferRight)
      elif self._x < self._machineCalibration.transferLeft:
        edge = Line(Line.VERTICLE_SLOPE, self._machineCalibration.transferLeft)

      # Do correct for transfer area (if needed)...
      if edge:
        # Make a line along the path from the anchor point to the
        # destination.
        start = self._headCompensation.anchorPoint()
        line = Line.fromLocations(start, currentLocation)

        # Get position where line crosses transfer area.
        location = line.intersection(edge)

        # Compensate for head's arm.
        self._y = self._headCompensation.correctY(location)
        self._x = location.x
        if GCodeHandlerBase.DEBUG_UNIT:
          print("Edge", self._x, self._y, end=" ")
    else:
      self._y = self._headCompensation.correctY(currentLocation)
      if GCodeHandlerBase.DEBUG_UNIT:
        print("new Y", self._y, end=" ")

    if GCodeHandlerBase.DEBUG_UNIT:
      print()

    self._request_xy_move()

  # ---------------------------------------------------------------------
  def _transferCorrect(self, function):
    """
    Correct for hand-off transfer.
    """

    # Current seek position.
    start = Location(self._x, self._y, self._z)

    # Current head position.
    zHead = self._getHeadPosition(self._headPosition)
    if zHead is None:
      return

    if GCodeHandlerBase.DEBUG_UNIT:
      print(
        "  TRANSFER_CORRECT",
        self._headCompensation.anchorPoint(),
        start,
        zHead,
        end=" ",
      )

    # Wire orientation and desired head position.
    correction = self._parameterExtract(function, 1, None, str, "correction")
    correction = correction.upper()

    orientation = self._headCompensation.orientation()
    if GCodeHandlerBase.DEBUG_UNIT:
      print("correction", correction, "orientation", orientation, end=" ")

    if "X" == correction:
      # Which side of the anchor point pin the wire sits (left or right).
      if orientation is None:
        direction = 0  # <- No pin compensation.
      elif orientation.find("L") > -1:
        direction = 1
      elif orientation.find("R") > -1:
        direction = -1
      else:
        data = [str(orientation)]
        raise GCodeExecutionError("Unknown orientation: " + orientation + ".", data)

      self._x = self._headCompensation.transferCorrectX(start, zHead, direction)
    elif "Y" == correction:
      # Which side of the anchor point pin the wire sits (top or bottom).
      if orientation is None:
        direction = 0  # <- No pin compensation.
      elif orientation.find("B") > -1:
        direction = -1
      elif orientation.find("T") > -1:
        direction = 1
      else:
        data = [str(orientation)]
        raise GCodeExecutionError("Unknown orientation: " + orientation + ".", data)

      self._y = self._headCompensation.transferCorrectY(start, zHead, direction)
    else:
      data = [str(correction)]
      raise GCodeExecutionError("Unknown correction type: " + str(correction) + ".", data)

    if GCodeHandlerBase.DEBUG_UNIT:
      print("x", self._x, "y", self._y)

  # ---------------------------------------------------------------------
  def _break(self, function):
    """
    Break point.  Stop G-Code execution.
    """
    self._request_stop()

  # ---------------------------------------------------------------------
  def _queueMerge(self, function):
    mode = self._parameterExtract(function, 1, None, str, "queue merge").upper()
    if mode not in ("PRECISE", "TOLERANT"):
      data = [str(mode)]
      raise GCodeExecutionError("Unknown queue merge mode: " + str(mode) + ".", data)
    self._instruction_queue_merge_mode = mode

  # ---------------------------------------------------------------------

  # ------------------------------------
  # Look-up table of all G-Code functions.
  # ------------------------------------
  G_CODE_FUNCTION_TABLE = {
    Opcode.LATCH: _latch,
    Opcode.WIRE_LENGTH: _wireLength,
    Opcode.SEEK_TRANSFER: _seekTransfer,
    Opcode.PIN_CENTER: _pinCenter,
    Opcode.CLIP: _clip,
    Opcode.OFFSET: _offset,
    Opcode.HEAD_LOCATION: _headLocation,
    Opcode.HEAD_TRANSFER: _headTransfer,
    Opcode.DELAY: _delay,
    Opcode.ANCHOR_POINT: _anchorPoint,
    Opcode.ARM_CORRECT: _armCorrect,
    Opcode.TRANSFER_CORRECT: _transferCorrect,
    Opcode.BREAK_POINT: _break,
    Opcode.TENSION_TESTING: _tensionTesting,
    Opcode.QUEUE_MERGE: _queueMerge,
  }

  # ---------------------------------------------------------------------
  def _runFunction(self, function):
    """
    Callback for G-Code function.

    Args:
      function: Function number to execute.

    Throws:
      GCodeExecutionError if formatting is incorrect.
    """
    number = self._parameterExtract(function, 0, None, int, "base")
    self._functions.append(function)

    # Toggle spool latch.
    if number in list(GCodeHandlerBase.G_CODE_FUNCTION_TABLE.keys()):
      GCodeHandlerBase.G_CODE_FUNCTION_TABLE[number](self, function)
    else:
      data = [str(number)]
      raise GCodeExecutionError("Unknown G-Code " + str(number), data)

  # ---------------------------------------------------------------------
  def setLimitVelocity(self, maxVelocity):
    """
    Set the maximum velocity at which any axis can move.  Useful to slow
    down operations.

    Args:
      maxVelocity: New maximum velocity.

    Note:
      Does not effect the whatever the motors are currently doing.
    """
    self._maxVelocity = maxVelocity

  # ---------------------------------------------------------------------
  def setVelocity(self, velocity):
    """
    Set the velocity (override the commanded velocity until next command).

    Args:
      velocity: New velocity.
    """
    self._velocity = velocity

  # ---------------------------------------------------------------------
  def useLayerCalibration(self, layerCalibration: LayerCalibration):
    """
    Give handler an instance of layerCalibration to use for pin locations.  Must
    be called before running G-Code.

    Args:
      layerCalibration: Calibration specific to the layer being wound.
    """
    self._layerCalibration = layerCalibration

  # ---------------------------------------------------------------------
  def getLayerCalibration(self):
    """
    Return the layer calibration currently in use.

    Returns:
      Instance of LayerCalibration.  None if no calibration loaded.
    """
    return self._layerCalibration

  # ---------------------------------------------------------------------
  def setInstructionTraceCallback(self, callback):
    """
    Register a callback invoked with the structured motion-trace payload after
    a traced instruction is interpreted.

    Args:
      callback: Callable taking one payload dict argument, or None to clear.
    """
    self._instruction_trace_callback = callback

  # ---------------------------------------------------------------------
  def setInitialLocation(self, x, y, headLocation):
    """
    Set the last machine location.  This is needed when loading a new recipe
    because seeks to transfer areas need to know form where to begin.

    Args:
      location: Coordinates of starting position.
    """

    self._startLocationX = x
    self._startLocationY = y
    self._startHeadLocation = headLocation

  # ---------------------------------------------------------------------
  def __init__(self, machineCalibration: MachineCalibration, headCompensation):
    """
    Constructor.

    Args:
      machineCalibration: Machine calibration instance.
      headCompensation: Instance of WirePathModel.
    """
    self._callbacks = GCodeCallbacks()
    self._callbacks.registerCallback("on_instruction", self.handle_instruction)

    self._functions = []

    # X/Y/Z positions.  Protected.
    self._x = None
    self._y = None
    self._z = None
    self._headPosition = None

    self._lastX = None
    self._lastY = None
    self._lastZ = None

    self._pending_actions = []
    self._pending_stop_request = False
    self._instruction_request_xy = False
    self._instruction_request_z = False
    self._instruction_request_head = False
    self._instruction_request_head_transfer = False
    self._instruction_request_latch = False
    self._instruction_request_stop = False
    self._instruction_contains_x = False
    self._instruction_contains_y = False
    self._instruction_contains_z = False
    self._instruction_force_xz = False
    self._instruction_queue_merge_mode = None

    # Current line number.
    self._line = 0

    self._delay = 5000

    self._wireTension = int(0)
    self._tensionTesting = False

    # Wire length consumed by line.
    self._wireLength = 0

    # Velocity.
    self._maxVelocity = float("inf")  # <- No limit.
    self._velocity = float("inf")

    self._layerCalibration = None
    self._machineCalibration = machineCalibration
    self._headCompensation = headCompensation
    self._instruction_trace = None
    self._instruction_trace_callback = None

    self._startLocationX = None
    self._startLocationY = None
    self._startHeadLocation = None
