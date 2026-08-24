"""The G-Code error latch that backs the operator popup.

WindMode logs a G-Code error and immediately calls clearCodeError(), which used
to leave nothing for the UI to poll.  The latch keeps a copy alive until the
operator acknowledges it.
"""

from __future__ import annotations

import unittest

from dune_winder.core.wind_mode import WindMode
from dune_winder.gcode.handler import GCodeHandler
from dune_winder.machine.calibration.defaults import DefaultMachineCalibration
from dune_winder.machine.head_compensation import WirePathModel


class _Axis:
    def __init__(self, position=0.0):
        self._position = float(position)

    def getPosition(self):
        return self._position


class _PLCLogic:
    def isReady(self):
        return True

    def stopSeek(self):
        return None


class _Head:
    def isReady(self):
        return True

    def hasError(self):
        return False

    def getLastError(self):
        return ""

    def readCurrentPosition(self):
        return 0

    def isTransferActive(self):
        return False

    def stop(self):
        return None

    def getTargetAxisPosition(self):
        return 0.0


class _IO:
    def __init__(self):
        self.xAxis = _Axis()
        self.yAxis = _Axis()
        self.zAxis = _Axis()
        self.plcLogic = _PLCLogic()
        self.head = _Head()


def _handler():
    calibration = DefaultMachineCalibration()
    return GCodeHandler(_IO(), calibration, WirePathModel(calibration))


class LatchedGCodeErrorTests(unittest.TestCase):
    def test_no_latch_when_there_is_no_error(self):
        handler = _handler()

        handler.latchG_CodeError()

        self.assertIsNone(handler.getLatchedG_CodeError())

    def test_latch_survives_clear_code_error(self):
        handler = _handler()
        handler._set_gcode_error("XZ move target Z out of bounds [0.0, 400.0].")

        handler.latchG_CodeError()
        handler.clearCodeError()

        self.assertFalse(handler.isG_CodeError())
        latched = handler.getLatchedG_CodeError()
        self.assertIsNotNone(latched)
        self.assertIn("out of bounds", latched["message"])

    def test_acknowledge_clears_the_latch(self):
        handler = _handler()
        handler._set_gcode_error("boom")
        handler.latchG_CodeError()

        handler.clearLatchedG_CodeError()

        self.assertIsNone(handler.getLatchedG_CodeError())

    def test_latched_payload_is_a_copy(self):
        handler = _handler()
        handler._set_gcode_error("boom")
        handler.latchG_CodeError()

        latched = handler.getLatchedG_CodeError()
        latched["data"].append("tampered")

        self.assertEqual(handler.getLatchedG_CodeError()["data"], [])


class _StubStateMachine:
    def __init__(self, gCodeHandler):
        self.gCodeHandler = gCodeHandler
        self.changed_to = None
        self.states = {}

    class States:
        STOP = 3

    def addState(self, state, stateIndex):
        self.states[stateIndex] = state

    def changeState(self, state):
        self.changed_to = state


class _StubLog:
    def __init__(self):
        self.entries = []

    def add(self, module, typeName, message, parameters=None):
        self.entries.append((module, typeName, message, parameters))


class _ErroringHandler:
    """Minimal gCodeHandler surface WindMode.update() touches."""

    def __init__(self):
        self._latched = None
        self.cleared = False

    def poll(self):
        return False

    def isG_CodeError(self):
        return not self.cleared

    def getG_CodeErrorMessage(self):
        return "Head transfer blocked: MASTER_Z_GO transfer lockout is not ready."

    def getG_CodeErrorData(self):
        return [12, "~anchorToTarget(B1201,B2001)"]

    def latchG_CodeError(self):
        self._latched = {
            "message": self.getG_CodeErrorMessage(),
            "data": list(self.getG_CodeErrorData()),
        }

    def clearCodeError(self):
        self.cleared = True

    def getLatchedG_CodeError(self):
        return self._latched

    def isG_CodeLoaded(self):
        return False

    def setLine(self, line):
        return None


class WindModeLatchesErrorTests(unittest.TestCase):
    def test_wind_mode_latches_before_clearing(self):
        gCodeHandler = _ErroringHandler()
        stateMachine = _StubStateMachine(gCodeHandler)
        log = _StubLog()
        mode = WindMode(stateMachine, 0, _IO(), log)

        mode.update()

        # The error was cleared from the live state, as before...
        self.assertTrue(gCodeHandler.cleared)
        # ...but a copy survives for the operator popup.
        latched = gCodeHandler.getLatchedG_CodeError()
        self.assertIsNotNone(latched)
        self.assertIn("MASTER_Z_GO", latched["message"])
        self.assertEqual(latched["data"][0], 12)

        # And the wind still reports the error to the log as it always did.
        self.assertTrue(any(entry[1] == "WIND_ERROR" for entry in log.entries))


if __name__ == "__main__":
    unittest.main()
