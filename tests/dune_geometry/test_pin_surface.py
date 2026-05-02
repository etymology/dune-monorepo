"""Surface tests for the dune_geometry PyO3 module.

Run with `uv run pytest tests/dune_geometry/` after the wheel is installed
via `uv sync`.

These tests prove the Rust ↔ Python boundary, not the underlying maths
(which is covered by `cargo test -p dune_geometry`).
"""

from __future__ import annotations

import pytest

dune_geometry = pytest.importorskip("dune_geometry")


def test_pin_constructor_and_string_form() -> None:
    pin = dune_geometry.Pin("U", "A", 1)
    assert pin.layer == "U"
    assert pin.side == "A"
    assert pin.number == 1
    assert str(pin) == "UA1"


def test_pin_from_str_round_trip() -> None:
    for name in ("UA1", "UA2401", "VB1199", "VA2399", "UB1500"):
        pin = dune_geometry.Pin.from_str(name)
        assert str(pin) == name


def test_invalid_pin_number_raises() -> None:
    with pytest.raises(ValueError):
        dune_geometry.Pin("U", "A", 0)
    with pytest.raises(ValueError):
        dune_geometry.Pin("U", "A", 2402)
    with pytest.raises(ValueError):
        dune_geometry.Pin("V", "A", 2400)


def test_invalid_layer_or_side_raises() -> None:
    with pytest.raises(ValueError):
        dune_geometry.Pin("X", "A", 1)
    with pytest.raises(ValueError):
        dune_geometry.Pin("U", "C", 1)


def test_face_classifications() -> None:
    assert dune_geometry.Pin("U", "A", 1).face == "head"
    assert dune_geometry.Pin("U", "A", 401).face == "bottom"
    assert dune_geometry.Pin("U", "A", 1201).face == "foot"
    assert dune_geometry.Pin("U", "A", 1602).face == "top"
    assert dune_geometry.Pin("V", "B", 399).face == "head"
    assert dune_geometry.Pin("V", "B", 400).face == "bottom"
    assert dune_geometry.Pin("V", "B", 1200).face == "foot"
    assert dune_geometry.Pin("V", "B", 1600).face == "top"


def test_tangent_normal_sign_examples() -> None:
    # Mirrors the Rust unit tests; double-checked through the FFI boundary.
    assert dune_geometry.Pin("U", "B", 1).tangent_normal_sign == (1, 1)
    assert dune_geometry.Pin("U", "A", 1).tangent_normal_sign == (1, -1)
    assert dune_geometry.Pin("U", "A", 1500).tangent_normal_sign == (-1, 1)
    assert dune_geometry.Pin("V", "A", 200).tangent_normal_sign == (1, 1)
    assert dune_geometry.tangent_sides("U", "B", 1) == (1, 1)


def test_endpoint_membership_matches_table() -> None:
    table_u = set(dune_geometry.endpoint_pins("U"))
    table_v = set(dune_geometry.endpoint_pins("V"))
    assert dune_geometry.Pin("U", "A", 1).is_endpoint
    assert dune_geometry.Pin("U", "A", 2).is_endpoint is False
    assert 1 in table_u
    assert 2401 in table_u
    assert 1 in table_v
    assert 2399 in table_v


def test_board_widths() -> None:
    assert dune_geometry.Pin("U", "A", 1).board_a_to_b_z_mm == 130.0
    assert dune_geometry.Pin("V", "A", 1).board_a_to_b_z_mm == 120.0
    assert dune_geometry.board_a_to_b_z_mm("U") == 130.0
    assert dune_geometry.board_a_to_b_z_mm("V") == 120.0


def test_pin_count() -> None:
    assert dune_geometry.pin_count("U") == 2401
    assert dune_geometry.pin_count("V") == 2399


def test_face_ranges_cover_layer() -> None:
    for layer, expected_max in (("U", 2401), ("V", 2399)):
        ranges = dune_geometry.face_ranges(layer)
        assert ranges[0][0] == "head"
        assert ranges[0][1] == 1
        assert ranges[-1][0] == "top"
        assert ranges[-1][2] == expected_max


def test_pin_equality_and_hash() -> None:
    a = dune_geometry.Pin("U", "A", 1)
    b = dune_geometry.Pin("U", "A", 1)
    assert a == b
    assert hash(a) == hash(b)
    s = {a, b, dune_geometry.Pin("U", "A", 2)}
    assert len(s) == 2
