
import unittest
from unittest.mock import MagicMock
from dune_winder.core.motion_service import MotionService
from dune_winder.core.control_state_machine import ControlStateMachine
from dune_winder.core.control_events import ManualModeEvent

class TestServoDisableRepro(unittest.TestCase):
    def test_servo_disable_not_dispatched_in_stop_state(self):
        # Mock dependencies
        io = MagicMock()
        log = MagicMock()
        state_machine = MagicMock()
        safety = MagicMock()
        gcode_handler = MagicMock()
        head_compensation = MagicMock()
        x_backlash = MagicMock()
        workspace_getter = MagicMock()

        # Instantiate MotionService
        service = MotionService(
            io, log, state_machine, safety, gcode_handler, head_compensation, x_backlash, workspace_getter
        )

        # Scenario: State machine is in STOP state
        state_machine.isInMotion.return_value = False
        
        # Call servoDisable
        service.servoDisable()

        # Assert: dispatch was NOT called
        state_machine.dispatch.assert_not_called()

    def test_servo_disable_dispatched_in_wind_state(self):
        # Mock dependencies
        io = MagicMock()
        log = MagicMock()
        state_machine = MagicMock()
        safety = MagicMock()
        gcode_handler = MagicMock()
        head_compensation = MagicMock()
        x_backlash = MagicMock()
        workspace_getter = MagicMock()

        # Instantiate MotionService
        service = MotionService(
            io, log, state_machine, safety, gcode_handler, head_compensation, x_backlash, workspace_getter
        )

        # Scenario: State machine is in WIND state (which is in motion)
        state_machine.isInMotion.return_value = True
        
        # Call servoDisable
        service.servoDisable()

        # Assert: dispatch WAS called with ManualModeEvent(idleServos=True)
        state_machine.dispatch.assert_called_once()
        event = state_machine.dispatch.call_args[0][0]
        self.assertIsInstance(event, ManualModeEvent)
        self.assertTrue(event.idleServos)

if __name__ == "__main__":
    unittest.main()
