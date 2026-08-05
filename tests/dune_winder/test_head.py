import unittest

from dune_winder.io.controllers.head import Head


class _Tag:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _Axis:
    def __init__(self, position):
        self._position = _Tag(position)


class _PLCLogic:
    def __init__(
        self,
        *,
        stage_present=True,
        fixed_present=True,
        stage_latched=False,
        fixed_latched=False,
        actuator_pos=1,
        z_position=0.0,
    ):
        self._zStageLatchedBit = _Tag(stage_latched)
        self._zFixedLatchedBit = _Tag(fixed_latched)
        self._zStagePresentBit = _Tag(stage_present)
        self._zFixedPresentBit = _Tag(fixed_present)
        self._actuatorPosition = _Tag(actuator_pos)
        self._zAxis = _Axis(z_position)
        self._ready = True
        self._error = False
        self.z_moves = []
        self.latch_moves = 0
        self.latch_results = []
        self.auto_advance_to_safe_pos = True
        self.stop_requests = 0
        self._latch_settle_until = None

    def isReady(self):
        return self._ready

    def isError(self):
        return self._error

    def setZ_Position(self, position, velocity=None):
        self.z_moves.append((float(position), velocity))
        self._zAxis._position.set(float(position))

    def move_latch(self):
        self.latch_moves += 1
        if self.latch_results:
            result = bool(self.latch_results.pop(0))
            if (
                result
                and self.auto_advance_to_safe_pos
                and self._actuatorPosition.get() != 2
            ):
                self._actuatorPosition.set(2)
            return result
        return True

    def set_current_time(self, time_value):
        self._current_time = time_value

    def stopSeek(self):
        self.stop_requests += 1

    def getTransferStateNow(self):
        z_position = float(self._zAxis._position.get())
        z_extended = z_position >= 417.0
        return {
            "stagePresent": bool(self._zStagePresentBit.get()),
            "fixedPresent": bool(self._zFixedPresentBit.get()),
            "stageLatched": bool(self._zStageLatchedBit.get()),
            "fixedLatched": bool(self._zFixedLatchedBit.get()),
            "zExtended": z_extended,
            "enableActuator": (
                bool(self._zStagePresentBit.get())
                and bool(self._zFixedPresentBit.get())
                and z_extended
            ),
            "actuatorPos": int(self._actuatorPosition.get()),
            "zPosition": z_position,
        }


