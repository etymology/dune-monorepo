import unittest

from dune_winder.core.control_events import ManualModeEvent
from dune_winder.core.motion_service import MotionService
from dune_winder.core.safety_validation_service import SafetyValidationService
from dune_winder.core.x_backlash_compensation import XBacklashCompensation


class _Axis:
    def __init__(self, position):
        self._position = float(position)

    def getPosition(self):
        return self._position


class _Signal:
    def __init__(self, value):
        self._value = bool(value)

    def get(self):
        return self._value


class _PLCLogic:
    def __init__(self):
        self.xy_calls = []
        self.z_calls = []
        self.xz_calls = []
        self.yz_calls = []

    def setXY_Position(self, x, y, velocity=None, acceleration=None, deceleration=None):
        self.xy_calls.append((x, y, velocity, acceleration, deceleration))

    def setZ_Position(self, position, velocity=None):
        self.z_calls.append((position, velocity))

    def setXZ_Position(self, x, z, velocity=None):
        self.xz_calls.append((x, z, velocity))

    def setYZ_Position(self, y, z, velocity=None):
        self.yz_calls.append((y, z, velocity))


class _IO:
    def __init__(
        self,
        x_position=0.0,
        y_position=0.0,
        z_position=0.0,
        y_transfer_ok=False,
        x_transfer_ok=False,
        frame_locks=None,
    ):
        self.xAxis = _Axis(x_position)
        self.yAxis = _Axis(y_position)
        self.zAxis = _Axis(z_position)
        self.plcLogic = _PLCLogic()
        self.X_Transfer_OK = _Signal(x_transfer_ok)
        self.Y_Transfer_OK = _Signal(y_transfer_ok)

        locks = frame_locks or {}
        for name in (
            "FrameLockHeadTop",
            "FrameLockHeadMid",
            "FrameLockHeadBtm",
            "FrameLockFootTop",
            "FrameLockFootMid",
            "FrameLockFootBtm",
        ):
            setattr(self, name, _Signal(bool(locks.get(name, False))))


class _ControlStateMachine:
    def __init__(self):
        self.events = []

    def isReadyForMovement(self):
        return True

    def isJogging(self):
        return False

    def dispatch(self, event):
        self.events.append(event)
        return True


class _Log:
    def __init__(self):
        self.entries = []

    def add(self, source, code, message, data=None):
        self.entries.append((source, code, message, data))


def _build_safety(io, *, z_collision_threshold=100.0):
    safety = object.__new__(SafetyValidationService)
    safety._io = io
    safety._controlStateMachine = None
    safety._maxVelocity = 300.0
    safety._maxSlowVelocity = 50.0
    safety._transferLeft = -1000.0
    safety._transferRight = 10000.0
    safety._transferLeftMargin = 10.0
    safety._transferYThreshold = 1000.0
    safety._limitLeft = -1000.0
    safety._limitRight = 10000.0
    safety._limitTop = 10000.0
    safety._limitBottom = -1000.0
    safety._zlimitFront = 0.0
    safety._zlimitRear = 100.0
    safety._headwardPivotX = 150.0
    safety._headwardPivotY = 1400.0
    safety._headwardPivotXTolerance = 150.0
    safety._headwardPivotYTolerance = 300.0
    safety._queuedMotionZCollisionThreshold = float(z_collision_threshold)
    safety._arcMaxStepRad = 0.0523598
    safety._arcMaxChord = 5.0
    safety._apaCollisionBottomY = 50.0
    safety._apaCollisionTopY = 2250.0
    safety._transferZoneHeadMinX = 400.0
    safety._transferZoneHeadMaxX = 500.0
    safety._transferZoneFootMinX = 7100.0
    safety._transferZoneFootMaxX = 7200.0
    safety._supportCollisionBottomMinY = 80.0
    safety._supportCollisionBottomMaxY = 450.0
    safety._supportCollisionMiddleMinY = 1050.0
    safety._supportCollisionMiddleMaxY = 1550.0
    safety._supportCollisionTopMinY = 2200.0
    safety._supportCollisionTopMaxY = 2650.0
    safety._geometryEpsilon = 1e-9
    return safety


def _build_service(io, control=None, log=None):
    if control is None:
        control = _ControlStateMachine()
    if log is None:
        log = _Log()
    safety = _build_safety(io)
    backlash = XBacklashCompensation(0.0)
    service = MotionService(
        io,
        log,
        control,
        safety,
        gCodeHandler=None,
        headCompensation=None,
        xBacklash=backlash,
        workspaceGetter=lambda: None,
    )
    return service, control, log


