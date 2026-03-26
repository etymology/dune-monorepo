import importlib.util
import json
from pathlib import Path
import sys
import types


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "dune_tension"
    / "gui"
    / "state.py"
)


def _load_state_module(monkeypatch):
    tk_stub = types.ModuleType("tkinter")
    tk_stub.Entry = object
    tk_stub.END = "end"
    monkeypatch.setitem(sys.modules, "tkinter", tk_stub)

    dune_pkg = types.ModuleType("dune_tension")
    dune_pkg.__path__ = []
    gui_pkg = types.ModuleType("dune_tension.gui")
    gui_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "dune_tension", dune_pkg)
    monkeypatch.setitem(sys.modules, "dune_tension.gui", gui_pkg)

    config = types.ModuleType("dune_tension.config")
    config.MEASUREMENT_WIGGLE_CONFIG = types.SimpleNamespace(
        y_sigma_mm=0.2,
        focus_sigma_quarter_us=100.0,
    )
    monkeypatch.setitem(sys.modules, "dune_tension.config", config)

    context = types.ModuleType("dune_tension.gui.context")
    context.GUIContext = object
    monkeypatch.setitem(sys.modules, "dune_tension.gui.context", context)

    module_name = "gui_state_under_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


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
        entry_apa=_FakeEntry("USAPA12"),
        measurement_mode_var=_FakeVar("legacy"),
        layer_var=_FakeVar("X"),
        side_var=_FakeVar("A"),
        flipped_var=_FakeVar(False),
        a_taped_var=_FakeVar(False),
        b_taped_var=_FakeVar(False),
        entry_wire=_FakeEntry("1"),
        entry_wire_list=_FakeEntry("500-900"),
        entry_confidence=_FakeEntry("0.6"),
        plot_audio_var=_FakeVar(False),
        skip_measured_var=_FakeVar(True),
        focus_slider=_FakeScale(focus_value),
        entry_condition=_FakeEntry("t>7"),
        entry_times_sigma=_FakeEntry("2.0"),
        entry_set_tension=_FakeEntry("(481,5)"),
        entry_record_duration=_FakeEntry("1"),
        entry_measuring_duration=_FakeEntry("10"),
        entry_wiggle_y_sigma=_FakeEntry("0.2"),
        entry_focus_wiggle_sigma=_FakeEntry("100"),
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


def test_load_state_falls_back_for_invalid_focus_target(monkeypatch, tmp_path):
    state = _load_state_module(monkeypatch)
    state_file = tmp_path / "gui_state.json"
    state_file.write_text(json.dumps({"focus_target": ""}), encoding="utf-8")

    widgets = _build_widgets()
    ctx = types.SimpleNamespace(
        widgets=widgets,
        state_file=str(state_file),
        focus_command_var=_FakeVar(""),
    )

    state.load_state(ctx)

    assert widgets.focus_slider.get() == 4000
    assert ctx.focus_command_var.get() == "4000"
