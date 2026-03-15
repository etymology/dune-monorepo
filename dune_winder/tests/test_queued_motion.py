import time
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
  def __init__(self, queued_motion=None):
    self._maxAcceleration = 1000.0
    self._maxDeceleration = 1000.0
    self.queuedMotion = object() if queued_motion is None else queued_motion
    self.legacy_xy_moves = []

  def isReady(self):
    return True

  def setXY_Position(self, x, y, velocity=None, acceleration=None, deceleration=None):
    self.legacy_xy_moves.append((float(x), float(y), velocity, acceleration, deceleration))

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
  def __init__(self, x, y, z=0.0, plc_logic=None):
    self.xAxis = _Axis(x)
    self.yAxis = _Axis(y)
    self.zAxis = _Axis(z)
    self.plcLogic = _QueuedMotionPLCLogic() if plc_logic is None else plc_logic
    self.head = _Head()


class _PLCTagAxis:
  def __init__(self, plc, tag_name):
    self._plc = plc
    self._tag_name = str(tag_name)

  def getPosition(self):
    return float(self._plc.get_tag(self._tag_name))


class _RuntimeQueuedMotionIO:
  def __init__(self, plc):
    plc_logic = _QueuedMotionPLCLogic(queued_motion=QueuedMotionPLCInterface(plc))
    self.xAxis = _PLCTagAxis(plc, "X_axis.ActualPosition")
    self.yAxis = _PLCTagAxis(plc, "Y_axis.ActualPosition")
    self.zAxis = _PLCTagAxis(plc, "Z_axis.ActualPosition")
    self.plcLogic = plc_logic
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

  def test_single_step_g113_queues_first_planned_segment_with_full_stop(self):
    calibration = DefaultMachineCalibration()
    merge_lines = [
      "G113 PPRECISE X500.0 Y100.0",
      "G113 PPRECISE X550.0 Y150.0",
    ]
    preview_handler = GCodeHandler(_IO(400.0, 100.0), calibration, WirePathModel(calibration))
    preview_handler._x = 400.0
    preview_handler._y = 100.0
    preview_handler._z = 0.0
    preview_handler._gCode = GCodeProgramExecutor(
      merge_lines,
      preview_handler._callbacks,
    )

    full_block = preview_handler._build_queued_block(0)
    self.assertIsNotNone(full_block)
    full_first_segment = full_block["segments"][0]
    self.assertEqual(full_first_segment.term_type, 4)
    self.assertEqual(full_block["resume_line"], 2)

    stepped_handler = GCodeHandler(_IO(400.0, 100.0), calibration, WirePathModel(calibration))
    stepped_handler._x = 400.0
    stepped_handler._y = 100.0
    stepped_handler._z = 0.0
    stepped_handler._gCode = GCodeProgramExecutor(
      merge_lines,
      stepped_handler._callbacks,
    )

    stepped_block = stepped_handler._build_queued_block(0, single_step_queue=True)

    self.assertIsNotNone(stepped_block)
    self.assertEqual(stepped_block["resume_line"], 1)
    self.assertTrue(stepped_block["stop_after_block"])
    self.assertEqual(len(stepped_block["segments"]), 1)
    stepped_segment = stepped_block["segments"][0]
    self.assertEqual(stepped_segment.term_type, 0)
    self.assertEqual(stepped_segment.seq, full_first_segment.seq)
    self.assertEqual(stepped_segment.seg_type, full_first_segment.seg_type)
    self.assertAlmostEqual(stepped_segment.x, full_first_segment.x, places=6)
    self.assertAlmostEqual(stepped_segment.y, full_first_segment.y, places=6)
    self.assertAlmostEqual(stepped_segment.via_center_x, full_first_segment.via_center_x, places=6)
    self.assertAlmostEqual(stepped_segment.via_center_y, full_first_segment.via_center_y, places=6)
    self.assertEqual(stepped_segment.direction, full_first_segment.direction)

  def test_single_step_g113_executes_queue_and_stops_before_next_line(self):
    plc = SimulatedPLC("SIM")
    plc.set_tag("X_axis.ActualPosition", 400.0)
    plc.set_tag("Y_axis.ActualPosition", 100.0)
    calibration = DefaultMachineCalibration()
    merge_lines = [
      "G113 PPRECISE X500.0 Y100.0",
      "G113 PPRECISE X550.0 Y150.0",
    ]
    handler = GCodeHandler(_RuntimeQueuedMotionIO(plc), calibration, WirePathModel(calibration))
    handler.loadG_Code(
      merge_lines,
      None,
    )
    handler.singleStep = True

    preview_handler = GCodeHandler(_IO(400.0, 100.0), calibration, WirePathModel(calibration))
    preview_handler._x = 400.0
    preview_handler._y = 100.0
    preview_handler._z = 0.0
    preview_handler._gCode = GCodeProgramExecutor(
      merge_lines,
      preview_handler._callbacks,
    )
    expected_segment = preview_handler._build_queued_block(0, single_step_queue=True)["segments"][0]

    stopped = False
    for _ in range(12):
      stopped = handler.poll()
      if stopped and handler._queued_session is None:
        break
      time.sleep(0.12)

    self.assertTrue(stopped)
    self.assertIsNone(handler._queued_session)
    self.assertEqual(handler._currentLine, 0)
    self.assertEqual(handler._nextLine, 0)
    self.assertEqual(handler._queued_stop_mode, None)
    self.assertEqual(handler._io.plcLogic.legacy_xy_moves, [])
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), expected_segment.x, places=6)
    self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), expected_segment.y, places=6)
    self.assertEqual(plc.get_tag("IncomingSeg")["TermType"], 0)


if __name__ == "__main__":
  unittest.main()
