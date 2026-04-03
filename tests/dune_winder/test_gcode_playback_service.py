import unittest

from dune_winder.core.control_events import StopMotionEvent
from dune_winder.core.gcode_playback_service import GCodePlaybackService
from dune_winder.core.x_backlash_compensation import XBacklashCompensation


class _FakeGCodeHandler:
  def __init__(self):
    self.stop_next_calls = 0

  def isG_CodeLoaded(self):
    return False

  def stopNext(self):
    self.stop_next_calls += 1


class _FakeControlStateMachine:
  def __init__(self, in_motion):
    self._in_motion = in_motion
    self.dispatched = []

  def isInMotion(self):
    return self._in_motion

  def isReadyForMovement(self):
    return False

  def dispatch(self, event):
    self.dispatched.append(event)


class _FakeLog:
  def __init__(self):
    self.records = []

  def add(self, *args):
    self.records.append(args)


class _FakeAxis:
  def __init__(self, seeking=False):
    self._seeking = seeking

  def isSeeking(self):
    return self._seeking


class _FakePLCLogic:
  def __init__(self, ready=True):
    self._ready = ready
    self.stop_requests = 0

  def isReady(self):
    return self._ready

  def stopSeek(self):
    self.stop_requests += 1


class _FakeHead:
  def __init__(self, ready=True):
    self._ready = ready
    self.stop_requests = 0
    self._error = False

  def isReady(self):
    return self._ready

  def hasError(self):
    return self._error

  def getLastError(self):
    return ""

  def stop(self):
    self.stop_requests += 1


class _FakeIO:
  def __init__(self, *, plc_ready=True, axis_seeking=False, head_ready=True):
    self.plcLogic = _FakePLCLogic(plc_ready)
    self.xAxis = _FakeAxis(axis_seeking)
    self.yAxis = _FakeAxis(False)
    self.zAxis = _FakeAxis(axis_seeking)
    self.head = _FakeHead(head_ready)


class GCodePlaybackServiceTests(unittest.TestCase):
  def _build_service(self, *, in_motion, plc_ready=True, axis_seeking=False, head_ready=True):
    return GCodePlaybackService(
      _FakeGCodeHandler(),
      _FakeControlStateMachine(in_motion),
      _FakeLog(),
      _FakeIO(plc_ready=plc_ready, axis_seeking=axis_seeking, head_ready=head_ready),
      safety=None,
      xBacklash=XBacklashCompensation(),
      workspaceGetter=lambda: None,
    )

  def test_stop_always_issues_direct_hmi_stop_and_dispatches_event_while_in_motion(self):
    service = self._build_service(in_motion=True)

    service.stop()

    self.assertEqual(len(service._controlStateMachine.dispatched), 1)
    self.assertIsInstance(service._controlStateMachine.dispatched[0], StopMotionEvent)
    self.assertEqual(service._io.plcLogic.stop_requests, 1)
    self.assertEqual(service._io.head.stop_requests, 1)

  def test_stop_issues_direct_hmi_stop_even_when_control_state_machine_is_idle(self):
    service = self._build_service(in_motion=False, plc_ready=True, axis_seeking=False, head_ready=True)

    service.stop()

    self.assertEqual(service._controlStateMachine.dispatched, [])
    self.assertEqual(service._io.plcLogic.stop_requests, 1)
    self.assertEqual(service._io.head.stop_requests, 1)


if __name__ == "__main__":
  unittest.main()
