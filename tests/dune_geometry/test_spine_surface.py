"""Smoke tests for the spine PyO3 surface.

Spec source of truth: `specs/spine-calibration.allium`. Each test pins
a contract from that spec.
"""

from __future__ import annotations

import pytest

dune_geometry = pytest.importorskip("dune_geometry")


def _pin(layer: str, side: str, number: int):
    return dune_geometry.Pin(layer, side, number)


def test_derive_a_side_is_minus_half_width_in_z() -> None:
    spine = (10.0, 20.0, 100.0)
    derived = dune_geometry.derive_pin_position_from_spine(spine, _pin("U", "A", 1))
    assert derived == (10.0, 20.0, 35.0)  # 100 - 65


def test_derive_b_side_is_plus_half_width_in_z() -> None:
    spine = (10.0, 20.0, 100.0)
    derived = dune_geometry.derive_pin_position_from_spine(spine, _pin("U", "B", 1))
    assert derived == (10.0, 20.0, 165.0)  # 100 + 65


def test_derive_is_symmetric_about_spine() -> None:
    spine = (1.0, 2.0, 50.0)
    a = dune_geometry.derive_pin_position_from_spine(spine, _pin("V", "A", 5))
    b = dune_geometry.derive_pin_position_from_spine(spine, _pin("V", "B", 5))
    assert a[0] == b[0] == spine[0]
    assert a[1] == b[1] == spine[1]
    assert (a[2] + b[2]) / 2 == spine[2]
    assert b[2] - a[2] == 120.0  # V board width; B is +, A is -


def test_observe_round_trips_with_derive() -> None:
    spine = (3.0, 4.0, 12.0)
    for side in ("A", "B"):
        pin = _pin("U", side, 17)
        winder = dune_geometry.derive_pin_position_from_spine(spine, pin)
        observed = dune_geometry.observe_spine_point_from_touch(pin, winder)
        for actual, expected in zip(observed, spine, strict=True):
            assert abs(actual - expected) < 1e-12


def test_solve_plane_flat_observations() -> None:
    pin_1 = _pin("U", "A", 1)
    pin_601 = _pin("U", "A", 601)
    winder_1 = dune_geometry.derive_pin_position_from_spine((0.0, 0.0, 207.0), pin_1)
    winder_601 = dune_geometry.derive_pin_position_from_spine(
        (100.0, 50.0, 207.0), pin_601
    )
    plane = dune_geometry.solve_spine_plane([(pin_1, winder_1), (pin_601, winder_601)])
    assert abs(plane.c - 207.0) < 1.0
    assert abs(plane.a) < 0.01
    assert abs(plane.b) < 0.01


def test_solve_plane_accepts_mixed_layers() -> None:
    ua = _pin("U", "A", 1)
    vb = _pin("V", "B", 1)
    winder_ua = dune_geometry.derive_pin_position_from_spine((0.0, 0.0, 207.0), ua)
    winder_vb = dune_geometry.derive_pin_position_from_spine((100.0, 0.0, 207.0), vb)
    plane = dune_geometry.solve_spine_plane([(ua, winder_ua), (vb, winder_vb)])
    assert abs(plane.c - 207.0) < 1.0


def test_solve_plane_rejects_empty_touches() -> None:
    with pytest.raises(ValueError):
        dune_geometry.solve_spine_plane([])


def test_spine_calibration_file_z_at() -> None:
    plane = dune_geometry.SpinePlane(0.0, 0.0, 207.0)
    f = dune_geometry.SpineCalibrationFile("test", plane)
    z_a = f.z_at("U", "A", 0.0, 0.0)
    z_b = f.z_at("U", "B", 0.0, 0.0)
    assert z_a == 207.0 - 65.0  # A is −half_w
    assert z_b == 207.0 + 65.0  # B is +half_w


def test_spine_calibration_file_same_plane_all_layers() -> None:
    plane = dune_geometry.SpinePlane(0.0, 0.0, 207.0)
    f = dune_geometry.SpineCalibrationFile("test", plane)
    u_mid = (f.z_at("U", "A", 0.0, 0.0) + f.z_at("U", "B", 0.0, 0.0)) / 2
    v_mid = (f.z_at("V", "A", 0.0, 0.0) + f.z_at("V", "B", 0.0, 0.0)) / 2
    assert u_mid == 207.0
    assert v_mid == 207.0


def test_spine_calibration_file_defaults_when_absent() -> None:
    f = dune_geometry.SpineCalibrationFile("test")
    z_a = f.z_at("U", "A", 0.0, 0.0)
    assert z_a == 207.0 - 65.0  # default plane Z=207
