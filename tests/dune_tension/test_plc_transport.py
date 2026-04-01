from pathlib import Path
import sys
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

sys.modules.setdefault("requests", types.ModuleType("requests"))

import dune_tension.plc_desktop as desktop
import dune_tension.plc_io as plc


@pytest.fixture(autouse=True)
def _reset_plc_mode_warnings():
    plc._WARNED_PLC_IO_MODE_VALUES.clear()


def test_read_tag_defaults_to_desktop_mode(monkeypatch):
    monkeypatch.delenv("PLC_IO_MODE", raising=False)
    monkeypatch.setattr(
        desktop,
        "desktop_read_tag",
        lambda tag_name: (tag_name, "desktop"),
    )
    monkeypatch.setattr(
        plc,
        "_read_tag_direct",
        lambda _tag_name: pytest.fail("direct transport should not be used by default"),
    )

    assert plc.read_tag("STATE", timeout=0.01, retry_interval=0.0) == ("STATE", "desktop")


def test_direct_mode_routes_reads_and_writes_to_direct_transport(monkeypatch):
    monkeypatch.setenv("PLC_IO_MODE", "direct")
    monkeypatch.setattr(plc, "_read_tag_direct", lambda tag_name: (tag_name, "direct"))
    monkeypatch.setattr(
        plc,
        "_read_tag_server",
        lambda _tag_name: pytest.fail("server transport should not be used in direct mode"),
    )
    monkeypatch.setattr(
        plc,
        "_write_tag_direct",
        lambda tag_name, value: {"tag": tag_name, "value": value, "transport": "direct"},
    )
    monkeypatch.setattr(
        plc,
        "_write_tag_server",
        lambda _tag_name, _value: pytest.fail(
            "server transport should not be used in direct mode"
        ),
    )

    assert plc.read_tag("STATE", timeout=0.01, retry_interval=0.0) == ("STATE", "direct")
    assert plc.write_tag("STATE", 7) == {
        "tag": "STATE",
        "value": 7,
        "transport": "direct",
    }


def test_desktop_mode_rejects_low_level_motion_tag_writes(monkeypatch):
    monkeypatch.setenv("PLC_IO_MODE", "desktop")
    monkeypatch.setattr(
        desktop,
        "_post_command",
        lambda *_args, **_kwargs: pytest.fail(
            "desktop mode should not proxy low-level motion tag writes"
        ),
    )

    response = plc.write_tag("STATE", 7)

    assert "error" in response
    assert "manual_seek_xy" in response["error"]


def test_reset_plc_in_desktop_mode_calls_acknowledge_error(monkeypatch):
    monkeypatch.setenv("PLC_IO_MODE", "desktop")
    calls = []
    monkeypatch.setattr(
        desktop,
        "_post_command",
        lambda name, args: calls.append((name, args)) or {"ok": True, "data": None},
    )

    assert plc.reset_plc() is True
    assert calls == [("process.acknowledge_error", {})]


def test_reset_plc_in_server_mode_only_requests_reset_move_type(monkeypatch):
    monkeypatch.setenv("PLC_IO_MODE", "server")
    calls = []
    monkeypatch.setattr(
        plc,
        "_write_required",
        lambda tag_name, value: calls.append((tag_name, value)) or True,
    )
    monkeypatch.setattr(
        plc,
        "set_speed",
        lambda *_args, **_kwargs: pytest.fail("reset_plc should not force XY speed"),
    )

    assert plc.reset_plc() is True
    assert calls == [("MOVE_TYPE", plc.IDLE_MOVE_TYPE)]


