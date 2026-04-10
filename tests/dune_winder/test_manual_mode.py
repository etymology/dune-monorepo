import unittest

from dune_winder.core.control_events import ManualModeEvent
from dune_winder.core.manual_mode import ManualMode


class _FakeAxis:
  def __init__(self, seeking_states=None):
    self._seeking_states = list(seeking_states or [False])
    self._index = 0

  def isSeeking(self):
    value = self._seeking_states[min(self._index, len(self._seeking_states) - 1)]
    self._index += 1
    return value

  def getPosition(self):
    return 0.0


class _FakePLCLogic:
  def __init__(self, ready_states):
    self._ready_states = list(ready_states)
    self._index = 0
    self.z_moves = []
    self.stop_requests = 0

  def isReady(self):
    value = self._ready_states[min(self._index, len(self._ready_states) - 1)]
    self._index += 1
    return value

  def setZ_Position(self, position, velocity=None):
    self.z_moves.append((position, velocity))

  def stopSeek(self):
    self.stop_requests += 1


class _FakeHead:
  def __init__(self):
    self.stop_requests = 0
    self._ready_states = [True]
    self._index = 0
    self._transfer_active = False

  def isReady(self):
    value = self._ready_states[min(self._index, len(self._ready_states) - 1)]
    self._index += 1
    return value

  def hasError(self):
    return False

  def getLastError(self):
    return ""

  def isTransferActive(self):
    return self._transfer_active

  def clearQueuedTransfer(self):
    pass

  def stop(self):
    self.stop_requests += 1


class _FakeLog:
  def add(self, *_args, **_kwargs):
    pass


class _FakeStateMachine:
  class States:
    STOP = "STOP"

  def __init__(self):
    self.changed_to = []
    self.states = {}

  def addState(self, state, index):
    self.states[index] = state

  def changeState(self, state):
    self.changed_to.append(state)
    return False


class _FakeIO:
  def __init__(self, ready_states, axis_seeking_states=None, head_ready_states=None, head_transfer_active=False):
    self.plcLogic = _FakePLCLogic(ready_states)
    self.head = _FakeHead()
    if head_ready_states is not None:
      self.head._ready_states = list(head_ready_states)
    self.head._transfer_active = bool(head_transfer_active)
    axis_states = axis_seeking_states or [False]
    self.xAxis = _FakeAxis(axis_states)
    self.yAxis = _FakeAxis([False])
    self.zAxis = _FakeAxis(axis_states)


class ManualModeTests(unittest.TestCase):
  def test_plc_seek_waits_for_busy_transition_before_returning_to_stop(self):
    io = _FakeIO(
      ready_states=[True, False, False, True],
      axis_seeking_states=[False],
    )
    machine = _FakeStateMachine()
    mode = ManualMode(machine, "MANUAL", io, _FakeLog())
    mode.setRequest(ManualModeEvent(seekZ=43.0, velocity=100.0))

    self.assertFalse(mode.enter())
    self.assertEqual(io.plcLogic.z_moves, [(43.0, 100.0)])

    mode.update()
    self.assertEqual(machine.changed_to, [])

    mode.update()
    self.assertEqual(machine.changed_to, [])

    mode.update()
    self.assertEqual(machine.changed_to, [])

    mode.update()
    self.assertEqual(machine.changed_to, ["STOP"])

  def test_plc_seek_returns_to_stop_after_eot_recovery_without_axis_busy_bits(self):
    io = _FakeIO(
      ready_states=[False, True],
      axis_seeking_states=[False],
    )
    machine = _FakeStateMachine()
    mode = ManualMode(machine, "MANUAL", io, _FakeLog())
    mode.setRequest(ManualModeEvent(seekZ=43.0, velocity=100.0))

    self.assertFalse(mode.enter())
    self.assertEqual(io.plcLogic.z_moves, [(43.0, 100.0)])

    mode.update()
    self.assertEqual(machine.changed_to, [])

    mode.update()
    self.assertEqual(machine.changed_to, ["STOP"])

  def test_execute_gcode_waits_while_head_transfer_substate_is_active(self):
    io = _FakeIO(
      ready_states=[True],
      head_ready_states=[False, False, True],
      head_transfer_active=True,
    )
    machine = _FakeStateMachine()
    mode = ManualMode(machine, "MANUAL", io, _FakeLog())
    mode.setRequest(ManualModeEvent(executeGCode=True))

    self.assertFalse(mode.enter())
    self.assertEqual(mode.getSubState(), ManualMode.SubStates.HEAD_TRANSFER)

    mode.update()
    self.assertEqual(machine.changed_to, [])

    io.head._transfer_active = False
    mode.update()
    self.assertEqual(machine.changed_to, [])

    mode.update()
    self.assertEqual(machine.changed_to, ["STOP"])


if __name__ == "__main__":
  unittest.main()
