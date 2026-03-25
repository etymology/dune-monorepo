###############################################################################
# Name: Head.py
# Uses: Handling the passing around of the head via Z-axis.
# Date: 2016-04-18
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import time

from dune_winder.io.controllers.plc_logic import PLC_Logic


class Head:
  class States:
    # Continuous states.
    IDLE = 0  # head is latched on one side, z retracted, done with moves
    SEEKING_TO_FINAL_POSITION = 1  # moving to final z position
    PRE_LATCHING = 2  # pulsing latch until actuator reaches transfer-safe 2
    EXTENDING_TO_TRANSFER = 3  # waiting for z extension before transfer latch
    LATCHING = 4  # waiting for latch pulses / actuator movement
    ERROR = 5  # local latch timeout or other head-only failure

  # end class

  HEAD_ABSENT = -1
  STAGE_SIDE = 0
  LEVEL_A_SIDE = 1
  LEVEL_B_SIDE = 2
  FIXED_SIDE = 3

  # ---------------------------------------------------------------------
  @staticmethod
  def _enumName(enumClass, value):
    for name, enumValue in vars(enumClass).items():
      if name.startswith("_"):
        continue
      if enumValue == value:
        return name
    return "UNKNOWN(" + str(value) + ")"

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
    self._stageLatchedTag = self._plcLogic._zStageLatchedBit
    self._fixedLatchedTag = self._plcLogic._zFixedLatchedBit
    self._stagePresentTag = self._plcLogic._zStagePresentBit
    self._fixedPresentTag = self._plcLogic._zFixedPresentBit
    self._actuatorPosTag = self._plcLogic._actuatorPosition
    self._zPosTag = self._plcLogic._zAxis._position
    self._velocity = 300
    self._headState = self.States.IDLE
    self._headPositionTarget = -1  # STAGE_SIDE/LEVEL_A_SIDE/LEVEL_B_SIDE/EXTENDED
    self._headZTarget = -1  # position in mm
    self._headLatchTarget = -1  # STAGE_SIDE or FIXED_SIDE
    self._latchRetryIntervalSeconds = 1
    self._latchTimeoutSeconds = 10.0
    self._latchSafeExtendedZThreshold = 400.0
    self._latchStateStartedAt = None
    self._nextLatchPulseAt = None
    self._latchWaitActuatorPos = None
    self._preLatchZTarget = None
    self._preLatchNextState = None
    self._clock = time.monotonic
    self._headErrorMessage = ""

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
    self._headErrorMessage = ""
    self._resetLatchRetryState()

  def setLatchTiming(self, retry_interval_seconds, timeout_seconds):
    """
    Configure local latch retry timing.
    """
    retryInterval = float(retry_interval_seconds)
    timeout = float(timeout_seconds)
    if retryInterval <= 0:
      raise ValueError("Latch retry interval must be positive.")
    if timeout <= 0:
      raise ValueError("Latch timeout must be positive.")
    self._latchRetryIntervalSeconds = retryInterval
    self._latchTimeoutSeconds = timeout

  def _resetLatchRetryState(self):
    """
    Clear local latch retry bookkeeping.
    """
    self._latchStateStartedAt = None
    self._nextLatchPulseAt = None
    self._latchWaitActuatorPos = None
    self._preLatchZTarget = None
    self._preLatchNextState = None

  def _startLatchingState(self):
    """
    Initialize local latch retry bookkeeping.
    """
    now = self._clock()
    self._latchStateStartedAt = now
    self._nextLatchPulseAt = now
    self._latchWaitActuatorPos = int(self._actuatorPosTag.get())

  def _setLatchError(self, message):
    """
    Put the head controller into a local error state.
    """
    print("DEBUG: " + str(message))
    self._resetLatchRetryState()
    self._headErrorMessage = str(message)
    self._headState = self.States.ERROR

  # ---------------------------------------------------------------------
  def getState(self):
    """
    Return the current local head-controller state value.
    """
    return self._headState

  # ---------------------------------------------------------------------
  def getStateName(self):
    """
    Return the current local head-controller state name.
    """
    return self._enumName(self.States, self._headState)

  # ---------------------------------------------------------------------
  def getReadinessBlocker(self):
    """
    Return structured detail describing why the head controller is not ready.
    """
    self.update()
    if self._headState == self.States.IDLE:
      return None

    blocker = {
      "state": self.getStateName(),
      "transfer": self._readTransferState(),
    }

    if self._headPositionTarget != -1:
      blocker["positionTarget"] = int(self._headPositionTarget)
    if self._headLatchTarget != -1:
      blocker["latchTarget"] = int(self._headLatchTarget)
    if self._headZTarget != -1:
      blocker["zTarget"] = float(self._headZTarget)
    if self._headErrorMessage:
      blocker["errorMessage"] = self._headErrorMessage

    return blocker

  def _readTransferState(self):
    """
    Read the raw PLC tags that define head transfer state.
    """
    return {
      "stagePresent": bool(self._stagePresentTag.get()),
      "fixedPresent": bool(self._fixedPresentTag.get()),
      "stageLatched": bool(self._stageLatchedTag.get()),
      "fixedLatched": bool(self._fixedLatchedTag.get()),
      "actuatorPos": int(self._actuatorPosTag.get()),
    }

  def _getCurrentSide(self):
    """
    Resolve which side the head is logically on from the raw PLC tags.

    Returns:
      STAGE_SIDE, FIXED_SIDE, or HEAD_ABSENT when neither final-side state is
      currently satisfied.
    """
    state = self._readTransferState()

    if not state["stagePresent"] and not state["fixedPresent"]:
      return self.HEAD_ABSENT

    if self._getCurrentTransferSide(
      state
    ) == self.FIXED_SIDE and self._isFixedFinalState(state):
      return self.FIXED_SIDE

    if self._getCurrentTransferSide(
      state
    ) == self.STAGE_SIDE and self._isStageFinalState(state):
      return self.STAGE_SIDE

    return self.HEAD_ABSENT

  def _getCurrentTransferSide(self, state):
    """
    Resolve which side currently holds the head, even if the latch is not yet
    in its final command-complete actuator position.
    """
    if not state["stagePresent"] and not state["fixedPresent"]:
      return self.HEAD_ABSENT

    if state["fixedPresent"] and state["fixedLatched"] and not state["stageLatched"]:
      return self.FIXED_SIDE

    if state["stagePresent"] and state["stageLatched"] and not state["fixedLatched"]:
      return self.STAGE_SIDE

    return self.HEAD_ABSENT

  def _isStageFinalState(self, state):
    """
    Final stable state for P0 / P1 / P2.
    """
    return (
      state["stagePresent"]
      and state["stageLatched"]
      and not state["fixedLatched"]
      and state["actuatorPos"] == 1
    )

  def _isFixedFinalState(self, state):
    """
    Final stable state for P3.
    """
    return (
      state["fixedPresent"]
      and state["fixedLatched"]
      and not state["stageLatched"]
      and state["actuatorPos"] == 2
    )

  def _isTransferLatchTargetReached(self):
    """
    Check whether the transfer latch phase has reached the requested side.
    """
    state = self._readTransferState()

    if self._headLatchTarget == self.FIXED_SIDE:
      return self._isFixedFinalState(state)

    if self._headLatchTarget == self.STAGE_SIDE:
      return (
        state["stagePresent"]
        and state["stageLatched"]
        and not state["fixedLatched"]
        and state["actuatorPos"] == 2
      )

    raise ValueError("Unknown head latch target: " + str(self._headLatchTarget))

  def _isFinalTargetStateReached(self):
    """
    Check whether the requested G106 target has reached its final state.
    """
    state = self._readTransferState()

    if self._headPositionTarget in (
      self.STAGE_SIDE,
      self.LEVEL_A_SIDE,
      self.LEVEL_B_SIDE,
    ):
      return self._isStageFinalState(state)

    if self._headPositionTarget == self.FIXED_SIDE:
      return self._isFixedFinalState(state)

    raise ValueError("Unknown head position target: " + str(self._headPositionTarget))

  def _isPreLatchTransferPositionReached(self, state):
    """
    Check whether the latch is in actuator position 2, which is required before
    extending Z for transfer when the stage is not present.
    """
    return int(state["actuatorPos"]) == 2

  def _requiresActuatorTwoBeforeZMove(self, target_z, state):
    """
    Any head-controlled Z move above the extension threshold must be issued
    with the fixed latch already sitting in actuator position 2.
    """
    return (
      float(target_z) > self._latchSafeExtendedZThreshold
      and state["fixedLatched"]
      and int(state["actuatorPos"]) != 2
    )

  def _startPreLatchingForZMove(self, target_z, next_state):
    """
    Enter the local pre-latch loop before a high-extension Z move.
    """
    self._preLatchZTarget = float(target_z)
    self._preLatchNextState = next_state
    self._startLatchingState()
    self._headState = self.States.PRE_LATCHING
    self._updatePreLatchingState()

  def _commandZMove(self, target_z, next_state):
    """
    Issue a Z move immediately, or pre-latch first if that is required.
    """
    state = self._readTransferState()
    if self._requiresActuatorTwoBeforeZMove(target_z, state):
      self._startPreLatchingForZMove(target_z, next_state)
      return

    self._plcLogic.setZ_Position(target_z, self._velocity)
    self._headState = next_state

  def _updatePreLatchingState(self):
    """
    Pulse the latch until actuator position 2 is reached, then issue the
    queued high-extension Z move.
    """
    state = self._readTransferState()

    if self._isPreLatchTransferPositionReached(state):
      targetZ = self._preLatchZTarget
      nextState = self._preLatchNextState
      self._resetLatchRetryState()
      self._plcLogic.setZ_Position(targetZ, self._velocity)
      self._headState = nextState
      return

    if self._latchStateStartedAt is None:
      self._startLatchingState()

    now = self._clock()
    if now - self._latchStateStartedAt >= self._latchTimeoutSeconds:
      self._setLatchError("Pre-latch transfer positioning timed out")
      return

    if state["actuatorPos"] != self._latchWaitActuatorPos:
      self._latchWaitActuatorPos = state["actuatorPos"]
      self._nextLatchPulseAt = now
      if self._isPreLatchTransferPositionReached(state):
        targetZ = self._preLatchZTarget
        nextState = self._preLatchNextState
        self._resetLatchRetryState()
        self._plcLogic.setZ_Position(targetZ, self._velocity)
        self._headState = nextState
        return

    if self._nextLatchPulseAt is not None and now < self._nextLatchPulseAt:
      return

    pulseSent = self._plcLogic.move_latch()
    self._nextLatchPulseAt = now + self._latchRetryIntervalSeconds
    if pulseSent:
      return

  def _updateLatchingState(self):
    """
    Drive the pulse-and-wait latch loop until the transfer target is reached.
    """
    state = self._readTransferState()

    if self._isTransferLatchTargetReached():
      self._resetLatchRetryState()
      self._plcLogic.setZ_Position(self._headZTarget, self._velocity)
      self._headState = self.States.SEEKING_TO_FINAL_POSITION
      return

    if self._latchStateStartedAt is None:
      self._startLatchingState()

    now = self._clock()
    if now - self._latchStateStartedAt >= self._latchTimeoutSeconds:
      self._setLatchError("Latch transfer timed out")
      return

    if state["actuatorPos"] != self._latchWaitActuatorPos:
      self._latchWaitActuatorPos = state["actuatorPos"]
      self._nextLatchPulseAt = now
      if self._isTransferLatchTargetReached():
        self._resetLatchRetryState()
        self._plcLogic.setZ_Position(self._headZTarget, self._velocity)
        self._headState = self.States.SEEKING_TO_FINAL_POSITION
        return

    if self._nextLatchPulseAt is not None and now < self._nextLatchPulseAt:
      return

    pulseSent = self._plcLogic.move_latch()
    if pulseSent:
      self._nextLatchPulseAt = now + self._latchRetryIntervalSeconds
    else:
      # Retry later, but never pulse while the transfer-present interlock is false.
      self._nextLatchPulseAt = now + self._latchRetryIntervalSeconds

  def update(self):
    """
    Update state machine logic.
    """

    if self._headState == self.States.IDLE:
      # Do nothing.
      pass
    elif self._headState == self.States.ERROR:
      # Wait for an explicit clear/reset via stop() or a new command.
      pass
    elif self._plcLogic.isError():
      # PLC hit an error mid-transfer; abort the queued sequence so that the
      # next command doesn't try to continue (e.g. latch before extending).
      self.clearQueuedTransfer()
    elif self._headState == self.States.SEEKING_TO_FINAL_POSITION:
      # This is the final seek to the target position.
      if self._plcLogic.isReady() and self._isFinalTargetStateReached():
        self._headState = self.States.IDLE
    elif self._headState == self.States.PRE_LATCHING:
      self._updatePreLatchingState()
    elif self._headState == self.States.EXTENDING_TO_TRANSFER:
      if self._plcLogic.isReady():
        # We are in position to start the pulse-and-wait latch loop now.
        self._startLatchingState()
        self._headState = self.States.LATCHING
        self._updateLatchingState()
    elif self._headState == self.States.LATCHING:
      self._updateLatchingState()
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

    currentTransferState = self._readTransferState()
    currentHeadSide = self._getCurrentTransferSide(currentTransferState)

    # If neither side reports head present, there is nothing to move.
    if (
      not currentTransferState["stagePresent"]
      and not currentTransferState["fixedPresent"]
    ):
      print("DEBUG: Head not present, skipping G106 command")
      return False

    # Ignore commands while the raw tags do not resolve to a stable side.
    if currentHeadSide == self.HEAD_ABSENT:
      print("DEBUG: Head state unresolved, skipping G106 command")
      return False

    target_lookup = {
      self.STAGE_SIDE: (self._retracted_z_position, self.STAGE_SIDE),
      self.LEVEL_A_SIDE: (self._front_z_position, self.STAGE_SIDE),
      self.LEVEL_B_SIDE: (self._back_z_position, self.STAGE_SIDE),
      self.FIXED_SIDE: (self._retracted_z_position, self.FIXED_SIDE),
    }
    # set the target z position and latch side
    if head_position_target not in target_lookup:
      raise ValueError("Unknown head position request: " + str(head_position_target))
    else:
      self._headZTarget, self._headLatchTarget = target_lookup[head_position_target]

    if self._headZTarget is None:
      raise ValueError("Unknown head position request: " + str(head_position_target))

    if self._headLatchTarget != currentHeadSide:
      # head is not latched to the side we want
      self._commandZMove(self._extended_z_position, self.States.EXTENDING_TO_TRANSFER)
    else:
      # otherwise just move the z axis to the target position
      self._commandZMove(self._headZTarget, self.States.SEEKING_TO_FINAL_POSITION)

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
    return self.readCurrentPosition()

  def readCurrentPosition(self):
    """
    Poll the PLC to determine the current logical head position.

    Reads the raw transfer tags directly and, when on the stage side, uses the
    current Z axis position to distinguish STAGE_SIDE / LEVEL_A_SIDE /
    LEVEL_B_SIDE.

    Returns:
      STAGE_SIDE / LEVEL_A_SIDE / LEVEL_B_SIDE / FIXED_SIDE, or HEAD_ABSENT
      if the head is not latched to either side.
    """
    side = self._getCurrentSide()
    if side == self.HEAD_ABSENT:
      return self.HEAD_ABSENT
    if side == self.FIXED_SIDE:
      return self.FIXED_SIDE
    # On the stage side; use Z to distinguish 0 / 1 / 2.
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
