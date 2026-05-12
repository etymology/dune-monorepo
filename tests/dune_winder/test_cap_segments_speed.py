"""Tests for cap_segments_speed_by_axis_velocity.

The core invariant is: after capping, every segment's axis-projected
velocity stays within bounds. That invariant is property-fuzzed across
random sequences of mixed lines and arcs. Edge cases (empty input,
infinite limits, non-positive limits, degenerate geometry) are kept as
explicit examples.
"""

import math
import unittest

from hypothesis import HealthCheck, assume, given, settings, strategies as st

from dune_winder.queued_motion.segment_patterns import (
    _segment_tangent_component_bounds,
    cap_segments_speed_by_axis_velocity,
)
from dune_winder.queued_motion.segment_types import (
    CIRCLE_TYPE_CENTER,
    MCCM_DIR_2D_CCW,
    MCCM_DIR_2D_CW,
    MotionSegment,
    SEG_TYPE_CIRCLE,
    SEG_TYPE_LINE,
)


def _line(seq, x, y, speed=9999.0):
    return MotionSegment(seq=seq, x=x, y=y, speed=speed, seg_type=SEG_TYPE_LINE)


def _arc(seq, x, y, cx, cy, direction=MCCM_DIR_2D_CCW, speed=9999.0):
    return MotionSegment(
        seq=seq,
        x=x,
        y=y,
        speed=speed,
        seg_type=SEG_TYPE_CIRCLE,
        circle_type=CIRCLE_TYPE_CENTER,
        via_center_x=cx,
        via_center_y=cy,
        direction=direction,
    )


def _assert_within_axis_bounds(test, segments, v_x_max, v_y_max, start_xy):
    prev_x, prev_y = start_xy
    for seg in segments:
        max_tx, max_ty = _segment_tangent_component_bounds(prev_x, prev_y, seg)
        if max_tx > 1e-9:
            test.assertLessEqual(
                seg.speed * max_tx,
                v_x_max + 1e-6,
                f"seq={seg.seq}: x-axis velocity {seg.speed * max_tx:.3f} exceeds {v_x_max}",
            )
        if max_ty > 1e-9:
            test.assertLessEqual(
                seg.speed * max_ty,
                v_y_max + 1e-6,
                f"seq={seg.seq}: y-axis velocity {seg.speed * max_ty:.3f} exceeds {v_y_max}",
            )
        prev_x, prev_y = seg.x, seg.y


_coord = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False)
_speed = st.floats(
    min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)
_axis_limit = st.floats(
    min_value=10.0, max_value=2000.0, allow_nan=False, allow_infinity=False
)
_direction = st.sampled_from([MCCM_DIR_2D_CCW, MCCM_DIR_2D_CW])


@st.composite
def _segment_sequence(draw):
    n = draw(st.integers(min_value=1, max_value=8))
    start_xy = (draw(_coord), draw(_coord))
    segments = []
    prev_x, prev_y = start_xy
    for i in range(n):
        if draw(st.booleans()):
            ex, ey = draw(_coord), draw(_coord)
            segments.append(_line(i + 1, ex, ey, speed=draw(_speed)))
            prev_x, prev_y = ex, ey
        else:
            cx, cy = draw(_coord), draw(_coord)
            radius = math.hypot(prev_x - cx, prev_y - cy)
            assume(radius > 1.0)  # avoid degenerate arcs
            angle = draw(st.floats(min_value=0.1, max_value=2 * math.pi - 0.1))
            direction = draw(_direction)
            sign = 1.0 if direction == MCCM_DIR_2D_CCW else -1.0
            start_angle = math.atan2(prev_y - cy, prev_x - cx)
            end_angle = start_angle + sign * angle
            ex = cx + radius * math.cos(end_angle)
            ey = cy + radius * math.sin(end_angle)
            segments.append(
                _arc(i + 1, ex, ey, cx, cy, direction=direction, speed=draw(_speed))
            )
            prev_x, prev_y = ex, ey
    return segments, start_xy


class CapSegmentsSpeedProperties(unittest.TestCase):
    @given(seq=_segment_sequence(), v_x_max=_axis_limit, v_y_max=_axis_limit)
    @settings(
        max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_capped_speeds_satisfy_axis_velocity_bounds(self, seq, v_x_max, v_y_max):
        segments, start_xy = seq
        result = cap_segments_speed_by_axis_velocity(
            segments, v_x_max=v_x_max, v_y_max=v_y_max, start_xy=start_xy
        )
        _assert_within_axis_bounds(self, result, v_x_max, v_y_max, start_xy)

    @given(seq=_segment_sequence(), v_x_max=_axis_limit, v_y_max=_axis_limit)
    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_capping_is_idempotent(self, seq, v_x_max, v_y_max):
        segments, start_xy = seq
        first = cap_segments_speed_by_axis_velocity(
            segments, v_x_max=v_x_max, v_y_max=v_y_max, start_xy=start_xy
        )
        second = cap_segments_speed_by_axis_velocity(
            first, v_x_max=v_x_max, v_y_max=v_y_max, start_xy=start_xy
        )
        for a, b in zip(first, second):
            self.assertAlmostEqual(a.speed, b.speed, places=6)

    @given(seq=_segment_sequence(), v_x_max=_axis_limit, v_y_max=_axis_limit)
    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow]
    )
    def test_capping_never_increases_speed(self, seq, v_x_max, v_y_max):
        segments, start_xy = seq
        result = cap_segments_speed_by_axis_velocity(
            segments, v_x_max=v_x_max, v_y_max=v_y_max, start_xy=start_xy
        )
        for original, capped in zip(segments, result):
            self.assertLessEqual(capped.speed, original.speed + 1e-9)


class CapSegmentsSpeedEdgeCases(unittest.TestCase):
    def test_empty_list_returns_empty(self):
        self.assertEqual(cap_segments_speed_by_axis_velocity([]), [])

    def test_both_axes_infinite_returns_unchanged(self):
        segs = [_line(1, 100.0, 0.0, speed=5000.0)]
        result = cap_segments_speed_by_axis_velocity(segs, math.inf, math.inf)
        self.assertEqual(result[0].speed, 5000.0)

    def test_zero_vx_raises(self):
        with self.assertRaises(ValueError):
            cap_segments_speed_by_axis_velocity([_line(1, 10.0, 0.0)], v_x_max=0.0)

    def test_negative_vy_raises(self):
        with self.assertRaises(ValueError):
            cap_segments_speed_by_axis_velocity([_line(1, 0.0, 10.0)], v_y_max=-1.0)

    def test_zero_length_segment_does_not_produce_nan(self):
        segs = [_line(1, 0.0, 0.0, speed=9999.0)]
        result = cap_segments_speed_by_axis_velocity(
            segs, v_x_max=500.0, v_y_max=500.0, start_xy=(0.0, 0.0)
        )
        self.assertFalse(math.isnan(result[0].speed))
        self.assertFalse(math.isinf(result[0].speed))

    def test_no_start_xy_uses_conservative_first_segment_cap(self):
        v_x_max = 300.0
        segs = [_line(1, 100.0, 0.0, speed=9999.0), _line(2, 200.0, 0.0, speed=9999.0)]
        result = cap_segments_speed_by_axis_velocity(
            segs, v_x_max=v_x_max, v_y_max=math.inf
        )
        for seg in result:
            self.assertLessEqual(seg.speed, v_x_max + 1e-6)


if __name__ == "__main__":
    unittest.main()
