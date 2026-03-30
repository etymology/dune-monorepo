###############################################################################
# Name: PLC_Motor.py
# Uses: Motor on a PLC.
# Date: 2016-02-07
# Author(s):
#   Andrew Que <aque@bb7.com>
#
# $$$FUTURE - To-do:
#  - Accelerations.
#
###############################################################################

from dune_winder.io.primitives.motor import Motor
from dune_winder.io.devices.plc import PLC
from typing import List


class PLC_Motor(Motor):
  instances: List["PLC_Motor"] = []

  # ---------------------------------------------------------------------
  def __init__(self, name, plc, tagBase):
    """
    Constructor.

    Args:
      name: Name of motor.
      plc: Instance of IO_Device.PLC.
      tagBase: All tags will start with this prepended to the name.
    """

    Motor.__init__(self, name)
    PLC_Motor.instances.append(self)

    self._plc = plc
    self._tagBase = tagBase

    # Write tags.
    attributes = PLC.Tag.Attributes()
    attributes.defaultValue = 0
    self._targetPosition = PLC.Tag(plc, tagBase + "_POSITION", attributes, "REAL")
    self._jogSpeed = PLC.Tag(plc, tagBase + "_SPEED", attributes, "REAL")
    self._jogDirection = PLC.Tag(plc, tagBase + "_DIR", attributes, "DINT")

    # Read-only attributes tags.
    attributes = PLC.Tag.Attributes()
    attributes.isPolled = True
    attributes.canWrite = False

    self._position = PLC.Tag(plc, tagBase + "_axis.ActualPosition", attributes)
    self._velocity = PLC.Tag(plc, tagBase + "_axis.ActualVelocity", attributes)
    self._acceleration = PLC.Tag(plc, tagBase + "_axis.CommandAcceleration", attributes)
    self._movement = PLC.Tag(plc, tagBase + "_axis.CoordinatedMotionStatus", attributes)
    #    print(self._position)
    # Motor status tag defaults to a faulted state in case read fails.
    attributes = PLC.Tag.Attributes()
    attributes.isPolled = True
    attributes.canWrite = False
    attributes.defaultValue = True
    self._faulted = PLC.Tag(plc, tagBase + "_axis.ModuleFault", attributes)

    # print("self._faulted")
    # print(self._faulted.get())
    self._seekStartPosition = 0

  # ---------------------------------------------------------------------
  def isFunctional(self):
    """
    Check to see if motor is ready to run.

    Returns:
      True if functional, False if not.
    """

    # print("not bool(self._faulted.get()) in isFunctional PLC_Motor.py")
    # print(not bool(self._faulted.get()))
    return not bool(self._faulted.get())

  # ---------------------------------------------------------------------
  def setDesiredPosition(self, position):
    """
    Go to a location.

    Args:
      positions: Position to seek (in motor units).
    """
    self._seekStartPosition = self.getPosition()
    self._targetPosition.set(position)

  # ---------------------------------------------------------------------
  def getSeekStartPosition(self):
    """
    Get the position the current (or last) seek started from.

    Returns:
      Position the current (or last) seek started from.
    """
    return self._seekStartPosition

  # ---------------------------------------------------------------------
  def getDesiredPosition(self):
    """
    Return the desired (seeking) position.

    Returns:
      Desired motor position.
    """
    return self._targetPosition.get()

  # ---------------------------------------------------------------------
  def isSeeking(self):
    """
    See if the motor is in motion.

    Returns:
      True if seeking desired position, False if at desired position.
    """

    result = bool(self._movement.get())

    return result

  # ---------------------------------------------------------------------
  def getPosition(self):
    """
    Return current motor position.

    Returns:
      Motor position (in motor units).
    """

    return self._position.get()

  # ---------------------------------------------------------------------
  def setMaxVelocity(self, maxVelocity):
    """
    Set maximum velocity motor may move.

    Args:
      maxVelocity: Maximum velocity.

    """
    self._jogSpeed.set(maxVelocity)

  # ---------------------------------------------------------------------
  def getMaxVelocity(self):
    """
    Get maximum velocity motor may move.

    Args:
      maxVelocity: Maximum velocity.

    """

    return None

  # ---------------------------------------------------------------------
  def getVelocity(self):
    """
    Get current motor velocity.

    Returns:
      Current motor velocity (in motor units/second).
    """

    return self._velocity.get()

  # ---------------------------------------------------------------------
  def setVelocity(self, velocity):
    """
    Set motor velocity.  Useful for jogging motor.  Set to 0 to stop.

    Args:
      velocity: Desired velocity.  Negative velocity is reverse direction.
    """

    direction = 0
    if velocity < 0:
      direction = 1
      velocity = -velocity

    self._jogSpeed.set(velocity)
    self._jogDirection.set(direction)

  # ---------------------------------------------------------------------
  def setMaxAcceleration(self, maxAcceleration):
    """
    Set maximum acceleration motor may move.

    Args:
      maxAcceleration: Maximum acceleration motor may move.

    """

    pass

  # ---------------------------------------------------------------------
  def getMaxAcceleration(self):
    """
    Get maximum acceleration motor may move.

    Returns:
      Maximum acceleration motor may move.
    """

    pass

  # ---------------------------------------------------------------------
  def getAcceleration(self):
    """
    Get current motor acceleration.

    Returns:
      Motor acceleration (in motor units/second squared).
    """

    return self._acceleration.get()

  # ---------------------------------------------------------------------
  def poll(self):
    """
    Update motor.  Call periodically.  (Unneeded for this type of motor.)
    """
    pass


# end class
