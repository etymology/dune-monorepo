"""Tests for queued_motion submodules with no other coverage."""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from dune_winder.queued_motion.diagnostics import serialize_segment_diagnostics
from dune_winder.queued_motion.filleted_path import (
    WaypointCircle,
    build_waypoint_circles,
    circle_pair_tangent_pairs,
    distance_xy,
    dynamic_min_radius,
    filleted_polygon_segments,
    point_circle_tangent_points,
    unit_vector_between,
)
from dune_winder.queued_motion.jerk_limits import (
    DEFAULT_QUEUED_MOTION_ACCEL_JERK,
    is_valid_queued_motion_jerk,
    normalize_queued_motion_jerk,
)
from dune_winder.queued_motion.segment_types import (
    CIRCLE_TYPE_CENTER,
    MotionSegment,
    SEG_TYPE_CIRCLE,
    SEG_TYPE_LINE,
)


_finite_coord = st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False)
_xy = st.tuples(_finite_coord, _finite_coord)
_positive_finite = st.floats(
    min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False
)


# ---------------------------------------------------------------------------
# jerk_limits


@given(value=_positive_finite)
def test_normalize_jerk_returns_input_for_positive_finite_numeric(value):
    assert normalize_queued_motion_jerk(value) == pytest.approx(value)
    assert normalize_queued_motion_jerk(str(value)) == pytest.approx(value)
    assert is_valid_queued_motion_jerk(value) is True


@given(
    value=st.one_of(
        st.none(),
        st.text(min_size=1, max_size=4).filter(
            lambda s: not s.lstrip("-+").replace(".", "", 1).isdigit()
        ),
        st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
        st.just(float("nan")),
        st.just(float("inf")),
        st.just(float("-inf")),
    )
)
def test_normalize_jerk_falls_back_for_invalid_inputs(value):
    assert normalize_queued_motion_jerk(value) == DEFAULT_QUEUED_MOTION_ACCEL_JERK
    assert is_valid_queued_motion_jerk(value) is False


@given(default=_positive_finite)
def test_normalize_jerk_uses_supplied_default(default):
    assert normalize_queued_motion_jerk(None, default=default) == pytest.approx(default)


# ---------------------------------------------------------------------------
# distance_xy and unit_vector_between


@given(p0=_xy, p1=_xy)
def test_distance_xy_is_symmetric_and_non_negative(p0, p1):
    d = distance_xy(p0, p1)
    assert d >= 0.0
    assert distance_xy(p1, p0) == pytest.approx(d)


@given(p0=_xy, p1=_xy, p2=_xy)
def test_distance_xy_satisfies_triangle_inequality(p0, p1, p2):
    a = distance_xy(p0, p1)
    b = distance_xy(p1, p2)
    c = distance_xy(p0, p2)
    assert a + b + 1e-9 >= c


@given(p0=_xy, p1=_xy)
def test_unit_vector_has_unit_magnitude_or_none_when_coincident(p0, p1):
    # unit_vector_between collapses points within its 1e-6 epsilon; check both branches.
    vector = unit_vector_between(p0, p1)
    if vector is None:
        assert distance_xy(p0, p1) <= 1e-6
    else:
        assert math.hypot(vector[0], vector[1]) == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# dynamic_min_radius


@given(
    speed=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False),
    base=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    accel=_positive_finite,
    jerk=_positive_finite,
)
def test_dynamic_min_radius_never_below_base(speed, base, accel, jerk):
    radius = dynamic_min_radius(
        speed=speed, base_min_radius=base, accel_limit=accel, jerk_limit=jerk
    )
    assert radius >= base - 1e-9


@given(
    speed_low=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    speed_high=st.floats(min_value=100.0, max_value=1000.0, allow_nan=False),
    base=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    accel=_positive_finite,
    jerk=_positive_finite,
)
def test_dynamic_min_radius_monotone_in_speed(speed_low, speed_high, base, accel, jerk):
    assume(speed_low <= speed_high)
    low = dynamic_min_radius(
        speed=speed_low, base_min_radius=base, accel_limit=accel, jerk_limit=jerk
    )
    high = dynamic_min_radius(
        speed=speed_high, base_min_radius=base, accel_limit=accel, jerk_limit=jerk
    )
    assert high + 1e-9 >= low


def test_dynamic_min_radius_jerk_dominates_high_accel():
    radius = dynamic_min_radius(
        speed=10.0, base_min_radius=0.0, accel_limit=1e9, jerk_limit=10.0
    )
    assert radius == pytest.approx(math.sqrt(1000.0 / 10.0))


def test_dynamic_min_radius_zero_speed_returns_base():
    assert dynamic_min_radius(
        speed=0.0, base_min_radius=5.0, accel_limit=100.0, jerk_limit=100.0
    ) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# diagnostics


def test_serialize_segment_diagnostics_empty():
    diagnostics, summary = serialize_segment_diagnostics(
        start_xy=(0.0, 0.0), segments=[]
    )
    assert diagnostics == []
    assert summary["segmentCount"] == 0
    assert summary["lineCount"] == 0
    assert summary["circleCount"] == 0
    assert summary["totalPathLength"] == 0.0


