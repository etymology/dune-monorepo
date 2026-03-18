"""Integration tests: verify QueuedMotionSession caps SegQueue speeds on the
simulated PLC before issuing the start pulse.

_validate_plc_seg_queue_speeds reads SegQueue[i].Speed from the PLC after the
prefill enqueue, compares to the axis-velocity cap, and calls
write_seg_queue_speed for any segment whose speed is too high.

We intercept write_seg_queue_speed to record every (index, speed) write, then
also run sessions to completion and verify the simulated PLC's actual motion
reached the target with no fault.
"""
import math
import unittest
from unittest.mock import patch

from dune_winder.io.devices.plc import PLC
from dune_winder.io.devices.simulated_plc import SimulatedPLC
from dune_winder.queued_motion.plc_interface import QueuedMotionPLCInterface
from dune_winder.queued_motion.queue_session import QueuedMotionSession
from dune_winder.queued_motion.segment_types import (
  CIRCLE_TYPE_CENTER,
  MCCM_DIR_2D_CCW,
  MotionSegment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)


# ── helpers ──────────────────────────────────────────────────────────────────

class _FakeClock:
  def __init__(self):
    self.now = 0.0

  def __call__(self):
    return self.now

  def advance(self, delta=0.15):
    self.now += float(delta)


def _run_session(session: QueuedMotionSession, clock: _FakeClock,
                 max_ticks: int = 80) -> None:
  for _ in range(max_ticks):
    if session.done or session.error:
      return
    session.advance()
    clock.advance()


def _make_session(segs, *, v_x_max, v_y_max, start_xy=(0.0, 0.0)):
  plc = SimulatedPLC("SIM")
  queue = QueuedMotionPLCInterface(plc)
  clock = _FakeClock()
  session = QueuedMotionSession(
    queue, segs, now_fn=clock,
    v_x_max=v_x_max, v_y_max=v_y_max, start_xy=start_xy,
  )
  return session, plc, queue, clock


# ── tests ─────────────────────────────────────────────────────────────────────

