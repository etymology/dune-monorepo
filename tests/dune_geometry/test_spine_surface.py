"""Smoke tests for the spine PyO3 surface.

Spec source of truth: `specs/spine-calibration.allium`. Each test pins
a contract from that spec; golden parity fixtures for the closed-loop
fit will land alongside the higher-fidelity solver in a follow-up.
"""

from __future__ import annotations

import pytest

dune_geometry = pytest.importorskip("dune_geometry")


def _pin(layer: str, side: str, number: int):
    return dune_geometry.Pin(layer, side, number)


def test_derive_a_side_is_plus_half_width_in_z() -> None:
    spine = (10.0, 20.0, 100.0)
    derived = dune_geometry.derive_pin_position_from_spine(spine, _pin("U", "A", 1))
    assert derived == (10.0, 20.0, 165.0)


def test_derive_b_side_is_minus_half_width_in_z() -> None:
    spine = (10.0, 20.0, 100.0)
    derived = dune_geometry.derive_pin_position_from_spine(spine, _pin("U", "B", 1))
    assert derived == (10.0, 20.0, 35.0)


def test_derive_is_symmetric_about_spine() -> None:
    spine = (1.0, 2.0, 50.0)
    a = dune_geometry.derive_pin_position_from_spine(spine, _pin("V", "A", 5))
    b = dune_geometry.derive_pin_position_from_spine(spine, _pin("V", "B", 5))
    assert a[0] == b[0] == spine[0]
    assert a[1] == b[1] == spine[1]
    assert (a[2] + b[2]) / 2 == spine[2]
    assert a[2] - b[2] == 120.0  # V board width


def test_observe_round_trips_with_derive() -> None:
    spine = (3.0, 4.0, 12.0)
    for side in ("A", "B"):
        pin = _pin("U", side, 17)
        winder = dune_geometry.derive_pin_position_from_spine(spine, pin)
        observed = dune_geometry.observe_spine_point_from_touch(pin, winder)
        for actual, expected in zip(observed, spine, strict=True):
            assert abs(actual - expected) < 1e-12


def test_solve_with_two_observations_interpolates_linearly() -> None:
    pin_1 = _pin("U", "A", 1)
    pin_1201 = _pin("U", "A", 1201)
    winder_1 = dune_geometry.derive_pin_position_from_spine((0.0, 0.0, 0.0), pin_1)
    winder_1201 = dune_geometry.derive_pin_position_from_spine(
        (100.0, 0.0, 10.0), pin_1201
    )
    loop = dune_geometry.solve_spine_loop(
        "U", [(pin_1, winder_1), (pin_1201, winder_1201)]
    )
    assert len(loop.points) == 2401
    spine_at_1 = loop.point(1).xyz
    spine_at_1201 = loop.point(1201).xyz
    spine_at_601 = loop.point(601).xyz
    assert (spine_at_1.x, spine_at_1.y, spine_at_1.z) == (0.0, 0.0, 0.0)
    assert (spine_at_1201.x, spine_at_1201.y, spine_at_1201.z) == (100.0, 0.0, 10.0)
    # Halfway along the forward arc 1 → 1201 is pin 601; lerp midpoint
    # is (50, 0, 5).
    assert abs(spine_at_601.x - 50.0) < 1e-9
    assert abs(spine_at_601.y - 0.0) < 1e-9
    assert abs(spine_at_601.z - 5.0) < 1e-9


def test_solve_rejects_empty_touches() -> None:
    with pytest.raises(ValueError):
        dune_geometry.solve_spine_loop("U", [])


def test_solve_rejects_layer_mismatch() -> None:
    with pytest.raises(ValueError):
        dune_geometry.solve_spine_loop("U", [(_pin("V", "A", 1), (0.0, 0.0, 0.0))])
