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

    # Transfer availability classes reported by getTransferAvailability().
    #
    # readCurrentPosition() collapses ABSENT and BLOCKED into HEAD_ABSENT, which
    # makes a real latch conflict indistinguishable from an unmounted head.
    # Callers that must tell them apart use getTransferAvailability() instead.
    TRANSFER_ABSENT = "absent"  # no head mounted -- skipping a transfer is correct
    TRANSFER_READY = "ready"  # sitting on a clean, known side
    TRANSFER_BLOCKED = "blocked"  # mounted, but the latch/actuator conflicts

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
        self._preemptiveLatchRetryCount = 3
        self._clock = time.monotonic
        self._activeTransferMode = None
        self._lastError = ""
        self._g206Transitions = []
        self._g206TransitionIndex = 0
        self._g206PulseAttempts = 0
        self._g206SettleStartedAt = None
        self._g206SettleSeconds = 0.5
        self._g206TransitionStartedAt = None
        self._g206ExtendStartedAt = None
        self._g206ExtendTimeoutSeconds = 10.0
        # Bounded re-latch retries.  When a transfer reaches its final Z check
        # but the latch actuator stalled short of its settled detent (the
        # operator-reported "stuck in state 3" instead of "state 2, ready to
        # withdraw"), re-issue the latch command this many times before
        # reporting a failure.
        self._g206MaxLatchResettleAttempts = 3
        self._g206LatchResettleAttempts = 0

    def isReady(self):
        self.update()
        return self.States.IDLE == self._headState

    def hasError(self):
        return bool(self._lastError)

    def getState(self):
        return self._headState

    def getLastError(self):
        return self._lastError

    def consumeLastError(self):
        error = str(self._lastError)
        self._lastError = ""
        return error

    def isTransferActive(self):
        return (
            self._activeTransferMode == self._TRANSFER_MODE_G206
            and self._headState != self.States.IDLE
        )

    def clearQueuedTransfer(self):
        self._headState = self.States.IDLE
        self._headPositionTarget = -1
        self._headZTarget = -1
        self._headLatchTarget = -1
        self._activeTransferMode = None
        self._lastError = ""
        # Reset the re-latch retry budget here (transfer start / teardown) rather
        # than in _resetG206State, which also runs on the in-flight latching ->
        # Z-move handoff and must not refill the budget mid-transfer.
        self._g206LatchResettleAttempts = 0
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

    def _resetG206State(self):
        self._g206Transitions = []
        self._g206TransitionIndex = 0
        self._g206PulseAttempts = 0
        self._g206SettleStartedAt = None
        self._g206TransitionStartedAt = None
        self._g206ExtendStartedAt = None

    def _setHeadError(self, message):
        self._lastError = str(message)
        self._resetG206State()
        self._activeTransferMode = None
        self._headState = self.States.IDLE

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

    def _getCurrentStrictTransferSide(self, state):
        if not state["stagePresent"] and not state["fixedPresent"]:
            return self.HEAD_ABSENT

        if self._isStrictFixedSideState(state):
            return self.FIXED_SIDE

        if self._isStrictStageSideState(state):
            return self.STAGE_SIDE

        return self.HEAD_ABSENT

    def _getCurrentTransferSide(self, state):
        if not state["stagePresent"] and not state["fixedPresent"]:
            return self.HEAD_ABSENT

        if (
            state["fixedPresent"]
            and state["fixedLatched"]
            and not state["stageLatched"]
        ):
            return self.FIXED_SIDE

        if (
            state["stagePresent"]
            and state["stageLatched"]
            and not state["fixedLatched"]
        ):
            return self.STAGE_SIDE

        return self.HEAD_ABSENT

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

    def _isG206FinalTargetReached(self, state):
        if self._headPositionTarget == self.FIXED_SIDE:
            return self._isStrictFixedSideState(state) and self._isCloseToTargetZ(
                state["zPosition"], self._retracted_z_position
            )

        if self._headPositionTarget in (
            self.STAGE_SIDE,
            self.LEVEL_A_SIDE,
            self.LEVEL_B_SIDE,
        ):
            return self._isStrictStageSideState(state) and self._isCloseToTargetZ(
                state["zPosition"], self._headZTarget
            )

        return False

    def _isCloseToTargetZ(self, actual, target):
        return abs(float(actual) - float(target)) <= 1.0

    def _isFixedLatchSafeForZMove(self, state):
        return (not bool(state["fixedLatched"])) or int(state["actuatorPos"]) == 2

    def _ensureSafeFixedLatchForZMove(self):
        state = self._readTransferStateNow()
        if self._isFixedLatchSafeForZMove(state):
            return True

        for attempt in range(self._preemptiveLatchRetryCount):
            if not self._plcLogic.move_latch():
                if attempt + 1 >= self._preemptiveLatchRetryCount:
                    break
                time.sleep(self._latchRetryIntervalSeconds)
                state = self._readTransferStateNow()
                if self._isFixedLatchSafeForZMove(state):
                    return True
                continue

            deadline = self._clock() + self._latchTimeoutSeconds
            while self._clock() < deadline:
                if self._plcLogic.isError():
                    self._setHeadError(
                        "PLC entered error state during latch recovery before Z move."
                    )
                    return False
                if self._plcLogic.isReady():
                    break
                time.sleep(self._latchRetryIntervalSeconds)

            state = self._readTransferStateNow()
            if self._isFixedLatchSafeForZMove(state):
                return True

            if attempt + 1 < self._preemptiveLatchRetryCount:
                time.sleep(self._latchRetryIntervalSeconds)

        self._setHeadError(
            "Cannot move Z while fixed-latched unless actuator reaches position 2."
        )
        return False

    def _commandZMove(self, target_z, next_state):
        if not self._ensureSafeFixedLatchForZMove():
            return False
        self._plcLogic.setZ_Position(target_z, self._velocity)
        self._headState = next_state
        return True

    def _commandNextG206Pulse(self):
        state = self._readTransferStateNow()

        if not bool(state["enableActuator"]):
            return

        pulseSent = self._plcLogic.move_latch()
        if not pulseSent:
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

    def _isG206LatchTargetReached(self, state):
        if self._headLatchTarget == self.FIXED_SIDE:
            return self._isStrictFixedSideState(state)
        if self._headLatchTarget == self.STAGE_SIDE:
            return self._isStrictStageSideState(state)
        return False

    def _canResettleG206Latch(self, state):
        """
        Whether another latch command can still drive the latch to its detent.

        The recoverable failure the operator reported is a fixed-side transfer
        whose latch engaged the fixed mount but whose actuator stalled at
        ACTUATOR_POS 3 instead of settling at 2 ("ready to withdraw").  A fresh
        latch pulse only helps while the head is still extended between the two
        mounts -- i.e. while ENABLE_ACTUATOR is true; once the arm has retracted
        the actuator interlock refuses the pulse.  If the latch target is
        already reached there is nothing left to resettle.
        """
        return bool(state["enableActuator"]) and not self._isG206LatchTargetReached(
            state
        )

    def _isExpectedTransitionSuccess(self, state, toPos):
        if toPos == 1:
            return self._isStrictStageSideState(state)
        if toPos == 2:
            return self._isStrictFixedSideState(state)
        if toPos == 3:
            return self._isStrictIntermediateThreeState(state)
        return False

    def _formatTransferState(self, state):
        return (
            "stagePresent="
            + str(int(bool(state["stagePresent"])))
            + ", fixedPresent="
            + str(int(bool(state["fixedPresent"])))
            + ", stageLatched="
            + str(int(bool(state["stageLatched"])))
            + ", fixedLatched="
            + str(int(bool(state["fixedLatched"])))
            + ", zExtended="
            + str(int(bool(state["zExtended"])))
            + ", enableActuator="
            + str(int(bool(state["enableActuator"])))
            + ", actuatorPos="
            + str(int(state["actuatorPos"]))
            + ", zPosition="
            + str(float(state["zPosition"]))
        )

    def _transitionLabel(self, transition):
        return str(int(transition["from"])) + " -> " + str(int(transition["to"]))

    def _updateG206LatchingState(self):
        state = self._readTransferStateNow()
        now = self._clock()

        if self._isG206LatchTargetReached(state):
            self._g206SettleStartedAt = None
            self._g206TransitionStartedAt = None
            if self._commandZMove(
                self._headZTarget, self.States.SEEKING_TO_FINAL_POSITION
            ):
                self._resetG206State()
            return

        if not self._plcLogic.isReady():
            return

        if not bool(state["enableActuator"]):
            if self._g206TransitionStartedAt is None:
                self._g206TransitionStartedAt = now
            if (now - self._g206TransitionStartedAt) >= self._latchTimeoutSeconds:
                self._setHeadError(
                    "Latch phase timed out while waiting for ENABLE_ACTUATOR while targeting latch side "
                    + str(int(self._headLatchTarget))
                    + "; last state: "
                    + self._formatTransferState(state)
                )
            return

        if self._plcLogic.move_latch():
            self._g206TransitionStartedAt = now
            return

        if self._g206TransitionStartedAt is None:
            self._g206TransitionStartedAt = now
            return

        if (now - self._g206TransitionStartedAt) >= self._latchTimeoutSeconds:
            self._setHeadError(
                "Latch phase timed out while targeting latch side "
                + str(int(self._headLatchTarget))
                + " after "
                + str(float(self._latchTimeoutSeconds))
                + " s; last state: "
                + self._formatTransferState(state)
            )

    def update(self):
        if self._headState == self.States.IDLE:
            return

        if self._plcLogic.isError():
            self._setHeadError("PLC entered error state during head transfer.")
            return

        if self._activeTransferMode == self._TRANSFER_MODE_G206:
            self._updateG206()

    def _updateG206(self):
        if self._headState == self.States.EXTENDING_TO_TRANSFER:
            state = self._readTransferStateNow()
            if bool(state["zExtended"]) and bool(state["enableActuator"]):
                self._headState = self.States.LATCHING
                self._g206TransitionStartedAt = self._clock()
                self._commandNextG206Pulse()
                return

            if not self._plcLogic.isReady():
                return

            if self._g206ExtendStartedAt is None:
                self._g206ExtendStartedAt = self._clock()

            if (
                self._clock() - self._g206ExtendStartedAt
            ) < self._g206ExtendTimeoutSeconds:
                return

            if not bool(state["zExtended"]):
                self._setHeadError(
                    "Head transfer did not reach Z_EXTENDED before latching; last state: "
                    + self._formatTransferState(state)
                )
                return
            if not bool(state["enableActuator"]):
                self._setHeadError(
                    "Head transfer reached extension but ENABLE_ACTUATOR never became true; last state: "
                    + self._formatTransferState(state)
                )
                return
            self._headState = self.States.LATCHING
            self._g206TransitionStartedAt = self._clock()
            self._commandNextG206Pulse()
            return

        if self._headState == self.States.LATCHING:
            self._updateG206LatchingState()
            return

        if self._headState == self.States.SEEKING_TO_FINAL_POSITION:
            if not self._plcLogic.isReady():
                return
            state = self._readTransferStateNow()
            if self._isG206FinalTargetReached(state):
                self._headState = self.States.IDLE
                self._activeTransferMode = None
                self._lastError = ""
                return
            if (
                self._g206LatchResettleAttempts < self._g206MaxLatchResettleAttempts
                and self._canResettleG206Latch(state)
            ):
                # The transfer reached its final Z check but the latch actuator
                # stalled short of its settled detent (fixed-latched at
                # ACTUATOR_POS 3 rather than 2, "ready to withdraw").  The head
                # is still extended between the mounts, so a fresh latch command
                # can still drive the actuator home: re-enter the latching phase
                # and try again instead of failing outright.  The latching phase
                # will re-issue the Z withdrawal once the latch settles at 2.
                self._g206LatchResettleAttempts += 1
                self._headState = self.States.LATCHING
                self._g206TransitionStartedAt = self._clock()
                self._commandNextG206Pulse()
                return
            self._setHeadError(
                "Head transfer final state did not settle as requested for target "
                + str(int(self._headPositionTarget))
                + "; last state: "
                + self._formatTransferState(state)
            )
            return

        raise ValueError("Unknown head state: " + str(self._headState))

    def setHeadPosition(self, head_position_target: int, velocity):
        return self.setTransferPosition(head_position_target, velocity)

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
            return self._failTransferRequest(
                "Unknown head transfer request: " + str(head_position_target)
            )

        self._headZTarget, self._headLatchTarget = target_lookup[head_position_target]

        state = self._readTransferStateNow()
        currentSide = self._getCurrentTransferSide(state)
        if currentSide == self.HEAD_ABSENT:
            return self._failTransferRequest(
                "Head transfer requires a valid stable starting state."
            )

        if currentSide == self.STAGE_SIDE and int(state["actuatorPos"]) != 1:
            return self._failTransferRequest(
                "Stage-latched transfers require ACTUATOR_POS 1."
            )

        if self._headLatchTarget == currentSide:
            if not self._commandZMove(
                self._headZTarget, self.States.SEEKING_TO_FINAL_POSITION
            ):
                return self._lastError
            return None

        self._g206Transitions = []
        if currentSide == self.STAGE_SIDE and self._headLatchTarget == self.FIXED_SIDE:
            self._g206Transitions = [{"from": 1, "to": 3}, {"from": 3, "to": 2}]
        elif (
            currentSide == self.FIXED_SIDE and self._headLatchTarget == self.STAGE_SIDE
        ):
            self._g206Transitions = [{"from": 2, "to": 1}]
        else:
            return self._failTransferRequest(
                "Unsupported head transfer side combination."
            )

        self._g206ExtendStartedAt = self._clock()
        if not self._commandZMove(
            self._extended_z_position, self.States.EXTENDING_TO_TRANSFER
        ):
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

    def getTransferAvailability(self):
        """
        Classify whether a head transfer can start.

        Returns:
          Tuple of (availability, state).  `availability` is one of
          TRANSFER_ABSENT / TRANSFER_READY / TRANSFER_BLOCKED; `state` is the
          live _readTransferStateNow() dictionary so callers can reuse it
          instead of issuing a second PLC read.
        """
        state = self._readTransferStateNow()

        if not state["stagePresent"] and not state["fixedPresent"]:
            return (self.TRANSFER_ABSENT, state)

        if self._getCurrentStrictTransferSide(state) != self.HEAD_ABSENT:
            return (self.TRANSFER_READY, state)

        return (self.TRANSFER_BLOCKED, state)

    def describeLatchConflict(self, state):
        """
        Explain why a mounted head is not resting on a clean transfer side.

        This is the head-controller half of the MASTER_Z_GO diagnosis; it covers
        the `no_latch_collision` term plus the latch states that leave the head
        in no well-defined side at all.

        Args:
          state: A _readTransferStateNow() dictionary.

        Returns:
          Operator-facing explanation, or "" when the state is a clean side.
        """
        if not state["stagePresent"] and not state["fixedPresent"]:
            # No head mounted, so there is no conflict to describe.
            return ""

        if self._getCurrentStrictTransferSide(state) != self.HEAD_ABSENT:
            return ""

        actuatorPos = int(state["actuatorPos"])
        stageLatched = bool(state["stageLatched"])
        fixedLatched = bool(state["fixedLatched"])

        if stageLatched and fixedLatched:
            return (
                "both latches are engaged (stage and fixed); the head must be "
                "held by exactly one side before the arm can extend"
            )

        if fixedLatched:
            return (
                "fixed-latched, ACTUATOR_POS="
                + str(actuatorPos)
                + " (needs 2, mid_engagement, before the arm can extend; "
                "otherwise the latch fouls the fixed mount)"
            )

        if stageLatched:
            return (
                "stage-latched, ACTUATOR_POS="
                + str(actuatorPos)
                + " (needs 1, stage_latched)"
            )

        return (
            "the head is present but neither latch is engaged (floating), "
            "ACTUATOR_POS=" + str(actuatorPos)
        )

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
