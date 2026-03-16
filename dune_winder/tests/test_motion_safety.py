import unittest

from dune_winder.queued_motion.safety import (
  MotionSafetyLimits,
  QueuedMotionCollisionState,
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
    )

  def _z_state(self, z_actual_position, **locks):
    defaults = {
      "frame_lock_head_top": False,
      "frame_lock_head_mid": False,
      "frame_lock_head_btm": False,
      "frame_lock_foot_top": False,
      "frame_lock_foot_mid": False,
      "frame_lock_foot_btm": False,
    }
    defaults.update(locks)
    return QueuedMotionCollisionState(
      z_actual_position=float(z_actual_position),
      **defaults,
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

  def test_validate_allows_central_apa_motion_when_z_not_extended(self):
    validate_xy_move_within_safety_limits(
      (1000.0, 25.0),
      (1000.0, 150.0),
      self._z_collision_limits(),
      queued_motion_collision_state=self._z_state(50.0),
    )

  def test_validate_rejects_central_apa_motion_when_z_extended(self):
    with self.assertRaisesRegex(ValueError, "APA collision zone"):
      validate_xy_move_within_safety_limits(
        (1000.0, 25.0),
        (1000.0, 150.0),
        self._z_collision_limits(),
        queued_motion_collision_state=self._z_state(200.0),
      )

  def test_validate_allows_head_transfer_zone_motion_when_supports_clear(self):
    validate_xy_move_within_safety_limits(
      (450.0, 25.0),
      (450.0, 2200.0),
      self._z_collision_limits(),
      queued_motion_collision_state=self._z_state(200.0),
    )

  def test_validate_rejects_head_support_endpoint_when_lock_active(self):
    with self.assertRaisesRegex(ValueError, "head bottom frame-support keepout"):
      validate_xy_move_within_safety_limits(
        (450.0, 25.0),
        (450.0, 200.0),
        self._z_collision_limits(),
        queued_motion_collision_state=self._z_state(200.0, frame_lock_head_btm=True),
      )

  def test_validate_rejects_foot_support_passthrough_when_lock_active(self):
    with self.assertRaisesRegex(ValueError, "foot middle frame-support keepout"):
      validate_xy_move_within_safety_limits(
        (7150.0, 1000.0),
        (7150.0, 1600.0),
        self._z_collision_limits(),
        queued_motion_collision_state=self._z_state(200.0, frame_lock_foot_mid=True),
      )

  def test_validate_rejects_arc_crossing_apa_collision_zone_when_z_extended(self):
    segments = [
      MotionSegment(
        seq=1,
        x=350.0,
        y=2260.0,
        seg_type=SEG_TYPE_CIRCLE,
        circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=350.0,
        via_center_y=1150.0,
        direction=MCCM_DIR_2D_CCW,
      )
    ]

    with self.assertRaisesRegex(ValueError, "APA collision zone"):
      validate_segments_within_safety_limits(
        segments,
        self._z_collision_limits(),
        start_xy=(350.0, 40.0),
        queued_motion_collision_state=self._z_state(200.0),
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
          "zBack": 13.0,
          "queuedMotionZCollisionThreshold": 14.0,
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
    self.assertEqual(limits.queued_motion_z_collision_threshold, 14.0)

  def test_motion_safety_limits_default_z_collision_threshold_uses_z_back(self):
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
          "zBack": 123.0,
        }
      )
    )

    self.assertEqual(limits.queued_motion_z_collision_threshold, 123.0)


if __name__ == "__main__":
  unittest.main()
