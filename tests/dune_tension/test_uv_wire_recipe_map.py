from __future__ import annotations

import pytest

import dune_tension.geometry as geometry
import dune_tension.uv_wire_planner as uv_wire_planner
import dune_tension.uv_wire_recipe_map as uv_wire_recipe_map


def _fake_calibration(layer: str) -> dict[str, object]:
    pin_max = 2401 if str(layer).upper() == "U" else 2399
    return {
        "layer": str(layer).upper(),
        "pinDiameterMm": 0.0,
        "locations": {
            f"B{pin_number}": {
                "x": float(pin_number),
                "y": 0.0,
                "z": 0.0,
            }
            for pin_number in range(1, pin_max + 1)
        },
    }


@pytest.fixture(autouse=True)
def _clear_recipe_map_caches() -> None:
    uv_wire_recipe_map._canonical_segment_comments.cache_clear()
    uv_wire_recipe_map._layer_metadata.cache_clear()
    uv_wire_recipe_map._layer_calibration.cache_clear()
    yield
    uv_wire_recipe_map._canonical_segment_comments.cache_clear()
    uv_wire_recipe_map._layer_metadata.cache_clear()
    uv_wire_recipe_map._layer_calibration.cache_clear()


def test_public_wire_pin_pair_matches_requested_sanity_checks() -> None:
    assert uv_wire_planner.wire_pin_pair("V", 401) == ("B449", "B1950")
    assert uv_wire_planner.wire_pin_pair("U", 1) == ("B450", "B350")


def test_wrap_to_wire_numbers_has_400_wraps_of_six_entries(monkeypatch) -> None:
    monkeypatch.setattr(uv_wire_recipe_map, "load_normalized_layer_calibration", _fake_calibration)

    v_maps = uv_wire_recipe_map.build_uv_wire_recipe_maps("V")
    u_maps = uv_wire_recipe_map.build_uv_wire_recipe_maps("U")

    assert sorted(v_maps.wrap_to_wire_numbers) == list(range(1, 401))
    assert sorted(u_maps.wrap_to_wire_numbers) == list(range(1, 401))
    assert all(len(wires) == 6 for wires in v_maps.wrap_to_wire_numbers.values())
    assert all(len(wires) == 6 for wires in u_maps.wrap_to_wire_numbers.values())
    assert v_maps.wrap_to_wire_numbers[50] == [401, 1902, 1201, 1102, 2001, 302]
    assert u_maps.wrap_to_wire_numbers[50] == [801, 1601, 1, -99, 1602, 702]


def test_wire_to_wrap_is_complete_and_unique_for_valid_wires(monkeypatch) -> None:
    monkeypatch.setattr(uv_wire_recipe_map, "load_normalized_layer_calibration", _fake_calibration)

    for layer in ("U", "V"):
        maps = uv_wire_recipe_map.build_uv_wire_recipe_maps(layer)
        assert sorted(maps.wire_to_wrap) == list(
            range(uv_wire_recipe_map.VALID_WIRE_MIN, uv_wire_recipe_map.VALID_WIRE_MAX + 1)
        )


def test_explicit_sanity_checks_and_representative_inversions(monkeypatch) -> None:
    monkeypatch.setattr(uv_wire_recipe_map, "load_normalized_layer_calibration", _fake_calibration)

    v_maps = uv_wire_recipe_map.build_uv_wire_recipe_maps("V")
    u_maps = uv_wire_recipe_map.build_uv_wire_recipe_maps("U")

    assert v_maps.wire_to_wrap[401] == uv_wire_recipe_map.WireWrapRef(
        wrap_number=50,
        segment_index=1,
        segment_line=2,
        segment_comment="Top B corner - foot end",
        start_pin="B449",
        end_pin="B1950",
    )
    assert u_maps.wrap_to_wire_numbers[50][2] == 1
    assert uv_wire_planner.wire_pin_pair("U", u_maps.wrap_to_wire_numbers[50][2])[0] == "B450"

    assert v_maps.wire_to_wrap[8].wrap_number == 344
    assert v_maps.wire_to_wrap[8].segment_line == 22
    assert u_maps.wire_to_wrap[401].wrap_number == 351
    assert u_maps.wire_to_wrap[401].segment_line == 22
    assert v_maps.wire_to_wrap[1146].wrap_number == 6
    assert v_maps.wire_to_wrap[1146].segment_line == 14
    assert u_maps.wire_to_wrap[1146].wrap_number == 395
    assert u_maps.wire_to_wrap[1146].segment_line == 2


def test_applied_length_uses_calibrated_pin_distance_not_length_lookup(monkeypatch) -> None:
    monkeypatch.setattr(uv_wire_recipe_map, "load_normalized_layer_calibration", _fake_calibration)
    monkeypatch.setattr(
        geometry,
        "length_lookup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("length_lookup should not be used")
        ),
    )

    v_maps = uv_wire_recipe_map.build_uv_wire_recipe_maps("V")
    u_maps = uv_wire_recipe_map.build_uv_wire_recipe_maps("U")

    assert v_maps.wire_to_applied_length_mm[401] == pytest.approx(1501.0)
    assert u_maps.wire_to_applied_length_mm[401] == pytest.approx(1501.0)
    assert u_maps.wire_to_applied_length_mm[8] == pytest.approx(114.0)


def test_wire_to_endpoint_sides_uses_manual_calibration_metadata(monkeypatch) -> None:
    monkeypatch.setattr(uv_wire_recipe_map, "load_normalized_layer_calibration", _fake_calibration)

    v_maps = uv_wire_recipe_map.build_uv_wire_recipe_maps("V")
    u_maps = uv_wire_recipe_map.build_uv_wire_recipe_maps("U")

    assert v_maps.wire_to_endpoint_sides[401] == ("bottom", "top")
    assert v_maps.wire_to_endpoint_sides[8] == ("head", "top")
    assert u_maps.wire_to_endpoint_sides[8] == ("bottom", "head")
    assert u_maps.wire_to_endpoint_sides[401] == ("bottom", "top")
