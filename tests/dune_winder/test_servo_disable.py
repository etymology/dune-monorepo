import unittest
from unittest.mock import MagicMock

from dune_winder.core.motion_service import MotionService
from dune_winder.core.control_events import ManualModeEvent


def _build_service(state_machine):
    return MotionService(
        MagicMock(),
        MagicMock(),
        state_machine,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )


class ServoDisableTests(unittest.TestCase):
    def test_servo_disable_not_dispatched_when_stationary(self):
        state_machine = MagicMock()
        state_machine.isInMotion.return_value = False
        service = _build_service(state_machine)

        service.servoDisable()

        state_machine.dispatch.assert_not_called()

    def test_servo_disable_dispatches_idle_servos_when_in_motion(self):
        state_machine = MagicMock()
        state_machine.isInMotion.return_value = True
        service = _build_service(state_machine)

        service.servoDisable()

        state_machine.dispatch.assert_called_once()
        event = state_machine.dispatch.call_args[0][0]
        self.assertIsInstance(event, ManualModeEvent)
        self.assertTrue(event.idleServos)


if __name__ == "__main__":
    unittest.main()
