import json
import sys
import types
from pathlib import Path
from typing import Any, cast

from _gui_test_support import (
    REPO_SRC,
    install_dune_tension_pkg_shell,
    load_module_from_path,
)


MODULE_PATH = REPO_SRC / "gui" / "state.py"
APA_NAMING_PATH = REPO_SRC / "apa_naming.py"


def _load_state_module(monkeypatch):
    tk_stub = cast(Any, types.ModuleType("tkinter"))
    tk_stub.Entry = object
    tk_stub.END = "end"
    monkeypatch.setitem(sys.modules, "tkinter", tk_stub)

    dune_pkg, _gui_pkg = install_dune_tension_pkg_shell(monkeypatch)

    apa_module = load_module_from_path(
        monkeypatch, "dune_tension.apa_naming", APA_NAMING_PATH
    )
    dune_pkg.apa_naming = apa_module

    config = cast(Any, types.ModuleType("dune_tension.config"))
    config.MEASUREMENT_WIGGLE_CONFIG = types.SimpleNamespace(
        y_sigma_mm=0.2,
        focus_sigma_quarter_us=100.0,
    )
    monkeypatch.setitem(sys.modules, "dune_tension.config", config)

    context = cast(Any, types.ModuleType("dune_tension.gui.context"))
    context.GUIContext = object
    monkeypatch.setitem(sys.modules, "dune_tension.gui.context", context)

    return load_module_from_path(monkeypatch, "gui_state_under_test", MODULE_PATH)


class _FakeEntry:
    def __init__(self, value="") -> None:
        self.value = str(value)

    def get(self):
        return self.value

    def delete(self, _start, _end=None) -> None:
        self.value = ""

    def insert(self, _index, value) -> None:
        self.value = str(value)


class _FakeVar:
    def __init__(self, value=None) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class _FakeScale(_FakeVar):
    pass


def _build_widgets(focus_value="4807.0"):
    return types.SimpleNamespace(
        apa_location_var=_FakeVar("US"),
        apa_number_var=_FakeVar("012"),
        measurement_mode_var=_FakeVar("legacy"),
        layer_var=_FakeVar("X"),
        side_var=_FakeVar("A"),
        flipped_var=_FakeVar(False),
        a_taped_var=_FakeVar(False),
        b_taped_var=_FakeVar(False),
        entry_wire=_FakeEntry("1"),
        entry_wire_list=_FakeEntry("500-900"),
        entry_wire_zone=_FakeEntry(""),
        skip_measured_zone_var=_FakeVar(False),
        entry_confidence=_FakeEntry("0.6"),
        confidence_source_var=_FakeVar("Signal Amplitude"),
        use_harmonic_comb_trigger_var=_FakeVar(True),
        plot_audio_var=_FakeVar(False),
        suppress_wire_preview_var=_FakeVar(False),
        skip_measured_var=_FakeVar(True),
        focus_slider=_FakeScale(focus_value),
        disable_x_compensation_var=_FakeVar(False),
        entry_condition=_FakeEntry("t>7"),
        entry_legacy_tension_condition=_FakeEntry("t<7"),
        entry_times_sigma=_FakeEntry("2.0"),
        entry_set_tension=_FakeEntry("(481,5)"),
        entry_record_duration=_FakeEntry("1"),
        entry_measuring_duration=_FakeEntry("10"),
        entry_wiggle_y_sigma=_FakeEntry("0.2"),
        sweeping_wiggle_var=_FakeVar(False),
        entry_sweeping_wiggle_span_mm=_FakeEntry("1.0"),
        entry_focus_wiggle_sigma=_FakeEntry("100"),
        use_manual_focus_var=_FakeVar(False),
        laser_offset_pin_var=_FakeVar("B400"),
    )


def test_save_state_accepts_float_like_focus_slider(monkeypatch, tmp_path):
    state = _load_state_module(monkeypatch)
    ctx = types.SimpleNamespace(
        widgets=_build_widgets("4807.0"),
        state_file=str(tmp_path / "gui_state.json"),
    )

    state.save_state(ctx)

    data = json.loads(Path(ctx.state_file).read_text(encoding="utf-8"))
    assert data["focus_target"] == 4807
    assert data["confidence_source"] == "Signal Amplitude"
    assert data["use_harmonic_comb_trigger"] is True
    assert data["legacy_tension_condition"] == "t<7"
    assert data["disable_x_compensation"] is False
    assert data["laser_offset_pin"] == "B400"
    assert data["suppress_wire_preview"] is False


def test_load_state_falls_back_for_invalid_focus_target(monkeypatch, tmp_path):
    state = _load_state_module(monkeypatch)
    state_file = tmp_path / "gui_state.json"
    state_file.write_text(
        json.dumps({"focus_target": "", "legacy_tension_condition": "4<t"}),
        encoding="utf-8",
    )

    widgets = _build_widgets()
    ctx = types.SimpleNamespace(
        widgets=widgets,
        state_file=str(state_file),
        focus_command_var=_FakeVar(""),
    )

    state.load_state(ctx)

    assert widgets.focus_slider.get() == 4000
    assert ctx.focus_command_var.get() == "4000"
    assert widgets.confidence_source_var.get() == "Neural Net"
    assert widgets.use_harmonic_comb_trigger_var.get() is False
    assert widgets.entry_legacy_tension_condition.get() == "4<t"
    assert widgets.disable_x_compensation_var.get() is False
    assert widgets.laser_offset_pin_var.get() == ""
    assert widgets.suppress_wire_preview_var.get() is False


def test_load_state_restores_disable_x_compensation(monkeypatch, tmp_path):
    state = _load_state_module(monkeypatch)
    state_file = tmp_path / "gui_state.json"
    state_file.write_text(
        json.dumps(
            {
                "focus_target": 4500,
                "disable_x_compensation": True,
                "use_harmonic_comb_trigger": True,
            }
        ),
        encoding="utf-8",
    )

    widgets = _build_widgets()
    ctx = types.SimpleNamespace(
        widgets=widgets,
        state_file=str(state_file),
        focus_command_var=_FakeVar(""),
    )

    state.load_state(ctx)

    assert widgets.focus_slider.get() == 4500
    assert widgets.disable_x_compensation_var.get() is True
    assert widgets.use_harmonic_comb_trigger_var.get() is True


def test_load_state_restores_suppress_wire_preview(monkeypatch, tmp_path):
    state = _load_state_module(monkeypatch)
    state_file = tmp_path / "gui_state.json"
    state_file.write_text(
        json.dumps(
            {
                "suppress_wire_preview": True,
            }
        ),
        encoding="utf-8",
    )

    widgets = _build_widgets()
    ctx = types.SimpleNamespace(
        widgets=widgets,
        state_file=str(state_file),
        focus_command_var=_FakeVar(""),
    )

    state.load_state(ctx)

    assert widgets.suppress_wire_preview_var.get() is True
