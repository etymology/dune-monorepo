import time
import unittest
from unittest.mock import patch

from dune_winder.gcode.handler import GCodeHandler
from dune_winder.gcode.runtime import GCodeProgramExecutor
from dune_winder.io.devices.plc import PLC
from dune_winder.io.devices.simulated_plc import SimulatedPLC
from dune_winder.machine.calibration.defaults import DefaultMachineCalibration
from dune_winder.machine.head_compensation import WirePathModel
from dune_winder.queued_motion.plc_interface import QueuedMotionPLCInterface
from dune_winder.queued_motion.queue_client import MotionQueueClient
from dune_winder.queued_motion.queue_session import QueuedMotionSession
from dune_winder.queued_motion.safety import MotionSafetyLimits
from dune_winder.queued_motion.segment_types import MotionSegment


class _Axis:
  def __init__(self, position):
    self._position = float(position)

  def getPosition(self):
    return self._position


class _Input:
  def __init__(self, value=False):
    self._value = bool(value)

  def get(self):
    return self._value


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
  def __init__(self, x, y, z=0.0, plc_logic=None, **locks):
    self.xAxis = _Axis(x)
    self.yAxis = _Axis(y)
    self.zAxis = _Axis(z)
    self.plcLogic = _QueuedMotionPLCLogic() if plc_logic is None else plc_logic
    self.head = _Head()
    self.FrameLockHeadTop = _Input(locks.get("frame_lock_head_top", False))
    self.FrameLockHeadMid = _Input(locks.get("frame_lock_head_mid", False))
    self.FrameLockHeadBtm = _Input(locks.get("frame_lock_head_btm", False))
    self.FrameLockFootTop = _Input(locks.get("frame_lock_foot_top", False))
    self.FrameLockFootMid = _Input(locks.get("frame_lock_foot_mid", False))
    self.FrameLockFootBtm = _Input(locks.get("frame_lock_foot_btm", False))


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
    self.FrameLockHeadTop = _Input(bool(plc.get_tag("MACHINE_SW_STAT[26]")))
    self.FrameLockHeadMid = _Input(bool(plc.get_tag("MACHINE_SW_STAT[27]")))
    self.FrameLockHeadBtm = _Input(bool(plc.get_tag("MACHINE_SW_STAT[28]")))
    self.FrameLockFootTop = _Input(bool(plc.get_tag("MACHINE_SW_STAT[29]")))
    self.FrameLockFootMid = _Input(bool(plc.get_tag("MACHINE_SW_STAT[30]")))
    self.FrameLockFootBtm = _Input(bool(plc.get_tag("MACHINE_SW_STAT[31]")))


class _FakeClock:
  def __init__(self):
    self.now = 0.0

  def __call__(self):
    return self.now

  def advance(self, delta=0.11):
    self.now += float(delta)


