###############################################################################
# Name: HeadCompensation.py
# Uses: Compensation calculations to account for arm and rollers on winder head.
# Date: 2016-08-19
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   This unit is trigonometric intensive.  The equations are explained in
#   the development log, verified visually on drawings and with spreadsheets.
# References:
#   Spreadsheet file "2016-09-15 -- Roller correction worksheet.ods"
#   Spreadsheet file "2016-08-25 -- Tangent circle worksheet.ods".
###############################################################################

import math
from dune_winder.library.MathExtra import MathExtra
from dune_winder.library.Geometry.Location import Location
from dune_winder.library.Geometry.Circle import Circle


class HeadCompensation:
  # ---------------------------------------------------------------------
  def __init__(self, machineCalibration):
    """
    Constructor.

    Args:
      machineCalibration - Instance of MachineCalibration.
    """
    self._machineCalibration = machineCalibration
    self._anchorPoint = Location(-1)

    # Anchor offset is used after pin compensation is calculated.
    # Anytime the anchor point is changed, the offset is set to 0.  If pin
    # compensation is calculated, the offset is stored here and used in
    # additional correction.
    self._anchorOffset = Location()
    self._orientation = None

  # ---------------------------------------------------------------------
  def orientation(self, value=None):
    """
    Get/set orientation of connecting wire.

    Args:
      value - New orientation (omit to read).

    Returns:
      The current orientation.
    """

    if value is not None:
      self._orientation = value

    return self._orientation

  # ---------------------------------------------------------------------
  def anchorPoint(self, location=None):
    """
    Get/set anchor point.

    Args:
      location - Location of the anchor point (omit to read).

    Returns:
      The current anchor point.
    """
    if location is not None:
      self._anchorPoint = location.copy()
      self._anchorOffset = Location()

    return self._anchorPoint

  # ---------------------------------------------------------------------
  def pinCompensation(self, endPoint):
    """
    Get the anchor position while compensating for the pin radius.
    This will compute a point for which the connecting line will run tangent
    to the anchor point circle.

    Args:
      endPoint: Target destination to run tangent line.

    Returns:
      Instance of location.  None if the orientation is incorrect for the
      target location.
    """

    result = None
    if self._orientation:
      pinRadius = self._machineCalibration.pinDiameter / 2
      circle = Circle(self._anchorPoint, pinRadius)
      result = circle.tangentPoint(self._orientation, endPoint)
      if result is not None:
        self._anchorOffset = result.sub(self._anchorPoint)
      else:
        # Preserve a neutral offset when tangent point cannot be established.
        # Caller will handle this as an invalid transfer geometry/orientation.
        self._anchorOffset = Location()
    else:
      result = self._anchorPoint
      self._anchorOffset = Location()

    return result

  # ---------------------------------------------------------------------
  def getHeadAngle(self, location):
    """
    Get the angle of the arm.

    Args:
      location: Location of actual machine position.

    Returns:
      Angle of the arm (-pi to +pi).
    """
    deltaX = location.x - self._anchorPoint.x
    deltaZ = location.z - self._anchorPoint.z
    return math.atan2(deltaX, deltaZ)

  # ---------------------------------------------------------------------
  def getActualLocation(self, machineLocation):
    """
    Get the actual wire position given machine position.  Assume an anchor
    point has been specified.

    Args:
      machineLocation - Actual machine position.

    Returns:
      Location object with the adjusted coordinates.
    """

    anchorPoint = self._anchorPoint.add(self._anchorOffset)

    #
    # First compensation is to correct for the angle of the arm on the head.
    #

    # Compute various lengths.
    deltaX = machineLocation.x - anchorPoint.x
    deltaZ = machineLocation.z - anchorPoint.z
    lengthXZ = math.sqrt(deltaX**2 + deltaZ**2)
    headRatio = self._machineCalibration.headArmLength / lengthXZ

    # Make correction.
    x = machineLocation.x - deltaX * headRatio
    y = machineLocation.y
    z = machineLocation.z - deltaZ * headRatio

    #
    # Second correction to the correct for the offset caused by the upper and
    # lower roller on the front of the head.
    #

    # Compute various lengths.
    deltaX = x - anchorPoint.x
    deltaY = y - anchorPoint.y
    deltaZ = z - anchorPoint.z
    lengthXZ = math.sqrt(deltaX**2 + deltaZ**2)
    lengthXYZ = math.sqrt(deltaX**2 + deltaY**2 + deltaZ**2)

    # The rollers are in two plans: Y and XZ.
    rollerOffsetY = self._machineCalibration.headRollerRadius * lengthXZ / lengthXYZ
    rollerOffsetXZ = self._machineCalibration.headRollerRadius * deltaY / lengthXYZ

    # Get the specific X and Z components out of the combine XZ value.
    rollerOffsetX = abs(rollerOffsetXZ * deltaX / lengthXZ)
    rollerOffsetZ = abs(rollerOffsetXZ * deltaZ / lengthXZ)

    # Correct for the roller offset made up of the radius, and the gap between
    # them.
    rollerOffsetY -= self._machineCalibration.headRollerRadius
    rollerOffsetY -= self._machineCalibration.headRollerGap / 2

    # Correct for direction form anchor point.
    if deltaX < 0:
      rollerOffsetX = -rollerOffsetX

    if deltaZ < 0:
      rollerOffsetZ = -rollerOffsetZ

    if deltaY > 0:
      rollerOffsetY = -rollerOffsetY

    # Make correction.
    x -= rollerOffsetX
    y -= rollerOffsetY
    z -= rollerOffsetZ

    return Location(x, y, z)

  # ---------------------------------------------------------------------
  def correctY(self, machineLocation):
    """
    Calculation a correction factor to Y that will place X as the nominal
    position.

    Args:
      machineLocation - Actual machine position.

    Returns:
      Corrected Y value.
    """

    anchorPoint = self._anchorPoint.add(self._anchorOffset)

    #
    # Head arm correction.
    #

    # Compute various lengths.
    deltaX = machineLocation.x - anchorPoint.x
    deltaY = machineLocation.y - anchorPoint.y

    # Compute a correction for the arm.
    headCorrection = -self._machineCalibration.headArmLength * deltaY / abs(deltaX)

    # Compute the new end point.
    machineLocation.y + headCorrection

    #
    # Roller correction.
    #

    # Offset to Y caused by the roller.
    # NOTE: This correction actually changes the tangent line, but the change
    # is so small (1 part in 1500) it is ignored.  Otherwise an iterative method
    # is required.
    rollerCorrection = deltaY**2 / deltaX**2
    rollerCorrection += 1
    rollerCorrection = math.sqrt(rollerCorrection)
    rollerCorrection -= 1
    rollerCorrection *= self._machineCalibration.headRollerRadius
    rollerCorrection -= self._machineCalibration.headRollerGap / 2

    if deltaY > 0:
      rollerCorrection = -rollerCorrection

    # Correct the Y position with two offsets.
    correctedY = machineLocation.y + headCorrection + rollerCorrection

    return correctedY

  # ---------------------------------------------------------------------
  def correctX(self, machineLocation):
    """
    Calculation a correction factor to X that will place Y as the nominal
    position.

    Args:
      machineLocation - Actual machine position.

    Returns:
      Corrected X value.
    """

    anchorPoint = self._anchorPoint.add(self._anchorOffset)

    # Compute various lengths.
    deltaX = machineLocation.x - anchorPoint.x
    deltaY = machineLocation.y - anchorPoint.y

    if deltaX > 0:
      x = machineLocation.x + self._machineCalibration.headArmLength
    else:
      x = machineLocation.x - self._machineCalibration.headArmLength

    rollerX = deltaY**2
    rollerX /= deltaX**2
    rollerX += 1
    rollerX = math.sqrt(rollerX)
    rollerX *= self._machineCalibration.headRollerRadius
    rollerX -= self._machineCalibration.headRollerRadius
    rollerX -= self._machineCalibration.headRollerGap / 2
    rollerX *= deltaX / abs(deltaY)

    x += rollerX

    return x

  # ---------------------------------------------------------------------
  def _transferCorrect(self, machineLocation, zDesired, direction):
    """
    Calculate correction for a transfer.

    Args:
      machineLocation - Target machine position.
      zDesired - Where Z will ultimately end.
      direction - Direction for pin diameter compensation (1/-1/0).

    Returns:
      Array with correction values for x, and y (in that order).

    Notes:
      This happens when doing hand-offs from side to side.  The anchor point
      causes a slight angle in the wire path, and X or Y need to be adjusted to
      compensate.

      There are three Z positions: anchor point, target, and desired.  Both the
      anchor point and target Z positions are either level front or back side of
      the current layer with one always opposite the other.  The desired Z will
      be the fully extended/retracted for the target side.
    """
    radius = self._machineCalibration.pinDiameter / 2
    radius *= direction
    offset = Location(radius, radius)
    anchorPoint = self._anchorPoint.add(offset)

    deltaX = machineLocation.x - anchorPoint.x
    deltaY = machineLocation.y - anchorPoint.y
    deltaZ = machineLocation.z - anchorPoint.z

    travelZ = abs(zDesired - anchorPoint.z)
    lengthXZ = math.sqrt(deltaX**2 + deltaZ**2)
    lengthYZ = math.sqrt(deltaY**2 + deltaZ**2)

    x = anchorPoint.x
    y = anchorPoint.y

    if 0 != lengthXZ:
      xCorrection = travelZ * deltaX / lengthXZ
      x += xCorrection

    if 0 != lengthYZ:
      yCorrection = travelZ * deltaY / lengthYZ
      y += yCorrection

    return [x, y]

  # ---------------------------------------------------------------------
  def transferCorrectX(self, machineLocation, zDesired, direction):
    """
    Calculate correction to X for a transfer.

    Args:
      machineLocation - Target machine position.
      zDesired - Where Z will ultimately end.
      direction - Direction for pin diameter compensation (1/-1/0).

    Returns:
      Corrected X value.
    """
    [x, y] = self._transferCorrect(machineLocation, zDesired, direction)

    return x

  # ---------------------------------------------------------------------
  def transferCorrectY(self, machineLocation, zDesired, direction):
    """
    Calculate correction to Y for a transfer.

    Args:
      machineLocation - Target machine position.
      zDesired - Where Z will ultimately end.
      direction - Direction for pin diameter compensation (1/-1/0).

    Returns:
      Corrected Y value.
    """
    [x, y] = self._transferCorrect(machineLocation, zDesired, direction)

    return y


