import math
import unittest

from hypothesis import HealthCheck, given, settings, strategies as st

from dune_winder.queued_motion.safety import (
    MotionSafetyLimits,
    validate_segments_within_safety_limits,
)
from dune_winder.queued_motion.segment_patterns import (
    apply_merge_term_types,
    apsidal_precessing_orbit_segments,
    fibonacci_spiral_arc_segments,
    lissajous_segments,
    simple_two_segment_test,
    tangent_line_arc_segments,
)
from dune_winder.queued_motion.segment_types import (
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


def _bounds_strategy(span_min: float = 100.0, span_max: float = 5000.0):
    @st.composite
    def builder(draw):
        x_min = draw(st.floats(min_value=-2000.0, max_value=2000.0, allow_nan=False))
        y_min = draw(st.floats(min_value=-2000.0, max_value=2000.0, allow_nan=False))
        width = draw(st.floats(min_value=span_min, max_value=span_max, allow_nan=False))
        height = draw(
            st.floats(min_value=span_min, max_value=span_max, allow_nan=False)
        )
        return x_min, x_min + width, y_min, y_min + height

    return builder()


class FibonacciSpiralProperties(unittest.TestCase):
    @given(
        bounds=_bounds_strategy(),
        arc_count=st.integers(min_value=2, max_value=12),
        direction=st.sampled_from(["ccw", "cw"]),
    )
    @settings(
        max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_fits_requested_bounds_for_any_direction(
        self, bounds, arc_count, direction
    ):
        x_min, x_max, y_min, y_max = bounds
        segments = fibonacci_spiral_arc_segments(
            arc_count=arc_count,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            direction=direction,
        )

        circle_segments = [seg for seg in segments if seg.seg_type == SEG_TYPE_CIRCLE]
        self.assertEqual(len(circle_segments), arc_count)
        expected_dir = MCCM_DIR_2D_CCW if direction == "ccw" else MCCM_DIR_2D_CW
        self.assertTrue(all(seg.direction == expected_dir for seg in circle_segments))

        limits = MotionSafetyLimits(
            limit_left=x_min,
            limit_right=x_max,
            limit_bottom=y_min,
            limit_top=y_max,
            transfer_left=-1e9,
            transfer_y_threshold=1e9,
            headward_pivot_x=1e9,
            headward_pivot_y=1e9,
            headward_pivot_x_tolerance=1.0,
            headward_pivot_y_tolerance=1.0,
        )
        validate_segments_within_safety_limits(
            segments, limits, start_xy=_first_start_xy(segments)
        )

    def test_rejects_invalid_direction(self):
        with self.assertRaises(ValueError):
            fibonacci_spiral_arc_segments(direction="left")


class ApsidalOrbitProperties(unittest.TestCase):
    @given(
        bounds=_bounds_strategy(span_min=500.0, span_max=4000.0),
        revolutions=st.floats(min_value=1.0, max_value=6.0),
        eccentricity=st.floats(min_value=0.0, max_value=0.85),
        precession=st.floats(min_value=0.0, max_value=45.0),
        points_per_revolution=st.integers(min_value=30, max_value=120),
    )
    @settings(
        max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_orbit_stays_within_bounds(
        self, bounds, revolutions, eccentricity, precession, points_per_revolution
    ):
        x_min, x_max, y_min, y_max = bounds
        segments = apsidal_precessing_orbit_segments(
            start_seq=100,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            revolutions=revolutions,
            points_per_revolution=points_per_revolution,
            eccentricity=eccentricity,
            precession_deg_per_revolution=precession,
            boundary_margin=30.0,
        )

        self.assertGreater(len(segments), 1)
        self.assertEqual(segments[0].seg_type, SEG_TYPE_LINE)
        xs = [seg.x for seg in segments]
        ys = [seg.y for seg in segments]
        self.assertGreaterEqual(min(xs), x_min)
        self.assertLessEqual(max(xs), x_max)
        self.assertGreaterEqual(min(ys), y_min)
        self.assertLessEqual(max(ys), y_max)


class MergeTermTypeTests(unittest.TestCase):
    def test_marks_non_tangent_as_term0(self):
        tuned = apply_merge_term_types(
            simple_two_segment_test(start_seq=10, term_type=4), start_xy=(0.0, 0.0)
        )
        self.assertEqual(tuned[0].term_type, 0)
        self.assertEqual(tuned[1].term_type, 4)

    def test_marks_tangent_chain_as_term4(self):
        tuned = apply_merge_term_types(
            tangent_line_arc_segments(start_seq=20, term_type=0), start_xy=(0.0, 0.0)
        )
        self.assertTrue(all(seg.term_type == 4 for seg in tuned[:-1]))


class LissajousTests(unittest.TestCase):
    def test_uses_tangent_arc_interpolation(self):
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


class ApsidalOrbitPrecessionTests(unittest.TestCase):
    """Frequency-style analysis: kept as an example, not property-fuzzed."""

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
            if (
                radii[i] >= peak_threshold
                and radii[i] >= radii[i - 1]
                and radii[i] > radii[i + 1]
            ):
                candidate_indices.append(i)

        peak_indices: list[int] = []
        min_sep = max(10, points_per_rev // 3)
        for idx in candidate_indices:
            if not peak_indices or idx - peak_indices[-1] >= min_sep:
                peak_indices.append(idx)

        self.assertGreaterEqual(len(peak_indices), 5)

        peak_angles = [
            math.atan2(points[i][1] - cy, points[i][0] - cx) for i in peak_indices
        ]
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

        deltas_deg = [
            math.degrees(unwrapped[i] - unwrapped[i - 1])
            for i in range(1, len(unwrapped))
        ]
        for delta in deltas_deg:
            self.assertAlmostEqual(delta, precession, delta=4.0)


if __name__ == "__main__":
    unittest.main()
