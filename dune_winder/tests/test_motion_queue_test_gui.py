import unittest

from motionQueueTest_gui import (
  _effective_planner_start_xy,
  _planned_speed_summary_text,
)
from dune_winder.queued_motion.segment_types import MotionSegment


class MotionQueueTestGuiTests(unittest.TestCase):
  def test_effective_planner_start_xy_prefers_explicit_start(self):
    start_xy = _effective_planner_start_xy(
      [(1.0, 2.0), (3.0, 4.0)],
      (10.0, 20.0),
    )

    self.assertEqual(start_xy, (10.0, 20.0))

  def test_effective_planner_start_xy_defaults_to_first_waypoint(self):
    start_xy = _effective_planner_start_xy(
      [(1.0, 2.0), (3.0, 4.0)],
      None,
    )

    self.assertEqual(start_xy, (1.0, 2.0))

  def test_effective_planner_start_xy_returns_none_without_waypoints(self):
    self.assertIsNone(_effective_planner_start_xy([], None))

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
