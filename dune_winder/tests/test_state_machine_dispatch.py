import unittest

from dune_winder.core.control_state_machine import ControlStateMachine
from dune_winder.library.state_machine import StateMachine
from dune_winder.library.state_machine_state import StateMachineState


class _HandledState(StateMachineState):
  def __init__(self, stateMachine, stateIndex):
    StateMachineState.__init__(self, stateMachine, stateIndex)
    self.events = []

  def handle(self, event):
    self.events.append(event)
    return True


class _IgnoredState(StateMachineState):
  pass


class StateMachineDispatchTests(unittest.TestCase):
  def test_dispatch_routes_to_active_state_handle(self):
    machine = StateMachine()
    handledState = _HandledState(machine, 0)
    _IgnoredState(machine, 1)
    machine.changeState(0)

    event = object()
    wasHandled = machine.dispatch(event)

    self.assertTrue(wasHandled)
    self.assertEqual(handledState.events, [event])

  def test_dispatch_returns_false_for_unhandled_event(self):
    machine = StateMachine()
    _IgnoredState(machine, 0)
    machine.changeState(0)

    self.assertFalse(machine.dispatch(object()))

  def test_control_state_machine_motion_check_is_not_tautology(self):
    machine = object.__new__(ControlStateMachine)

    machine.getState = lambda: ControlStateMachine.States.HARDWARE
    self.assertFalse(ControlStateMachine.isInMotion(machine))

    machine.getState = lambda: ControlStateMachine.States.STOP
    self.assertFalse(ControlStateMachine.isInMotion(machine))

    machine.getState = lambda: ControlStateMachine.States.WIND
    self.assertTrue(ControlStateMachine.isInMotion(machine))

  def test_control_states_are_enum_members(self):
    self.assertIsInstance(
      ControlStateMachine.States.HARDWARE,
      ControlStateMachine.States,
    )


if __name__ == "__main__":
  unittest.main()
