import unittest

from motionQueueTest_gui import _effective_planner_start_xy


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


if __name__ == "__main__":
  unittest.main()