# end class


if __name__ == "__main__":
  from .MachineCalibration import MachineCalibration

  # Make up a calibration setup for all tests.
  machineCalibration = MachineCalibration()
  machineCalibration.headArmLength = 125
  machineCalibration.headRollerRadius = 6.35
  machineCalibration.headRollerGap = 1.27
  machineCalibration.pinDiameter = 2.43

  # Setup instance of compensation.
  headCompensation = HeadCompensation(machineCalibration)

  #
  # Above and to the right.
  # Values come from spreadsheet "2016-09-15 -- Roller correction worksheet",
  # on sheet "Head_X+++" and "Head_Y+++"
  #

  # Setup test values.
  anchorPoint = Location(6581.6559158273, 113.186368912, 174.15)
  machinePosition = Location(6363.6442868365, 4, 0)
  headCompensation.anchorPoint(anchorPoint)

  # Run tests.
  correctX = headCompensation.correctX(machinePosition)
  correctY = headCompensation.correctY(machinePosition)
  correctedPositionX = machinePosition.copy(x=correctX)
  correctedPositionY = machinePosition.copy(y=correctY)
  headAngleX = headCompensation.getHeadAngle(correctedPositionX)
  headAngleY = headCompensation.getHeadAngle(correctedPositionY)
  wireX = headCompensation.getActualLocation(correctedPositionX)
  wireY = headCompensation.getActualLocation(correctedPositionY)

  desiredCorrectX = 6238.4109348003
  desiredCorrectY = 66.7203926635

  desiredHeadAngleX = -116.9015774072 / 180 * math.pi
  desiredHeadAngleY = -128.6182306977 / 180 * math.pi
  desiredWireX = Location(6352.0774120067, 5.1306535219, 57.6702300097)
  # desiredWireY = Location(  )

  assert MathExtra.isclose(desiredCorrectX, correctX)
  assert MathExtra.isclose(desiredCorrectY, correctY)
  assert MathExtra.isclose(desiredHeadAngleX, headAngleX)
  assert MathExtra.isclose(desiredHeadAngleY, headAngleY)
  assert desiredWireX == wireX

  #
  # Pin compensation.
  # Values come from spreadsheet "2016-08-25 -- Tangent circle worksheet".
  #

  # Setup test values.
  anchorPoint = Location(588.274, 170.594)
  targetPosition = Location(598.483, 166.131)
  headCompensation.anchorPoint(anchorPoint)
  headCompensation.orientation("TR")

  newTarget = headCompensation.pinCompensation(targetPosition)
  desiredTarget = Location(588.8791774069, 171.6475584019)

  assert newTarget == desiredTarget
