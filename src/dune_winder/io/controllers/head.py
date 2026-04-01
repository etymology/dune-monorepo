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
    IDLE = 0
    SEEKING_TO_FINAL_POSITION = 1
    EXTENDING_TO_TRANSFER = 2
    LATCHING = 3
    ERROR = 4

  HEAD_ABSENT = -1
  STAGE_SIDE = 0
  LEVEL_A_SIDE = 1
  LEVEL_B_SIDE = 2
  FIXED_SIDE = 3

  _TRANSFER_MODE_LEGACY = "legacy"
  _TRANSFER_MODE_G206 = "g206"

  def __init__(self, plcLogic: PLC_Logic):
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
    self._headPositionTarget = -1
    self._headZTarget = -1
    self._headLatchTarget = -1
    self._latchRetryIntervalSeconds = 1
    self._latchTimeoutSeconds = 10.0
    self._latchStateStartedAt = None
    self._nextLatchPulseAt = None
    self._latchWaitActuatorPos = None
    self._clock = time.monotonic
    self._activeTransferMode = None
    self._lastError = ""
    self._g206Transitions = []
    self._g206TransitionIndex = 0
    self._g206PulseAttempts = 0
    self._g206SettleStartedAt = None
    self._g206SettleSeconds = 1.0
    self._g206MaxPulseAttempts = 5

  def isReady(self):
    self.update()
    return self.States.IDLE == self._headState

  def hasError(self):
    return self.States.ERROR == self._headState

  def getLastError(self):
    return self._lastError

  def clearQueuedTransfer(self):
    self._headState = self.States.IDLE
    self._activeTransferMode = None
    self._lastError = ""
    self._resetLatchRetryState()
    self._resetG206State()

  def setLatchTiming(self, retry_interval_seconds, timeout_seconds):
    retryInterval = float(retry_interval_seconds)
    timeout = float(timeout_seconds)
    if retryInterval <= 0:
      raise ValueError("Latch retry interval must be positive.")
    if timeout <= 0:
      raise ValueError("Latch timeout must be positive.")
    self._latchRetryIntervalSeconds = retryInterval
    self._latchTimeoutSeconds = timeout

  def _resetLatchRetryState(self):
    self._latchStateStartedAt = None
    self._nextLatchPulseAt = None
    self._latchWaitActuatorPos = None

  def _resetG206State(self):
    self._g206Transitions = []
    self._g206TransitionIndex = 0
    self._g206PulseAttempts = 0
    self._g206SettleStartedAt = None

  def _startLatchingState(self):
    now = self._clock()
    self._latchStateStartedAt = now
    self._nextLatchPulseAt = now
    self._latchWaitActuatorPos = int(self._actuatorPosTag.get())

  def _setHeadError(self, message):
    self._lastError = str(message)
    self._resetLatchRetryState()
    self._resetG206State()
    self._headState = self.States.ERROR

  def _setLatchError(self, message):
    self._setHeadError(message)

  def _readTransferState(self):
    return {
      "stagePresent": bool(self._stagePresentTag.get()),
      "fixedPresent": bool(self._fixedPresentTag.get()),
      "stageLatched": bool(self._stageLatchedTag.get()),
      "fixedLatched": bool(self._fixedLatchedTag.get()),
      "actuatorPos": int(self._actuatorPosTag.get()),
    }

  def _readTransferStateNow(self):
    if hasattr(self._plcLogic, "getTransferStateNow"):
      return self._plcLogic.getTransferStateNow()

    zPosition = float(self._zPosTag.get())
    stagePresent = bool(self._stagePresentTag.get())
    fixedPresent = bool(self._fixedPresentTag.get())
    zExtended = zPosition >= (self._extended_z_position - 1.0)
    return {
      "stagePresent": stagePresent,
      "fixedPresent": fixedPresent,
      "stageLatched": bool(self._stageLatchedTag.get()),
      "fixedLatched": bool(self._fixedLatchedTag.get()),
      "zExtended": zExtended,
      "enableActuator": stagePresent and fixedPresent and zExtended,
      "actuatorPos": int(self._actuatorPosTag.get()),
      "zPosition": zPosition,
    }

  def _getCurrentSide(self):
    state = self._readTransferState()

    if not state["stagePresent"] and not state["fixedPresent"]:
      return self.HEAD_ABSENT

    if self._isFixedSideState(state):
      return self.FIXED_SIDE

    if self._isStageSideState(state):
      return self.STAGE_SIDE

    return self.HEAD_ABSENT

  def _getCurrentTransferSide(self, state):
    if not state["stagePresent"] and not state["fixedPresent"]:
      return self.HEAD_ABSENT

    if self._isFixedSideState(state):
      return self.FIXED_SIDE

    if self._isStageSideState(state):
      return self.STAGE_SIDE

    return self.HEAD_ABSENT

  def _getCurrentStrictTransferSide(self, state):
    if not state["stagePresent"] and not state["fixedPresent"]:
      return self.HEAD_ABSENT

    if self._isStrictFixedSideState(state):
      return self.FIXED_SIDE

    if self._isStrictStageSideState(state):
      return self.STAGE_SIDE

    return self.HEAD_ABSENT

  def _isStageSideState(self, state):
    return (
      state["stagePresent"]
      and state["stageLatched"]
      and not state["fixedLatched"]
    )

  def _isFixedSideState(self, state):
    return (
      state["fixedPresent"]
      and state["fixedLatched"]
      and not state["stageLatched"]
    )

  def _isStrictStageSideState(self, state):
    return (
      state["stagePresent"]
      and state["stageLatched"]
      and not state["fixedLatched"]
      and int(state["actuatorPos"]) == 1
    )

  def _isStrictFixedSideState(self, state):
    return (
      state["fixedPresent"]
      and state["fixedLatched"]
      and not state["stageLatched"]
      and int(state["actuatorPos"]) == 2
    )

  def _isStrictIntermediateThreeState(self, state):
    return (
      state["stagePresent"]
      and state["fixedPresent"]
      and not state["stageLatched"]
      and not state["fixedLatched"]
      and int(state["actuatorPos"]) == 3
    )

  def _isTransferLatchTargetReached(self):
    state = self._readTransferState()

    if self._headLatchTarget == self.FIXED_SIDE:
      return self._isFixedSideState(state) and state["actuatorPos"] == 2

    if self._headLatchTarget == self.STAGE_SIDE:
      return self._isStageSideState(state) and state["actuatorPos"] == 2

    raise ValueError("Unknown head latch target: " + str(self._headLatchTarget))

  def _isFinalTargetStateReached(self):
    state = self._readTransferState()

    if self._headPositionTarget in (
      self.STAGE_SIDE,
      self.LEVEL_A_SIDE,
      self.LEVEL_B_SIDE,
    ):
      return self._isStageSideState(state)

    if self._headPositionTarget == self.FIXED_SIDE:
      return self._isFixedSideState(state)

    raise ValueError("Unknown head position target: " + str(self._headPositionTarget))

  def _isG206FinalTargetReached(self, state):
    if self._headPositionTarget == self.FIXED_SIDE:
      return (
        self._isStrictFixedSideState(state)
        and self._isCloseToTargetZ(state["zPosition"], self._retracted_z_position)
      )

    if self._headPositionTarget in (
      self.STAGE_SIDE,
      self.LEVEL_A_SIDE,
      self.LEVEL_B_SIDE,
    ):
      return (
        self._isStrictStageSideState(state)
        and self._isCloseToTargetZ(state["zPosition"], self._headZTarget)
      )

    return False

  def _isCloseToTargetZ(self, actual, target):
    return abs(float(actual) - float(target)) <= 1.0

  def _commandZMove(self, target_z, next_state):
    state = self._readTransferStateNow()
    if state["fixedLatched"] and int(state["actuatorPos"]) != 2:
      self._setHeadError("Cannot move Z while fixed-latched unless actuator is at position 2.")
      return False
    self._plcLogic.setZ_Position(target_z, self._velocity)
    self._headState = next_state
    return True

  def _updateLatchingState(self):
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
    self._nextLatchPulseAt = now + self._latchRetryIntervalSeconds
    if pulseSent:
      return

  def _commandNextG206Pulse(self):
    state = self._readTransferStateNow()
    transition = self._g206Transitions[self._g206TransitionIndex]

    if not bool(state["enableActuator"]):
      self._setHeadError("Cannot pulse latch unless ENABLE_ACTUATOR is true.")
      return

    if not self._isExpectedRetryState(state, transition["from"]):
      self._setHeadError("Latch transition entered an invalid state before pulsing.")
      return

    if self._g206PulseAttempts >= self._g206MaxPulseAttempts:
      self._setHeadError("Latch transition failed after 5 pulse attempts.")
      return

    pulseSent = self._plcLogic.move_latch()
    if not pulseSent:
      self._setHeadError("PLC rejected latch pulse while ENABLE_ACTUATOR was true.")
      return

    self._g206PulseAttempts += 1
    self._g206SettleStartedAt = self._clock()

  def _isExpectedRetryState(self, state, fromPos):
    if fromPos == 1:
      return self._isStrictStageSideState(state)
    if fromPos == 2:
      return self._isStrictFixedSideState(state)
    if fromPos == 3:
      return self._isStrictIntermediateThreeState(state)
    return False

  def _isExpectedTransitionSuccess(self, state, toPos):
    if toPos == 1:
      return self._isStrictStageSideState(state)
    if toPos == 2:
      return self._isStrictFixedSideState(state)
    if toPos == 3:
      return self._isStrictIntermediateThreeState(state)
    return False

  def _updateG206LatchingState(self):
    if self._g206SettleStartedAt is None:
      self._commandNextG206Pulse()
      return

    if (self._clock() - self._g206SettleStartedAt) < self._g206SettleSeconds:
      return

    state = self._readTransferStateNow()
    transition = self._g206Transitions[self._g206TransitionIndex]
    self._g206SettleStartedAt = None

    if self._isExpectedTransitionSuccess(state, transition["to"]):
      self._g206TransitionIndex += 1
      self._g206PulseAttempts = 0
      if self._g206TransitionIndex >= len(self._g206Transitions):
        if self._commandZMove(self._headZTarget, self.States.SEEKING_TO_FINAL_POSITION):
          self._resetG206State()
        return
      self._commandNextG206Pulse()
      return

    if not self._isExpectedRetryState(state, transition["from"]):
      self._setHeadError("Latch transition settled into an invalid state.")
      return

    if self._g206PulseAttempts >= self._g206MaxPulseAttempts:
      self._setHeadError("Latch transition failed after 5 pulse attempts.")
      return

    self._commandNextG206Pulse()

  def update(self):
    if self._headState == self.States.IDLE:
      return

    if self._headState == self.States.ERROR:
      return

    if self._plcLogic.isError():
      self._setHeadError("PLC entered error state during head transfer.")
      return

    if self._activeTransferMode == self._TRANSFER_MODE_G206:
      self._updateG206()
      return

    self._updateLegacy()

  def _updateLegacy(self):
    if self._headState == self.States.SEEKING_TO_FINAL_POSITION:
      if self._plcLogic.isReady() and self._isFinalTargetStateReached():
        self._resetLatchRetryState()
        self._headState = self.States.IDLE
        self._activeTransferMode = None
    elif self._headState == self.States.EXTENDING_TO_TRANSFER:
      if self._plcLogic.isReady():
        self._startLatchingState()
        self._headState = self.States.LATCHING
        self._updateLatchingState()
    elif self._headState == self.States.LATCHING:
      self._updateLatchingState()
    else:
      raise ValueError("Unknown head state: " + str(self._headState))

  def _updateG206(self):
    if self._headState == self.States.EXTENDING_TO_TRANSFER:
      if not self._plcLogic.isReady():
        return
      state = self._readTransferStateNow()
      if not bool(state["zExtended"]):
        self._setHeadError("Head transfer requires Z_EXTENDED before latching.")
        return
      if not bool(state["enableActuator"]):
        self._setHeadError("Head transfer requires ENABLE_ACTUATOR before latching.")
        return
      self._headState = self.States.LATCHING
      self._commandNextG206Pulse()
      return

    if self._headState == self.States.LATCHING:
      self._updateG206LatchingState()
      return

    if self._headState == self.States.SEEKING_TO_FINAL_POSITION:
      if not self._plcLogic.isReady():
        return
      state = self._readTransferStateNow()
      if not self._isG206FinalTargetReached(state):
        self._setHeadError("Head transfer final state did not settle as requested.")
        return
      self._headState = self.States.IDLE
      self._activeTransferMode = None
      self._lastError = ""
      return

    raise ValueError("Unknown head state: " + str(self._headState))

  def setHeadPosition(self, head_position_target: int, velocity):
    self._headPositionTarget = head_position_target
    self._velocity = velocity
    self.clearQueuedTransfer()
    self._activeTransferMode = self._TRANSFER_MODE_LEGACY

    currentTransferState = self._readTransferState()
    currentHeadSide = self._getCurrentTransferSide(currentTransferState)

    if (
      not currentTransferState["stagePresent"]
      and not currentTransferState["fixedPresent"]
    ):
      print("DEBUG: Head not present, skipping G106 command")
      self._activeTransferMode = None
      return False

    if currentHeadSide == self.HEAD_ABSENT:
      print("DEBUG: Head state unresolved, skipping G106 command")
      self._activeTransferMode = None
      return False

    target_lookup = {
      self.STAGE_SIDE: (self._retracted_z_position, self.STAGE_SIDE),
      self.LEVEL_A_SIDE: (self._front_z_position, self.STAGE_SIDE),
      self.LEVEL_B_SIDE: (self._back_z_position, self.STAGE_SIDE),
      self.FIXED_SIDE: (self._retracted_z_position, self.FIXED_SIDE),
    }
    if head_position_target not in target_lookup:
      raise ValueError("Unknown head position request: " + str(head_position_target))
    self._headZTarget, self._headLatchTarget = target_lookup[head_position_target]

    if self._headLatchTarget != currentHeadSide:
      self._commandZMove(self._extended_z_position, self.States.EXTENDING_TO_TRANSFER)
    else:
      self._commandZMove(self._headZTarget, self.States.SEEKING_TO_FINAL_POSITION)

    return False

  def setTransferPosition(self, head_position_target: int, velocity):
    self.clearQueuedTransfer()
    self._activeTransferMode = self._TRANSFER_MODE_G206
    self._headPositionTarget = head_position_target
    self._velocity = velocity

    target_lookup = {
      self.STAGE_SIDE: (self._retracted_z_position, self.STAGE_SIDE),
      self.LEVEL_A_SIDE: (self._front_z_position, self.STAGE_SIDE),
      self.LEVEL_B_SIDE: (self._back_z_position, self.STAGE_SIDE),
      self.FIXED_SIDE: (self._retracted_z_position, self.FIXED_SIDE),
    }
    if head_position_target not in target_lookup:
      return self._failTransferRequest("Unknown head transfer request: " + str(head_position_target))

    self._headZTarget, self._headLatchTarget = target_lookup[head_position_target]

    state = self._readTransferStateNow()
    currentSide = self._getCurrentStrictTransferSide(state)
    if currentSide == self.HEAD_ABSENT:
      return self._failTransferRequest("Head transfer requires a valid stable starting state.")

    if currentSide == self.FIXED_SIDE and int(state["actuatorPos"]) != 2:
      return self._failTransferRequest("Fixed-latched transfers require ACTUATOR_POS 2.")

    if currentSide == self.STAGE_SIDE and int(state["actuatorPos"]) != 1:
      return self._failTransferRequest("Stage-latched transfers require ACTUATOR_POS 1.")

    if self._headLatchTarget == currentSide:
      if not self._commandZMove(self._headZTarget, self.States.SEEKING_TO_FINAL_POSITION):
        return self._lastError
      return None

    self._g206Transitions = []
    if currentSide == self.STAGE_SIDE and self._headLatchTarget == self.FIXED_SIDE:
      self._g206Transitions = [{"from": 1, "to": 3}, {"from": 3, "to": 2}]
    elif currentSide == self.FIXED_SIDE and self._headLatchTarget == self.STAGE_SIDE:
      self._g206Transitions = [{"from": 2, "to": 1}]
    else:
      return self._failTransferRequest("Unsupported head transfer side combination.")

    if not self._commandZMove(self._extended_z_position, self.States.EXTENDING_TO_TRANSFER):
      return self._lastError
    return None

  def _failTransferRequest(self, message):
    self._setHeadError(message)
    return self._lastError

  def setFrontAndBack(self, front, back):
    self._front_z_position = front
    self._back_z_position = back

  def setExtendedAndRetracted(self, retracted, extended):
    self._extended_z_position = extended
    self._retracted_z_position = retracted

  def getPosition(self):
    return self.readCurrentPosition()

  def readCurrentPosition(self):
    state = self._readTransferStateNow()
    side = self._getCurrentStrictTransferSide(state)
    if side == self.HEAD_ABSENT:
      return self.HEAD_ABSENT
    if side == self.FIXED_SIDE:
      return self.FIXED_SIDE
    z = float(state["zPosition"])
    candidates = {
      self.STAGE_SIDE: self._retracted_z_position,
      self.LEVEL_A_SIDE: self._front_z_position,
      self.LEVEL_B_SIDE: self._back_z_position,
    }
    return min(candidates, key=lambda p: abs(candidates[p] - z))

  def getTargetAxisPosition(self):
    return self._headZTarget

  def stop(self):
    if self.States.IDLE != self._headState:
      if self.States.SEEKING_TO_FINAL_POSITION == self._headState:
        self._plcLogic.stopSeek()
      self.clearQueuedTransfer()
