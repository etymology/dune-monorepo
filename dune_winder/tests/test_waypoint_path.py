import math
import unittest

from dune_winder.queued_motion.segment_patterns import (
  DEFAULT_WAYPOINT_ORDER_MODE,
  waypoint_path_segments,
)
from dune_winder.queued_motion.segment_types import (
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
  arc_sweep_rad,
  circle_center_for_segment,
)


class WaypointPathTests(unittest.TestCase):
  def test_default_order_mode_preserves_input_order(self):
    self.assertEqual(DEFAULT_WAYPOINT_ORDER_MODE, "input")

  def test_waypoint_path_uses_filleted_polygon_as_default(self):
    segments = waypoint_path_segments(
      start_seq=10,
      term_type=4,
      waypoints=[(0.0, 0.0), (10.0, 0.0), (20.0, 10.0), (20.0, 20.0)],
      min_arc_radius=3.0,
    )

    self.assertEqual(
      [seg.seg_type for seg in segments],
      [SEG_TYPE_LINE, SEG_TYPE_CIRCLE, SEG_TYPE_LINE, SEG_TYPE_CIRCLE, SEG_TYPE_LINE],
    )

    first_arc_start = segments[0]
    first_arc = segments[1]
    center = circle_center_for_segment(first_arc_start, first_arc)
    self.assertIsNotNone(center)
    start_angle = math.atan2(first_arc_start.y - center[1], first_arc_start.x - center[0])
    end_angle = math.atan2(first_arc.y - center[1], first_arc.x - center[0])
    sweep = abs(arc_sweep_rad(start_angle, end_angle, first_arc.direction))
    self.assertAlmostEqual(sweep, math.pi / 4.0, delta=0.05)

  def test_waypoint_path_falls_back_to_stop_lines_when_fillets_are_impossible(self):
    segments = waypoint_path_segments(
      start_seq=10,
      term_type=4,
      waypoints=[(0.0, 0.0), (10.0, 0.0), (20.0, 10.0), (20.0, 20.0)],
      min_arc_radius=100.0,
    )

    self.assertEqual([seg.seg_type for seg in segments], [SEG_TYPE_LINE] * 4)
    self.assertTrue(all(seg.term_type == 0 for seg in segments))


if __name__ == "__main__":
  unittest.main()
