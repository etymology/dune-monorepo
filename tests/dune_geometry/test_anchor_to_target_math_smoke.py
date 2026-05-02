"""Direct smoke tests for the smaller anchorToTarget math helpers ported
into `dune_geometry`.

These don't get golden fixtures because the math is small enough that
the parity surface is the legacy Python source itself — we cross-check
the Rust output against the legacy implementation called in-process.
"""

from __future__ import annotations

import math

import pytest

dune_geometry = pytest.importorskip("dune_geometry")
from dune_winder.queued_motion.filleted_path import (  # noqa: E402
    WaypointCircle,
    circle_pair_tangent_pairs as legacy_circle_pair_tangent_pairs,
)
from dune_winder.uv_head_target_parts.geometry2d import (  # noqa: E402
    _line_equation_from_tangent_points,
    _tangent_candidates_for_pin_pair,
)
from dune_winder.uv_head_target_parts.models import Point2D  # noqa: E402


_TOL = 1e-9


def _close_pair(actual, expected) -> bool:
    (afx, afy), (asx, asy) = actual
    (efx, efy), (esx, esy) = expected
    return (
        abs(afx - efx) <= _TOL
        and abs(afy - efy) <= _TOL
        and abs(asx - esx) <= _TOL
        and abs(asy - esy) <= _TOL
    )


def test_line_equation_horizontal_matches_legacy() -> None:
    actual = dune_geometry.line_equation_from_tangent_points((0.0, 5.0), (10.0, 5.0))
    legacy = _line_equation_from_tangent_points(Point2D(0.0, 5.0), Point2D(10.0, 5.0))
    assert actual == (legacy.slope, legacy.intercept, legacy.is_vertical)


def test_line_equation_vertical_matches_legacy() -> None:
    actual = dune_geometry.line_equation_from_tangent_points((3.0, 0.0), (3.0, 7.0))
    legacy = _line_equation_from_tangent_points(Point2D(3.0, 0.0), Point2D(3.0, 7.0))
    assert math.isinf(actual[0]) and math.isinf(legacy.slope)
    assert actual[1] == legacy.intercept
    assert actual[2] is True and legacy.is_vertical is True


def test_line_equation_diagonal_matches_legacy() -> None:
    actual = dune_geometry.line_equation_from_tangent_points((1.0, 2.0), (4.0, 8.0))
    legacy = _line_equation_from_tangent_points(Point2D(1.0, 2.0), Point2D(4.0, 8.0))
    assert actual == (legacy.slope, legacy.intercept, legacy.is_vertical)


def test_tangent_candidates_two_radii_match_legacy_realistic_pin_pair() -> None:
    point_a = (100.0, 50.0)
    point_b = (105.75, 50.5)
    radius_a = 0.5
    radius_b = 0.6  # legacy = pin_radius + clearance
    actual = dune_geometry.tangent_candidates_for_pin_pair(
        point_a, point_b, radius_a, radius_b
    )
    legacy_raw = legacy_circle_pair_tangent_pairs(
        WaypointCircle(waypoint_xy=point_a, center_xy=point_a, radius=radius_a),
        WaypointCircle(waypoint_xy=point_b, center_xy=point_b, radius=radius_b),
    )
    legacy_via_helper = _tangent_candidates_for_pin_pair(
        Point2D(*point_a),
        Point2D(*point_b),
        radius_a,
        point_b_radius=radius_b,
    )
    legacy_via_helper_tuples = [((p.x, p.y), (q.x, q.y)) for p, q in legacy_via_helper]
    assert len(actual) == len(legacy_raw) == len(legacy_via_helper_tuples)
    for ai, ei in zip(actual, legacy_raw):
        assert _close_pair(ai, ei)
    for ai, ei in zip(actual, legacy_via_helper_tuples):
        assert _close_pair(ai, ei)


def test_tangent_candidates_rejects_coincident_centers() -> None:
    with pytest.raises(ValueError):
        dune_geometry.tangent_candidates_for_pin_pair((1.0, 2.0), (1.0, 2.0), 0.5, 0.5)
