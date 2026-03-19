import unittest

from motionQueueTest_gui import (
  _live_position_matches_plan_start,
  _planner_waypoints,
  _planned_speed_summary_text,
  _required_waypoint_min_arc_radius,
  _segment_dynamic_min_radius,
)
from dune_winder.queued_motion.segment_types import MotionSegment
from dune_winder.queued_motion.segment_types import SEG_TYPE_CIRCLE


class MotionQueueTestGuiTests(unittest.TestCase):
  def test_planner_waypoints_prepends_live_position_as_waypoint_zero(self):
    planner_waypoints = _planner_waypoints(
      (10.0, 20.0),
      [(1.0, 2.0), (3.0, 4.0)],
    )

    self.assertEqual(planner_waypoints, [(10.0, 20.0), (1.0, 2.0), (3.0, 4.0)])

  def test_planner_waypoints_deduplicates_first_destination_matching_live_position(self):
    planner_waypoints = _planner_waypoints(
      (10.0, 20.0),
      [(10.0, 20.0), (30.0, 40.0)],
    )

    self.assertEqual(planner_waypoints, [(10.0, 20.0), (30.0, 40.0)])

  def test_planner_waypoints_requires_live_position(self):
    self.assertIsNone(_planner_waypoints(None, [(1.0, 2.0)]))

  def test_live_position_matches_plan_start_within_tolerance(self):
    self.assertTrue(
      _live_position_matches_plan_start((10.0, 20.0), (10.05, 20.05), tolerance_mm=0.1)
    )

  def test_live_position_rejects_plan_start_outside_tolerance(self):
    self.assertFalse(
      _live_position_matches_plan_start((10.0, 20.0), (10.2, 20.0), tolerance_mm=0.1)
    )

  def test_planned_speed_summary_reports_uniform_planned_speed(self):
    text = _planned_speed_summary_text(
      1000.0,
      [
        MotionSegment(seq=1, x=10.0, y=0.0, speed=600.0),
        MotionSegment(seq=2, x=20.0, y=0.0, speed=600.0),
      ],
    )

    self.assertEqual(text, "requested_speed=1000.0 planned_speed=600.0")

  def test_planned_speed_summary_reports_capped_speed_range(self):
    text = _planned_speed_summary_text(
      1000.0,
      [
        MotionSegment(seq=1, x=10.0, y=0.0, speed=825.0),
        MotionSegment(seq=2, x=20.0, y=5.0, speed=600.0),
      ],
    )

    self.assertEqual(text, "requested_speed=1000.0 planned_speed[min/max]=600.0/825.0")

  def test_segment_dynamic_min_radius_respects_requested_minimum(self):
    seg = MotionSegment(seq=1, x=10.0, y=0.0, speed=100.0)

    self.assertEqual(_segment_dynamic_min_radius(seg, 75.0), 75.0)

  def test_required_waypoint_min_arc_radius_uses_dynamic_radius_for_arcs(self):
    requested_min_arc_radius = 50.0
    arc = MotionSegment(
      seq=1,
      x=10.0,
      y=10.0,
      speed=1000.0,
      seg_type=SEG_TYPE_CIRCLE,
    )

    required_radius = _required_waypoint_min_arc_radius([arc], requested_min_arc_radius)

    self.assertEqual(required_radius, _segment_dynamic_min_radius(arc, requested_min_arc_radius))
    self.assertGreater(required_radius, requested_min_arc_radius)

  def test_required_waypoint_min_arc_radius_ignores_non_arc_segments(self):
    requested_min_arc_radius = 50.0
    line = MotionSegment(seq=1, x=10.0, y=0.0, speed=1000.0)

    self.assertEqual(
      _required_waypoint_min_arc_radius([line], requested_min_arc_radius),
      requested_min_arc_radius,
    )


if __name__ == "__main__":
  unittest.main()
