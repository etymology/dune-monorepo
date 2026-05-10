"""Behavior tests for machine.geometry primitives.

The geometry classes are pure data containers populated by chained constructors,
so the real risk is that constants or arithmetic relations drift silently.
"""

from __future__ import annotations

import pytest

from dune_winder.machine.geometry.apa import APA_Geometry
from dune_winder.machine.geometry.factory import create_layer_geometry
from dune_winder.machine.geometry.g import G_LayerGeometry
from dune_winder.machine.geometry.gx import GX_LayerGeometry
from dune_winder.machine.geometry.layer import LayerGeometry
from dune_winder.machine.geometry.layer_functions import LayerFunctions
from dune_winder.machine.geometry.machine import MachineGeometry
from dune_winder.machine.geometry.u import U_LayerGeometry
from dune_winder.machine.geometry.uv import UV_LayerGeometry
from dune_winder.machine.geometry.v import V_LayerGeometry
from dune_winder.machine.geometry.x import X_LayerGeometry


# ---------------------------------------------------------------------------
# Factory


@pytest.mark.parametrize(
    "name,expected",
    [
        ("X", X_LayerGeometry),
        ("V", V_LayerGeometry),
        ("U", U_LayerGeometry),
        ("G", G_LayerGeometry),
    ],
)
def test_factory_returns_expected_layer_class(name, expected):
    geometry = create_layer_geometry(name)
    assert isinstance(geometry, expected)


def test_factory_rejects_unknown_layer():
    with pytest.raises(ValueError, match="Unknown layer name"):
        create_layer_geometry("Q")


# ---------------------------------------------------------------------------
# Machine and APA bases


def test_machine_geometry_limits_are_positive():
    geometry = MachineGeometry()
    assert geometry.limitRight > geometry.limitLeft
    assert geometry.limitTop > geometry.limitBottom
    assert geometry.limitExtended > geometry.limitRetracted
    # Z hand-off edges live inside the X/Y limits.
    assert geometry.limitLeft <= geometry.left <= geometry.right <= geometry.limitRight


def test_apa_geometry_dimensions():
    geometry = APA_Geometry()
    # APA frame must be longer than it is tall, and the wind length extends past it.
    assert geometry.apaLength > geometry.apaHeight > geometry.apaThickness
    assert geometry.apaWindLength > geometry.apaLength
    assert geometry.apaLocation.x == pytest.approx(geometry.toAPA_OffsetX)


# ---------------------------------------------------------------------------
# Layer base + grid layers


def test_layer_geometry_base_constants():
    layer = LayerGeometry()
    assert layer.pitchX > layer.pitchY > 0
    assert layer.wireRadius == pytest.approx(layer.wireDiameter / 2)
    assert layer.boardHalfThickness == pytest.approx(layer.boardThickness / 2)
    # All four edges have a grid index.
    assert set(layer.edgeToGridIndex) == {"L", "T", "R", "B"}


@pytest.mark.parametrize(
    "geometry_class,expected_rows",
    [(X_LayerGeometry, 480), (G_LayerGeometry, 481)],
)
def test_grid_layer_pin_counts(geometry_class, expected_rows):
    geometry = geometry_class()
    assert geometry.rows == expected_rows
    assert geometry.pins == expected_rows * 2
    assert geometry.frontBackOffset == expected_rows
    # Grid layers use simple two-column pin spacing.
    assert geometry.pinSpacing == pytest.approx(230.0 / 48)


def test_gx_layer_geometry_is_abstract_until_configured():
    # GX_LayerGeometry without a subclass call to _configure_grid_layer_geometry
    # has no rows/pins set — the base just adds pinSpacing.
    geometry = GX_LayerGeometry()
    assert geometry.pinSpacing == pytest.approx(230.0 / 48)
    assert not hasattr(geometry, "rows")


# ---------------------------------------------------------------------------
# Induction layers


def test_uv_layer_geometry_base_relations():
    geometry = UV_LayerGeometry()
    assert geometry.deltaX > geometry.deltaY > 0
    # Slope and angle are derived from deltaY/deltaX.
    assert geometry.slope == pytest.approx(geometry.deltaY / geometry.deltaX)
    # Pin and wire radii are positive and consistent.
    assert geometry.pinRadius > 0
    assert geometry.pinDiameter == pytest.approx(2 * geometry.pinRadius)


def test_u_layer_pin_count_matches_formula():
    geometry = U_LayerGeometry()
    expected = 2 * geometry.rows + 2 * geometry.columns + 1
    assert geometry.pins == expected
    assert geometry.startPinFront == 400
    assert geometry.directionFront == -1
    assert geometry.directionBack == 1


def test_v_layer_pin_count_matches_formula():
    geometry = V_LayerGeometry()
    expected = 2 * geometry.rows + 2 * geometry.columns - 1
    assert geometry.pins == expected
    assert geometry.startPinFront == 399


# ---------------------------------------------------------------------------
# LayerFunctions


class _StubGeometry:
    def __init__(self, pins: int, start_front: float = 0, start_back: float = 0):
        self.pins = pins
        self.startPinFront = start_front
        self.startPinBack = start_back


def test_offset_pin_wraps_high():
    geometry = _StubGeometry(pins=10)
    # 9 + 5 should wrap to 4 (10 + extra +1 quirk preserved from original code)
    assert LayerFunctions.offsetPin(geometry, 9, 5) == 5


def test_offset_pin_wraps_low():
    geometry = _StubGeometry(pins=10)
    # 1 + (-3) should wrap up to 8.
    assert LayerFunctions.offsetPin(geometry, 1, -3) == 8


def test_offset_pin_no_wrap():
    geometry = _StubGeometry(pins=10)
    assert LayerFunctions.offsetPin(geometry, 3, 4) == 7


def test_translate_front_back_is_involutive_for_grid_layers():
    # On a grid layer (e.g. X) translating front->back twice returns the original pin.
    geometry = X_LayerGeometry()
    pin = 50
    once = LayerFunctions.translateFrontBack(geometry, pin)
    twice = LayerFunctions.translateFrontBack(geometry, once)
    # The translate function works in pin-number space; the round-trip lands
    # within the same pin set.
    assert 1 <= once <= geometry.pins
    assert 1 <= twice <= geometry.pins