@given(
    start_xy=_xy,
    points=st.lists(_xy, min_size=1, max_size=8),
)
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_serialize_segment_diagnostics_sums_line_lengths(start_xy, points):
    segments = [
        MotionSegment(seq=i + 1, x=x, y=y, seg_type=SEG_TYPE_LINE, speed=100.0)
        for i, (x, y) in enumerate(points)
    ]
    diagnostics, summary = serialize_segment_diagnostics(
        start_xy=start_xy, segments=segments
    )
    expected_total = 0.0
    cursor = start_xy
    for x, y in points:
        expected_total += math.hypot(x - cursor[0], y - cursor[1])
        cursor = (x, y)
    assert summary["segmentCount"] == len(points)
    assert summary["lineCount"] == len(points)
    assert summary["circleCount"] == 0
    assert summary["totalPathLength"] == pytest.approx(expected_total, abs=1e-6)
    assert diagnostics[0]["start"] == {"x": start_xy[0], "y": start_xy[1]}


def test_serialize_segment_diagnostics_includes_circle_metadata():
    segments = [
        MotionSegment(seq=1, x=1.0, y=0.0, seg_type=SEG_TYPE_LINE),
        MotionSegment(
            seq=2,
            x=0.0,
            y=1.0,
            seg_type=SEG_TYPE_CIRCLE,
            circle_type=CIRCLE_TYPE_CENTER,
            via_center_x=0.0,
            via_center_y=0.0,
            direction=1,
        ),
    ]
    diagnostics, summary = serialize_segment_diagnostics(
        start_xy=(0.0, 0.0), segments=segments
    )
    assert summary["lineCount"] == 1
    assert summary["circleCount"] == 1
    circle = diagnostics[1]["circle"]
    assert isinstance(circle, dict)
    assert circle["radius"] == pytest.approx(1.0)
    assert circle["directionLabel"] == "CCW"


# ---------------------------------------------------------------------------
# filleted_path geometric primitives


@given(
    center=_xy,
    radius=st.floats(min_value=0.5, max_value=100.0, allow_nan=False),
    point_offset=st.floats(min_value=0.0, max_value=200.0, allow_nan=False),
    angle=st.floats(min_value=0.0, max_value=2 * math.pi),
)
@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_point_circle_tangent_points_lie_on_circle_iff_outside(
    center, radius, point_offset, angle
):
    # The implementation returns no tangents when the point is within radius+1e-9
    # of the center. Avoid the FP-wobble band straddling that boundary.
    assume(abs(point_offset - radius) > 1e-6)
    point = (
        center[0] + point_offset * math.cos(angle),
        center[1] + point_offset * math.sin(angle),
    )
    circle = WaypointCircle(waypoint_xy=center, center_xy=center, radius=radius)
    tangents = point_circle_tangent_points(point, circle)
    if point_offset < radius:
        assert tangents == []
    else:
        assert len(tangents) == 2
        for tx, ty in tangents:
            d = math.hypot(tx - center[0], ty - center[1])
            assert d == pytest.approx(radius, abs=1e-6)


def test_build_waypoint_circles_zero_radius_returns_empty_list():
    assert (
        build_waypoint_circles(start_xy=(0.0, 0.0), waypoints=[(1.0, 1.0)], radius=0.0)
        == []
    )


def test_build_waypoint_circles_right_angle_corner():
    circles = build_waypoint_circles(
        start_xy=(0.0, 0.0), waypoints=[(10.0, 0.0), (10.0, 10.0)], radius=1.0
    )
    assert circles is not None
    assert len(circles) == 1
    circle = circles[0]
    assert circle.waypoint_xy == (10.0, 0.0)
    assert circle.radius == pytest.approx(1.0)
    expected_offset = 1.0 / math.sqrt(2.0)
    assert circle.center_xy[0] == pytest.approx(10.0 - expected_offset)
    assert circle.center_xy[1] == pytest.approx(expected_offset)


def test_circle_pair_tangent_pairs_finds_external_tangents():
    a = WaypointCircle(waypoint_xy=(0.0, 0.0), center_xy=(0.0, 0.0), radius=1.0)
    b = WaypointCircle(waypoint_xy=(10.0, 0.0), center_xy=(10.0, 0.0), radius=1.0)
    pairs = circle_pair_tangent_pairs(a, b)
    assert len(pairs) >= 2
    for first, second in pairs:
        assert math.hypot(first[0], first[1]) == pytest.approx(1.0, abs=1e-6)
        assert math.hypot(second[0] - 10.0, second[1]) == pytest.approx(1.0, abs=1e-6)


def test_filleted_polygon_segments_empty_returns_empty():
    assert (
        filleted_polygon_segments(
            start_xy=(0.0, 0.0),
            waypoints=[],
            radius=1.0,
            line_term_type=0,
            arc_term_type=0,
            final_term_type=0,
        )
        == []
    )


def test_filleted_polygon_segments_single_waypoint_returns_one_line():
    segments = filleted_polygon_segments(
        start_xy=(0.0, 0.0),
        waypoints=[(5.0, 0.0)],
        radius=1.0,
        line_term_type=1,
        arc_term_type=2,
        final_term_type=3,
    )
    assert segments is not None
    assert len(segments) == 1
    assert segments[0].seg_type == SEG_TYPE_LINE
    assert segments[0].x == pytest.approx(5.0)
    assert segments[0].term_type == 3


def test_filleted_polygon_segments_right_angle_produces_arc():
    segments = filleted_polygon_segments(
        start_xy=(0.0, 0.0),
        waypoints=[(10.0, 0.0), (10.0, 10.0)],
        radius=1.0,
        line_term_type=1,
        arc_term_type=2,
        final_term_type=3,
    )
    assert segments is not None
    assert any(seg.seg_type == SEG_TYPE_CIRCLE for seg in segments)
    assert segments[-1].term_type == 3