class PLCSpeedCappingTests(unittest.TestCase):

  def setUp(self):
    self._saved_instances = list(PLC.Tag.instances)
    self._saved_lookup = dict(PLC.Tag.tag_lookup_table)
    PLC.Tag.instances = []
    PLC.Tag.tag_lookup_table = {}

  def tearDown(self):
    PLC.Tag.instances = self._saved_instances
    PLC.Tag.tag_lookup_table = self._saved_lookup

  # ── core: write_seg_queue_speed called with capped value ─────────────────

  def test_horizontal_line_write_back_called_with_capped_speed(self):
    """v_x_max=300; speed=9999 on a horizontal line → write_seg_queue_speed(0, ≤300)."""
    v_x_max = 300.0
    segs = [MotionSegment(seq=1, x=200.0, y=0.0, speed=9999.0)]
    session, plc, queue, clock = _make_session(
      segs, v_x_max=v_x_max, v_y_max=math.inf, start_xy=(0.0, 0.0)
    )

    writes: list[tuple[int, float]] = []
    original = queue.write_seg_queue_speed
    def _capture(index, speed):
      writes.append((index, speed))
      original(index, speed)
    queue.write_seg_queue_speed = _capture

    _run_session(session, clock)

    self.assertIsNone(session.error, session.error)
    self.assertTrue(session.done)
    # At least one write-back must have occurred
    self.assertGreater(len(writes), 0, "No write_seg_queue_speed calls — capping never ran")
    idx, capped = writes[0]
    self.assertEqual(idx, 0)
    self.assertLessEqual(capped, v_x_max + 1e-6,
                          f"Written speed {capped} still exceeds v_x_max {v_x_max}")

  def test_vertical_line_write_back_called_with_capped_speed(self):
    v_y_max = 200.0
    segs = [MotionSegment(seq=1, x=0.0, y=400.0, speed=9999.0)]
    session, plc, queue, clock = _make_session(
      segs, v_x_max=math.inf, v_y_max=v_y_max, start_xy=(0.0, 0.0)
    )

    writes: list[tuple[int, float]] = []
    original = queue.write_seg_queue_speed
    def _capture(index, speed):
      writes.append((index, speed))
      original(index, speed)
    queue.write_seg_queue_speed = _capture

    _run_session(session, clock)

    self.assertTrue(session.done)
    self.assertGreater(len(writes), 0, "No speed write-back for vertical segment")
    _, capped = writes[0]
    self.assertLessEqual(capped, v_y_max + 1e-6)

  # ── no write-back when speed already within limit ─────────────────────────

  def test_speed_within_limit_no_write_back(self):
    """Speed=100 with v_x_max=500 → capping must NOT write back (not necessary)."""
    segs = [MotionSegment(seq=1, x=200.0, y=0.0, speed=100.0)]
    session, plc, queue, clock = _make_session(
      segs, v_x_max=500.0, v_y_max=math.inf, start_xy=(0.0, 0.0)
    )

    writes: list[tuple[int, float]] = []
    original = queue.write_seg_queue_speed
    def _capture(index, speed):
      writes.append((index, speed))
      original(index, speed)
    queue.write_seg_queue_speed = _capture

    _run_session(session, clock)

    self.assertTrue(session.done)
    self.assertEqual(writes, [], f"Unexpected write-backs: {writes}")

  # ── multiple segments: each one that exceeds limit is written back ────────

  def test_multiple_segments_each_illegal_one_written_back(self):
    v_x_max, v_y_max = 350.0, 350.0
    segs = [
      MotionSegment(seq=1, x=200.0, y=0.0,  speed=9999.0),  # horiz → capped
      MotionSegment(seq=2, x=200.0, y=200.0, speed=50.0),   # within limit → no write
      MotionSegment(seq=3, x=400.0, y=200.0, speed=9999.0), # horiz → capped
    ]
    session, plc, queue, clock = _make_session(
      segs, v_x_max=v_x_max, v_y_max=v_y_max, start_xy=(0.0, 0.0)
    )

    writes: list[tuple[int, float]] = []
    original = queue.write_seg_queue_speed
    def _capture(index, speed):
      writes.append((index, speed))
      original(index, speed)
    queue.write_seg_queue_speed = _capture

    _run_session(session, clock)

    self.assertTrue(session.done)
    written_indices = {idx for idx, _ in writes}
    self.assertIn(0, written_indices, "Segment 0 (too fast) should have been written back")
    self.assertIn(2, written_indices, "Segment 2 (too fast) should have been written back")
    self.assertNotIn(1, written_indices, "Segment 1 (within limit) must not be written back")
    for idx, speed in writes:
      self.assertLessEqual(speed, max(v_x_max, v_y_max) + 1e-6,
                            f"SegQueue[{idx}] written speed {speed} still exceeds limit")

  # ── session completes without fault after capping ─────────────────────────

  def test_session_completes_after_horizontal_cap(self):
    segs = [MotionSegment(seq=10, x=300.0, y=0.0, speed=9999.0)]
    session, plc, queue, clock = _make_session(
      segs, v_x_max=400.0, v_y_max=math.inf, start_xy=(0.0, 0.0)
    )
    _run_session(session, clock)
    self.assertIsNone(session.error, session.error)
    self.assertTrue(session.done)

  def test_session_completes_after_arc_cap(self):
    segs = [MotionSegment(
      seq=20, x=0.0, y=200.0, speed=9999.0,
      seg_type=SEG_TYPE_CIRCLE,
      circle_type=CIRCLE_TYPE_CENTER,
      via_center_x=0.0, via_center_y=0.0,
      direction=MCCM_DIR_2D_CCW,
    )]
    session, plc, queue, clock = _make_session(
      segs, v_x_max=300.0, v_y_max=300.0, start_xy=(200.0, 0.0)
    )
    _run_session(session, clock)
    self.assertIsNone(session.error, session.error)
    self.assertTrue(session.done)

  # ── no limits: no write-back and session completes ────────────────────────

  def test_no_limits_no_write_back_session_completes(self):
    segs = [MotionSegment(seq=1, x=200.0, y=0.0, speed=9999.0)]
    plc = SimulatedPLC("SIM")
    queue = QueuedMotionPLCInterface(plc)
    clock = _FakeClock()
    session = QueuedMotionSession(queue, segs, now_fn=clock)

    writes: list = []
    original = queue.write_seg_queue_speed
    def _capture(index, speed):
      writes.append((index, speed))
      original(index, speed)
    queue.write_seg_queue_speed = _capture

    _run_session(session, clock)

    self.assertTrue(session.done)
    self.assertEqual(writes, [], "No limits → no write-back expected")

  # ── asymmetric limits: tighter axis governs write-back ───────────────────

  def test_asymmetric_limits_tighter_axis_governs(self):
    v_x_max = 900.0
    v_y_max = 150.0    # tighter
    # 45-degree diagonal: both axes see speed/√2; y-axis cap applies
    segs = [MotionSegment(seq=1, x=400.0, y=400.0, speed=9999.0)]
    session, plc, queue, clock = _make_session(
      segs, v_x_max=v_x_max, v_y_max=v_y_max, start_xy=(0.0, 0.0)
    )

    writes: list[tuple[int, float]] = []
    original = queue.write_seg_queue_speed
    def _capture(index, speed):
      writes.append((index, speed))
      original(index, speed)
    queue.write_seg_queue_speed = _capture

    _run_session(session, clock)

    self.assertTrue(session.done)
    self.assertGreater(len(writes), 0)
    _, capped = writes[0]
    # cap ≈ v_y_max * √2 ≈ 212; must be well below v_x_max=900
    self.assertLessEqual(capped, v_y_max * math.sqrt(2) + 1e-3)
    self.assertLess(capped, v_x_max)


if __name__ == "__main__":
  unittest.main()
