from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover
    pytest.skip("pandas required", allow_module_level=True)

from dune_tension.average_profile_clouds import (
    AverageProfileCloudOptions,
    LayerAnalysisResult,
    PLOT_MODE_APPLIED_LENGTH,
    PLOT_MODE_ENDPOINT_CATEGORIES,
    PLOT_MODE_ENDPOINT_MAPPING,
    PLOT_MODE_WIRE_NUMBER,
    PLOT_MODE_WRAP_NUMBER,
)


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dune_tension"
    / "gui"
    / "average_profile_clouds_app.py"
)


class _FakeVar:
    def __init__(self, master=None, value=None):
        self.value = value
        self.traces = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, mode, callback):
        self.traces.append((mode, callback))


class _FakeWidget:
    def __init__(self, master=None, **kwargs):
        self.master = master
        self.kwargs = kwargs
        self.children = []
        self.state_calls = []
        self.bindings = []
        self.grid_calls = 0
        self.grid_remove_calls = 0
        if master is not None and hasattr(master, "children"):
            master.children.append(self)

    def grid(self, *args, **kwargs):
        self.grid_calls += 1
        self.kwargs.update(kwargs)
        return None

    def grid_remove(self):
        self.grid_remove_calls += 1
        return None

    def columnconfigure(self, *args, **kwargs):
        return None

    def rowconfigure(self, *args, **kwargs):
        return None

    def destroy(self):
        if self.master is not None and hasattr(self.master, "children"):
            self.master.children = [
                child for child in self.master.children if child is not self
            ]

    def winfo_children(self):
        return list(self.children)

    def bind(self, event, callback):
        self.bindings.append((event, callback))

    def state(self, values):
        self.state_calls.append(tuple(values))

    def configure(self, **kwargs):
        self.kwargs.update(kwargs)


class _FakeCanvas(_FakeWidget):
    def __init__(self, master=None, **kwargs):
        super().__init__(master=master, **kwargs)
        self.created_windows = []
        self.itemconfigure_calls = []

    def create_window(self, coords, window=None, anchor=None):
        window_id = len(self.created_windows) + 1
        self.created_windows.append((window_id, coords, window, anchor))
        return window_id

    def bbox(self, _tag):
        return (0, 0, 1600, 900)

    def itemconfigure(self, item, **kwargs):
        self.itemconfigure_calls.append((item, kwargs))

    def yview(self, *args, **kwargs):
        return None

    def xview(self, *args, **kwargs):
        return None


class _FakeScrollbar(_FakeWidget):
    def set(self, *args, **kwargs):
        return None


class _FakeNotebook(_FakeWidget):
    def __init__(self, master=None, **kwargs):
        super().__init__(master=master, **kwargs)
        self.tabs = []
        self.current = ""

    def add(self, frame, text):
        self.tabs.append((frame, text))
        if not self.current:
            self.current = str(frame)

    def forget(self, frame):
        self.tabs = [tab for tab in self.tabs if tab[0] is not frame]

    def select(self):
        return self.current


class _FakeRoot(_FakeWidget):
    def __init__(self):
        super().__init__(master=None)
        self.after_calls = []
        self.after_cancel_calls = []
        self.title_value = None

    def title(self, value):
        self.title_value = value

    def after(self, delay, callback):
        token = f"after-{len(self.after_calls) + 1}"
        self.after_calls.append((token, delay, callback))
        return token

    def after_cancel(self, token):
        self.after_cancel_calls.append(token)

    def mainloop(self):
        return None


class _FakePhotoImage:
    def __init__(self, master=None, data=None):
        self.master = master
        self.data = data


