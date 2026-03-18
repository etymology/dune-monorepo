"""Tests for cap_segments_speed_by_axis_velocity.

Each test queues segments whose nominal speed exceeds at least one axis
velocity limit, then verifies the capper reduces every segment to a
speed that keeps axis-projected velocity within bounds.
"""
import math
import unittest

from dune_winder.queued_motion.segment_patterns import cap_segments_speed_by_axis_velocity
from dune_winder.queued_motion.segment_types import (
  CIRCLE_TYPE_CENTER,
  MCCM_DIR_2D_CCW,
  MCCM_DIR_2D_CW,
  MotionSegment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _line(seq, x, y, speed=9999.0):
  return MotionSegment(seq=seq, x=x, y=y, speed=speed,
                       seg_type=SEG_TYPE_LINE)


def _arc(seq, x, y, cx, cy, direction=MCCM_DIR_2D_CCW, speed=9999.0):
  return MotionSegment(
    seq=seq, x=x, y=y, speed=speed,
    seg_type=SEG_TYPE_CIRCLE,
    circle_type=CIRCLE_TYPE_CENTER,
    via_center_x=cx, via_center_y=cy,
    direction=direction,
  )


def _check_capped(test: unittest.TestCase, result, v_x_max, v_y_max,
                  start_xy=None):
  """Assert every segment's speed satisfies the axis velocity constraints."""
  from dune_winder.queued_motion.segment_patterns import _segment_tangent_component_bounds
  prev_x = result[0].x if start_xy is None else start_xy[0]
  prev_y = result[0].y if start_xy is None else start_xy[1]
  if start_xy is None:
    prev_x = result[0].x
    prev_y = result[0].y
  for seg in result:
    max_tx, max_ty = _segment_tangent_component_bounds(prev_x, prev_y, seg)
    if max_tx > 1e-9:
      test.assertLessEqual(
        seg.speed * max_tx, v_x_max + 1e-6,
        f"seq={seg.seq}: x-axis velocity {seg.speed * max_tx:.3f} exceeds {v_x_max}",
      )
    if max_ty > 1e-9:
      test.assertLessEqual(
        seg.speed * max_ty, v_y_max + 1e-6,
        f"seq={seg.seq}: y-axis velocity {seg.speed * max_ty:.3f} exceeds {v_y_max}",
      )
    prev_x, prev_y = seg.x, seg.y


# ── test cases ────────────────────────────────────────────────────────────────

class CapSegmentsSpeedTests(unittest.TestCase):

  # ── edge / guard cases ────────────────────────────────────────────────────

  def test_empty_list_returns_empty(self):
    self.assertEqual(cap_segments_speed_by_axis_velocity([]), [])

  def test_both_axes_infinite_returns_unchanged(self):
    segs = [_line(1, 100.0, 0.0, speed=5000.0)]
    result = cap_segments_speed_by_axis_velocity(segs, math.inf, math.inf)
    self.assertEqual(result[0].speed, 5000.0)

  def test_zero_vx_raises(self):
    with self.assertRaises(ValueError):
      cap_segments_speed_by_axis_velocity([_line(1, 10.0, 0.0)], v_x_max=0.0)

  def test_negative_vy_raises(self):
    with self.assertRaises(ValueError):
      cap_segments_speed_by_axis_velocity([_line(1, 0.0, 10.0)], v_y_max=-1.0)

  # ── horizontal line: only x-axis matters ─────────────────────────────────

  def test_horizontal_line_capped_by_vx(self):
    v_x_max = 400.0
    segs = [_line(1, 200.0, 0.0, speed=9999.0)]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=math.inf,
      start_xy=(0.0, 0.0),
    )
    self.assertLessEqual(result[0].speed, v_x_max + 1e-6)

  def test_horizontal_line_within_limit_unchanged(self):
    v_x_max = 400.0
    segs = [_line(1, 200.0, 0.0, speed=100.0)]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=math.inf,
      start_xy=(0.0, 0.0),
    )
    self.assertAlmostEqual(result[0].speed, 100.0)

  # ── vertical line: only y-axis matters ───────────────────────────────────

  def test_vertical_line_capped_by_vy(self):
    v_y_max = 300.0
    segs = [_line(1, 0.0, 500.0, speed=9999.0)]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=math.inf, v_y_max=v_y_max,
      start_xy=(0.0, 0.0),
    )
    self.assertLessEqual(result[0].speed, v_y_max + 1e-6)

  # ── diagonal line: both axes constrain ───────────────────────────────────

  def test_diagonal_line_capped_by_tighter_axis(self):
    v_x_max = 500.0
    v_y_max = 200.0          # tighter
    # 45-degree line → max_tx = max_ty = 1/sqrt(2)
    d = 400.0
    segs = [_line(1, d, d, speed=9999.0)]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=v_y_max,
      start_xy=(0.0, 0.0),
    )
    _check_capped(self, result, v_x_max, v_y_max, start_xy=(0.0, 0.0))

  # ── multiple lines ────────────────────────────────────────────────────────

  def test_mixed_direction_lines_all_capped(self):
    v_x_max = 300.0
    v_y_max = 300.0
    segs = [
      _line(1, 200.0,   0.0, speed=9999.0),   # horizontal
      _line(2,   0.0, 200.0, speed=9999.0),   # diagonal back
      _line(3,   0.0, 400.0, speed=9999.0),   # vertical
      _line(4, 200.0, 400.0, speed=9999.0),   # horizontal
    ]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=v_y_max,
      start_xy=(0.0, 0.0),
    )
    _check_capped(self, result, v_x_max, v_y_max, start_xy=(0.0, 0.0))

  def test_speed_already_within_limit_not_raised(self):
    v_x_max, v_y_max = 500.0, 500.0
    original_speed = 10.0
    segs = [_line(1, 100.0, 100.0, speed=original_speed)]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=v_y_max,
      start_xy=(0.0, 0.0),
    )
    self.assertAlmostEqual(result[0].speed, original_speed)

  # ── circular arcs ─────────────────────────────────────────────────────────

  def test_quarter_arc_capped(self):
    # Quarter circle, radius 200, CCW: starts at (200,0) ends at (0,200)
    v_x_max = 250.0
    v_y_max = 250.0
    segs = [_arc(1, x=0.0, y=200.0, cx=0.0, cy=0.0,
                 direction=MCCM_DIR_2D_CCW, speed=9999.0)]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=v_y_max,
      start_xy=(200.0, 0.0),
    )
    _check_capped(self, result, v_x_max, v_y_max, start_xy=(200.0, 0.0))

  def test_full_circle_arc_capped(self):
    # Near-full arc (CW), large radius
    v_x_max = 400.0
    v_y_max = 400.0
    r = 300.0
    segs = [_arc(1, x=r, y=1e-3, cx=0.0, cy=0.0,
                 direction=MCCM_DIR_2D_CW, speed=9999.0)]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=v_y_max,
      start_xy=(r, 0.0),
    )
    _check_capped(self, result, v_x_max, v_y_max, start_xy=(r, 0.0))

  def test_mixed_line_arc_sequence_all_capped(self):
    v_x_max = 350.0
    v_y_max = 350.0
    r = 150.0
    segs = [
      _line(1, r,     0.0, speed=9999.0),       # approach
      _arc( 2, 0.0,   r,   cx=0.0, cy=0.0,
            direction=MCCM_DIR_2D_CCW, speed=9999.0),
      _line(3, 0.0, r+200.0, speed=9999.0),     # exit
    ]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=v_y_max,
      start_xy=(0.0, 0.0),
    )
    _check_capped(self, result, v_x_max, v_y_max, start_xy=(0.0, 0.0))

  # ── asymmetric axis limits ────────────────────────────────────────────────

  def test_asymmetric_limits_diagonal(self):
    v_x_max = 800.0
    v_y_max = 200.0
    segs = [_line(1, 500.0, 500.0, speed=9999.0)]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=v_y_max,
      start_xy=(0.0, 0.0),
    )
    _check_capped(self, result, v_x_max, v_y_max, start_xy=(0.0, 0.0))

  # ── degenerate geometry (zero-length segment) ─────────────────────────────

  def test_zero_length_segment_not_nan(self):
    segs = [_line(1, 0.0, 0.0, speed=9999.0)]   # start == end
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=500.0, v_y_max=500.0,
      start_xy=(0.0, 0.0),
    )
    self.assertFalse(math.isnan(result[0].speed))
    self.assertFalse(math.isinf(result[0].speed))

  # ── start_xy=None uses first segment start ────────────────────────────────

  def test_no_start_xy_uses_segment_zero_position(self):
    v_x_max = 300.0
    segs = [
      _line(1, 100.0, 0.0, speed=9999.0),
      _line(2, 200.0, 0.0, speed=9999.0),
    ]
    result = cap_segments_speed_by_axis_velocity(
      segs, v_x_max=v_x_max, v_y_max=math.inf,
    )
    for seg in result:
      self.assertLessEqual(seg.speed, v_x_max + 1e-6)


if __name__ == "__main__":
  unittest.main()