class HeadControllerTests(unittest.TestCase):
    def _build_head(self, **kwargs):
        plc = _PLCLogic(**kwargs)
        head = Head(plc)
        clock = {"now": 0.0}
        head._clock = lambda: clock["now"]
        head._latchRetryIntervalSeconds = 0
        original_update = head.update

        def update_with_time_sync():
            plc.set_current_time(clock["now"])
            return original_update()

        head.update = update_with_time_sync
        return head, plc, clock

    def test_same_side_stage_g206_move_only_seeks_z(self):
        head, plc, _clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
            z_position=0.0,
        )

        error = head.setTransferPosition(Head.LEVEL_B_SIDE, 321)

        self.assertIsNone(error)
        self.assertEqual(plc.z_moves, [(250.0, 321)])
        self.assertEqual(plc.latch_moves, 0)
        self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

    def test_stage_to_fixed_g206_runs_1_to_3_to_2_then_retracts(self):
        head, plc, clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
            z_position=0.0,
        )

        self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 400))
        self.assertEqual(plc.z_moves, [(418.0, 400)])
        self.assertEqual(head._headState, Head.States.EXTENDING_TO_TRANSFER)

        head.update()
        self.assertEqual(plc.latch_moves, 1)
        self.assertEqual(head._headState, Head.States.LATCHING)

        plc._zStageLatchedBit.set(False)
        plc._actuatorPosition.set(3)
        clock["now"] = 1.01
        head.update()
        self.assertEqual(plc.latch_moves, 2)

        plc._zFixedLatchedBit.set(True)
        plc._actuatorPosition.set(2)
        clock["now"] = 2.02
        head.update()

        self.assertEqual(plc.z_moves[-1], (0.0, 400))
        self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

    def test_fixed_to_stage_g206_runs_2_to_1_then_moves_to_requested_z(self):
        head, plc, clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=True,
            actuator_pos=2,
            z_position=0.0,
        )

        self.assertIsNone(head.setTransferPosition(Head.LEVEL_A_SIDE, 275))
        self.assertEqual(plc.z_moves, [(418.0, 275)])

        head.update()
        self.assertEqual(plc.latch_moves, 1)

        plc._zFixedLatchedBit.set(False)
        plc._zStageLatchedBit.set(True)
        plc._actuatorPosition.set(1)
        clock["now"] = 1.01
        head.update()

        self.assertEqual(plc.z_moves[-1], (150.0, 275))
        self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

    def test_same_side_fixed_move_proceeds_immediately_when_actuator_already_safe(self):
        head, plc, _clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=True,
            actuator_pos=2,
            z_position=0.0,
        )

        self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 400))
        self.assertEqual(plc.z_moves, [(0.0, 400)])
        self.assertEqual(plc.latch_moves, 0)

    def test_same_side_fixed_move_recovers_latch_before_commanding_z(self):
        head, plc, _clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=True,
            actuator_pos=3,
            z_position=0.0,
        )
        plc.latch_results = [True]

        self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 400))
        self.assertEqual(plc.latch_moves, 1)
        self.assertEqual(plc.z_moves, [(0.0, 400)])
        self.assertEqual(plc._actuatorPosition.get(), 2)

    def test_same_side_fixed_move_fails_after_three_unsuccessful_recovery_attempts(
        self,
    ):
        head, plc, _clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=True,
            actuator_pos=3,
            z_position=0.0,
        )
        plc.latch_results = [False, False, False]

        error = head.setTransferPosition(Head.FIXED_SIDE, 400)

        self.assertIsNotNone(error)
        self.assertEqual(plc.latch_moves, 3)
        self.assertEqual(plc.z_moves, [])
        self.assertIn("actuator reaches position 2", error)

    def test_same_side_fixed_move_succeeds_on_third_recovery_attempt(self):
        head, plc, _clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=True,
            actuator_pos=3,
            z_position=0.0,
        )
        plc.latch_results = [False, False, True]

        self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 400))
        self.assertEqual(plc.latch_moves, 3)
        self.assertEqual(plc.z_moves, [(0.0, 400)])

    def test_g206_waits_for_extension_and_enable_before_latching(self):
        head, plc, clock = self._build_head(
            stage_present=True,
            fixed_present=False,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
            z_position=0.0,
        )

        self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 400))
        head.update()
        self.assertEqual(head._headState, Head.States.EXTENDING_TO_TRANSFER)
        self.assertEqual(plc.latch_moves, 0)

        # Make fixed present so enableActuator becomes true
        plc._zFixedPresentBit.set(True)
        plc._zAxis._position.set(418.0)
        head.update()
        self.assertEqual(head._headState, Head.States.LATCHING)
        self.assertEqual(plc.latch_moves, 1)

    def test_invalid_g206_start_state_fails_immediately(self):
        head, plc, _clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=True,
            fixed_latched=True,
            actuator_pos=1,
            z_position=0.0,
        )

        error = head.setTransferPosition(Head.FIXED_SIDE, 400)

        self.assertIsNotNone(error)
        self.assertEqual(plc.z_moves, [])
        self.assertTrue(head.hasError())

    def test_fixed_latched_with_wrong_actuator_blocks_z_motion_when_recovery_cannot_fix_state(
        self,
    ):
        head, plc, _clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=True,
            actuator_pos=3,
            z_position=0.0,
        )
        plc.auto_advance_to_safe_pos = False
        plc.latch_results = [True, True, True]

        error = head.setTransferPosition(Head.LEVEL_A_SIDE, 200)

        self.assertIsNotNone(error)
        self.assertEqual(plc.z_moves, [])
        self.assertEqual(plc.latch_moves, 3)
        self.assertIn("actuator reaches position 2", error)

    def test_g206_extension_timeout_errors_and_clears_state(self):
        head, plc, clock = self._build_head(
            stage_present=True,
            fixed_present=False,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
            z_position=0.0,
        )

        self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 400))
        head.update()
        # Z should be commanded to extend but fixed not present yet
        self.assertEqual(head._headState, Head.States.EXTENDING_TO_TRANSFER)

        # Simulate extension timeout by advancing time past G206_EXTEND_TIMEOUT (10 seconds)
        # without fixed becoming present (so z stays retracted)
        for attempt in range(1, 15):
            clock["now"] = float(attempt)
            head.update()
            if head.hasError():
                break

        self.assertTrue(head.hasError())
        self.assertIn("ENABLE_ACTUATOR", head.getLastError())
        self.assertTrue(head.isReady())
        self.assertFalse(head.isTransferActive())

    def test_g206_waits_for_enable_actuator_before_first_pulse(self):
        head, plc, clock = self._build_head(
            stage_present=True,
            fixed_present=False,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
            z_position=0.0,
        )
        head.setLatchTiming(1.0, 3.0)

        self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 400))
        head.update()
        self.assertEqual(plc.latch_moves, 0)

        plc._zFixedPresentBit.set(True)
        head.update()
        self.assertEqual(plc.latch_moves, 1)

    def _drive_stage_to_fixed_into_seeking(self, head, plc, clock):
        """
        Run a STAGE->FIXED G206 through 1->3->2 until the Z withdrawal is
        commanded and the head enters SEEKING_TO_FINAL_POSITION.
        """
        self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 400))
        head.update()  # EXTENDING -> LATCHING, first pulse (1 -> 3)

        plc._zStageLatchedBit.set(False)
        plc._actuatorPosition.set(3)
        clock["now"] = 1.0
        head.update()  # pulse (3 -> 2)

        plc._zFixedLatchedBit.set(True)
        plc._actuatorPosition.set(2)
        clock["now"] = 2.0
        head.update()  # latch settled -> command Z withdrawal -> SEEKING
        self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)
        self.assertEqual(plc.z_moves[-1], (0.0, 400))

    def test_g206_relatches_when_actuator_stalls_at_3_before_final_settle(self):
        head, plc, clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
            z_position=0.0,
        )
        self._drive_stage_to_fixed_into_seeking(head, plc, clock)

        # The latch slips back to ACTUATOR_POS 3 with the head still extended
        # (ENABLE_ACTUATOR true): the final-settle check must re-latch, not fail.
        plc._actuatorPosition.set(3)
        plc._zAxis._position.set(418.0)
        latch_moves_before = plc.latch_moves
        clock["now"] = 3.0
        head.update()
        self.assertFalse(head.hasError())
        self.assertEqual(head._headState, Head.States.LATCHING)
        self.assertEqual(plc.latch_moves, latch_moves_before + 1)

        # The retry drives 3 -> 2 again; the latching phase re-commands the Z
        # withdrawal and the transfer then settles cleanly.
        plc._actuatorPosition.set(2)
        clock["now"] = 4.0
        head.update()
        self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

        plc._zAxis._position.set(0.0)
        clock["now"] = 5.0
        head.update()
        self.assertEqual(head._headState, Head.States.IDLE)
        self.assertTrue(head.isReady())
        self.assertFalse(head.hasError())

    def test_g206_does_not_relatch_when_head_no_longer_extended(self):
        head, plc, clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
            z_position=0.0,
        )
        self._drive_stage_to_fixed_into_seeking(head, plc, clock)

        # Latch short of its detent but the arm has retracted (z=0), so
        # ENABLE_ACTUATOR is false and a fresh pulse cannot help: fail outright.
        plc._actuatorPosition.set(3)
        plc._zAxis._position.set(0.0)
        latch_moves_before = plc.latch_moves
        clock["now"] = 3.0
        head.update()
        self.assertTrue(head.hasError())
        self.assertEqual(plc.latch_moves, latch_moves_before)
        self.assertIn("did not settle", head.getLastError())

    def test_g206_errors_after_exhausting_latch_resettle_retries(self):
        head, plc, clock = self._build_head(
            stage_present=True,
            fixed_present=True,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
            z_position=0.0,
        )
        self._drive_stage_to_fixed_into_seeking(head, plc, clock)

        now = 3.0
        for expected in range(1, head._g206MaxLatchResettleAttempts + 1):
            # Slip back to 3 while still extended -> should re-latch.
            plc._actuatorPosition.set(3)
            plc._zAxis._position.set(418.0)
            clock["now"] = now
            now += 1.0
            head.update()
            self.assertFalse(head.hasError())
            self.assertEqual(head._headState, Head.States.LATCHING)
            self.assertEqual(head._g206LatchResettleAttempts, expected)

            # Recover to 2 so the latching phase re-commands the withdrawal.
            plc._actuatorPosition.set(2)
            clock["now"] = now
            now += 1.0
            head.update()
            self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

        # Budget spent: the next stall must fail instead of re-latching again.
        plc._actuatorPosition.set(3)
        plc._zAxis._position.set(418.0)
        clock["now"] = now
        head.update()
        self.assertTrue(head.hasError())
        self.assertIn("did not settle", head.getLastError())
        self.assertIn("actuatorPos=3", head.getLastError())
        self.assertTrue(head.isReady())
        self.assertFalse(head.isTransferActive())


