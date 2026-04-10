from __future__ import annotations

import types

import dune_tension.uv_wire_planner as uv_wire_planner


def test_wire_pin_pair_matches_examples_and_wraparound() -> None:
    assert uv_wire_planner._wire_pin_pair("V", 1151) == ("B1199", "B1200")
    assert uv_wire_planner._wire_pin_pair("V", 1150) == ("B1198", "B1201")
    assert uv_wire_planner._wire_pin_pair("U", 1151) == ("B1600", "B1601")
    assert uv_wire_planner._wire_pin_pair("U", 1150) == ("B1599", "B1602")
    assert uv_wire_planner._wire_pin_pair("V", 8) == ("B56", "B2343")
    assert uv_wire_planner._wire_pin_pair("U", 8) == ("B457", "B343")


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
    assert (x_pose.x, x_pose.y, x_pose.focus_position) == (1.0, 2.0, 4100)
    assert fallback_calls == [("X", 3, 4100)]
