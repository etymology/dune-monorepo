from __future__ import annotations

import types

import pytest

import dune_tension.uv_wire_planner as uv_wire_planner


@pytest.fixture(autouse=True)
def _clear_uv_wire_plan_cache():
    uv_wire_planner.clear_plan_uv_wire_cache()
    yield
    uv_wire_planner.clear_plan_uv_wire_cache()


def test_wire_pin_pair_matches_examples_and_wraparound() -> None:
    assert uv_wire_planner._wire_pin_pair("V", "B", 1151) == ("B1199", "B1200")
    assert uv_wire_planner._wire_pin_pair("V", "A", 1151) == ("F1199", "F1200")
    assert uv_wire_planner._wire_pin_pair("V", "B", 1150) == ("B1198", "B1201")
    assert uv_wire_planner._wire_pin_pair("U", "B", 1151) == ("B1600", "B1601")
    assert uv_wire_planner._wire_pin_pair("U", "A", 1151) == ("F1600", "F1601")
    assert uv_wire_planner._wire_pin_pair("U", "B", 1150) == ("B1599", "B1602")
    assert uv_wire_planner._wire_pin_pair("V", "B", 8) == ("B56", "B2343")
    assert uv_wire_planner._wire_pin_pair("V", "A", 8) == ("F56", "F2343")
    assert uv_wire_planner._wire_pin_pair("U", "B", 8) == ("B457", "B343")
    assert uv_wire_planner._wire_pin_pair("U", "A", 8) == ("F457", "F343")


def test_legacy_uv_provider_uses_planner_for_uv_and_fallback_elsewhere(monkeypatch) -> None:
    fallback_calls = []

    class _Fallback:
        def invalidate(self):
            return None

        def get_pose(self, config, wire_number, current_focus_position=None):
            fallback_calls.append((config.layer, wire_number, current_focus_position))
            return uv_wire_planner.PlannedWirePose(
                wire_number=int(wire_number),
                x=1.0,
                y=2.0,
                focus_position=current_focus_position,
            )

    monkeypatch.setattr(
        uv_wire_planner,
        "plan_uv_wire",
        lambda _layer, _side, wire_number, taped=False: types.SimpleNamespace(
            midpoint=(float(wire_number), float(wire_number + 10)),
        ),
    )

    provider = uv_wire_planner.LegacyUVWirePositionProvider(_Fallback())
    uv_pose = provider.get_pose(
        types.SimpleNamespace(layer="U", side="A"),
        17,
        current_focus_position=4200,
    )
    x_pose = provider.get_pose(
        types.SimpleNamespace(layer="X", side="A"),
        3,
        current_focus_position=4100,
    )

    assert (uv_pose.x, uv_pose.y, uv_pose.focus_position) == (17.0, 27.0, 4200)
    assert uv_pose.zone is None
    assert (x_pose.x, x_pose.y, x_pose.focus_position) == (1.0, 2.0, 4100)
    assert fallback_calls == [("X", 3, 4100)]


def test_clip_line_to_rectangle_extends_beyond_tangent_endpoints() -> None:
    clipped = uv_wire_planner._clip_line_to_rectangle((10.0, 10.0), (20.0, 20.0))

    assert clipped == (
        (
            uv_wire_planner.GEOMETRY_CONFIG.measurable_x_min,
            uv_wire_planner.GEOMETRY_CONFIG.measurable_x_min,
        ),
        (
            uv_wire_planner.GEOMETRY_CONFIG.measurable_y_max,
            uv_wire_planner.GEOMETRY_CONFIG.measurable_y_max,
        ),
    )


def test_plan_uv_wire_clips_the_tangent_in_laser_space(monkeypatch) -> None:
    monkeypatch.setattr(
        uv_wire_planner,
        "load_layer_calibration_summary",
        lambda _layer: {
            "pinDiameterMm": 0.0,
            "locations": {
                "B1": {"x": 0.0, "y": 0.0},
                "B2": {"x": 1.0, "y": 1.0},
            },
        },
    )
    monkeypatch.setattr(uv_wire_planner, "get_laser_offset", lambda _side: {"x": -1000.0, "y": 0.0})
    monkeypatch.setattr(
        uv_wire_planner,
        "_wire_pin_pair",
        lambda _layer, _side, _wire_number: ("B1", "B2"),
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "LAYER_METADATA",
        {
            "V": {
                "pinToBoard": {
                    1: {"side": "top"},
                    2: {"side": "top"},
                }
            }
        },
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_wire_pin_pair",
        lambda _layer, _side, _wire_number: ("B1", "B2"),
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_solve_tangent_candidates",
        lambda **_kwargs: [((5000.0, 200.0), (5200.0, 600.0))],
    )
    monkeypatch.setattr(uv_wire_planner, "zone_lookup", lambda _x: 3)
    monkeypatch.setattr(
        uv_wire_planner,
        "length_lookup",
        lambda _layer, _wire_number, _zone, taped=False: 1.234,
    )

    planned = uv_wire_planner.plan_uv_wire("V", "A", 1100)

    assert planned.interval_start == (6065.0, 330.0)
    assert planned.interval_end == (7015.0, 2230.0)
    assert planned.midpoint == (6540.0, 1280.0)


