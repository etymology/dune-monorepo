import importlib
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from dune_tension.config import GEOMETRY_CONFIG


def _load_module(monkeypatch):
    data_cache = types.ModuleType("dune_tension.data_cache")
    data_cache.get_dataframe = lambda _path: None
    data_cache.select_dataframe = lambda *_, **__: pd.DataFrame()
    monkeypatch.setitem(sys.modules, "dune_tension.data_cache", data_cache)

    plc_io = types.ModuleType("dune_tension.plc_io")
    plc_io.is_motion_target_in_bounds = lambda x, y: (
        GEOMETRY_CONFIG.measurable_x_min <= float(x) <= GEOMETRY_CONFIG.measurable_x_max
        and GEOMETRY_CONFIG.measurable_y_min
        <= float(y)
        <= GEOMETRY_CONFIG.measurable_y_max
    )
    plc_io.is_in_measurable_area = plc_io.is_motion_target_in_bounds
    monkeypatch.setitem(sys.modules, "dune_tension.plc_io", plc_io)

    sys.modules.pop("dune_tension.tensiometer_functions", None)
    return importlib.import_module("dune_tension.tensiometer_functions")


def test_plan_measurement_triplets_filters_illegal_targets_and_orders_greedily(
    monkeypatch, caplog
):
    tensiometer_functions = _load_module(monkeypatch)
    caplog.set_level("WARNING")
    config = types.SimpleNamespace()
    positions = {
        1: (4010.0, 1460.0),
        2: (4076.5, -1816.9),
        3: (4000.0, 1460.0),
        4: (4200.0, 1495.0),
    }

    planned = tensiometer_functions.plan_measurement_triplets(
        config=config,
        wire_list=[1, 2, 3, 4],
        get_xy_from_file_func=lambda _config, wire: positions[wire],
        get_current_xy_func=lambda: (4200.0, 1460.0),
        preserve_order=False,
    )

    assert planned == [
        (4, 4200.0, 1495.0),
        (1, 4010.0, 1460.0),
        (3, 4000.0, 1460.0),
    ]
    assert (
        "Skipping wire 2 because position 4076.5,-1816.9 is outside the measurable area."
        in caplog.text
    )


def test_measure_list_uses_shared_planner_output(monkeypatch):
    tensiometer_functions = _load_module(monkeypatch)
    collected = []
    planner_calls = []

    monkeypatch.setattr(
        tensiometer_functions,
        "plan_measurement_poses",
        lambda **kwargs: (
            planner_calls.append(kwargs)
            or [
                tensiometer_functions.PlannedWirePose(8, 8.0, 80.0, 4100),
                tensiometer_functions.PlannedWirePose(3, 3.0, 30.0, 4200),
            ]
        ),
    )

    tensiometer_functions.measure_list(
        config=types.SimpleNamespace(),
        wire_list=[3, 8],
        get_pose_from_file_func=lambda *_args, **_kwargs: None,
        get_current_xy_func=lambda: (0.0, 0.0),
        collect_func=lambda wire, x, y, focus: collected.append((wire, x, y, focus)),
        preserve_order=False,
        profile=False,
        current_focus_position=4000,
    )

    assert len(planner_calls) == 1
    assert planner_calls[0]["wire_list"] == [3, 8]
    assert collected == [(8, 8.0, 80.0, 4100), (3, 3.0, 30.0, 4200)]


def test_wire_position_provider_caches_latest_positions_and_focus(monkeypatch):
    import dune_tension.tensiometer_functions as tensiometer_functions

    loader_calls = []
    df = pd.DataFrame(
        [
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 10,
                "x": 99.0,
                "y": 199.0,
                "focus_position": 4900,
                "confidence": 0.2,
                "measurement_mode": "legacy",
                "time": "2026-03-10T10:00:00",
            },
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 10,
                "x": 100.0,
                "y": 200.0,
                "focus_position": 5000,
                "confidence": 0.9,
                "measurement_mode": "legacy",
                "time": "2026-03-10T10:01:00",
            },
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 12,
                "x": 120.0,
                "y": 220.0,
                "focus_position": 5200,
                "confidence": 0.8,
                "measurement_mode": "legacy",
                "time": "2026-03-10T10:02:00",
            },
        ]
    )

    provider = tensiometer_functions.WirePositionProvider(
        dataframe_loader=lambda _path, **_kw: loader_calls.append(True) or df
    )
    config = tensiometer_functions.make_config(apa_name="APA", layer="X", side="A")

    xy_wire_10 = provider.get_xy(config, 10)
    pose_wire_12 = provider.get_pose(config, 12)

    assert loader_calls == [True]
    assert xy_wire_10 == (100.0, 200.0)
    assert pose_wire_12 == tensiometer_functions.PlannedWirePose(12, 120.0, 220.0, 5200)


