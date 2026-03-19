import unittest

from motionQueueTest_gui import (
  _live_position_matches_plan_start,
  _planner_waypoints,
  _planned_speed_summary_text,
)
from dune_winder.queued_motion.segment_types import MotionSegment


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


if __name__ == "__main__":
  unittest.main()
