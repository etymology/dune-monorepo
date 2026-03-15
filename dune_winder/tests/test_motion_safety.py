import unittest

from dune_winder.queued_motion.safety import (
  MotionSafetyLimits,
  motion_safety_limits_from_calibration,
  validate_xy_move_within_safety_limits,
  validate_segments_within_safety_limits,
)
from dune_winder.queued_motion.segment_types import (
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

  def test_validate_xy_move_reuses_shared_bounds_logic(self):
    with self.assertRaises(ValueError):
      validate_xy_move_within_safety_limits(
        (430.0, 500.0),
        (570.0, 500.0),
        self._limits(),
      )

  def test_motion_safety_limits_can_be_built_from_calibration(self):
    class _Calibration:
      def __init__(self, values):
        self._values = dict(values)

      def get(self, key):
        return self._values.get(key)

    limits = motion_safety_limits_from_calibration(
      _Calibration(
        {
          "limitLeft": 1.0,
          "limitRight": 2.0,
          "limitBottom": 3.0,
          "limitTop": 4.0,
          "transferLeft": 5.0,
          "transferRight": 6.0,
          "transferLeftMargin": 7.0,
          "transferYThreshold": 8.0,
          "headwardPivotX": 9.0,
          "headwardPivotY": 10.0,
          "headwardPivotXTolerance": 11.0,
          "headwardPivotYTolerance": 12.0,
        }
      )
    )

    self.assertEqual(limits.limit_left, 1.0)
    self.assertEqual(limits.limit_right, 2.0)
    self.assertEqual(limits.limit_bottom, 3.0)
    self.assertEqual(limits.limit_top, 4.0)
    self.assertEqual(limits.transfer_left, 5.0)
    self.assertEqual(limits.transfer_right, 6.0)
    self.assertEqual(limits.transfer_left_margin, 7.0)
    self.assertEqual(limits.transfer_y_threshold, 8.0)


if __name__ == "__main__":
  unittest.main()
