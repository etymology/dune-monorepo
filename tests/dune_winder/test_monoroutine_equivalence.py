"""Equivalence tests: MonoroutineLadderSimulatedPLC vs LadderSimulatedPLC ensemble.

Both simulators are driven with identical inputs and their observable outputs are
compared after each step.  The monoroutine is a self-contained routine that should
produce the same externally-visible behaviour as the full ensemble.

Timer / counter note: unregistered timer and counter tags default to PRE=10 so
timing-related transitions behave deterministically across both simulators.
"""

from __future__ import annotations

import unittest

from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC
from dune_winder.io.devices.monoroutine_simulated_plc import MonoroutineLadderSimulatedPLC
from dune_winder.queued_motion.segment_types import (
  MotionSegment,
  MCCM_DIR_2D_CCW,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
  CIRCLE_TYPE_CENTER,
)

# ---------------------------------------------------------------------------
# Tags compared after each step
# ---------------------------------------------------------------------------
COMPARE_TAGS = [
  "STATE",
  "NEXTSTATE",
  "ERROR_CODE",
  "MOVE_TYPE",
  "QueueCount",
  "CurIssued",
  "NextIssued",
  "IncomingSegAck",
  "ActiveSeq",
  "PendingSeq",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ensemble() -> LadderSimulatedPLC:
  return LadderSimulatedPLC("SIM")


def _make_mono() -> MonoroutineLadderSimulatedPLC:
  return MonoroutineLadderSimulatedPLC("SIM")


def _advance(plc, scans: int = 1):
  for _ in range(scans):
    plc.read("STATE")


def _advance_until(plc, predicate, limit: int = 100):
  for _ in range(limit):
    plc.read("STATE")
    if predicate():
      return True
  return False


def _advance_both(ensemble, mono, scans: int = 1):
  _advance(ensemble, scans)
  _advance(mono, scans)


def _advance_both_until(ensemble, mono, predicate_e, predicate_m, limit: int = 100):
  for _ in range(limit):
    _advance_both(ensemble, mono)
    if predicate_e() and predicate_m():
      return True
  return False


def _enqueue_segment(plc, req_id: int, segment: MotionSegment, limit: int = 100):
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
  return _advance_until(plc, lambda: plc.get_tag("IncomingSegAck") == req_id, limit)


def _enqueue_both(ensemble, mono, req_id: int, segment: MotionSegment, limit: int = 100):
  ok_e = _enqueue_segment(ensemble, req_id, segment, limit)
  ok_m = _enqueue_segment(mono, req_id, segment, limit)
  return ok_e, ok_m


def _assert_tags_equal(tc: unittest.TestCase, ensemble, mono, tags=COMPARE_TAGS, msg_prefix=""):
  for tag in tags:
    e_val = ensemble.get_tag(tag)
    m_val = mono.get_tag(tag)
    tc.assertEqual(
      e_val,
      m_val,
      f"{msg_prefix}Mismatch on {tag!r}: ensemble={e_val!r} mono={m_val!r}",
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class MonoroutineEquivalenceTests(unittest.TestCase):

  # ------------------------------------------------------------------
  # Startup / initial state
  # ------------------------------------------------------------------

  def test_initial_state_both_ready(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    _assert_tags_equal(self, ensemble, mono)

  def test_initial_state_error_code_zero(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    self.assertEqual(ensemble.get_tag("ERROR_CODE"), 0)
    self.assertEqual(mono.get_tag("ERROR_CODE"), 0)

  def test_initial_queue_empty(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    self.assertEqual(ensemble.get_tag("QueueCount"), 0)
    self.assertEqual(mono.get_tag("QueueCount"), 0)
    self.assertFalse(ensemble.get_tag("CurIssued"))
    self.assertFalse(mono.get_tag("CurIssued"))

  # ------------------------------------------------------------------
  # MOVE_TYPE state transitions
  # ------------------------------------------------------------------

  def test_xy_jog_state_transition(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    ensemble.write(("MOVE_TYPE", ensemble.MOVE_JOG_XY))
    mono.write(("MOVE_TYPE", mono.MOVE_JOG_XY))
    _advance_both(ensemble, mono, 3)
    _assert_tags_equal(self, ensemble, mono, ["STATE", "MOVE_TYPE"])

  def test_xy_seek_state_transition(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    for plc in (ensemble, mono):
      plc.write(("X_POSITION", 50.0))
      plc.write(("Y_POSITION", 50.0))
      plc.write(("XY_SPEED", 1000.0))
      plc.write(("XY_ACCELERATION", 1000.0))
      plc.write(("XY_DECELERATION", 1000.0))
      plc.write(("MOVE_TYPE", plc.MOVE_SEEK_XY))
    _advance_both(ensemble, mono, 2)
    _assert_tags_equal(self, ensemble, mono, ["STATE"])
    # Both should reach READY
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("STATE") == ensemble.STATE_READY,
        lambda: mono.get_tag("STATE") == mono.STATE_READY,
      ),
      "Both simulators did not return to READY after XY seek",
    )
    _assert_tags_equal(self, ensemble, mono, ["STATE", "MOVE_TYPE"])

  def test_z_jog_state_transition(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    ensemble.write(("MOVE_TYPE", ensemble.MOVE_JOG_Z))
    mono.write(("MOVE_TYPE", mono.MOVE_JOG_Z))
    _advance_both(ensemble, mono, 3)
    _assert_tags_equal(self, ensemble, mono, ["STATE"])

  def test_z_seek_state_transition(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    ensemble.write(("MOVE_TYPE", ensemble.MOVE_SEEK_Z))
    mono.write(("MOVE_TYPE", mono.MOVE_SEEK_Z))
    _advance_both(ensemble, mono, 2)
    _assert_tags_equal(self, ensemble, mono, ["STATE"])

  def test_unservo_state_transition(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    ensemble.write(("MOVE_TYPE", ensemble.MOVE_UNSERVO))
    mono.write(("MOVE_TYPE", mono.MOVE_UNSERVO))
    _advance_both(ensemble, mono, 3)
    _assert_tags_equal(self, ensemble, mono, ["STATE"])

  def test_hmi_stop_state_transition(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    # First trigger a seek so HMI stop has something to interrupt
    for plc in (ensemble, mono):
      plc.write(("X_POSITION", 500.0))
      plc.write(("Y_POSITION", 500.0))
      plc.write(("XY_SPEED", 1000.0))
      plc.write(("XY_ACCELERATION", 1000.0))
      plc.write(("XY_DECELERATION", 1000.0))
      plc.write(("MOVE_TYPE", plc.MOVE_SEEK_XY))
    _advance_both(ensemble, mono)
    ensemble.write(("MOVE_TYPE", ensemble.MOVE_HMI_STOP_REQUEST))
    mono.write(("MOVE_TYPE", mono.MOVE_HMI_STOP_REQUEST))
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("STATE") == ensemble.STATE_HMI_STOP,
        lambda: mono.get_tag("STATE") == mono.STATE_HMI_STOP,
      ),
      "Both simulators did not reach HMI_STOP",
    )
    _assert_tags_equal(self, ensemble, mono, ["STATE"])

  def test_error_clear_returns_to_ready(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    # Force error by issuing XZ seek without transfer override set
    ensemble.set_tag("MACHINE_SW_STAT[17]", 0, override=True)
    mono.set_tag("MACHINE_SW_STAT[17]", 0, override=True)
    ensemble.write(("xz_position_target", [100.0, 50.0]))
    mono.write(("xz_position_target", [100.0, 50.0]))
    ensemble.write(("MOVE_TYPE", ensemble.MOVE_SEEK_XZ))
    mono.write(("MOVE_TYPE", mono.MOVE_SEEK_XZ))
    _advance_both(ensemble, mono, 3)
    _assert_tags_equal(self, ensemble, mono, ["STATE", "ERROR_CODE"])
    self.assertEqual(ensemble.get_tag("STATE"), ensemble.STATE_ERROR)
    self.assertEqual(mono.get_tag("STATE"), mono.STATE_ERROR)
    # Clear error
    ensemble.write(("MOVE_TYPE", ensemble.MOVE_RESET))
    mono.write(("MOVE_TYPE", mono.MOVE_RESET))
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("STATE") == ensemble.STATE_READY,
        lambda: mono.get_tag("STATE") == mono.STATE_READY,
      ),
      "Both simulators did not return to READY after error clear",
    )
    _assert_tags_equal(self, ensemble, mono, ["STATE", "MOVE_TYPE"])

  # ------------------------------------------------------------------
  # Segment queue handshake
  # ------------------------------------------------------------------

  def test_segment_enqueue_ack_matches(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    seg = MotionSegment(seq=1, x=100.0, y=200.0, speed=1000.0)
    ok_e, ok_m = _enqueue_both(ensemble, mono, req_id=1, segment=seg)
    self.assertTrue(ok_e, "Ensemble did not ACK segment")
    self.assertTrue(ok_m, "Monoroutine did not ACK segment")
    _assert_tags_equal(self, ensemble, mono, ["QueueCount", "IncomingSegAck"])

  def test_multiple_segments_queue_count_matches(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    segments = [
      MotionSegment(seq=i, x=float(i * 50), y=float(i * 30), speed=800.0)
      for i in range(1, 5)
    ]
    for i, seg in enumerate(segments, start=1):
      ok_e, ok_m = _enqueue_both(ensemble, mono, req_id=i, segment=seg)
      self.assertTrue(ok_e, f"Ensemble did not ACK segment {i}")
      self.assertTrue(ok_m, f"Monoroutine did not ACK segment {i}")
      _assert_tags_equal(
        self, ensemble, mono,
        ["QueueCount", "IncomingSegAck"],
        msg_prefix=f"After enqueue {i}: ",
      )

  def test_queue_abort_clears_state(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    # Enqueue 3 segments
    for i in range(1, 4):
      seg = MotionSegment(seq=i, x=float(i * 100), y=0.0)
      _enqueue_both(ensemble, mono, req_id=i, segment=seg)
    # Abort
    ensemble.set_tag("AbortQueue", True)
    mono.set_tag("AbortQueue", True)
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("QueueCount") == 0,
        lambda: mono.get_tag("QueueCount") == 0,
      ),
      "Queue not cleared after abort",
    )
    _assert_tags_equal(self, ensemble, mono, ["QueueCount", "CurIssued"])

  def test_start_queued_path_activates_cur_issued(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    # Prefill 2 segments
    for i in range(1, 3):
      seg = MotionSegment(seq=i, x=float(i * 100), y=float(i * 50))
      _enqueue_both(ensemble, mono, req_id=i, segment=seg)
    # Start
    ensemble.set_tag("StartQueuedPath", True)
    mono.set_tag("StartQueuedPath", True)
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("CurIssued"),
        lambda: mono.get_tag("CurIssued"),
      ),
      "CurIssued not set after StartQueuedPath",
    )
    _assert_tags_equal(self, ensemble, mono, ["CurIssued", "STATE"])

  def test_next_issued_when_two_or_more_queued(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    for i in range(1, 4):
      seg = MotionSegment(seq=i, x=float(i * 100), y=float(i * 50))
      _enqueue_both(ensemble, mono, req_id=i, segment=seg)
    ensemble.set_tag("StartQueuedPath", True)
    mono.set_tag("StartQueuedPath", True)
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("NextIssued"),
        lambda: mono.get_tag("NextIssued"),
      ),
      "NextIssued not set with 3 queued segments",
    )
    _assert_tags_equal(self, ensemble, mono, ["NextIssued", "CurIssued"])

  def test_active_seq_advances_with_segment(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    for i in range(1, 3):
      seg = MotionSegment(seq=i, x=float(i * 200), y=0.0)
      _enqueue_both(ensemble, mono, req_id=i, segment=seg)
    ensemble.set_tag("StartQueuedPath", True)
    mono.set_tag("StartQueuedPath", True)
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("CurIssued"),
        lambda: mono.get_tag("CurIssued"),
      ),
    )
    _assert_tags_equal(self, ensemble, mono, ["ActiveSeq"])

  def test_queue_stop_request_drains_gracefully(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    for i in range(1, 4):
      seg = MotionSegment(seq=i, x=float(i * 150), y=0.0)
      _enqueue_both(ensemble, mono, req_id=i, segment=seg)
    ensemble.set_tag("StartQueuedPath", True)
    mono.set_tag("StartQueuedPath", True)
    _advance_both(ensemble, mono, 5)
    ensemble.set_tag("QueueStopRequest", True)
    mono.set_tag("QueueStopRequest", True)
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("STATE") == ensemble.STATE_READY,
        lambda: mono.get_tag("STATE") == mono.STATE_READY,
        limit=200,
      ),
      "Both simulators did not reach READY after QueueStopRequest",
    )
    _assert_tags_equal(self, ensemble, mono, ["STATE", "CurIssued", "QueueCount"])

  # ------------------------------------------------------------------
  # Arc segment tests
  # ------------------------------------------------------------------

  def test_arc_segment_enqueued_correctly(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    arc = MotionSegment(
      seq=1,
      x=100.0,
      y=0.0,
      speed=500.0,
      seg_type=SEG_TYPE_CIRCLE,
      circle_type=CIRCLE_TYPE_CENTER,
      via_center_x=50.0,
      via_center_y=0.0,
      direction=MCCM_DIR_2D_CCW,
    )
    ok_e, ok_m = _enqueue_both(ensemble, mono, req_id=1, segment=arc)
    self.assertTrue(ok_e, "Ensemble did not ACK arc segment")
    self.assertTrue(ok_m, "Monoroutine did not ACK arc segment")
    _assert_tags_equal(self, ensemble, mono, ["QueueCount", "IncomingSegAck"])

  # ------------------------------------------------------------------
  # Parameterized XY seek with physics inputs
  # ------------------------------------------------------------------

  def _run_xy_seek_with_physics(self, start_x, start_y):
    ensemble = _make_ensemble()
    mono = _make_mono()
    for plc in (ensemble, mono):
      plc.set_tag("X_axis.ActualPosition", start_x)
      plc.set_tag("Y_axis.ActualPosition", start_y)
      plc.write(("X_POSITION", start_x + 100.0))
      plc.write(("Y_POSITION", start_y + 100.0))
      plc.write(("XY_SPEED", 1000.0))
      plc.write(("XY_ACCELERATION", 1000.0))
      plc.write(("XY_DECELERATION", 1000.0))
      plc.write(("MOVE_TYPE", plc.MOVE_SEEK_XY))
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("STATE") == ensemble.STATE_READY,
        lambda: mono.get_tag("STATE") == mono.STATE_READY,
        limit=200,
      ),
      f"XY seek from ({start_x},{start_y}) did not complete",
    )
    _assert_tags_equal(self, ensemble, mono, msg_prefix=f"xy_seek({start_x},{start_y}): ")

  def test_xy_seek_from_origin(self):
    self._run_xy_seek_with_physics(0.0, 0.0)

  def test_xy_seek_from_mid_range(self):
    self._run_xy_seek_with_physics(500.0, 500.0)

  def test_xy_seek_from_far(self):
    self._run_xy_seek_with_physics(3000.0, 1200.0)

  # ------------------------------------------------------------------
  # Parameterized segment stream
  # ------------------------------------------------------------------

  def _run_segment_stream(self, segments):
    ensemble = _make_ensemble()
    mono = _make_mono()
    for i, seg in enumerate(segments, start=1):
      ok_e, ok_m = _enqueue_both(ensemble, mono, req_id=i, segment=seg)
      self.assertTrue(ok_e, f"Ensemble did not ACK segment {i}")
      self.assertTrue(ok_m, f"Monoroutine did not ACK segment {i}")
      _assert_tags_equal(
        self, ensemble, mono,
        ["QueueCount"],
        msg_prefix=f"After enqueue {i}: ",
      )
    ensemble.set_tag("StartQueuedPath", True)
    mono.set_tag("StartQueuedPath", True)
    self.assertTrue(
      _advance_both_until(
        ensemble, mono,
        lambda: ensemble.get_tag("STATE") == ensemble.STATE_READY,
        lambda: mono.get_tag("STATE") == mono.STATE_READY,
        limit=300,
      ),
      "Segment stream did not complete",
    )
    _assert_tags_equal(self, ensemble, mono)

  def test_single_line_segment_stream(self):
    self._run_segment_stream([
      MotionSegment(seq=1, x=100.0, y=0.0, speed=1000.0, term_type=0),
    ])

  def test_four_line_segment_stream(self):
    self._run_segment_stream([
      MotionSegment(seq=i, x=float(i * 100), y=float(i * 50), speed=800.0, term_type=3)
      for i in range(1, 5)
    ])

  def test_arc_segment_stream(self):
    self._run_segment_stream([
      MotionSegment(
        seq=1, x=100.0, y=0.0, speed=500.0, term_type=3,
        seg_type=SEG_TYPE_CIRCLE, circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=50.0, via_center_y=0.0, direction=MCCM_DIR_2D_CCW,
      ),
      MotionSegment(seq=2, x=200.0, y=100.0, speed=600.0, term_type=0),
    ])

  def test_mixed_segment_stream(self):
    self._run_segment_stream([
      MotionSegment(seq=1, x=100.0, y=0.0, speed=800.0, term_type=3),
      MotionSegment(
        seq=2, x=200.0, y=100.0, speed=500.0, term_type=3,
        seg_type=SEG_TYPE_CIRCLE, circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=150.0, via_center_y=50.0, direction=MCCM_DIR_2D_CCW,
      ),
      MotionSegment(seq=3, x=300.0, y=0.0, speed=700.0, term_type=3),
      MotionSegment(seq=4, x=400.0, y=100.0, speed=600.0, term_type=0),
    ])

  # ------------------------------------------------------------------
  # Segment speed capping
  # ------------------------------------------------------------------

  def test_segment_speed_capping_identical(self):
    ensemble = _make_ensemble()
    mono = _make_mono()
    # Set axis limits
    for plc in (ensemble, mono):
      plc.set_tag("v_x_max", 500.0)
      plc.set_tag("v_y_max", 400.0)
    seg = MotionSegment(seq=1, x=100.0, y=100.0, speed=99999.0)
    ok_e, ok_m = _enqueue_both(ensemble, mono, req_id=1, segment=seg)
    self.assertTrue(ok_e, "Ensemble did not ACK segment")
    self.assertTrue(ok_m, "Monoroutine did not ACK segment")
    e_speed = ensemble.get_tag("SegQueue[0].Speed")
    m_speed = mono.get_tag("SegQueue[0].Speed")
    self.assertAlmostEqual(e_speed, m_speed, places=4, msg="Capped speed mismatch")
    self.assertLess(e_speed, 99999.0, "Speed was not capped in ensemble")
    self.assertLess(m_speed, 99999.0, "Speed was not capped in monoroutine")


if __name__ == "__main__":
  unittest.main()