def test_plan_uv_wire_uses_the_longest_comb_free_interval(monkeypatch) -> None:
    monkeypatch.setattr(
        uv_wire_planner,
        "load_layer_calibration_summary",
        lambda _layer: {
            "pinDiameterMm": 0.0,
            "locations": {
                "B1": {"x": 0.0, "y": 500.0},
                "B2": {"x": 10.0, "y": 500.0},
            },
        },
    )
    monkeypatch.setattr(uv_wire_planner, "get_laser_offset", lambda _side: {"x": 0.0, "y": 0.0})
    monkeypatch.setattr(
        uv_wire_planner,
        "_wire_pin_pair",
        lambda _layer, _side, _wire_number: ("B1", "B2"),
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "LAYER_METADATA",
        {
            "V": {
                "pinToBoard": {
                    1: {"side": "top"},
                    2: {"side": "top"},
                }
            }
        },
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_solve_tangent_candidates",
        lambda **_kwargs: [((0.0, 500.0), (10.0, 500.0))],
    )
    monkeypatch.setattr(uv_wire_planner, "zone_lookup", lambda _x: 5)
    monkeypatch.setattr(
        uv_wire_planner,
        "length_lookup",
        lambda _layer, _wire_number, _zone, taped=False: 2.0,
    )

    planned = uv_wire_planner.plan_uv_wire("V", "A", 1100)

    assert planned.interval_start == (5770.0, 500.0)
    assert planned.interval_end == (7015.0, 500.0)
    assert planned.midpoint == (6392.5, 500.0)


def test_plan_uv_wire_prefers_lowest_segment_within_ten_percent_of_longest(monkeypatch) -> None:
    monkeypatch.setattr(
        uv_wire_planner,
        "load_layer_calibration_summary",
        lambda _layer: {
            "pinDiameterMm": 0.0,
            "locations": {
                "B1": {"x": 0.0, "y": 0.0},
                "B2": {"x": 10.0, "y": 10.0},
            },
        },
    )
    monkeypatch.setattr(uv_wire_planner, "get_laser_offset", lambda _side: {"x": 0.0, "y": 0.0})
    monkeypatch.setattr(
        uv_wire_planner,
        "_wire_pin_pair",
        lambda _layer, _side, _wire_number: ("B1", "B2"),
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "LAYER_METADATA",
        {
            "V": {
                "pinToBoard": {
                    1: {"side": "top"},
                    2: {"side": "top"},
                }
            }
        },
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_solve_tangent_candidates",
        lambda **_kwargs: [((0.0, 0.0), (10.0, 10.0))],
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_clip_line_to_rectangle",
        lambda *_args: ((0.0, 0.0), (1.0, 1.0)),
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_split_segment_at_combs",
        lambda *_args: [
            ((1100.0, 900.0), (1200.0, 900.0)),
            ((1100.0, 500.0), (1195.0, 500.0)),
        ],
    )
    monkeypatch.setattr(uv_wire_planner, "zone_lookup", lambda _x: 1)
    monkeypatch.setattr(
        uv_wire_planner,
        "length_lookup",
        lambda _layer, _wire_number, _zone, taped=False: 2.0,
    )

    planned = uv_wire_planner.plan_uv_wire("V", "A", 1100)

    assert planned.interval_start == (1100.0, 500.0)
    assert planned.interval_end == (1195.0, 500.0)
    assert planned.midpoint == (1147.5, 500.0)