def test_wire_position_provider_uses_confidence_weighted_y_fit() -> None:
    import dune_tension.tensiometer_functions as tensiometer_functions

    config = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="X",
        side="A",
        flipped=False,
        wire_max=100,
        dx=0.0,
        dy=10.0,
    )
    df = pd.DataFrame(
        [
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 10,
                "x": 10.0,
                "y": 100.0,
                "focus_position": 5000,
                "confidence": 100.0,
                "measurement_mode": "legacy",
                "time": "2026-03-10T10:00:00",
            },
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 20,
                "x": 20.0,
                "y": 200.0,
                "focus_position": 6000,
                "confidence": 100.0,
                "measurement_mode": "legacy",
                "time": "2026-03-10T10:01:00",
            },
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 30,
                "x": 30.0,
                "y": 300.0,
                "focus_position": 9000,
                "confidence": 0.01,
                "measurement_mode": "legacy",
                "time": "2026-03-10T10:02:00",
            },
        ]
    )

    provider = tensiometer_functions.WirePositionProvider(
        dataframe_loader=lambda _path, **_kw: df
    )

    pose = provider.get_pose(config, 25, current_focus_position=4300)

    assert pose is not None
    assert pose.y == pytest.approx(250.0)
    assert pose.focus_position is not None
    assert 6400 <= pose.focus_position <= 6700


def test_wire_position_provider_ignores_non_legacy_rows_and_falls_back_to_nearest_focus() -> (
    None
):
    import dune_tension.tensiometer_functions as tensiometer_functions

    config = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="X",
        side="A",
        flipped=False,
        wire_max=100,
        dx=0.0,
        dy=10.0,
    )
    df = pd.DataFrame(
        [
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 10,
                "x": 10.0,
                "y": 100.0,
                "focus_position": 5000,
                "confidence": 0.9,
                "measurement_mode": "legacy",
                "time": "2026-03-10T10:00:00",
            },
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 20,
                "x": 20.0,
                "y": 200.0,
                "focus_position": 8000,
                "confidence": 0.9,
                "measurement_mode": "stream_sweep",
                "time": "2026-03-10T10:01:00",
            },
        ]
    )

    provider = tensiometer_functions.WirePositionProvider(
        dataframe_loader=lambda _path, **_kw: df
    )

    pose = provider.get_pose(config, 15, current_focus_position=4300)

    assert pose is not None
    assert pose.focus_position == 5000


def test_wire_position_provider_uses_tension_layer_calibration_path(
    monkeypatch,
) -> None:
    import dune_tension.layer_calibration as layer_calibration
    import dune_tension.tensiometer_functions as tensiometer_functions

    calibration_path = Path("/tmp/U_Calibration.json")
    calls = []

    monkeypatch.setattr(
        layer_calibration,
        "get_local_layer_calibration_path",
        lambda layer: calibration_path,
    )
    monkeypatch.setattr(
        layer_calibration,
        "get_laser_offset",
        lambda side: {"x": 0.0, "y": 0.0},
    )

    def _compute_geometry(**kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(
            tangent_point_a=types.SimpleNamespace(x=2000.0, y=500.0),
            tangent_point_b=types.SimpleNamespace(x=2100.0, y=700.0),
        )

    monkeypatch.setattr(
        tensiometer_functions,
        "compute_pin_pair_tangent_geometry",
        _compute_geometry,
    )

    config = types.SimpleNamespace(layer="U", side="A")
    provider = tensiometer_functions.WirePositionProvider(
        dataframe_loader=lambda _path, **_kw: pd.DataFrame()
    )

    xy = provider._resolve_geometry_pose(config, 1095)

    assert xy is not None
    assert calls[0]["pin_a"] == "A1258"
    assert calls[0]["pin_b"] == "A1145"
    assert calls[0]["layer_calibration_path"] == calibration_path


def test_wire_position_provider_falls_back_to_current_focus_when_no_saved_focus_exists() -> (
    None
):
    import dune_tension.tensiometer_functions as tensiometer_functions

    config = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="X",
        side="A",
        flipped=False,
        wire_max=100,
        dx=0.0,
        dy=10.0,
    )
    df = pd.DataFrame(
        [
            {
                "apa_name": "APA",
                "layer": "X",
                "side": "A",
                "wire_number": 10,
                "x": 10.0,
                "y": 100.0,
                "focus_position": None,
                "confidence": 0.9,
                "measurement_mode": "legacy",
                "time": "2026-03-10T10:00:00",
            },
        ]
    )

    provider = tensiometer_functions.WirePositionProvider(
        dataframe_loader=lambda _path, **_kw: df
    )

    pose = provider.get_pose(config, 10, current_focus_position=4321)

    assert pose is not None
    assert pose.focus_position == 4321