class TransferAvailabilityTests(unittest.TestCase):
    """
    readCurrentPosition() reports HEAD_ABSENT both for a missing head and for a
    mounted head in a conflicting latch state.  getTransferAvailability() must
    tell those two apart so the interpreter can skip one and fault the other.
    """

    def _head(self, **kwargs):
        return Head(_PLCLogic(**kwargs))

    def test_absent_when_neither_presence_sensor_sees_the_head(self):
        head = self._head(stage_present=False, fixed_present=False)

        availability, state = head.getTransferAvailability()

        self.assertEqual(availability, Head.TRANSFER_ABSENT)
        self.assertEqual(head.readCurrentPosition(), Head.HEAD_ABSENT)
        self.assertEqual(head.describeLatchConflict(state), "")

    def test_ready_on_clean_stage_side(self):
        head = self._head(
            stage_present=True,
            fixed_present=False,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=1,
        )

        availability, state = head.getTransferAvailability()

        self.assertEqual(availability, Head.TRANSFER_READY)
        self.assertEqual(head.describeLatchConflict(state), "")

    def test_ready_on_clean_fixed_side(self):
        head = self._head(
            stage_present=False,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=True,
            actuator_pos=2,
        )

        availability, _state = head.getTransferAvailability()

        self.assertEqual(availability, Head.TRANSFER_READY)

    def test_blocked_when_fixed_latched_at_rocker_at_fixed(self):
        # ACTUATOR_POS 3 is the no_latch_collision violation: the latch would
        # foul the fixed mount if the arm extended.
        head = self._head(
            stage_present=False,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=True,
            actuator_pos=3,
        )

        availability, state = head.getTransferAvailability()

        self.assertEqual(availability, Head.TRANSFER_BLOCKED)
        self.assertEqual(head.readCurrentPosition(), Head.HEAD_ABSENT)
        detail = head.describeLatchConflict(state)
        self.assertIn("fixed-latched", detail)
        self.assertIn("ACTUATOR_POS=3", detail)

    def test_blocked_when_both_latches_engaged(self):
        head = self._head(
            stage_present=True,
            fixed_present=True,
            stage_latched=True,
            fixed_latched=True,
            actuator_pos=2,
        )

        availability, state = head.getTransferAvailability()

        self.assertEqual(availability, Head.TRANSFER_BLOCKED)
        self.assertIn("both latches", head.describeLatchConflict(state))

    def test_blocked_when_stage_latched_at_wrong_actuator_position(self):
        head = self._head(
            stage_present=True,
            fixed_present=False,
            stage_latched=True,
            fixed_latched=False,
            actuator_pos=3,
        )

        availability, state = head.getTransferAvailability()

        self.assertEqual(availability, Head.TRANSFER_BLOCKED)
        detail = head.describeLatchConflict(state)
        self.assertIn("stage-latched", detail)
        self.assertIn("ACTUATOR_POS=3", detail)

    def test_blocked_when_present_but_floating(self):
        head = self._head(
            stage_present=True,
            fixed_present=True,
            stage_latched=False,
            fixed_latched=False,
            actuator_pos=3,
        )

        availability, state = head.getTransferAvailability()

        self.assertEqual(availability, Head.TRANSFER_BLOCKED)
        self.assertIn("neither latch", head.describeLatchConflict(state))


if __name__ == "__main__":
    unittest.main()
