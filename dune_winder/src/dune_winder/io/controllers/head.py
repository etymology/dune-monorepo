###############################################################################
# Name: Head.py
# Uses: Handling the passing around of the head via Z-axis.
# Date: 2016-04-18
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
from dune_winder.io.controllers.plc_logic import PLC_Logic


class Head:
  class States:
    # Continuous states.
    IDLE = 0  # head is latched on one side, z retracted, done with moves
    SEEKING_TO_FINAL_POSITION = 1  # moving to final z position
    EXTENDING_TO_TRANSFER = 2  # latching to transfer
    LATCHING = 3  # latching to transfer

  # end class

  HEAD_ABSENT = -1
  STAGE_SIDE = 0
  LEVEL_A_SIDE = 1
  LEVEL_B_SIDE = 2
  FIXED_SIDE = 3

  def __init__(self, plcLogic: PLC_Logic):
    """
    Constructor.

    Args:
      plcLogic: Instance of PLC_Logic.
    """
    self._plcLogic = plcLogic
    self._extended_z_position = 418
    self._retracted_z_position = 0
    self._front_z_position = 150
    self._back_z_position = 250
    self._headLatchStateTag = self._plcLogic._headLatchState
    self._zPosTag = self._plcLogic._zAxis._position
    self._velocity = 300
    self._headState = self.States.IDLE
    self._headPositionTarget = -1  # STAGE_SIDE/LEVEL_A_SIDE/LEVEL_B_SIDE/EXTENDED
    self._headZTarget = -1  # position in mm
    self._headLatchTarget = -1  # 0 or 3

  def isReady(self):
    """
    See if state head is idle (i.e. not in a state of motion).  Make sure
    this is True before requesting a move.

    Returns:
      True if not in motion, False if not.
    """
    # update the state machine first
    self.update()

    return self.States.IDLE == self._headState

  def clearQueuedTransfer(self):
    """
    Clear any queued multi-step transfer sequence.

    This is a local state-machine reset only. It intentionally does not issue
    additional PLC commands.
    """
    self._headState = self.States.IDLE

  def update(self):
    """
    Update state machine logic.
    """

    if self._headState == self.States.IDLE:
      # Do nothing.
      pass
    elif self._plcLogic.isError():
      # PLC hit an error mid-transfer; abort the queued sequence so that the
      # next command doesn't try to continue (e.g. latch before extending).
      self.clearQueuedTransfer()
    elif self._headState == self.States.SEEKING_TO_FINAL_POSITION:
      # This is the final seek to the target position.
      if self._plcLogic.isReady():
        self._headState = self.States.IDLE
    elif self._headState == self.States.EXTENDING_TO_TRANSFER:
      if self._plcLogic.isReady():
        # we are in a position to latch now
        self._plcLogic.move_latch()
        self._headState = self.States.LATCHING
    elif self._headState == self.States.LATCHING:
      if self._plcLogic.isReady():
        # we completed a latching move
        if self._headLatchStateTag.get() != self._headLatchTarget:
          self._plcLogic.move_latch()
          self._headState = self.States.LATCHING
        else:
          self._plcLogic.setZ_Position(self._headZTarget, self._velocity) # finished latching
          self._headState = self.States.SEEKING_TO_FINAL_POSITION
    else:
      raise ValueError("Unknown head state: " + str(self._headState))

  def setHeadPosition(self, head_position_target: int, velocity):
    """
    Set the head position.

    Args:
      position: STAGE_SIDE/LEVEL_A_SIDE/LEVEL_B_SIDE/EXTENDED.
      velocity: Max travel velocity.

    """

    self._headPositionTarget = head_position_target
    self._velocity = velocity
    self.clearQueuedTransfer()

    currentHeadLatchState = self._plcLogic._headLatchState.get()  # 0, 3 or -1

    # if the head is not latched to either side, do nothing
    if currentHeadLatchState == -1:
      print("DEBUG: Head not present, skipping G106 command")
      return False

    target_lookup = {
      self.STAGE_SIDE: (self._retracted_z_position, 0),
      self.LEVEL_A_SIDE: (self._front_z_position, 0),
      self.LEVEL_B_SIDE: (self._back_z_position, 0),
      self.FIXED_SIDE: (self._retracted_z_position, 3),
    }
    # set the target z position and latch side
    if head_position_target not in target_lookup:
      raise ValueError("Unknown head position request: " + str(head_position_target))
    else:
      self._headZTarget, self._headLatchTarget = target_lookup[head_position_target]

    if self._headZTarget is None:
      raise ValueError("Unknown head position request: " + str(head_position_target))

    if self._headLatchTarget != currentHeadLatchState:
      # head is not latched to the side we want
      self._plcLogic.setZ_Position(self._extended_z_position, self._velocity)
      # extend the head to transfer
      self._headState = self.States.EXTENDING_TO_TRANSFER
    else:
      # otherwise just move the z axis to the target position
      self._plcLogic.setZ_Position(self._headZTarget, self._velocity)
      self._headState = self.States.SEEKING_TO_FINAL_POSITION

    return False

  def setFrontAndBack(self, front, back):
    """
    Set the front and back locations (i.e. locations to put head level with
    the current layer).

    Args:
      front: Z-location to make head level with current layer on front side.
      back: Z-location to make head level with current layer on back side.
    """
    self._front_z_position = front
    self._back_z_position = back

  def setExtendedAndRetracted(self, retracted, extended):
    """
    Set the extended and retracted position for the Z-axis.

    Args:
      retracted: Z-position for fully retracted.
      extended: Z-position for fully extended (i.e. ready to latch).
    """
    self._extended_z_position = extended
    self._retracted_z_position = retracted

  def getPosition(self):
    """
    Get the current position of the head.

    Returns:
      STAGE_SIDE/LEVEL_A_SIDE/LEVEL_B_SIDE/EXTENDED.
    """
    return self._headLatchStateTag.get()

  def readCurrentPosition(self):
    """
    Poll the PLC to determine the current logical head position.

    Reads the latch state and, when on the stage side (latch=0), uses the
    current Z axis position to distinguish STAGE_SIDE / LEVEL_A_SIDE /
    LEVEL_B_SIDE.

    Returns:
      STAGE_SIDE / LEVEL_A_SIDE / LEVEL_B_SIDE / FIXED_SIDE, or HEAD_ABSENT
      if the head is not latched to either side.
    """
    latch = self._headLatchStateTag.get()
    if latch == self.HEAD_ABSENT:
      return self.HEAD_ABSENT
    if latch == 3:
      return self.FIXED_SIDE
    # latch == 0: on the stage side; use Z to distinguish 0 / 1 / 2
    z = self._zPosTag.get()
    candidates = {
      self.STAGE_SIDE: self._retracted_z_position,
      self.LEVEL_A_SIDE: self._front_z_position,
      self.LEVEL_B_SIDE: self._back_z_position,
    }
    return min(candidates, key=lambda p: abs(candidates[p] - z))

  def getTargetAxisPosition(self):
    """
    Get the target location of head axis.

    Returns:
      Target location of head axis.
    """
    return self._headZTarget

  def stop(self):
    """
    Stop/abort transfer.
    """

    # If in transition...
    if self.States.IDLE != self._headState:
      # If Z axis is in motion, stop it.
      if self.States.SEEKING_TO_FINAL_POSITION == self._headState:
        self._plcLogic.stopSeek()

      # Idle the state machine.
      self.clearQueuedTransfer()


# end class
