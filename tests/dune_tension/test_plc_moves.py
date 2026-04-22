import sys
from pathlib import Path
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

# Provide a minimal 'requests' module for import
sys.modules.setdefault("requests", types.ModuleType("requests"))

import dune_tension.plc_io as plc
from dune_tension.config import GEOMETRY_CONFIG


def _setup(
    monkeypatch,
    start_x: float = 2000.0,
    start_y: float = float(GEOMETRY_CONFIG.measurable_y_min),
):
    moves = []
    cur = {"x": None, "y": None}

    def dummy_write_tag(name, value):
        if name == "X_POSITION":
            cur["x"] = value
        elif name == "Y_POSITION":
            cur["y"] = value
        elif name == "MOVE_TYPE" and value == plc.XY_MOVE_TYPE:
            moves.append((cur["x"], cur["y"]))
        return {}

    monkeypatch.setattr(plc, "write_tag", dummy_write_tag)
    monkeypatch.setattr(plc, "get_state", lambda: plc.IDLE_STATE)
    monkeypatch.setattr(plc, "get_movetype", lambda: plc.IDLE_MOVE_TYPE)
    monkeypatch.setattr(plc, "get_plc_io_mode", lambda: "server")
    monkeypatch.setattr(plc, "set_speed", lambda speed: True)
    monkeypatch.setattr(plc.time, "sleep", lambda s: None)
    plc._TRUE_XY = [start_x, start_y]
    plc._LAST_X_DIR = 0
    plc._X_DEADZONE_LEFT = 0.0
    return moves


def test_crossing_comb_splits_move(monkeypatch):
    moves = _setup(monkeypatch)
    plc.goto_xy(3500.0, float(GEOMETRY_CONFIG.measurable_y_max))
    assert moves == [
        (2000.0, 0.0),
        (3500.0, 0.0),
        (3500.0, float(GEOMETRY_CONFIG.measurable_y_max)),
    ]


def test_no_crossing_single_move(monkeypatch):
    moves = _setup(monkeypatch)
    plc.goto_xy(2100.0, float(GEOMETRY_CONFIG.measurable_y_max))
    assert moves == [(2100.0, float(GEOMETRY_CONFIG.measurable_y_max))]


def test_goto_xy_recovers_from_tracked_x_outside_measurable_area(monkeypatch):
    moves = _setup(
        monkeypatch,
        start_x=float(GEOMETRY_CONFIG.measurable_x_max) + 6.0947265625,
        start_y=float(GEOMETRY_CONFIG.measurable_y_min),
    )

    moved = plc.goto_xy(6819.937637261673, 470.3958943833805)

    assert moved is True
    assert moves == [(6819.937637261673, 470.3958943833805)]


def test_get_cached_xy_seeds_tracking_from_live_read(monkeypatch):
    monkeypatch.setattr(plc, "get_xy", lambda: (1234.5, 678.9))
    plc._TRUE_XY = [None, None]

    assert plc.get_cached_xy() == (1234.5, 678.9)
    assert plc._TRUE_XY == [1234.5, 678.9]


def test_goto_xy_uses_manual_seek_path_in_desktop_mode(monkeypatch):
    seek_calls = []

    monkeypatch.setattr(plc, "get_plc_io_mode", lambda: "desktop")
    monkeypatch.setattr(plc, "_ensure_tracked_xy", lambda: (2000.0, 100.0))
    monkeypatch.setattr(plc, "is_in_measurable_area", lambda *_args: True)
    monkeypatch.setattr(plc, "write_tag", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("desktop goto_xy should not write motion tags directly")
    ))
    monkeypatch.setattr(
        "dune_tension.plc_desktop.desktop_seek_xy",
        lambda x, y, speed, move_timeout, idle_timeout=20.0, wait_for_completion=True: (
            seek_calls.append((x, y, speed, move_timeout, idle_timeout, wait_for_completion)) or True
        ),
    )
    plc._TRUE_XY = [2000.0, 100.0]
    plc._LAST_X_DIR = 0
    plc._X_DEADZONE_LEFT = 0.0

    moved = plc.goto_xy(2100.0, 250.0, speed=123.0, move_timeout=9.0, idle_timeout=4.0)

    assert moved is True
    assert seek_calls == [(2100.0, 250.0, 123.0, 9.0, 4.0, True)]


