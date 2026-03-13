import math
import unittest

from dune_winder.motion.safety import MotionSafetyLimits, validate_segments_within_safety_limits
from dune_winder.motion.segment_patterns import (
  apply_merge_term_types,
  apsidal_precessing_orbit_segments,
  fibonacci_spiral_arc_segments,
  lissajous_segments,
  simple_two_segment_test,
  tangent_line_arc_segments,
)
from dune_winder.motion.segment_types import (
  MCCM_DIR_2D_CCW,
  MCCM_DIR_2D_CW,
  SEG_TYPE_CIRCLE,
  SEG_TYPE_LINE,
)


def _first_start_xy(segments):
  first = next(seg for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE)
  ex = first.x - first.via_center_x
  ey = first.y - first.via_center_y
  if first.direction == MCCM_DIR_2D_CCW:
    return (first.via_center_x + ey, first.via_center_y - ex)
  return (first.via_center_x - ey, first.via_center_y + ex)


class MotionSegmentPatternTests(unittest.TestCase):
  def test_fibonacci_spiral_fits_requested_bounds_ccw(self):
    segments = fibonacci_spiral_arc_segments(
      arc_count=8,
      x_min=100.0,
      x_max=600.0,
      y_min=200.0,
      y_max=900.0,
      direction="ccw",
    )

    circle_segments = [seg for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE]
    self.assertEqual(len(circle_segments), 8)
    self.assertTrue(all(seg.direction == MCCM_DIR_2D_CCW for seg in circle_segments))

    start_xy = _first_start_xy(segments)
    limits = MotionSafetyLimits(
      limit_left=100.0,
      limit_right=600.0,
      limit_bottom=200.0,
      limit_top=900.0,
      transfer_left=-1e9,
      transfer_y_threshold=1e9,
      headward_pivot_x=1e9,
      headward_pivot_y=1e9,
      headward_pivot_x_tolerance=1.0,
      headward_pivot_y_tolerance=1.0,
    )
    validate_segments_within_safety_limits(segments, limits, start_xy=start_xy)

  def test_fibonacci_spiral_fits_requested_bounds_cw(self):
    segments = fibonacci_spiral_arc_segments(
      arc_count=8,
      x_min=500.0,
      x_max=1400.0,
      y_min=1000.0,
      y_max=1800.0,
      direction="cw",
    )

    circle_segments = [seg for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE]
    self.assertEqual(len(circle_segments), 8)
    self.assertTrue(all(seg.direction == MCCM_DIR_2D_CW for seg in circle_segments))

    start_xy = _first_start_xy(segments)
    limits = MotionSafetyLimits(
      limit_left=500.0,
      limit_right=1400.0,
      limit_bottom=1000.0,
      limit_top=1800.0,
      transfer_left=-1e9,
      transfer_y_threshold=1e9,
      headward_pivot_x=1e9,
      headward_pivot_y=1e9,
      headward_pivot_x_tolerance=1.0,
      headward_pivot_y_tolerance=1.0,
    )
    validate_segments_within_safety_limits(segments, limits, start_xy=start_xy)

  def test_fibonacci_spiral_rejects_invalid_direction(self):
    with self.assertRaises(ValueError):
      fibonacci_spiral_arc_segments(direction="left")

  def test_apply_merge_term_types_marks_non_tangent_as_term0(self):
    segments = simple_two_segment_test(start_seq=10, term_type=4)

    tuned = apply_merge_term_types(segments, start_xy=(0.0, 0.0))

    self.assertEqual(tuned[0].term_type, 0)
    self.assertEqual(tuned[1].term_type, 4)

  def test_apply_merge_term_types_marks_tangent_chain_as_term4(self):
    segments = tangent_line_arc_segments(start_seq=20, term_type=0)

    tuned = apply_merge_term_types(segments, start_xy=(0.0, 0.0))

    self.assertTrue(all(seg.term_type == 4 for seg in tuned[:-1]))

  def test_lissajous_uses_tangent_arc_interpolation(self):
    segments = lissajous_segments(
      start_seq=50,
      tessellation_segments=80,
      x_min=1000.0,
      x_max=3000.0,
      y_min=200.0,
      y_max=1800.0,
    )

    self.assertGreater(len(segments), 10)
    self.assertEqual(segments[0].seg_type, SEG_TYPE_LINE)
    circle_segments = [seg for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE]
    self.assertGreater(len(circle_segments), 0)
    self.assertTrue(all(seg.circle_type == 1 for seg in circle_segments))

  def test_apsidal_orbit_stays_in_bounds(self):
    x_min = 1200.0
    x_max = 4200.0
    y_min = 200.0
    y_max = 2200.0
    segments = apsidal_precessing_orbit_segments(
      start_seq=100,
      x_min=x_min,
      x_max=x_max,
      y_min=y_min,
      y_max=y_max,
      revolutions=4.0,
      points_per_revolution=90,
      eccentricity=0.55,
      precession_deg_per_revolution=20.0,
      boundary_margin=30.0,
    )

    self.assertGreater(len(segments), 100)
    xs = [seg.x for seg in segments]
    ys = [seg.y for seg in segments]
    self.assertGreaterEqual(min(xs), x_min)
    self.assertLessEqual(max(xs), x_max)
    self.assertGreaterEqual(min(ys), y_min)
    self.assertLessEqual(max(ys), y_max)
    self.assertEqual(segments[0].seg_type, SEG_TYPE_LINE)
    self.assertGreater(sum(1 for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE), 0)

  def test_apsidal_orbit_precesses_per_revolution(self):
    points_per_rev = 120
    precession = 17.0
    x_min = 1000.0
    x_max = 5000.0
    y_min = 0.0
    y_max = 2500.0
    cx = 0.5 * (x_min + x_max)
    cy = 0.5 * (y_min + y_max)

    segments = apsidal_precessing_orbit_segments(
      start_seq=200,
      x_min=x_min,
      x_max=x_max,
      y_min=y_min,
      y_max=y_max,
      revolutions=3.0,
      points_per_revolution=points_per_rev,
      eccentricity=0.6,
      precession_deg_per_revolution=precession,
    )

    points = [(seg.x, seg.y) for seg in segments]
    radii = [math.hypot(x - cx, y - cy) for x, y in points]
    peak_threshold = 0.98 * max(radii)
    candidate_indices: list[int] = []
    for i in range(1, len(radii) - 1):
      if radii[i] >= peak_threshold and radii[i] >= radii[i - 1] and radii[i] > radii[i + 1]:
        candidate_indices.append(i)

    # Keep only peaks that are well-separated along the path.
    peak_indices: list[int] = []
    min_sep = max(10, points_per_rev // 3)
    for idx in candidate_indices:
      if not peak_indices or idx - peak_indices[-1] >= min_sep:
        peak_indices.append(idx)

    self.assertGreaterEqual(len(peak_indices), 5)

    peak_angles = [math.atan2(points[i][1] - cy, points[i][0] - cx) for i in peak_indices]
    reference = peak_angles[0]
    same_branch: list[float] = []
    for angle in peak_angles:
      if math.cos(angle - reference) > 0.0:
        same_branch.append(angle)

    self.assertGreaterEqual(len(same_branch), 3)
    angles = same_branch[:3]
    unwrapped = [angles[0]]
    for angle in angles[1:]:
      value = angle
      while value - unwrapped[-1] > math.pi:
        value -= 2.0 * math.pi
      while value - unwrapped[-1] < -math.pi:
        value += 2.0 * math.pi
      unwrapped.append(value)

    deltas_deg = [math.degrees(unwrapped[i] - unwrapped[i - 1]) for i in range(1, len(unwrapped))]
    for delta in deltas_deg:
      self.assertAlmostEqual(delta, precession, delta=4.0)


if __name__ == "__main__":
  unittest.main()