def _load_module(monkeypatch):
    tk_module = types.ModuleType("tkinter")
    tk_module.Misc = object
    tk_module.Tk = _FakeRoot
    tk_module.StringVar = _FakeVar
    tk_module.BooleanVar = _FakeVar
    tk_module.PhotoImage = _FakePhotoImage
    tk_module.Canvas = _FakeCanvas
    monkeypatch.setitem(sys.modules, "tkinter", tk_module)

    ttk_module = types.ModuleType("tkinter.ttk")
    ttk_module.Frame = _FakeWidget
    ttk_module.LabelFrame = _FakeWidget
    ttk_module.Label = _FakeWidget
    ttk_module.Entry = _FakeWidget
    ttk_module.Button = _FakeWidget
    ttk_module.Checkbutton = _FakeWidget
    ttk_module.Combobox = _FakeWidget
    ttk_module.Notebook = _FakeNotebook
    ttk_module.Scrollbar = _FakeScrollbar
    monkeypatch.setitem(sys.modules, "tkinter.ttk", ttk_module)
    tk_module.ttk = ttk_module

    module_name = "average_profile_clouds_gui_under_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _make_result(
    layer: str, *, empty: bool = False, label: str | None = None
) -> LayerAnalysisResult:
    cloud = pd.DataFrame(
        columns=[
            "wire_number",
            "tension",
            "side",
            "apa_name",
            "wrap_number",
            "applied_length_mm",
            "endpoint_side_mapping",
        ]
    )
    if not empty:
        cloud = pd.DataFrame(
            {
                "wire_number": [1, 2],
                "tension": [6.0, 6.5],
                "side": ["A", "B"],
                "apa_name": ["APA1", "APA1"],
                "wrap_number": [50, 51],
                "applied_length_mm": [1200.0, 1210.0],
                "endpoint_side_mapping": ["bottom→top", "head→foot"],
            }
        )
    return LayerAnalysisResult(
        layer=layer,
        location_filter=None if label is None else label.lower(),
        location_label=label,
        location_output_tag="tag",
        global_mode_value=6.1,
        cloud=cloud,
        mu_by_side={"A": pd.Series([6.0], index=[1]), "B": pd.Series([6.4], index=[1])},
        n_by_side={"A": pd.Series([1], index=[1]), "B": pd.Series([1], index=[1])},
        profile_df=pd.DataFrame(
            {"wire_number": [1], "mu_A": [6.0], "mu_B": [6.4], "n_A": [1], "n_B": [1]}
        ),
        scale_df=pd.DataFrame({"apa_name": ["APA1"], "k": [1.0]}),
        output_path=Path("/tmp/out.png"),
        profile_summary_path=Path("/tmp/profile.csv"),
        scale_summary_path=Path("/tmp/scales.csv"),
        status_message=f"{layer} status",
    )