def test_goto_xy_can_skip_waiting_for_move_completion(monkeypatch):
    moves = _setup(monkeypatch)
    movetype_reads = {"count": 0}
    monkeypatch.setattr(plc, "get_movetype", lambda: movetype_reads.__setitem__("count", movetype_reads["count"] + 1) or plc.XY_MOVE_TYPE)

    moved = plc.goto_xy(
        2100.0,
        float(GEOMETRY_CONFIG.measurable_y_max),
        move_timeout=1.0,
        wait_for_completion=False,
    )

    assert moved is True
    assert moves == [(2100.0, float(GEOMETRY_CONFIG.measurable_y_max))]
    assert movetype_reads["count"] == 0


def test_goto_xy_clears_move_type_when_xy_seek_times_out_without_motion(monkeypatch):
    writes = []
    monotonic_values = iter([0.0, 0.0, 1.0, 1.0, 2.0])

    def dummy_write_tag(name, value):
        writes.append((name, value))
        return {}

    monkeypatch.setattr(plc, "write_tag", dummy_write_tag)
    monkeypatch.setattr(plc, "get_state", lambda: plc.IDLE_STATE)
    monkeypatch.setattr(plc, "get_movetype", lambda: plc.XY_MOVE_TYPE)
    monkeypatch.setattr(plc, "get_plc_io_mode", lambda: "server")
    monkeypatch.setattr(plc, "set_speed", lambda speed: True)
    monkeypatch.setattr(plc, "get_xy", lambda: (2000.0, float(GEOMETRY_CONFIG.measurable_y_min)))
    monkeypatch.setattr(plc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(plc.time, "monotonic", lambda: next(monotonic_values))
    plc._TRUE_XY = [2000.0, float(GEOMETRY_CONFIG.measurable_y_min)]
    plc._LAST_X_DIR = 0
    plc._X_DEADZONE_LEFT = 0.0

    moved = plc.goto_xy(
        2100.0,
        float(GEOMETRY_CONFIG.measurable_y_max),
        move_timeout=1.0,
    )

    assert moved is False
    assert writes[-1] == ("MOVE_TYPE", plc.IDLE_MOVE_TYPE)


def test_goto_xy_does_not_clear_move_type_when_xy_seek_times_out_after_motion(monkeypatch):
    writes = []
    monotonic_values = iter([0.0, 0.0, 1.0, 1.0, 2.0])

    def dummy_write_tag(name, value):
        writes.append((name, value))
        return {}

    monkeypatch.setattr(plc, "write_tag", dummy_write_tag)
    monkeypatch.setattr(plc, "get_state", lambda: plc.IDLE_STATE)
    monkeypatch.setattr(plc, "get_movetype", lambda: plc.XY_MOVE_TYPE)
    monkeypatch.setattr(plc, "get_plc_io_mode", lambda: "server")
    monkeypatch.setattr(plc, "set_speed", lambda speed: True)
    monkeypatch.setattr(plc, "get_xy", lambda: (2000.5, float(GEOMETRY_CONFIG.measurable_y_min)))
    monkeypatch.setattr(plc.time, "sleep", lambda _s: None)
    monkeypatch.setattr(plc.time, "monotonic", lambda: next(monotonic_values))
    plc._TRUE_XY = [2000.0, float(GEOMETRY_CONFIG.measurable_y_min)]
    plc._LAST_X_DIR = 0
    plc._X_DEADZONE_LEFT = 0.0

    moved = plc.goto_xy(
        2100.0,
        float(GEOMETRY_CONFIG.measurable_y_max),
        move_timeout=1.0,
    )

    assert moved is False
    assert writes.count(("MOVE_TYPE", plc.IDLE_MOVE_TYPE)) == 1