def test_plan_uv_wire_uses_front_pin_family_for_a_side(monkeypatch) -> None:
    centers = []

    monkeypatch.setattr(
        uv_wire_planner,
        "load_layer_calibration_summary",
        lambda _layer: {
            "pinDiameterMm": 0.0,
            "locations": {
                "F1199": {"x": 10.0, "y": 20.0},
                "F1200": {"x": 30.0, "y": 40.0},
                "B1199": {"x": 100.0, "y": 200.0},
                "B1200": {"x": 300.0, "y": 400.0},
            },
        },
    )
    monkeypatch.setattr(uv_wire_planner, "get_laser_offset", lambda _side: {"x": 0.0, "y": 0.0})
    monkeypatch.setattr(
        uv_wire_planner,
        "LAYER_METADATA",
        {
            "V": {
                "pinToBoard": {
                    1199: {"side": "bottom"},
                    1200: {"side": "foot"},
                }
            }
        },
    )

    def _record_centers(**kwargs):
        centers.append((kwargs["center_a"], kwargs["center_b"]))
        return [((10.0, 20.0), (30.0, 40.0))]

    monkeypatch.setattr(uv_wire_planner, "_solve_tangent_candidates", _record_centers)
    monkeypatch.setattr(uv_wire_planner, "zone_lookup", lambda _x: 1)
    monkeypatch.setattr(
        uv_wire_planner,
        "length_lookup",
        lambda _layer, _wire_number, _zone, taped=False: 1.0,
    )

    planned = uv_wire_planner.plan_uv_wire("V", "A", 1151)

    assert (planned.pin_a, planned.pin_b) == ("F1199", "F1200")
    assert centers == [((10.0, 20.0), (30.0, 40.0))]


def test_plan_uv_wire_zone_avoids_length_lookup(monkeypatch) -> None:
    monkeypatch.setattr(
        uv_wire_planner,
        "load_layer_calibration_summary",
        lambda _layer: {
            "pinDiameterMm": 0.0,
            "locations": {
                "B1": {"x": 0.0, "y": 0.0},
                "B2": {"x": 10.0, "y": 10.0},
            },
        },
    )
    monkeypatch.setattr(uv_wire_planner, "get_laser_offset", lambda _side: {"x": 0.0, "y": 0.0})
    monkeypatch.setattr(
        uv_wire_planner,
        "LAYER_METADATA",
        {
            "V": {
                "pinToBoard": {
                    1: {"side": "top"},
                    2: {"side": "top"},
                }
            }
        },
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_wire_pin_pair",
        lambda _layer, _side, _wire_number: ("B1", "B2"),
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_solve_tangent_candidates",
        lambda **_kwargs: [((0.0, 0.0), (10.0, 10.0))],
    )
    monkeypatch.setattr(uv_wire_planner, "zone_lookup", lambda _x: 4)
    monkeypatch.setattr(
        uv_wire_planner,
        "length_lookup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("length lookup should not be used")),
    )

    assert uv_wire_planner.plan_uv_wire_zone("V", "A", 1100) == 4


def test_plan_uv_wire_caches_geometry_for_repeated_inputs(monkeypatch) -> None:
    solve_calls = []

    monkeypatch.setattr(
        uv_wire_planner,
        "load_layer_calibration_summary",
        lambda _layer: {
            "pinDiameterMm": 0.0,
            "locations": {
                "B1": {"x": 0.0, "y": 0.0},
                "B2": {"x": 10.0, "y": 10.0},
            },
        },
    )
    monkeypatch.setattr(uv_wire_planner, "get_laser_offset", lambda _side: {"x": 0.0, "y": 0.0})
    monkeypatch.setattr(
        uv_wire_planner,
        "LAYER_METADATA",
        {
            "V": {
                "pinToBoard": {
                    1: {"side": "top"},
                    2: {"side": "top"},
                }
            }
        },
    )
    monkeypatch.setattr(
        uv_wire_planner,
        "_wire_pin_pair",
        lambda _layer, _side, _wire_number: ("B1", "B2"),
    )

    def _solve(**kwargs):
        solve_calls.append(kwargs)
        return [((0.0, 0.0), (10.0, 10.0))]

    monkeypatch.setattr(uv_wire_planner, "_solve_tangent_candidates", _solve)
    monkeypatch.setattr(uv_wire_planner, "zone_lookup", lambda _x: 1)
    monkeypatch.setattr(
        uv_wire_planner,
        "length_lookup",
        lambda _layer, _wire_number, _zone, taped=False: 1.0,
    )

    first = uv_wire_planner.plan_uv_wire("V", "A", 1100)
    second = uv_wire_planner.plan_uv_wire("V", "A", 1100)

    assert first == second
    assert len(solve_calls) == 1
