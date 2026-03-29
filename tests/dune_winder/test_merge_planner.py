import unittest

from dune_winder.queued_motion.merge_planner import MergeWaypoint, build_merge_path_segments
from dune_winder.queued_motion.safety import MotionSafetyLimits
from dune_winder.queued_motion.segment_types import (
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)


def _permissive_limits() -> MotionSafetyLimits:
  return MotionSafetyLimits(
    limit_left=-1e6,
    limit_right=1e6,
    limit_bottom=-1e6,
    limit_top=1e6,
    transfer_left=-1e6,
    transfer_right=1e6,
    transfer_left_margin=0.0,
    transfer_y_threshold=1e9,
    headward_pivot_x=1e9,
    headward_pivot_y=1e9,
    headward_pivot_x_tolerance=1.0,
    headward_pivot_y_tolerance=1.0,
    queued_motion_z_collision_threshold=1e9,
    apa_collision_bottom_y=-1e6,
    apa_collision_top_y=1e6,
    transfer_zone_head_min_x=-1e6,
    transfer_zone_head_max_x=1e6,
    transfer_zone_foot_min_x=-1e6,
    transfer_zone_foot_max_x=1e6,
    support_collision_bottom_min_y=-1e6,
    support_collision_bottom_max_y=-1e6 + 1.0,
    support_collision_middle_min_y=-1e6,
    support_collision_middle_max_y=-1e6 + 1.0,
    support_collision_top_min_y=-1e6,
    support_collision_top_max_y=-1e6 + 1.0,
  )


def _waypoints(points: list[tuple[float, float]]) -> list[MergeWaypoint]:
  return [
    MergeWaypoint(line_index=index + 1, x=x, y=y, mode="PRECISE")
    for index, (x, y) in enumerate(points)
  ]


class MergePlannerTests(unittest.TestCase):
  def test_prefers_filleted_polygon_with_waypoints_on_arcs(self):
    segments = build_merge_path_segments(
      start_xy=(0.0, 0.0),
      waypoints=_waypoints([(10.0, 0.0), (20.0, 10.0), (20.0, 20.0)]),
      start_seq=100,
      speed=20.0,
      accel=200.0,
      decel=200.0,
      min_arc_radius=0.0,
      safety_limits=_permissive_limits(),
    )

    self.assertEqual(
      [seg.seg_type for seg in segments],
      [SEG_TYPE_LINE, SEG_TYPE_CIRCLE, SEG_TYPE_LINE, SEG_TYPE_CIRCLE, SEG_TYPE_LINE],
    )
    self.assertEqual([seg.term_type for seg in segments], [4, 4, 4, 4, 0])
    self.assertNotAlmostEqual(segments[0].x, 10.0, places=3)
    self.assertNotAlmostEqual(segments[2].x, 20.0, places=3)
    self.assertNotAlmostEqual(segments[2].y, 10.0, places=3)

    arc_starts = [(segments[0].x, segments[0].y), (segments[2].x, segments[2].y)]
    arc_waypoints = [(10.0, 0.0), (20.0, 10.0)]
    arc_segments = [segments[1], segments[3]]
    for start_xy, waypoint_xy, arc in zip(arc_starts, arc_waypoints, arc_segments):
      start_radius = ((start_xy[0] - arc.via_center_x) ** 2 + (start_xy[1] - arc.via_center_y) ** 2) ** 0.5
      waypoint_radius = (
        (waypoint_xy[0] - arc.via_center_x) ** 2 + (waypoint_xy[1] - arc.via_center_y) ** 2
      ) ** 0.5
      self.assertAlmostEqual(start_radius, waypoint_radius, places=6)

  def test_uses_jerk_limited_radius_larger_than_machine_minimum(self):
    segments = build_merge_path_segments(
      start_xy=(0.0, 0.0),
      waypoints=_waypoints([(500.0, 0.0), (1000.0, 500.0), (1000.0, 1000.0)]),
      start_seq=100,
      speed=200.0,
      accel=5000.0,
      decel=5000.0,
      jerk_accel=1500.0,
      jerk_decel=3000.0,
      min_arc_radius=10.0,
      safety_limits=_permissive_limits(),
    )

    first_arc = next(seg for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE)
    radius = ((segments[0].x - first_arc.via_center_x) ** 2 + (segments[0].y - first_arc.via_center_y) ** 2) ** 0.5
    self.assertGreater(radius, 70.0)

  def test_seeds_fillets_from_axis_limited_corner_speed(self):
    segments = build_merge_path_segments(
      start_xy=(0.0, 0.0),
      waypoints=_waypoints([(600.0, 0.0), (600.0, 600.0)]),
      start_seq=100,
      speed=900.0,
      accel=5000.0,
      decel=5000.0,
      jerk_accel=1000.0,
      jerk_decel=1000.0,
      min_arc_radius=10.0,
      safety_limits=_permissive_limits(),
      v_x_max=900.0,
      v_y_max=400.0,
    )

    self.assertEqual(
      [seg.seg_type for seg in segments],
      [SEG_TYPE_LINE, SEG_TYPE_CIRCLE, SEG_TYPE_LINE],
    )
    self.assertAlmostEqual(segments[0].speed, 900.0, places=6)
    self.assertAlmostEqual(segments[1].speed, 400.0, places=6)
    self.assertGreater(segments[2].speed, segments[1].speed)

    first_arc = segments[1]
    radius = ((segments[0].x - first_arc.via_center_x) ** 2 + (segments[0].y - first_arc.via_center_y) ** 2) ** 0.5
    self.assertGreater(radius, 250.0)
    self.assertLess(radius, 300.0)

  def test_falls_back_to_precise_stop_lines_when_filleted_path_is_impossible(self):
    segments = build_merge_path_segments(
      start_xy=(0.0, 0.0),
      waypoints=_waypoints([(10.0, 0.0), (20.0, 10.0), (20.0, 20.0)]),
      start_seq=100,
      speed=100.0,
      accel=200.0,
      decel=200.0,
      min_arc_radius=100.0,
      safety_limits=_permissive_limits(),
    )

    self.assertEqual(len(segments), 3)
    self.assertTrue(all(seg.seg_type == SEG_TYPE_LINE for seg in segments))
    self.assertTrue(all(seg.term_type == 0 for seg in segments))


if __name__ == "__main__":
  unittest.main()
