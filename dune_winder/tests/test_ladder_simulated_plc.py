from __future__ import annotations

import math
import unittest

from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC
from dune_winder.queued_motion.segment_patterns import _segment_tangent_component_bounds
from dune_winder.queued_motion.segment_types import MotionSegment
from dune_winder.queued_motion.segment_types import CIRCLE_TYPE_CENTER
from dune_winder.queued_motion.segment_types import MCCM_DIR_2D_CCW
from dune_winder.queued_motion.segment_types import SEG_TYPE_CIRCLE


class LadderSimulatedPlcTests(unittest.TestCase):
  def _advance(self, plc: LadderSimulatedPLC, scans: int = 1):
    for _ in range(scans):
      plc.read("STATE")

  def _advance_until(self, plc: LadderSimulatedPLC, predicate, limit: int = 50):
    for _ in range(limit):
      plc.read("STATE")
      if predicate():
        return
    self.fail("Timed out waiting for ladder simulator condition.")

  def _enqueue_segment(self, plc: LadderSimulatedPLC, req_id: int, segment: MotionSegment):
    plc.set_tag(
      "IncomingSeg",
      {
        "Valid": True,
        "SegType": segment.seg_type,
        "XY": [segment.x, segment.y],
        "Speed": segment.speed,
        "Accel": segment.accel,
        "Decel": segment.decel,
        "JerkAccel": segment.jerk_accel,
        "JerkDecel": segment.jerk_decel,
        "TermType": segment.term_type,
        "Seq": segment.seq,
        "CircleType": segment.circle_type,
        "ViaCenter": [segment.via_center_x, segment.via_center_y],
        "Direction": segment.direction,
      },
    )
    plc.set_tag("IncomingSegReqID", req_id)
    self._advance_until(plc, lambda: plc.get_tag("IncomingSegAck") == req_id)

  def _expected_capped_speed(
    self,
    start_xy: tuple[float, float],
    segment: MotionSegment,
    v_x_max: float,
    v_y_max: float,
  ) -> float:
    max_tx, max_ty = _segment_tangent_component_bounds(start_xy[0], start_xy[1], segment)
    limit_x = math.inf if max_tx <= 1e-9 else (v_x_max / max_tx)
    limit_y = math.inf if max_ty <= 1e-9 else (v_y_max / max_ty)
    return min(float(segment.speed), limit_x, limit_y)

  def _assert_capped_to_axis_components(
    self,
    speed: float,
    start_xy: tuple[float, float],
    segment: MotionSegment,
    v_x_max: float,
    v_y_max: float,
  ):
    max_tx, max_ty = _segment_tangent_component_bounds(start_xy[0], start_xy[1], segment)
    self.assertLessEqual(speed * max_tx, v_x_max + 1e-6)
    self.assertLessEqual(speed * max_ty, v_y_max + 1e-6)

  def test_initial_state_uses_ladder_seeded_tags(self):
    plc = LadderSimulatedPLC("SIM")

    self.assertEqual(plc.get_status()["simEngine"], "LADDER")
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_READY)
    self.assertEqual(plc.get_tag("ERROR_CODE"), 0)
    self.assertEqual(plc.get_tag("HEAD_POS"), 0)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 0)
    self.assertTrue(plc.get_tag("MACHINE_SW_STAT[6]"))
    self.assertFalse(plc.get_tag("MACHINE_SW_STAT[7]"))
    self.assertEqual(plc.get_tag("QueueCtl.POS"), 0)

  def test_xy_seek_move_reaches_target_and_returns_ready(self):
    plc = LadderSimulatedPLC("SIM")
    plc.write(("X_POSITION", 123.4))
    plc.write(("Y_POSITION", 456.7))
    plc.write(("XY_SPEED", 1000.0))
    plc.write(("XY_ACCELERATION", 1000.0))
    plc.write(("XY_DECELERATION", 1000.0))
    plc.write(("MOVE_TYPE", plc.MOVE_SEEK_XY))

    self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)

    self.assertEqual(plc.get_tag("MOVE_TYPE"), 0)
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 123.4, places=6)
    self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), 456.7, places=6)
    self.assertTrue(plc.get_tag("main_xy_move.PC"))

  def test_xy_seek_move_reaches_target_with_imperative_backend(self):
    plc = LadderSimulatedPLC("SIM", routine_backend="imperative")
    plc.write(("X_POSITION", 123.4))
    plc.write(("Y_POSITION", 456.7))
    plc.write(("XY_SPEED", 1000.0))
    plc.write(("XY_ACCELERATION", 1000.0))
    plc.write(("XY_DECELERATION", 1000.0))
    plc.write(("MOVE_TYPE", plc.MOVE_SEEK_XY))

    self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)

    self.assertEqual(plc.get_tag("MOVE_TYPE"), 0)
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 123.4, places=6)
    self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), 456.7, places=6)
    self.assertTrue(plc.get_tag("main_xy_move.PC"))

  def test_latch_stub_cycles_positions_without_stalling_state_machine(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag("HEAD_POS", 0)
    plc.set_tag("ACTUATOR_POS", 0)

    plc.write(("MOVE_TYPE", plc.MOVE_LATCH))
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCHING)
    self._advance(plc)
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCHING)
    self.assertEqual(plc.get_tag("PREV_ACT_POS"), 0)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 1)
    self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 1)
    self.assertEqual(plc.get_tag("HEAD_POS"), 0)

    plc.write(("MOVE_TYPE", plc.MOVE_LATCH))
    self._advance(plc)
    self.assertEqual(plc.get_tag("PREV_ACT_POS"), 1)
    self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 2)
    self.assertEqual(plc.get_tag("HEAD_POS"), 3)

    plc.write(("MOVE_TYPE", plc.MOVE_LATCH))
    self._advance(plc)
    self.assertEqual(plc.get_tag("PREV_ACT_POS"), 2)
    self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 0)
    self.assertEqual(plc.get_tag("HEAD_POS"), 3)

  def test_latch_home_and_unlock_stub_update_homed_status(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag("HEAD_POS", 3)
    plc.set_tag("ACTUATOR_POS", 2)
    plc.set_tag("LATCH_ACTUATOR_HOMED", False)

    plc.write(("MOVE_TYPE", plc.MOVE_LATCH_UNLOCK))
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCH_RELEASE)
    self._advance(plc)
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCH_RELEASE)
    self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 2)
    self.assertFalse(plc.get_tag("LATCH_ACTUATOR_HOMED"))
    self.assertFalse(plc.get_tag("MACHINE_SW_STAT[0]"))

    plc.write(("MOVE_TYPE", plc.MOVE_HOME_LATCH))
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCH_HOMEING)
    self._advance(plc)
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_LATCH_HOMEING)
    self._advance_until(plc, lambda: plc.get_tag("STATE") == plc.STATE_READY)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 0)
    self.assertTrue(plc.get_tag("LATCH_ACTUATOR_HOMED"))
    self.assertTrue(plc.get_tag("MACHINE_SW_STAT[0]"))

  def test_xz_seek_respects_transfer_override(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag("MACHINE_SW_STAT[17]", 0, override=True)
    plc.write(("xz_position_target", [321.0, 210.5]))
    plc.write(("MOVE_TYPE", plc.MOVE_SEEK_XZ))

    self._advance(plc, 2)

    self.assertEqual(plc.get_tag("STATE"), plc.STATE_ERROR)
    self.assertEqual(plc.get_tag("ERROR_CODE"), 5003)
    self.assertFalse(plc.get_tag("Y_XFER_OK"))
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 0.0, places=6)
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 0.0, places=6)

  def test_queue_segment_enqueues_and_executes_via_motion_queue_routine(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag(
      "IncomingSeg",
      {
        "Valid": True,
        "SegType": 1,
        "XY": [125.0, 250.0],
        "Speed": 1000.0,
        "Accel": 2000.0,
        "Decel": 2000.0,
        "JerkAccel": 1500.0,
        "JerkDecel": 3000.0,
        "TermType": 3,
        "Seq": 1,
        "CircleType": 1,
        "ViaCenter": [0.0, 0.0],
        "Direction": 1,
      },
    )
    plc.set_tag("IncomingSegReqID", 1)

    self._advance_until(plc, lambda: plc.get_tag("QueueCount") == 1)

    self.assertEqual(plc.get_tag("IncomingSegAck"), 1)
    self.assertEqual(plc.get_tag("LastIncomingSegReqID"), 1)

    plc.set_tag("StartQueuedPath", 1)
    self._advance_until(
      plc,
      lambda: (
        plc.get_tag("STATE") == plc.STATE_READY
        and not plc.get_tag("CurIssued")
        and plc.get_tag("QueueCount") == 0
      ),
    )

    self.assertEqual(plc.get_tag("QueueCount"), 0)
    self.assertFalse(plc.get_tag("CurIssued"))
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 125.0, places=6)
    self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), 250.0, places=6)

  def test_queue_circle_segment_executes_via_motion_queue_routine(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag(
      "IncomingSeg",
      {
        "Valid": True,
        "SegType": SEG_TYPE_CIRCLE,
        "XY": [100.0, 100.0],
        "Speed": 800.0,
        "Accel": 1600.0,
        "Decel": 1600.0,
        "JerkAccel": 1500.0,
        "JerkDecel": 3000.0,
        "TermType": 3,
        "Seq": 2,
        "CircleType": CIRCLE_TYPE_CENTER,
        "ViaCenter": [0.0, 100.0],
        "Direction": MCCM_DIR_2D_CCW,
      },
    )
    plc.set_tag("IncomingSegReqID", 2)

    self._advance_until(plc, lambda: plc.get_tag("QueueCount") == 1)

    plc.set_tag("StartQueuedPath", 1)
    self._advance_until(
      plc,
      lambda: (
        plc.get_tag("STATE") == plc.STATE_READY
        and not plc.get_tag("CurIssued")
        and plc.get_tag("QueueCount") == 0
      ),
      limit=100,
    )

    self.assertEqual(plc.get_tag("IncomingSegAck"), 2)
    self.assertEqual(plc.get_tag("QueueCount"), 0)
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 100.0, places=6)
    self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), 100.0, places=6)

  def test_queue_start_caps_diagonal_segment_before_cmd_a_issue(self):
    plc = LadderSimulatedPLC("SIM")
    v_x_max = 300.0
    v_y_max = 200.0
    segment = MotionSegment(seq=1, x=100.0, y=100.0, speed=9999.0)

    plc.set_tag("v_x_max", v_x_max)
    plc.set_tag("v_y_max", v_y_max)
    self._enqueue_segment(plc, 1, segment)

    plc.set_tag("StartQueuedPath", 1)
    self._advance_until(plc, lambda: plc.get_tag("CurSeg.Seq") == segment.seq)

    expected_speed = self._expected_capped_speed((0.0, 0.0), segment, v_x_max, v_y_max)
    self.assertAlmostEqual(plc.get_tag("CurSeg.Speed"), expected_speed, places=6)
    self.assertLess(plc.get_tag("CurSeg.Speed"), segment.speed)
    self._assert_capped_to_axis_components(
      plc.get_tag("CurSeg.Speed"),
      (0.0, 0.0),
      segment,
      v_x_max,
      v_y_max,
    )

    self._advance_until(plc, lambda: plc.get_tag("CurIssued"))
    self.assertAlmostEqual(plc.get_tag("CmdA_Speed"), expected_speed, places=6)
    self._assert_capped_to_axis_components(
      plc.get_tag("CmdA_Speed"),
      (0.0, 0.0),
      segment,
      v_x_max,
      v_y_max,
    )

  def test_queue_start_caps_pending_segment_before_cmd_b_issue(self):
    plc = LadderSimulatedPLC("SIM")
    v_x_max = 300.0
    v_y_max = 200.0
    first = MotionSegment(seq=1, x=100.0, y=100.0, speed=9999.0)
    second = MotionSegment(seq=2, x=200.0, y=100.0, speed=9999.0)

    plc.set_tag("v_x_max", v_x_max)
    plc.set_tag("v_y_max", v_y_max)
    self._enqueue_segment(plc, 1, first)
    self._enqueue_segment(plc, 2, second)

    plc.set_tag("StartQueuedPath", 1)
    self._advance_until(
      plc,
      lambda: plc.get_tag("CurSeg.Seq") == first.seq and plc.get_tag("NextSeg.Seq") == second.seq,
    )

    expected_first = self._expected_capped_speed((0.0, 0.0), first, v_x_max, v_y_max)
    expected_second = self._expected_capped_speed((first.x, first.y), second, v_x_max, v_y_max)

    self.assertAlmostEqual(plc.get_tag("CurSeg.Speed"), expected_first, places=6)
    self.assertAlmostEqual(plc.get_tag("NextSeg.Speed"), expected_second, places=6)
    self.assertLess(plc.get_tag("NextSeg.Speed"), second.speed)
    self._assert_capped_to_axis_components(
      plc.get_tag("NextSeg.Speed"),
      (first.x, first.y),
      second,
      v_x_max,
      v_y_max,
    )

    self._advance_until(plc, lambda: plc.get_tag("NextIssued"))
    self.assertAlmostEqual(plc.get_tag("CmdB_Speed"), expected_second, places=6)
    self._assert_capped_to_axis_components(
      plc.get_tag("CmdB_Speed"),
      (first.x, first.y),
      second,
      v_x_max,
      v_y_max,
    )

  def test_queue_start_caps_arc_segment_to_axis_component_limits(self):
    plc = LadderSimulatedPLC("SIM")
    v_x_max = 250.0
    v_y_max = 250.0
    start_xy = (200.0, 0.0)
    segment = MotionSegment(
      seq=1,
      x=0.0,
      y=200.0,
      speed=9999.0,
      seg_type=SEG_TYPE_CIRCLE,
      circle_type=CIRCLE_TYPE_CENTER,
      via_center_x=0.0,
      via_center_y=0.0,
      direction=MCCM_DIR_2D_CCW,
    )

    plc.set_tag("X_axis.ActualPosition", start_xy[0])
    plc.set_tag("Y_axis.ActualPosition", start_xy[1])
    plc.set_tag("v_x_max", v_x_max)
    plc.set_tag("v_y_max", v_y_max)
    self._enqueue_segment(plc, 1, segment)

    plc.set_tag("StartQueuedPath", 1)
    self._advance_until(plc, lambda: plc.get_tag("CurSeg.Seq") == segment.seq)

    expected_speed = self._expected_capped_speed(start_xy, segment, v_x_max, v_y_max)
    self.assertAlmostEqual(plc.get_tag("CurSeg.Speed"), expected_speed, places=6)
    self.assertLess(plc.get_tag("CurSeg.Speed"), segment.speed)
    self._assert_capped_to_axis_components(
      plc.get_tag("CurSeg.Speed"),
      start_xy,
      segment,
      v_x_max,
      v_y_max,
    )

    self._advance_until(plc, lambda: plc.get_tag("CurIssued"))
    self.assertAlmostEqual(plc.get_tag("CmdA_Speed"), expected_speed, places=6)
    self._assert_capped_to_axis_components(
      plc.get_tag("CmdA_Speed"),
      start_xy,
      segment,
      v_x_max,
      v_y_max,
    )


if __name__ == "__main__":
  unittest.main()