class XZJogConversionTests(unittest.TestCase):
    def test_x_only_jog_in_y_transfer_zone_dispatches_xz(self):
        io = _IO(x_position=420.0, y_position=200.0, z_position=42.0, y_transfer_ok=True)
        service, control, _ = _build_service(io)

        is_error = service.manualSeekXY(xPosition=430.0, velocity=100.0)

        self.assertFalse(is_error)
        self.assertEqual(io.plcLogic.xy_calls, [])
        self.assertEqual(len(control.events), 1)
        event = control.events[0]
        self.assertIsInstance(event, ManualModeEvent)
        self.assertEqual(event.combinedAxis, "XZ")
        self.assertAlmostEqual(event.seekX, 430.0)
        self.assertAlmostEqual(event.seekZ, 42.0)
        self.assertIsNone(event.seekY)

    def test_x_only_jog_outside_y_transfer_zone_uses_xy_path(self):
        io = _IO(x_position=600.0, y_position=200.0, z_position=42.0, y_transfer_ok=False)
        service, control, _ = _build_service(io)

        is_error = service.manualSeekXY(xPosition=610.0, velocity=100.0)

        self.assertFalse(is_error)
        self.assertEqual(len(control.events), 1)
        event = control.events[0]
        self.assertIsNone(event.combinedAxis)
        self.assertAlmostEqual(event.seekX, 610.0)
        self.assertEqual(event.seekY, None)
        self.assertIsNone(event.seekZ)

    def test_xy_seek_with_both_axes_does_not_convert(self):
        io = _IO(x_position=420.0, y_position=200.0, z_position=42.0, y_transfer_ok=True)
        service, control, _ = _build_service(io)

        is_error = service.manualSeekXY(xPosition=430.0, yPosition=210.0, velocity=100.0)

        self.assertFalse(is_error)
        self.assertEqual(len(control.events), 1)
        event = control.events[0]
        self.assertIsNone(event.combinedAxis)
        self.assertAlmostEqual(event.seekX, 430.0)
        self.assertAlmostEqual(event.seekY, 210.0)


class YZJogConversionTests(unittest.TestCase):
    def test_y_only_jog_in_x_transfer_zone_dispatches_yz(self):
        io = _IO(
            x_position=450.0,
            y_position=800.0,
            z_position=42.0,
            x_transfer_ok=True,
        )
        service, control, _ = _build_service(io)

        is_error = service.manualSeekXY(yPosition=820.0, velocity=100.0)

        self.assertFalse(is_error)
        self.assertEqual(len(control.events), 1)
        event = control.events[0]
        self.assertEqual(event.combinedAxis, "YZ")
        self.assertAlmostEqual(event.seekY, 820.0)
        self.assertAlmostEqual(event.seekZ, 42.0)
        self.assertIsNone(event.seekX)

    def test_y_only_jog_outside_x_transfer_zone_uses_xy_path(self):
        io = _IO(
            x_position=450.0,
            y_position=800.0,
            z_position=42.0,
            x_transfer_ok=False,
        )
        service, control, _ = _build_service(io)

        is_error = service.manualSeekXY(yPosition=820.0, velocity=100.0)

        self.assertFalse(is_error)
        event = control.events[-1]
        self.assertIsNone(event.combinedAxis)
        self.assertAlmostEqual(event.seekY, 820.0)

    def test_yz_jog_refused_when_target_in_active_frame_lock_keepout(self):
        io = _IO(
            x_position=450.0,
            y_position=800.0,
            z_position=200.0,
            x_transfer_ok=True,
            frame_locks={"FrameLockHeadBtm": True},
        )
        service, control, log = _build_service(io)

        is_error = service.manualSeekXY(yPosition=200.0, velocity=100.0)

        self.assertTrue(is_error)
        self.assertEqual(control.events, [])
        ignored = [e for e in log.entries if e[2] == "Manual move YZ ignored."]
        self.assertEqual(len(ignored), 1)

    def test_yz_jog_allowed_when_z_is_retracted_below_threshold(self):
        io = _IO(
            x_position=450.0,
            y_position=800.0,
            z_position=10.0,
            x_transfer_ok=True,
            frame_locks={"FrameLockHeadBtm": True},
        )
        service, control, _ = _build_service(io)

        is_error = service.manualSeekXY(yPosition=200.0, velocity=100.0)

        self.assertFalse(is_error)
        event = control.events[0]
        self.assertEqual(event.combinedAxis, "YZ")
        self.assertAlmostEqual(event.seekY, 200.0)


if __name__ == "__main__":
    unittest.main()
