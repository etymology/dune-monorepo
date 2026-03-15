import unittest

from dune_winder.gcode.handler import GCodeHandler
from dune_winder.gcode.runtime import GCodeProgramExecutor
from dune_winder.io.devices.plc import PLC
from dune_winder.io.devices.simulated_plc import SimulatedPLC
from dune_winder.machine.calibration.defaults import DefaultMachineCalibration
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.queued_motion.plc_interface import QueuedMotionPLCInterface
from dune_winder.queued_motion.queue_session import QueuedMotionSession
from dune_winder.queued_motion.segment_types import MotionSegment


class _Axis:
  def __init__(self, position):
    self._position = float(position)

  def getPosition(self):
    return self._position


class _QueuedMotionPLCLogic:
  def __init__(self):
    self._maxAcceleration = 1000.0
    self._maxDeceleration = 1000.0
    self.queuedMotion = object()

  def isReady(self):
    return True

  def setXY_Position(self, x, y, velocity=None, acceleration=None, deceleration=None):
    raise AssertionError("Legacy XY motion should not be used during queued-block preview")

  def setZ_Position(self, z, velocity=None):
    raise AssertionError("Unexpected Z move")

  def move_latch(self):
    raise AssertionError("Unexpected latch move")


class _Head:
  def isReady(self):
    return True

  def readCurrentPosition(self):
    return 0

  def setHeadPosition(self, position, velocity=None):
    raise AssertionError("Unexpected head move")

  def stop(self):
    return None

  def getTargetAxisPosition(self):
    return 0.0


class _IO:
  def __init__(self, x, y, z=0.0):
    self.xAxis = _Axis(x)
    self.yAxis = _Axis(y)
    self.zAxis = _Axis(z)
    self.plcLogic = _QueuedMotionPLCLogic()
    self.head = _Head()


class _FakeClock:
  def __init__(self):
    self.now = 0.0

  def __call__(self):
    return self.now

  def advance(self, delta=0.11):
    self.now += float(delta)


class QueuedMotionTests(unittest.TestCase):
  def setUp(self):
    self._saved_tag_instances = list(PLC.Tag.instances)
    self._saved_tag_lookup = dict(PLC.Tag.tag_lookup_table)
    PLC.Tag.instances = []
    PLC.Tag.tag_lookup_table = {}

  def tearDown(self):
    PLC.Tag.instances = self._saved_tag_instances
    PLC.Tag.tag_lookup_table = self._saved_tag_lookup

  def test_single_segment_session_runs_to_idle(self):
    plc = SimulatedPLC("SIM")
    queue = QueuedMotionPLCInterface(plc)
    clock = _FakeClock()
    session = QueuedMotionSession(
      queue,
      [MotionSegment(seq=101, x=125.0, y=250.0)],
      now_fn=clock,
    )

    for _ in range(20):
      session.advance()
      if session.done or session.error:
        break
      clock.advance()

    self.assertTrue(session.done)
    self.assertIsNone(session.error)

    queue.poll()
    status = queue.status()
    self.assertTrue(status.is_idle)
    self.assertEqual(status.ack, 101)
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 125.0, places=6)
    self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), 250.0, places=6)

  def test_gcode_builder_keeps_single_merge_line_as_queued_block(self):
    calibration = DefaultMachineCalibration()
    handler = GCodeHandler(_IO(400.0, 100.0), calibration, WirePathModel(calibration))
    handler._x = 400.0
    handler._y = 100.0
    handler._z = 0.0
    handler._gCode = GCodeProgramExecutor(
      ["G113 PPRECISE X500.0 Y200.0"],
      handler._callbacks,
    )

    block = handler._build_queued_block(0)

    self.assertIsNotNone(block)
    self.assertEqual(block["start_line"], 0)
    self.assertEqual(block["resume_line"], 1)
    self.assertEqual(len(block["segments"]), 1)
    segment = block["segments"][0]
    self.assertEqual(segment.seq, 1000)
    self.assertEqual(segment.x, 500.0)
    self.assertEqual(segment.y, 200.0)


if __name__ == "__main__":
  unittest.main()
