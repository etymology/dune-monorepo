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
from dune_winder.uv_head_target_parts.geometry2d import (  # noqa: E402
    _line_equation_from_tangent_points,
)
from dune_winder.uv_head_target_parts.models import Point2D  # noqa: E402


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