def test_schedule_refresh_debounces_existing_callback(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.root = _FakeRoot()
    app.global_status_var = _FakeVar(value="")
    app._pending_refresh_id = "after-0"
    app.refresh_now = lambda: None

    module.AverageProfileExplorerApp.schedule_refresh(app)
    first_token = app._pending_refresh_id
    module.AverageProfileExplorerApp.schedule_refresh(app)

    assert app.root.after_cancel_calls == ["after-0", first_token]
    assert app.global_status_var.get() == "Refresh scheduled..."


def test_sync_split_by_location_state_disables_all_locations_when_not_split(
    monkeypatch,
):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.source_var = _FakeVar(value="legacy")
    app.split_by_location_var = _FakeVar(value=True)
    app.show_all_locations_var = _FakeVar(value=True)
    app.split_by_location_button = _FakeWidget()
    app.show_all_locations_button = _FakeWidget()

    module.AverageProfileExplorerApp._sync_split_by_location_state(app)

    assert app.split_by_location_var.get() is False
    assert app.show_all_locations_var.get() is False
    assert app.split_by_location_button.state_calls[-1] == ("disabled",)
    assert app.show_all_locations_button.state_calls[-1] == ("disabled",)


def test_sync_split_by_location_state_enables_all_locations_when_split(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.source_var = _FakeVar(value="dunedb")
    app.split_by_location_var = _FakeVar(value=True)
    app.show_all_locations_var = _FakeVar(value=False)
    app.split_by_location_button = _FakeWidget()
    app.show_all_locations_button = _FakeWidget()

    module.AverageProfileExplorerApp._sync_split_by_location_state(app)

    assert app.split_by_location_var.get() is True
    assert app.show_all_locations_var.get() is False
    assert app.split_by_location_button.state_calls[-1] == ("!disabled",)
    assert app.show_all_locations_button.state_calls[-1] == ("!disabled",)


def test_ensure_layer_tabs_creates_one_tab_per_layer(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.root = _FakeRoot()
    app.notebook = _FakeNotebook()
    app._tab_state = {}

    module.AverageProfileExplorerApp._ensure_layer_tabs(app, ("X", "V", "U", "G"))

    assert [text for _frame, text in app.notebook.tabs] == ["X", "V", "U", "G"]
    assert set(app._tab_state) == {"X", "V", "U", "G"}
    assert all(state.scroll_canvas.created_windows for state in app._tab_state.values())


def test_apply_refresh_success_updates_status_and_renders(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app._refresh_generation = 2
    app.global_status_var = _FakeVar(value="")
    app._latest_options = None
    app._latest_results = None
    rendered = []
    app._render_layer_results = lambda layer, layer_results, options: rendered.append(
        (layer, len(layer_results), options.layers)
    )

    options = AverageProfileCloudOptions(layers=("X", "G"))
    results = {"X": [_make_result("X")], "G": [_make_result("G", empty=True)]}

    module.AverageProfileExplorerApp._apply_refresh_success(app, 2, options, results)

    assert app._latest_options == options
    assert app._latest_results == results
    assert rendered == [("X", 1, ("X", "G")), ("G", 1, ("X", "G"))]
    assert app.global_status_var.get() == "Ready. Rendered 1 plot(s)."


def test_apply_refresh_error_sets_all_tab_statuses(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app._refresh_generation = 3
    app.global_status_var = _FakeVar(value="")
    app._tab_state = {
        "X": module.LayerTabState(
            frame=object(),
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        ),
        "G": module.LayerTabState(
            frame=object(),
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        ),
    }

    module.AverageProfileExplorerApp._apply_refresh_error(app, 3, "boom")

    assert app.global_status_var.get() == "Refresh failed."
    assert app._tab_state["X"].status_var.get() == "boom"
    assert app._tab_state["G"].status_var.get() == "boom"


def test_export_current_uses_selected_tab(monkeypatch):
    module = _load_module(monkeypatch)
    exported = []
    monkeypatch.setattr(
        module,
        "export_layer_analysis",
        lambda result, options: exported.append((result.layer, options.layers)),
    )

    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    frame_x = object()
    frame_g = object()
    app.notebook = types.SimpleNamespace(select=lambda: str(frame_g))
    app._tab_state = {
        "X": module.LayerTabState(
            frame=frame_x,
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        ),
        "G": module.LayerTabState(
            frame=frame_g,
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        ),
    }
    app.global_status_var = _FakeVar(value="")
    app.plot_mode_var = _FakeVar(value=PLOT_MODE_WIRE_NUMBER)
    options = AverageProfileCloudOptions(layers=("X", "G"))
    app.collect_options = lambda: options
    app._latest_options = options
    app._latest_results = {"X": [_make_result("X")], "G": [_make_result("G")]}

    module.AverageProfileExplorerApp.export_current(app)

    assert exported == [("G", ("X", "G"))]
    assert app.global_status_var.get() == "Exported G."


def test_toggle_parameters_panel_hides_and_restores_controls(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp(_FakeRoot())

    assert app._controls_visible is True
    assert app.controls_toggle_button.kwargs["text"] == "Hide parameters"

    module.AverageProfileExplorerApp.toggle_parameters_panel(app)

    assert app._controls_visible is False
    assert app.controls_panel.grid_remove_calls == 1
    assert app.controls_toggle_button.kwargs["text"] == "Show parameters"

    module.AverageProfileExplorerApp.toggle_parameters_panel(app)

    assert app._controls_visible is True
    assert app.controls_panel.grid_calls >= 2
    assert app.controls_toggle_button.kwargs["text"] == "Hide parameters"


def test_figure_to_photo_image_saves_with_tight_padding(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.root = _FakeRoot()
    captured = {}

    class _FakeFigure:
        def savefig(self, destination, **kwargs):
            destination.write(b"png-bytes")
            captured["kwargs"] = kwargs

    image = module.AverageProfileExplorerApp._figure_to_photo_image(app, _FakeFigure())

    assert captured["kwargs"]["dpi"] == 100
    assert captured["kwargs"]["format"] == "png"
    assert captured["kwargs"]["bbox_inches"] == "tight"
    assert captured["kwargs"]["pad_inches"] == 0.2
    assert image.data


def test_render_layer_results_split_by_side_builds_two_figures(monkeypatch):
    module = _load_module(monkeypatch)
    calls = []

    def _fake_build_layer_figure(_result, **kwargs):
        calls.append(kwargs.get("side_filter"))
        return object()

    monkeypatch.setattr(module, "build_layer_figure", _fake_build_layer_figure)

    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.root = _FakeRoot()
    app.plot_mode_var = _FakeVar(value=PLOT_MODE_WIRE_NUMBER)
    app._tab_state = {
        "X": module.LayerTabState(
            frame=_FakeWidget(),
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        )
    }
    app._figure_to_photo_image = lambda _figure: object()

    options = AverageProfileCloudOptions(split_by_side=True)
    module.AverageProfileExplorerApp._render_layer_results(
        app, "X", [_make_result("X")], options
    )

    assert calls == ["A", "B"]


def test_render_layer_results_endpoint_categories_ignores_split_by_side(monkeypatch):
    module = _load_module(monkeypatch)
    calls = []

    def _fake_build_layer_figure(_result, **kwargs):
        calls.append(kwargs.get("side_filter"))
        return object()

    monkeypatch.setattr(module, "build_layer_figure", _fake_build_layer_figure)

    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.root = _FakeRoot()
    app.plot_mode_var = _FakeVar(value=PLOT_MODE_ENDPOINT_CATEGORIES)
    app._tab_state = {
        "V": module.LayerTabState(
            frame=_FakeWidget(),
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        )
    }
    app._figure_to_photo_image = lambda _figure: object()

    options = AverageProfileCloudOptions(split_by_side=True)
    module.AverageProfileExplorerApp._render_layer_results(
        app, "V", [_make_result("V")], options
    )

    assert calls == [None]


def test_plot_mode_control_is_created(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp(_FakeRoot())

    assert app.plot_mode_var.get() == PLOT_MODE_WIRE_NUMBER


def test_render_layer_results_passes_plot_mode(monkeypatch):
    module = _load_module(monkeypatch)
    calls = []

    def _fake_build_layer_figure(_result, **kwargs):
        calls.append((kwargs.get("plot_mode"), kwargs.get("side_filter")))
        return object()

    monkeypatch.setattr(module, "build_layer_figure", _fake_build_layer_figure)

    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.root = _FakeRoot()
    app.plot_mode_var = _FakeVar(value=PLOT_MODE_WRAP_NUMBER)
    app._tab_state = {
        "V": module.LayerTabState(
            frame=_FakeWidget(),
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        )
    }
    app._figure_to_photo_image = lambda _figure: object()

    module.AverageProfileExplorerApp._render_layer_results(
        app,
        "V",
        [_make_result("V")],
        AverageProfileCloudOptions(),
    )

    assert calls == [(PLOT_MODE_WRAP_NUMBER, None)]


def test_render_layer_results_unsupported_mode_shows_placeholder(monkeypatch):
    module = _load_module(monkeypatch)
    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    app.root = _FakeRoot()
    app.plot_mode_var = _FakeVar(value=PLOT_MODE_ENDPOINT_MAPPING)
    content_frame = _FakeWidget()
    app._tab_state = {
        "X": module.LayerTabState(
            frame=_FakeWidget(),
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=content_frame,
        )
    }
    app._figure_to_photo_image = lambda _figure: object()

    module.AverageProfileExplorerApp._render_layer_results(
        app,
        "X",
        [_make_result("X")],
        AverageProfileCloudOptions(),
    )

    texts = [
        child.kwargs.get("text")
        for child in content_frame.children
        if "text" in child.kwargs
    ]
    assert any("supported for U/V layers only" in str(text) for text in texts)


def test_export_current_writes_exploratory_png_suffix(monkeypatch, tmp_path):
    module = _load_module(monkeypatch)
    exported_paths = []

    monkeypatch.setattr(module, "export_layer_analysis", lambda result, options: None)
    monkeypatch.setattr(
        module,
        "_save_figure_with_padding",
        lambda _figure, destination, **kwargs: exported_paths.append(Path(destination)),
    )
    monkeypatch.setattr(module, "build_layer_figure", lambda *args, **kwargs: object())

    result = _make_result("V")
    result = LayerAnalysisResult(
        **{**result.__dict__, "output_path": tmp_path / "plot.png"}
    )

    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    frame_v = object()
    app.root = _FakeRoot()
    app.notebook = types.SimpleNamespace(select=lambda: str(frame_v))
    app._tab_state = {
        "V": module.LayerTabState(
            frame=frame_v,
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        )
    }
    app.global_status_var = _FakeVar(value="")
    app.plot_mode_var = _FakeVar(value=PLOT_MODE_APPLIED_LENGTH)
    options = AverageProfileCloudOptions(layers=("V",))
    app.collect_options = lambda: options
    app._latest_options = options
    app._latest_results = {"V": [result]}

    module.AverageProfileExplorerApp.export_current(app)

    assert exported_paths == [tmp_path / "plot_by_applied_length.png"]


def test_export_current_endpoint_categories_ignores_split_by_side(
    monkeypatch, tmp_path
):
    module = _load_module(monkeypatch)
    exported_paths = []
    build_calls = []

    monkeypatch.setattr(module, "export_layer_analysis", lambda result, options: None)
    monkeypatch.setattr(
        module,
        "_save_figure_with_padding",
        lambda _figure, destination, **kwargs: exported_paths.append(Path(destination)),
    )

    def _fake_build_layer_figure(*args, **kwargs):
        build_calls.append(kwargs.get("side_filter"))
        return object()

    monkeypatch.setattr(module, "build_layer_figure", _fake_build_layer_figure)

    result = _make_result("V")
    result = LayerAnalysisResult(
        **{**result.__dict__, "output_path": tmp_path / "plot.png"}
    )

    app = module.AverageProfileExplorerApp.__new__(module.AverageProfileExplorerApp)
    frame_v = object()
    app.root = _FakeRoot()
    app.notebook = types.SimpleNamespace(select=lambda: str(frame_v))
    app._tab_state = {
        "V": module.LayerTabState(
            frame=frame_v,
            status_var=_FakeVar(value=""),
            scroll_canvas=_FakeCanvas(),
            content_frame=_FakeWidget(),
        )
    }
    app.global_status_var = _FakeVar(value="")
    app.plot_mode_var = _FakeVar(value=PLOT_MODE_ENDPOINT_CATEGORIES)
    options = AverageProfileCloudOptions(layers=("V",), split_by_side=True)
    app.collect_options = lambda: options
    app._latest_options = options
    app._latest_results = {"V": [result]}

    module.AverageProfileExplorerApp.export_current(app)

    assert build_calls == [None]
    assert exported_paths == [tmp_path / "plot_by_endpoint_categories.png"]
