import unittest
from unittest.mock import MagicMock

from dune_winder.core.motion_service import MotionService


def _build_service(state_machine, io):
    return MotionService(
        io,
        MagicMock(),
        state_machine,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )


class ServoDisableTests(unittest.TestCase):
    def test_servo_disable_requests_plc_state_when_stationary(self):
        state_machine = MagicMock()
        state_machine.isInMotion.return_value = False
        io = MagicMock()
        service = _build_service(state_machine, io)

        service.servoDisable()

        io.plcLogic.servoDisable.assert_called_once_with()
        state_machine.dispatch.assert_not_called()

    def test_servo_disable_requests_plc_state_when_in_motion(self):
        state_machine = MagicMock()
        state_machine.isInMotion.return_value = True
        io = MagicMock()
        service = _build_service(state_machine, io)

        service.servoDisable()

        io.plcLogic.servoDisable.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
