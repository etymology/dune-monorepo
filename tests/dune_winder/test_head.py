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
    self.stop_requests = 0

  def isReady(self):
    return self._ready

  def isError(self):
    return self._error

  def setZ_Position(self, position, velocity=None):
    self.z_moves.append((float(position), velocity))

  def move_latch(self):
    if self._zStagePresentBit.get() and not self._zFixedPresentBit.get():
      return False
    self.latch_moves += 1
    return True

  def stopSeek(self):
    self.stop_requests += 1


class HeadControllerTests(unittest.TestCase):
  def _build_head(self, **kwargs):
    plc = _PLCLogic(**kwargs)
    head = Head(plc)
    clock = {"now": 0.0}
    head._clock = lambda: clock["now"]
    head.setLatchTiming(0.25, 1.0)
    return head, plc, clock

  def test_read_current_position_uses_z_to_distinguish_stage_modes(self):
    head, plc, _clock = self._build_head(
      stage_present=True,
      fixed_present=False,
      stage_latched=True,
      fixed_latched=False,
      actuator_pos=1,
      z_position=150.0,
    )

    self.assertEqual(head.readCurrentPosition(), Head.LEVEL_A_SIDE)
    self.assertEqual(head.getPosition(), Head.LEVEL_A_SIDE)

  def test_stage_side_is_not_reported_until_actuator_reaches_final_pos_one(self):
    head, plc, _clock = self._build_head(
      stage_present=True,
      fixed_present=False,
      stage_latched=True,
      fixed_latched=False,
      actuator_pos=2,
      z_position=150.0,
    )

    self.assertEqual(head.readCurrentPosition(), Head.HEAD_ABSENT)

  def test_same_side_stage_moves_only_seek_z(self):
    head, plc, _clock = self._build_head(
      stage_present=True,
      fixed_present=True,
      stage_latched=True,
      fixed_latched=False,
      actuator_pos=1,
      z_position=0.0,
    )

    head.setHeadPosition(Head.LEVEL_B_SIDE, 321)

    self.assertEqual(plc.z_moves, [(250.0, 321)])
    self.assertEqual(plc.latch_moves, 0)
    self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

  def test_stage_to_fixed_transfer_retries_pulses_until_actuator_changes(self):
    head, plc, clock = self._build_head(
      stage_present=True,
      fixed_present=True,
      stage_latched=True,
      fixed_latched=False,
      actuator_pos=1,
      z_position=150.0,
    )

    head.setHeadPosition(Head.FIXED_SIDE, 400)

    self.assertEqual(plc.z_moves, [(418.0, 400)])
    self.assertEqual(head._headState, Head.States.EXTENDING_TO_TRANSFER)

    head.update()
    self.assertEqual(plc.latch_moves, 1)
    self.assertEqual(head._headState, Head.States.LATCHING)

    plc._zStageLatchedBit.set(False)
    plc._zFixedLatchedBit.set(True)
    plc._actuatorPosition.set(3)
    clock["now"] = 0.05
    head.update()
    self.assertEqual(plc.latch_moves, 2)
    self.assertEqual(plc.z_moves, [(418.0, 400)])
    self.assertEqual(head._headState, Head.States.LATCHING)

    plc._actuatorPosition.set(2)
    clock["now"] = 0.10
    head.update()
    self.assertEqual(plc.z_moves[-1], (0.0, 400))
    self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

  def test_fixed_to_stage_transfer_waits_for_actuator_two_before_retract(self):
    head, plc, clock = self._build_head(
      stage_present=True,
      fixed_present=True,
      stage_latched=False,
      fixed_latched=True,
      actuator_pos=2,
      z_position=0.0,
    )

    head.setHeadPosition(Head.LEVEL_A_SIDE, 275)

    self.assertEqual(plc.z_moves, [(418.0, 275)])
    self.assertEqual(head._headState, Head.States.EXTENDING_TO_TRANSFER)

    head.update()
    self.assertEqual(plc.latch_moves, 1)
    self.assertEqual(head._headState, Head.States.LATCHING)

    plc._zStageLatchedBit.set(True)
    plc._zFixedLatchedBit.set(False)
    plc._actuatorPosition.set(1)
    clock["now"] = 0.05
    head.update()

    self.assertEqual(plc.latch_moves, 2)
    self.assertEqual(plc.z_moves, [(418.0, 275)])
    self.assertEqual(head._headState, Head.States.LATCHING)

    plc._actuatorPosition.set(2)
    head.update()

    self.assertEqual(plc.z_moves[-1], (150.0, 275))
    self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

    head.update()
    self.assertEqual(head._headState, Head.States.SEEKING_TO_FINAL_POSITION)

    plc._actuatorPosition.set(1)
    head.update()
    self.assertEqual(head._headState, Head.States.IDLE)

  def test_fixed_latched_high_z_move_pre_latches_before_extension(self):
    head, plc, clock = self._build_head(
      stage_present=False,
      fixed_present=True,
      stage_latched=False,
      fixed_latched=True,
      actuator_pos=0,
      z_position=0.0,
    )

    head.setHeadPosition(Head.LEVEL_A_SIDE, 275)

    self.assertEqual(plc.z_moves, [])
    self.assertEqual(plc.latch_moves, 1)
    self.assertEqual(head._headState, Head.States.PRE_LATCHING)

    plc._actuatorPosition.set(3)
    clock["now"] = 0.05
    head.update()
    self.assertEqual(plc.latch_moves, 2)
    self.assertEqual(plc.z_moves, [])
    self.assertEqual(head._headState, Head.States.PRE_LATCHING)

    plc._actuatorPosition.set(2)
    clock["now"] = 0.10
    head.update()
    self.assertEqual(plc.z_moves, [(418.0, 275)])
    self.assertEqual(head._headState, Head.States.EXTENDING_TO_TRANSFER)

  def test_latching_skips_pulses_without_both_present_and_times_out(self):
    head, plc, clock = self._build_head(
      stage_present=True,
      fixed_present=False,
      stage_latched=True,
      fixed_latched=False,
      actuator_pos=1,
      z_position=150.0,
    )

    head.setHeadPosition(Head.FIXED_SIDE, 200)

    head.update()
    self.assertEqual(head._headState, Head.States.LATCHING)
    self.assertEqual(plc.latch_moves, 0)

    clock["now"] = 0.30
    head.update()
    self.assertEqual(plc.latch_moves, 0)
    self.assertEqual(head._headState, Head.States.LATCHING)

    clock["now"] = 1.10
    head.update()
    self.assertEqual(head._headState, Head.States.ERROR)

  def test_set_head_position_is_noop_when_neither_side_is_present(self):
    head, plc, _clock = self._build_head(
      stage_present=False,
      fixed_present=False,
      stage_latched=False,
      fixed_latched=False,
      actuator_pos=1,
      z_position=0.0,
    )

    head.setHeadPosition(Head.STAGE_SIDE, 200)

    self.assertEqual(plc.z_moves, [])
    self.assertEqual(plc.latch_moves, 0)
    self.assertEqual(head.readCurrentPosition(), Head.HEAD_ABSENT)
    self.assertEqual(head._headState, Head.States.IDLE)


if __name__ == "__main__":
  unittest.main()
