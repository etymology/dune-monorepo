"""Tests for the dune_geometry.Pin adapter on LayerCalibration.

Phase B of the UV layer rewrite added Pin-typed methods to
LayerCalibration so callers can address pins by structured Pin objects
without changing the on-disk legacy storage.
"""

from __future__ import annotations

import pytest

from dune_winder.geometry.primitives.location import Location
from dune_winder.machine.calibration.layer import LayerCalibration

dune_geometry = pytest.importorskip("dune_geometry")


def _build_calibration(layer: str) -> LayerCalibration:
    cal = LayerCalibration(layer=layer)
    cal.setPinLocation("A1", Location(1.0, 2.0, 3.0))
    cal.setPinLocation("B400", Location(4.0, 5.0, 6.0))
    return cal


def test_get_pin_objects_returns_pins() -> None:
    cal = _build_calibration("U")
    pins = cal.getPinObjects()
    assert {str(p) for p in pins} == {"UA1", "UB400"}


def test_get_pin_location_by_pin() -> None:
    cal = _build_calibration("U")
    pin = dune_geometry.Pin("U", "A", 1)
    loc = cal.getPinLocationByPin(pin)
    assert loc.x == 1.0
    assert loc.y == 2.0
    assert loc.z == 3.0


def test_set_pin_location_by_pin() -> None:
    cal = LayerCalibration(layer="V")
    pin = dune_geometry.Pin("V", "B", 23)
    cal.setPinLocationByPin(pin, Location(7.5, 8.5, 9.5))
    loc = cal.getPinLocation("B23")
    assert loc.x == 7.5
    assert loc.y == 8.5
    assert loc.z == 9.5


def test_get_pin_location_by_pin_layer_mismatch_raises() -> None:
    cal = _build_calibration("U")
    pin = dune_geometry.Pin("V", "A", 1)
    with pytest.raises(ValueError):
        cal.getPinLocationByPin(pin)


def test_get_pin_objects_requires_uv_layer() -> None:
    cal = LayerCalibration(layer=None)
    cal.setPinLocation("A1", Location(0.0, 0.0, 0.0))
    with pytest.raises(RuntimeError):
        cal.getPinObjects()


def test_canonical_keys_in_xml_normalize_back_to_legacy_storage() -> None:
    """Loading a JSON whose keys use canonical "UA1" form should populate the
    legacy "A1"-keyed internal store, so existing string lookups still work."""
    from dune_winder.machine.calibration.layer import _xml_import_pin_name

    assert _xml_import_pin_name("UA1") == "A1"
    assert _xml_import_pin_name("VB23") == "B23"
    # Pre-existing forms still pass through unchanged.
    assert _xml_import_pin_name("A1") == "A1"
    assert _xml_import_pin_name("F1") == "A1"
