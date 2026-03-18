import unittest

from dune_winder.queued_motion.segment_patterns import (
  DEFAULT_WAYPOINT_ORDER_MODE,
  waypoint_path_segments,
)
from dune_winder.queued_motion.segment_types import SEG_TYPE_CIRCLE, SEG_TYPE_LINE


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