def test_desktop_seek_xy_acknowledges_error_after_move_timeout(monkeypatch):
    calls = []
    monotonic_values = iter([0.0, 0.0, 0.2, 0.4, 0.49, 0.51, 0.7])
    monkeypatch.setattr(desktop.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(desktop.time, "sleep", lambda _seconds: None)

    def _post_command(name, args):
        calls.append((name, args))
        if name == "process.manual_seek_xy":
            return {"ok": True, "data": False}
        if name == "process.acknowledge_error":
            return {"ok": True, "data": None}
        if name == "process.get_control_state_name":
            if len(calls) == 1:
                return {"ok": True, "data": "StopMode"}
            return {"ok": True, "data": "XYMode"}
        return {"ok": True, "data": None}

    monkeypatch.setattr(desktop, "_post_command", _post_command)

    assert desktop.desktop_seek_xy(1.0, 2.0, 300.0, move_timeout=0.5) is False
    assert ("process.acknowledge_error", {}) in calls


def test_desktop_seek_xy_resets_while_waiting_for_ready_then_moves(monkeypatch):
    calls = []
    ready_states = iter(
        [
            {"ok": True, "data": "XYMode"},
            {"ok": True, "data": "XYMode"},
            {"ok": True, "data": "StopMode"},
            {"ok": True, "data": "StopMode"},
        ]
    )
    monotonic_values = iter([0.0, 0.1, 0.2, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2])
    monkeypatch.setattr(desktop.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(desktop.time, "sleep", lambda _seconds: None)

    def _post_command(name, args):
        calls.append((name, args))
        if name == "process.get_control_state_name":
            return next(ready_states)
        if name == "process.acknowledge_error":
            return {"ok": True, "data": None}
        if name == "process.manual_seek_xy":
            return {"ok": True, "data": False}
        return {"ok": True, "data": None}

    monkeypatch.setattr(desktop, "_post_command", _post_command)

    assert desktop.desktop_seek_xy(1.0, 2.0, 300.0, move_timeout=0.5, idle_timeout=0.5) is True
    assert ("process.acknowledge_error", {}) in calls
    assert ("process.manual_seek_xy", {"x": 1.0, "y": 2.0, "velocity": 300.0}) in calls


def test_invalid_mode_falls_back_to_desktop_with_warning(monkeypatch, caplog):
    monkeypatch.setenv("PLC_IO_MODE", "banana")
    monkeypatch.setattr(desktop, "desktop_read_tag", lambda _tag_name: 123)
    monkeypatch.setattr(
        plc,
        "_read_tag_direct",
        lambda _tag_name: pytest.fail("direct transport should not be used for invalid mode"),
    )

    with caplog.at_level("WARNING"):
        value = plc.read_tag("STATE", timeout=0.01, retry_interval=0.0)

    assert value == 123
    assert "Invalid PLC_IO_MODE='banana'" in caplog.text


def test_is_plc_available_uses_direct_probe_in_direct_mode(monkeypatch):
    monkeypatch.setenv("PLC_IO_MODE", "direct")
    monkeypatch.setattr(plc, "is_direct_plc_available", lambda: True)
    monkeypatch.setattr(
        plc,
        "is_web_server_active",
        lambda: pytest.fail("server liveness check should not run in direct mode"),
    )

    assert plc.is_plc_available() is True


def test_is_plc_available_uses_server_probe_in_server_mode(monkeypatch):
    monkeypatch.setenv("PLC_IO_MODE", "server")
    monkeypatch.setattr(plc, "is_web_server_active", lambda: True)
    monkeypatch.setattr(
        plc,
        "is_direct_plc_available",
        lambda: pytest.fail("direct liveness check should not run in server mode"),
    )

    assert plc.is_plc_available() is True


class _FakeHttpResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_write_tag_server_preserves_error_message(monkeypatch):
    monkeypatch.setattr(
        plc,
        "_request_with_retries",
        lambda *_args, **_kwargs: _FakeHttpResponse(
            400, {"error": "Tag STATE is read-only"}
        ),
    )

    assert plc._write_tag_server("STATE", 1) == {
        "error": "Tag STATE is read-only",
        "status_code": 400,
    }


def test_read_tag_server_preserves_error_message(monkeypatch):
    monkeypatch.setattr(
        plc,
        "_request_with_retries",
        lambda *_args, **_kwargs: _FakeHttpResponse(
            502, {"error": "PLC communication error"}
        ),
    )

    assert plc._read_tag_server("STATE") == {
        "error": "PLC communication error",
        "status_code": 502,
    }
