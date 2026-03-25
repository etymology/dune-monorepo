###############################################################################
# Name: PLC_Logic.py
# Uses: Interface for special logic inside PLC.
# Date: 2016-02-26
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   This unit is designed to work with specific PLC logic.  It handles how
#   operations must be preformed for the given setup, such as how to initiate
#   a synchronized X/Y movement, or other multi-step operation.  The scope of
#   this unit is limited to operations performed by the ladder logic in the
#   PLC.  No operation that isn't specific to the ladder logic should be in
#   this unit.
###################################################>############################
from dune_winder.io.devices.plc import PLC
from dune_winder.io.primitives.multi_axis_motor import MultiAxisMotor
from dune_winder.io.primitives.plc_motor import PLC_Motor
from dune_winder.queued_motion.plc_interface import QueuedMotionPLCInterface


class PLC_Logic:
  # States for primary state machine.
  class States:
    INIT = 0
    READY = 1
    XY_JOG = 2
    XY_SEEK = 3
    Z_JOG = 4
    Z_SEEK = 5
    LATCHING = 6
    LATCH_HOMEING = 7
    LATCH_RELEASE = 8
    UNSERVO = 9
    ERROR = 10
    EOT = 11
    XZ_SEEK = 12
    QUEUED_MOTION = 13

  # end class

  # States for move type state machine.
  class MoveTypes:
    RESET = 0
    JOG_XY = 1
    SEEK_XY = 2
    JOG_Z = 3
    SEEK_Z = 4
    LATCH = 5
    HOME_LATCH = 6
    LATCH_UNLOCK = 7
    UNSERVO = 8
    PLC_INIT = 9
    SEEK_XZ = 10

  # end class

  class LatchPosition:
    FULL_UP = 0
    PARTIAL_UP = 1
    DOWN = 2

  # end class

  # Lookup table of error code names.
  ERROR_CODES = {
    0: "None",
    1001: "Rotation lock missing",
    2001: "XY Jog, Z is extended",
    2002: "Physical X or Y axis fault",
    3001: "XY Seek, Z is extended",
    3002: "Physical X or Y axis fault",
    3003: "Motion complete, but position is incorrect",
    3004: "Emergency stop - STO active",
    4001: "Z Jog, Master Z Transfer Enable Not Ready",
    4002: "Physical Z axis fault",
    4003: "Latch not in position 2 when retrieving winder head",
    5001: "Z Seek, Master Z Transfer Enable Not Ready",
    5002: "Physical Z axis fault",
    5003: "Motion complete, but position is incorrect",
    5004: "Latch not in position 2 when retrieving winder head",
    6000: "Latching State Successful",
    6001: "Latching State, Z Stage not present OR Z Fixed not Present OR Z Not Extended",
    6002: "Latching State, Latch did not move to next position",
    7000: "Homing Latch State Successful",
    7001: "Homing Latch State, Z Stage Not Present",
    7002: "Homing Latch State, Latch did not move to home position",
    8000: "Unlock Latch Motor Successful",
    8001: "Wire broke",
    8002: "Wire over-tensioned",
  }

  # ---------------------------------------------------------------------
  def isReady(self):
    """
    Check to see if the PLC is in a ready state.  This can be used to determine
    if all motion has completed, including all motor motion and latching
    operations.

    Returns:
      True if ready, False if some other operation is taking place.
    """
    state = self._state.get()

    if self.States.READY == state:
      result = True
    else:
      result = False

    return result

  # ---------------------------------------------------------------------
  def isError(self):
    """
    Check to see if PLC state machine is in error.

    Returns:
      True if in error, False if not.
    """

    return self.States.ERROR == self._state.get()

  # ---------------------------------------------------------------------
  def stopSeek(self):
    """
    Stop all motor position seeks.
    """
    # self._moveType.set( self.MoveTypes.RESET )
    self._maxXY_Velocity.set(0)
    self._maxZ_Velocity.set(0)
    try:
      self.queuedMotion.poll()
      if not self.queuedMotion.status().is_idle:
        self.queuedMotion.set_stop_request(True)
    except Exception:
      pass

  # ---------------------------------------------------------------------
  def setXY_Position(self, x, y, velocity=None, acceleration=None, deceleration=None):
    """
    Make a coordinated move of the X/Y axis.

    Args:
      x: Position to seek in x-axis (in millimeters).
      y: Position to seek in y-axis (in millimeters).
      velocity: Maximum velocity at which to make move.  None to use last
        velocity.
    """
    if velocity is not None:
      self._velocity = velocity

    if acceleration is not None:
      self._maxXY_Acceleration.set(float(acceleration))

    if deceleration is not None:
      self._maxXY_Deceleration.set(float(deceleration))

    self._maxXY_Velocity.set(self._velocity)
    self._xyAxis.setDesiredPosition([x, y])
    self._moveType.set(self.MoveTypes.SEEK_XY)

  # ---------------------------------------------------------------------
  def jogXY(self, xVelocity, yVelocity, acceleration=None, deceleration=None):
    """
    Jog the X/Y axis at a given velocity.

    Args:
      xVelocity: Speed of travel on x-axis.  0 for no motion or stop, negative
        for seeking in reverse direction.
      yVelocity: Speed of travel on y-axis.  0 for no motion or stop, negative
        for seeking in reverse direction.
    """

    if acceleration is not None:
      self._maxXY_Acceleration.set(float(acceleration))

    if deceleration is not None:
      self._maxXY_Deceleration.set(float(deceleration))

    self._xyAxis.setVelocity([xVelocity, yVelocity])
    self._moveType.set(self.MoveTypes.JOG_XY)

  # ---------------------------------------------------------------------
  def setZ_Position(self, position, velocity=None):
    """
    Move Z-axis to a position.

    Args:
      position: Position to seek in z-axis (in millimeters).
      velocity: Maximum velocity at which to make move.  None to use last
        velocity.
    """
    if velocity is not None:
      self._velocity = velocity

    self._zAxis.setVelocity(self._velocity)
    self._zAxis.setDesiredPosition(position)
    self._pulseMoveType(self.MoveTypes.SEEK_Z)

  # ---------------------------------------------------------------------
  def setXZ_Position(self, x, z, velocity=None):
    """
    Move in the X/Z plane using the PLC transfer-motion interface.

    Args:
      x: Position to seek in x-axis (in millimeters).
      z: Position to seek in z-axis (in millimeters).
      velocity: Reserved for interface compatibility. Ignored by the PLC
        transfer-motion command.
    """
    del velocity

    yTransferOk = self._readTagNow(self._yTransferOk)
    if not bool(yTransferOk):
      raise ValueError("Y_Transfer_OK must be true before issuing an XZ move.")

    self._xzPositionTarget.set([float(x), float(z)])
    self._moveType.set(self.MoveTypes.SEEK_XZ)

  # ---------------------------------------------------------------------
  def _readTagNow(self, tag):
    """
    Read a tag immediately without relying on cached poll state.

    Notes:
      Uses the PLC multi-read shape (`read([tag])`) so it works with the real
      PLC driver, whose single-tag path expects iterable tag names.
    """
    result = self._plc.read([tag.getName()])
    if result is None or self._plc.isNotFunctional():
      return tag.get()

    for entry in result:
      if not isinstance(entry, (list, tuple)) or len(entry) < 2:
        continue
      if str(entry[0]) != tag.getName():
        continue
      tag.updateFromReadTag(entry[1])
      return entry[1]

    return tag.get()

  # ---------------------------------------------------------------------
  def _writeTagNow(self, tagName, value):
    """
    Write a tag immediately and fail fast if the PLC rejects the write.
    """
    result = self._plc.write((str(tagName), value))
    if result is None:
      raise RuntimeError("Write failed for PLC tag " + str(tagName) + ".")
    return result

  # ---------------------------------------------------------------------
  def _pulseMoveType(self, moveType):
    """
    Force a clean MOVE_TYPE edge for ladder transitions out of READY.

    The PLC READY-state ladder uses one-shots on comparisons like
    `MOVE_TYPE = 4`; rewriting the same value does not retrigger those rungs.
    Pulsing through RESET guarantees a fresh false->true transition for each
    Z move request.
    """
    requested = int(moveType)
    self._writeTagNow(self._moveType.getName(), self.MoveTypes.RESET)
    self._moveType.updateFromReadTag(self.MoveTypes.RESET)
    self._writeTagNow(self._moveType.getName(), requested)
    self._moveType.updateFromReadTag(requested)

  # ---------------------------------------------------------------------
  def jogZ(self, velocity):
    """
    Jog the Z axis at a given velocity.

    Args:
      velocity: Speed of travel.  0 for no motion or stop, negative
        for seeking in reverse direction.
    """

    self._zAxis.setVelocity(velocity)
    self._pulseMoveType(self.MoveTypes.JOG_Z)

  # ---------------------------------------------------------------------
  def getLatchPosition(self):
    """
    Get the current latch position.

    Returns:
      One of the PLC_Logic.LatchPosition elements.
    """
    return self._actuatorPosition.get()

  def getHeadPosition(self):
    """
    Get the current head position.

    Returns:
      Current head position.
    """
    return self._actuatorPosition.get()

  # ---------------------------------------------------------------------
  def canMoveLatch(self):
    """
    Check whether the latch pulse interlock is currently satisfied.

    Returns:
      True if both stage and fixed present bits are set, False otherwise.
    """
    stagePresent = bool(self._readTagNow(self._zStagePresentBit))
    fixedPresent = bool(self._readTagNow(self._zFixedPresentBit))
    return (stagePresent and fixedPresent) or (not stagePresent)

  # ---------------------------------------------------------------------
  def move_latch(self):
    """
    Pulse the GUI latch command.

    Returns:
      True if the pulse was sent, False if the transfer-present interlock is
      not satisfied.
    """
    if not self.canMoveLatch():
      return False

    self._writeTagNow(self._guiLatchPulse.getName(), 1)
    self._guiLatchPulse.updateFromReadTag(1)
    return True

  # ---------------------------------------------------------------------
  def poll(self):
    """
    Internal update. Call periodically.
    """
    PLC.Tag.pollAll(self._plc)

  # ---------------------------------------------------------------------
  def getMoveType(self):
    """
    Return the move type tag value.

    Returns:
      Move type tag value, number from PLC_Logic.MoveTypes.
    """
    return self._moveType.get()

  # ---------------------------------------------------------------------
  def getState(self):
    """
    Return the state tag value.

    Returns:
      State tag value, number from PLC_Logic.States.
    """
    return self._readTagNow(self._state)

  # ---------------------------------------------------------------------
  def reset(self):
    """
    Reset PLC logic.  Clears errors.
    """
    self._moveType.set(self.MoveTypes.RESET)

  # ---------------------------------------------------------------------
  # New function for PLC_Init - PWH - September 2021
  def PLC_init(self):
    """
    Initilize PLC logic.
    """

    self._moveType.set(self.MoveTypes.PLC_INIT)

  # ---------------------------------------------------------------------

  def latchHome(self):
    """
    Start a latch homing operation.
    """
    self._moveType.set(self.MoveTypes.HOME_LATCH)

  # ---------------------------------------------------------------------
  def latchUnlock(self):
    """
    Unlock latch motor for manual operation.  Requires PLC_Logic.reset after
    complete.
    """
    self._moveType.set(self.MoveTypes.LATCH_UNLOCK)

  # ---------------------------------------------------------------------
  def maxVelocity(self, maxVelocity=None):
    """
    Set/get the maximum velocity.

    Args:
      maxVelocity: New maximum velocity (optional).

    Returns:
      Maximum velocity.
    """
    if maxVelocity is not None:
      self._velocity = maxVelocity

    self._maxXY_Velocity.set(self._velocity)

    return self._velocity

  # ---------------------------------------------------------------------
  def maxAcceleration(self, maxAcceleration=None):
    """
    Set/get the maximum positive acceleration.

    Args:
      maxVelocity: New maximum positive acceleration (optional).

    Returns:
      Maximum positive acceleration.
    """
    if maxAcceleration is not None:
      self._maxAcceleration = maxAcceleration

    self._maxXY_Acceleration.set(self._maxAcceleration)
    self._maxZ_Acceleration.set(self._maxAcceleration)

    return self._maxAcceleration

  # ---------------------------------------------------------------------
  def maxDeceleration(self, maxDeceleration=None):
    """
    Set/get the maximum negative acceleration.

    Args:
      maxVelocity: New maximum negative acceleration (optional).

    Returns:
      Maximum positive acceleration.
    """
    if maxDeceleration is not None:
      self._maxDeceleration = maxDeceleration

    self._maxXY_Deceleration.set(self._maxDeceleration)
    self._maxZ_Deceleration.set(self._maxDeceleration)

    return self._maxDeceleration

  # ---------------------------------------------------------------------
  def setupLimits(self, maxVelocity=None, maxAcceleration=None, maxDeceleration=None):
    """
    Setup the velocity and acceleration limits.

    Args:
      maxVelocity: Maximum velocity.
      maxAcceleration: Maximum positive acceleration.
      maxDeceleration: Maximum negative acceleration.
    """
    if maxVelocity is not None:
      self._velocity = maxVelocity

    if maxAcceleration is not None:
      self._maxAcceleration = maxAcceleration

    if maxDeceleration is not None:
      self._maxDeceleration = maxDeceleration

    self._maxXY_Velocity.set(self._velocity)
    self._maxXY_Acceleration.set(self._maxAcceleration)
    self._maxXY_Deceleration.set(self._maxDeceleration)
    self._maxZ_Acceleration.set(self._maxAcceleration)
    self._maxZ_Deceleration.set(self._maxDeceleration)

  # ---------------------------------------------------------------------
  def servoDisable(self):
    """
    Disable servo control of motors.
    """
    self._moveType.set(self.MoveTypes.UNSERVO)

  # ---------------------------------------------------------------------
  def getErrorCode(self):
    """
    Get the error code reported by PLC.
    (Use 'getErrorCodeString' to translate code into string.)

    Returns:
      Integer error code.
    """
    return self._errorCode.get()

  # ---------------------------------------------------------------------
  def getErrorCodeString(self):
    """
    Get the error code reported by PLC as a string.

    Returns:
      String representation of error code.
    """
    errorCode = self._errorCode.get()

    if errorCode in PLC_Logic.ERROR_CODES:
      result = PLC_Logic.ERROR_CODES[errorCode]
    else:
      result = "Unknown " + str(errorCode)

    return result

  # ---------------------------------------------------------------------
  def __init__(self, plc, xyAxis: MultiAxisMotor, zAxis: PLC_Motor):
    """
    Constructor.

    Args:
      plc: Instance of PLC.
      xyAxis: Instance of MultiAxisMotor for X/Y axis.
    """
    self._plc = plc
    self._xyAxis = xyAxis
    self._zAxis = zAxis
    self._latchPosition = 0

    attributes = PLC.Tag.Attributes()
    attributes.isPolled = True
    self._state = PLC.Tag(plc, "STATE", attributes, tagType="DINT")
    self._errorCode = PLC.Tag(plc, "ERROR_CODE", attributes, tagType="DINT")
    self._headLatchState = PLC.Tag(plc, "HEAD_POS", attributes, tagType="DINT")
    self._actuatorPosition = PLC.Tag(plc, "ACTUATOR_POS", attributes, tagType="DINT")
    self._moveType = PLC.Tag(plc, "MOVE_TYPE", attributes, tagType="INT")
    self._yTransferOk = PLC.Tag(plc, "Y_XFER_OK", attributes, tagType="DINT")

    machineStatus = PLC.Tag.Attributes()
    machineStatus.canWrite = False
    machineStatus.defaultValue = 0
    self._zStageLatchedBit = PLC.Tag(plc, "MACHINE_SW_STAT[6]", machineStatus)
    self._zFixedLatchedBit = PLC.Tag(plc, "MACHINE_SW_STAT[7]", machineStatus)
    self._zStagePresentBit = PLC.Tag(plc, "MACHINE_SW_STAT[9]", machineStatus)
    self._zFixedPresentBit = PLC.Tag(plc, "MACHINE_SW_STAT[10]", machineStatus)

    pulseAttributes = PLC.Tag.Attributes()
    pulseAttributes.defaultValue = 0
    self._guiLatchPulse = PLC.Tag(plc, "gui_latch_pulse", pulseAttributes, tagType="BOOL")

    self._maxXY_Velocity = PLC.Tag(plc, "XY_SPEED", tagType="REAL")
    self._maxXY_Acceleration = PLC.Tag(plc, "XY_ACCELERATION", tagType="REAL")
    self._maxXY_Deceleration = PLC.Tag(plc, "XY_DECELERATION", tagType="REAL")
    self._maxZ_Velocity = PLC.Tag(plc, "Z_SPEED", tagType="REAL")
    self._maxZ_Acceleration = PLC.Tag(plc, "Z_ACCELERATION", tagType="REAL")
    self._maxZ_Deceleration = PLC.Tag(plc, "Z_DECELLERATION", tagType="REAL")

    writeOnly = PLC.Tag.Attributes()
    writeOnly.canRead = False
    self._xzPositionTarget = PLC.Tag(
      plc, "xz_position_target", writeOnly, tagType="REAL[2]"
    )

    self._velocity = 0.0
    self._maxAcceleration = 0
    self._maxDeceleration = 0
    self.queuedMotion = QueuedMotionPLCInterface(plc)


# end class
