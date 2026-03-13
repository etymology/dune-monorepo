import unittest

from dune_winder.motion.safety import (
  MotionSafetyLimits,
  validate_segments_within_safety_limits,
)
from dune_winder.motion.segment_types import (
  CIRCLE_TYPE_CENTER,
  MCCM_DIR_2D_CCW,
  MCCM_DIR_2D_CW,
  MotionSegment,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)


class MotionSafetyTests(unittest.TestCase):
  def _limits(self):
    return MotionSafetyLimits(
      limit_left=0.0,
      limit_right=1000.0,
      limit_bottom=0.0,
      limit_top=1000.0,
      transfer_left=100.0,
      transfer_left_margin=10.0,
      transfer_y_threshold=900.0,
      headward_pivot_x=500.0,
      headward_pivot_y=500.0,
      headward_pivot_x_tolerance=50.0,
      headward_pivot_y_tolerance=50.0,
    )

  def test_validate_accepts_safe_line_and_arc_path(self):
    segments = [
      MotionSegment(seq=1, x=200.0, y=200.0, seg_type=SEG_TYPE_LINE),
      MotionSegment(
        seq=2,
        x=300.0,
        y=300.0,
        seg_type=SEG_TYPE_CIRCLE,
        circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=200.0,
        via_center_y=300.0,
        direction=MCCM_DIR_2D_CCW,
      ),
    ]

    validate_segments_within_safety_limits(
      segments,
      self._limits(),
      start_xy=(100.0, 100.0),
    )

  def test_validate_rejects_point_outside_box_limits(self):
    segments = [MotionSegment(seq=1, x=1200.0, y=200.0, seg_type=SEG_TYPE_LINE)]

    with self.assertRaises(ValueError):
      validate_segments_within_safety_limits(segments, self._limits(), start_xy=(100.0, 100.0))

  def test_validate_rejects_line_crossing_pivot_keepout(self):
    segments = [MotionSegment(seq=1, x=570.0, y=500.0, seg_type=SEG_TYPE_LINE)]

    with self.assertRaises(ValueError):
      validate_segments_within_safety_limits(segments, self._limits(), start_xy=(430.0, 500.0))

  def test_validate_rejects_arc_crossing_pivot_keepout(self):
    segments = [
      MotionSegment(
        seq=1,
        x=530.0,
        y=450.0,
        seg_type=SEG_TYPE_CIRCLE,
        circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=450.0,
        via_center_y=450.0,
        direction=MCCM_DIR_2D_CW,
      )
    ]

    with self.assertRaises(ValueError):
      validate_segments_within_safety_limits(segments, self._limits(), start_xy=(370.0, 450.0))


if __name__ == "__main__":
  unittest.main()