class QueuedMotionTests(unittest.TestCase):
  def _z_collision_calibration(self):
    calibration = DefaultMachineCalibration()
    calibration.queuedMotionZCollisionThreshold = 100.0
    return calibration

  def _z_collision_limits(self):
    return MotionSafetyLimits(
      limit_left=0.0,
      limit_right=7360.0,
      limit_bottom=0.0,
      limit_top=3000.0,
      transfer_left=0.0,
      transfer_right=7360.0,
      transfer_left_margin=0.0,
      transfer_y_threshold=10000.0,
      headward_pivot_x=9000.0,
      headward_pivot_y=9000.0,
      headward_pivot_x_tolerance=0.0,
      headward_pivot_y_tolerance=0.0,
      queued_motion_z_collision_threshold=100.0,
      arc_max_step_rad=0.05235987755982989,  # radians(3.0)
      arc_max_chord=5.0,
      apa_collision_bottom_y=50.0,
      apa_collision_top_y=2250.0,
      transfer_zone_head_min_x=400.0,
      transfer_zone_head_max_x=500.0,
      transfer_zone_foot_min_x=7100.0,
      transfer_zone_foot_max_x=7200.0,
      support_collision_bottom_min_y=80.0,
      support_collision_bottom_max_y=450.0,
      support_collision_middle_min_y=1050.0,
      support_collision_middle_max_y=1550.0,
      support_collision_top_min_y=2200.0,
      support_collision_top_max_y=2650.0,
      geometry_epsilon=1e-9,
    )

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

  def test_start_queued_block_falls_back_when_queue_planner_rejects_path(self):
    calibration = DefaultMachineCalibration()
    handler = GCodeHandler(_IO(400.0, 100.0), calibration, WirePathModel(calibration))

    with patch.object(handler, "_build_queued_block", side_effect=ValueError("queued path invalid")):
      started = handler._start_queued_block(0)

    self.assertFalse(started)
    self.assertIsNone(handler._queued_session)

  def test_sub_resolution_xy_move_is_treated_as_noop(self):
    calibration = self._z_collision_calibration()
    handler = GCodeHandler(_IO(1000.0, 150.0, z=200.0), calibration, WirePathModel(calibration))

    error = handler.executeG_CodeLine("G113 PPRECISE X1000.05 Y150.00")

    self.assertIsNone(error)
    self.assertEqual(handler._io.plcLogic.legacy_xy_moves, [])

  def test_gcode_builder_rejects_central_apa_motion_when_z_extended(self):
    calibration = self._z_collision_calibration()
    handler = GCodeHandler(_IO(1000.0, 25.0, z=200.0), calibration, WirePathModel(calibration))
    handler._x = 1000.0
    handler._y = 25.0
    handler._z = 200.0
    handler._gCode = GCodeProgramExecutor(
      ["G113 PPRECISE X1000.0 Y150.0"],
      handler._callbacks,
    )

    with self.assertRaisesRegex(ValueError, "Unable to build a valid queued path"):
      handler._build_queued_block(0)

  def test_gcode_builder_allows_head_transfer_motion_when_supports_clear(self):
    calibration = self._z_collision_calibration()
    handler = GCodeHandler(_IO(450.0, 25.0, z=200.0), calibration, WirePathModel(calibration))
    handler._x = 450.0
    handler._y = 25.0
    handler._z = 200.0
    handler._gCode = GCodeProgramExecutor(
      ["G113 PPRECISE X450.0 Y2100.0"],
      handler._callbacks,
    )

    block = handler._build_queued_block(0)

    self.assertIsNotNone(block)
    self.assertEqual(len(block["segments"]), 1)
    self.assertEqual(block["segments"][0].x, 450.0)
    self.assertEqual(block["segments"][0].y, 2100.0)

  def test_gcode_builder_rejects_locked_head_support_window(self):
    calibration = self._z_collision_calibration()
    handler = GCodeHandler(
      _IO(450.0, 25.0, z=200.0, frame_lock_head_btm=True),
      calibration,
      WirePathModel(calibration),
    )
    handler._x = 450.0
    handler._y = 25.0
    handler._z = 200.0
    handler._gCode = GCodeProgramExecutor(
      ["G113 PPRECISE X450.0 Y500.0"],
      handler._callbacks,
    )

    with self.assertRaisesRegex(ValueError, "Unable to build a valid queued path"):
      handler._build_queued_block(0)

  def test_motion_queue_client_rejects_unsafe_segment_and_accepts_transfer_zone_segment(self):
    with MotionQueueClient("SIM") as motion:
      motion._safety_limits = self._z_collision_limits()
      motion._plc.set_tag("X_axis.ActualPosition", 450.0)
      motion._plc.set_tag("Y_axis.ActualPosition", 25.0)
      motion._plc.set_tag("Z_axis.ActualPosition", 200.0)
      motion._plc.set_tag("MACHINE_SW_STAT[26]", 0)
      motion._plc.set_tag("MACHINE_SW_STAT[27]", 0)
      motion._plc.set_tag("MACHINE_SW_STAT[28]", 0)
      motion._plc.set_tag("MACHINE_SW_STAT[29]", 0)
      motion._plc.set_tag("MACHINE_SW_STAT[30]", 0)
      motion._plc.set_tag("MACHINE_SW_STAT[31]", 0)
      motion.reset_queue()

      with self.assertRaisesRegex(ValueError, "APA collision zone"):
        motion.enqueue_segment(MotionSegment(seq=1, x=1000.0, y=150.0))

      motion.enqueue_segment(MotionSegment(seq=2, x=450.0, y=2100.0))
      motion._require_queue().poll()

      self.assertEqual(motion._require_queue().status().ack, 2)
      self.assertEqual(motion._last_point, (450.0, 2100.0))


if __name__ == "__main__":
  unittest.main()

