###############################################################################
# Name: G_CodeHandlerBase.py
# Uses: Base class to handle G-Code execution.
# Date: 2016-03-30
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   This class handles all the machine specific G-Code functions, but not the
# execution of the motions.  That is, it knows how to decode and handle
# specific G-Code functions that modify X/Y or signal other functions.
###############################################################################

from dune_winder.library.math_extra import MathExtra
from dune_winder.gcode.model import Opcode
from dune_winder.gcode.runtime import (
  GCodeCallbacks,
  GCodeExecutionError,
  GCodeProgramExecutor,
)

from dune_winder.library.Geometry.location import Location
from dune_winder.library.Geometry.line import Line
from dune_winder.library.Geometry.box import Box
from dune_winder.library.Geometry.segment import Segment

from .layer_calibration import LayerCalibration
from .machine_calibration import MachineCalibration


class G_CodeHandlerBase:
  DEBUG_UNIT = False

  # ---------------------------------------------------------------------
  def _setX(self, x):
    """
    Callback for setting x-axis.

    Args:
      x: Desired x-axis location.

    Returns:
      None.
    """
    self._xyChange = True
    self._x = x

  # ---------------------------------------------------------------------
  def _setY(self, y):
    """
    Callback for setting y-axis.

    Args:
      y: Desired y-axis location.

    Returns:
      None.
    """
    self._xyChange = True
    self._y = y

  # ---------------------------------------------------------------------
  def _setZ(self, z):
    """
    Callback for setting z-axis.

    Args:
      z: Desired z-axis location.

    Returns:
      None.
    """
    self._zChange = True
    self._z = z

  # ---------------------------------------------------------------------
  def _setVelocity(self, velocity):
    """
    Callback for setting velocity.

    Args:
      velocity: Desired maximum velocity.
    Returns:
      None.
    Notes:
      Limited to 'maxVelocity'.
    """
    if velocity < self._maxVelocity:
      self._velocity = velocity
    else:
      self._velocity = self._maxVelocity

  # ---------------------------------------------------------------------
  def _setLine(self, line):
    """
    Callback for setting line number.

    Args:
      line: Current line number.

    Returns:
      None.
    """
    self._line = line

    if G_CodeHandlerBase.DEBUG_UNIT:
      print("Line", line)

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
    self._latchRequest = True

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

    if G_CodeHandlerBase.DEBUG_UNIT:
      print("  SEEK_TRANSFER starting at", endLocation, end=" ")

    # Starting location based on anchor point.  Actual location has compensation
    # for pin diameter.
    startLocation = self._headCompensation.pinCompensation(endLocation)

    if G_CodeHandlerBase.DEBUG_UNIT:
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
    if G_CodeHandlerBase.DEBUG_UNIT:
      print("Finial location", location)

    if location is None:
      data = [str(edges), str(segment)]

      raise GCodeExecutionError(
        "G-Code seek transfer could not establish a finial location.", data
      )

    self._x = location.x
    self._y = location.y
    self._xyChange = True

  # ---------------------------------------------------------------------
  def _pinCenter(self, function):
    """
    Seek between pins.
    """

    pinNumberA = self._parameterExtract(function, 1, None, str, "pin center")
    pinNumberB = self._parameterExtract(function, 2, None, str, "pin center")
    axies = self._parameterExtract(function, 3, None, str, "pin center")

    if G_CodeHandlerBase.DEBUG_UNIT:
      print("  PIN_CENTER", pinNumberA, pinNumberB, end=" ")

    if not self._layerCalibration:
      raise GCodeExecutionError(
        "G-Code request for calibrated move, but no layer calibration to use."
      )

    pinA = self._getPin(pinNumberA)
    pinB = self._getPin(pinNumberB)
    center = pinA.center(pinB)
    center = center.add(self._layerCalibration.offset)
    if G_CodeHandlerBase.DEBUG_UNIT:
      print(pinA, pinB, center)

    if "X" in axies:
      self._x = center.x
      self._xyChange = True

    if "Y" in axies:
      self._y = center.y
      self._xyChange = True

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

    if G_CodeHandlerBase.DEBUG_UNIT:
      print("  CLIP", oldX, oldY, "->", self._x, self._y)

    self._xyChange |= (oldX != self._x) or (oldY != self._y)

  def _offset(self, function):
    # Offset coordinates.

    if G_CodeHandlerBase.DEBUG_UNIT:
      print("  OFFSET", end=" ")

    parameters = function[1:]
    for parameter in parameters:
      axis = self._parameterExtract(parameter, 0, None, str, "offset")
      offset = self._parameterExtract(parameter, 1, 1, float, "offset")

      if "X" == axis:
        if G_CodeHandlerBase.DEBUG_UNIT:
          print("x", offset, end=" ")

        self._x += offset
        self._xyChange = True

      if "Y" == axis:
        if G_CodeHandlerBase.DEBUG_UNIT:
          print("y", offset, end=" ")

        self._y += offset
        self._xyChange = True

      if G_CodeHandlerBase.DEBUG_UNIT:
        print()

  # ---------------------------------------------------------------------
  def _headLocation(self, function):
    """
    Head position.
    """

    self._headPosition = self._parameterExtract(function, 1, None, int, "head location")
    self._headPositionChange = True

    if G_CodeHandlerBase.DEBUG_UNIT:
      print("  HEAD_LOCATION", self._headPosition)

  # ---------------------------------------------------------------------
  def _delay(self, function):
    """
    Delay.
    """
    if G_CodeHandlerBase.DEBUG_UNIT:
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

    if G_CodeHandlerBase.DEBUG_UNIT:
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
    pin = pin.add(self._layerCalibration.offset)

    if "0" == orientation:
      orientation = None

    self._headCompensation.anchorPoint(pin)
    self._headCompensation.orientation(orientation)

    if G_CodeHandlerBase.DEBUG_UNIT:
      print("  ANCHOR_POINT", pinNumber, pin, orientation)

  # ---------------------------------------------------------------------
  def _armCorrect(self, function):
    """
    Correct for the arm on the winder head.
    """

    z = self._getHeadPosition(self._headPosition)

    currentLocation = Location(self._x, self._y, z)
    if G_CodeHandlerBase.DEBUG_UNIT:
      print("  ARM_CORRECT", currentLocation, end=" ")

    if MathExtra.isclose(
      self._y, self._machineCalibration.transferTop, abs_tol=1e-3
    ) or MathExtra.isclose(self._y, self._machineCalibration.transferBottom, abs_tol=1e-3):
      self._x = self._headCompensation.correctX(currentLocation)
      if G_CodeHandlerBase.DEBUG_UNIT:
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
        if G_CodeHandlerBase.DEBUG_UNIT:
          print("Edge", self._x, self._y, end=" ")
    else:
      self._y = self._headCompensation.correctY(currentLocation)
      if G_CodeHandlerBase.DEBUG_UNIT:
        print("new Y", self._y, end=" ")

    if G_CodeHandlerBase.DEBUG_UNIT:
      print()

    self._xyChange = True

  # ---------------------------------------------------------------------
  def _transferCorrect(self, function):
    """
    Correct for hand-off transfer.
    """

    # Current seek position.
    start = Location(self._x, self._y, self._z)

    # Current head position.
    zHead = self._getHeadPosition(self._headPosition)

    if G_CodeHandlerBase.DEBUG_UNIT:
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
    if G_CodeHandlerBase.DEBUG_UNIT:
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

    if G_CodeHandlerBase.DEBUG_UNIT:
      print("x", self._x, "y", self._y)

  # ---------------------------------------------------------------------
  def _break(self, function):
    """
    Break point.  Stop G-Code execution.
    """
    self._stopRequest = True

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
    Opcode.DELAY: _delay,
    Opcode.ANCHOR_POINT: _anchorPoint,
    Opcode.ARM_CORRECT: _armCorrect,
    Opcode.TRANSFER_CORRECT: _transferCorrect,
    Opcode.BREAK_POINT: _break,
    Opcode.TENSION_TESTING: _tensionTesting,
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
    if number in list(G_CodeHandlerBase.G_CODE_FUNCTION_TABLE.keys()):
      G_CodeHandlerBase.G_CODE_FUNCTION_TABLE[number](self, function)
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
      headCompensation: Instance of HeadCompensation.
    """
    self._callbacks = GCodeCallbacks()
    self._callbacks.registerCallback("X", self._setX)
    self._callbacks.registerCallback("Y", self._setY)
    self._callbacks.registerCallback("Z", self._setZ)
    self._callbacks.registerCallback("F", self._setVelocity)
    self._callbacks.registerCallback("G", self._runFunction)
    self._callbacks.registerCallback("N", self._setLine)

    self._functions = []

    # X/Y/Z positions.  Protected.
    self._x = None
    self._y = None
    self._z = None
    self._headPosition = None

    self._lastX = None
    self._lastY = None
    self._lastZ = None

    self._xyChange = False
    self._zChange = False
    self._headPositionChange = False
    self._stopRequest = False

    self._latchRequest = False

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

    self._startLocationX = None
    self._startLocationY = None
    self._startHeadLocation = None


# Unit test code.
if __name__ == "__main__":
  from dune_winder.library.math_extra import MathExtra
  from dune_winder.machine.default_calibration import (
    DefaultMachineCalibration,
    DefaultLayerCalibration,
  )
  from dune_winder.machine.head_compensation import HeadCompensation

  # Child of G-Code handler to do testing.
  class G_CodeTester(G_CodeHandlerBase):
    def __init__(self):
      # Create default calibrations and setup head compensation.
      machineCalibration = DefaultMachineCalibration()
      layerCalibration = DefaultLayerCalibration(None, None, "V")
      headCompensation = HeadCompensation(machineCalibration)

      # Some G-Code test lines.
      lines = [
        "X10 Y10 Z10",
        "G103 PF800 PF800 PXY",
        "G109 PF1200 PTR G103 PF1199 PF1198 PXY G102",
      ]

      # Construct G-Code handler.
      G_CodeHandlerBase.__init__(self, machineCalibration, headCompensation)
      self.useLayerCalibration(layerCalibration)

      # Setup G-Code interpreter.
      gCode = GCodeProgramExecutor(lines, self._callbacks)

      #
      # Run tests.
      #

      # Simple X/Y/Z seek.
      gCode.executeNextLine(0)
      assert Location(self._x, self._y, self._z) == Location(10, 10, 10)

      # Pin seek.
      gCode.executeNextLine(1)
      location = layerCalibration.getPinLocation("F800")
      location = location.add(layerCalibration.offset)
      location.z = 0
      assert location == Location(self._x, self._y)

      # Anchor point to transfer area check.
      # Anchor on pin F1, then center between F2399 and F2398.  Preserve the slope
      # of the line and seek to a transfer area.  This should intercept the bottom.
      gCode.executeNextLine(2)
      assert MathExtra.isclose(self._x, 887.701845335)
      assert MathExtra.isclose(self._y, 0)

  # Create instance of test class, thereby running tests.
  tester = G_CodeTester()


