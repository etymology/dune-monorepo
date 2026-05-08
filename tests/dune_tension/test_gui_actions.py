import importlib.util
from pathlib import Path
import sys
import threading
import time
import types
from typing import Any, cast


_REPO_SRC = Path(__file__).resolve().parents[2] / "src" / "dune_tension"
MODULE_PATH = _REPO_SRC / "gui" / "actions.py"
APA_NAMING_PATH = _REPO_SRC / "apa_naming.py"


def _load_actions_module(monkeypatch):
    dune_pkg = types.ModuleType("dune_tension")
    dune_pkg.__path__ = []
    gui_pkg = types.ModuleType("dune_tension.gui")
    gui_pkg.__path__ = []

    monkeypatch.setitem(
        sys.modules, "sounddevice", types.SimpleNamespace(stop=lambda: None)
    )
    monkeypatch.setitem(sys.modules, "dune_tension", dune_pkg)
    monkeypatch.setitem(sys.modules, "dune_tension.gui", gui_pkg)

    apa_spec = importlib.util.spec_from_file_location(
        "dune_tension.apa_naming", APA_NAMING_PATH
    )
    assert apa_spec is not None
    assert apa_spec.loader is not None
    apa_module = importlib.util.module_from_spec(apa_spec)
    monkeypatch.setitem(sys.modules, "dune_tension.apa_naming", apa_module)
    apa_spec.loader.exec_module(apa_module)
    cast(Any, dune_pkg).apa_naming = apa_module

    tk = cast(Any, types.ModuleType("tkinter"))
    tk.StringVar = lambda **kwargs: types.SimpleNamespace(
        get=lambda: "", set=lambda _: None
    )
    tk.BooleanVar = lambda **kwargs: types.SimpleNamespace(
        get=lambda: False, set=lambda _: None
    )
    tk.DoubleVar = lambda **kwargs: types.SimpleNamespace(
        get=lambda: 0.0, set=lambda _: None
    )
    tk.IntVar = lambda **kwargs: types.SimpleNamespace(
        get=lambda: 0, set=lambda _: None
    )
    tk.Misc = object
    monkeypatch.setitem(sys.modules, "tkinter", tk)

    tk_messagebox = cast(Any, types.ModuleType("tkinter.messagebox"))
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", tk_messagebox)

    config = cast(Any, types.ModuleType("dune_tension.config"))
    config.GEOMETRY_CONFIG = types.SimpleNamespace(
        comb_positions=[],
        measurable_x_min=0.0,
        measurable_x_max=0.0,
        measurable_y_min=0.0,
        measurable_y_max=0.0,
        zone_count=5,
    )
    config.LAYER_LAYOUTS = {}
    monkeypatch.setitem(sys.modules, "dune_tension.config", config)

    data_cache = cast(Any, types.ModuleType("dune_tension.data_cache"))
    data_cache.clear_wire_numbers = lambda *args, **kwargs: None
    data_cache.clear_wire_range = lambda *args, **kwargs: None
    data_cache.find_distribution_outliers = lambda *args, **kwargs: []
    data_cache.find_outliers = lambda *args, **kwargs: []
    data_cache.get_dataframe = lambda *args, **kwargs: None
    data_cache.update_dataframe = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dune_tension.data_cache", data_cache)

    results = cast(Any, types.ModuleType("dune_tension.results"))
    results.EXPECTED_COLUMNS = []
    monkeypatch.setitem(sys.modules, "dune_tension.results", results)

    tensiometer = cast(Any, types.ModuleType("dune_tension.tensiometer"))
    tensiometer.Tensiometer = object
    tensiometer.build_tensiometer = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "dune_tension.tensiometer", tensiometer)

    tensiometer_functions = cast(
        Any, types.ModuleType("dune_tension.tensiometer_functions")
    )
    tensiometer_functions.make_config = lambda **kwargs: types.SimpleNamespace(**kwargs)
    tensiometer_functions.normalize_confidence_source = lambda value: (
        str(value).strip().lower().replace(" ", "_")
    )
    monkeypatch.setitem(
        sys.modules,
        "dune_tension.tensiometer_functions",
        tensiometer_functions,
    )

    context = cast(Any, types.ModuleType("dune_tension.gui.context"))
    context.GUIContext = object
    monkeypatch.setitem(sys.modules, "dune_tension.gui.context", context)

    state = cast(Any, types.ModuleType("dune_tension.gui.state"))
    state.save_state = lambda _ctx: None
    monkeypatch.setitem(sys.modules, "dune_tension.gui.state", state)

    layer_calibration = cast(Any, types.ModuleType("dune_tension.layer_calibration"))
    layer_calibration.capture_laser_offset = lambda **kwargs: kwargs
    layer_calibration.ensure_layer_calibration_ready = lambda _layer: None
    layer_calibration.get_bottom_pin_options = lambda _layer, _side: [
        ("Bottom first (B400)", "B400"),
        ("Bottom last (B1199)", "B1199"),
    ]
    layer_calibration.get_calibrated_pin_xy_for_side = lambda _layer, _side, _pin: (
        100.0,
        200.0,
    )
    layer_calibration.get_laser_offset = lambda _side: None
    layer_calibration.resolve_pin_name_for_side = lambda _layer, _side, pin_name: (
        pin_name
    )
    monkeypatch.setitem(
        sys.modules, "dune_tension.layer_calibration", layer_calibration
    )

    plc_desktop = cast(Any, types.ModuleType("dune_tension.plc_desktop"))
    plc_desktop.desktop_seek_pin = lambda *_args, **_kwargs: True
    monkeypatch.setitem(sys.modules, "dune_tension.plc_desktop", plc_desktop)

    plc_io = cast(Any, types.ModuleType("dune_tension.plc_io"))
    plc_io.get_plc_io_mode = lambda: "desktop"
    monkeypatch.setitem(sys.modules, "dune_tension.plc_io", plc_io)

    uv_wire_planner = cast(Any, types.ModuleType("dune_tension.uv_wire_planner"))
    uv_wire_planner.plan_uv_wire = lambda *_args, **_kwargs: None
    uv_wire_planner.plan_uv_wire_zone = lambda *_args, **_kwargs: 0
    monkeypatch.setitem(sys.modules, "dune_tension.uv_wire_planner", uv_wire_planner)

    module_name = "gui_actions_under_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _wait_for(predicate, timeout=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_measurement_threads_are_serialized(monkeypatch):
    actions = _load_actions_module(monkeypatch)
    monkeypatch.setattr(actions, "_capture_worker_inputs", lambda _ctx: object())
    monkeypatch.setattr(actions, "save_state", lambda _ctx: None)

    calls = []
    started = threading.Event()
    release = threading.Event()

    @actions._run_in_thread(measurement=True)
    def fake_measurement(ctx, _inputs):
        calls.append(object())
        started.set()
        release.wait(timeout=1.0)

    ctx = types.SimpleNamespace(
        stop_event=threading.Event(),
        measurement_lock=threading.Lock(),
        measurement_active=False,
        active_measurement_name="",
    )

    fake_measurement(ctx)
    assert started.wait(timeout=1.0)

    fake_measurement(ctx)
    time.sleep(0.05)
    assert len(calls) == 1
    assert ctx.measurement_active is True

    release.set()
    assert _wait_for(lambda: ctx.measurement_active is False)
    assert ctx.active_measurement_name == ""

    fake_measurement(ctx)
    assert _wait_for(lambda: len(calls) == 2)


def test_create_tensiometer_uses_context_runtime_bundle(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    build_calls = []

    monkeypatch.setitem(
        sys.modules,
        "dune_tension.tensiometer",
        types.SimpleNamespace(
            build_tensiometer=lambda **kwargs: build_calls.append(kwargs) or kwargs,
            Tensiometer=object,
        ),
    )

    runtime = object()
    servo_controller = types.SimpleNamespace(
        focus_position=4100,
        nudge_focus=lambda _delta: None,
    )
    ctx = types.SimpleNamespace(
        runtime=runtime,
        stop_event=threading.Event(),
        strum=lambda: None,
        servo_controller=servo_controller,
        widgets=types.SimpleNamespace(),
    )
    inputs = types.SimpleNamespace(
        apa_name="APA",
        layer="X",
        side="A",
        flipped=False,
        a_taped=False,
        b_taped=False,
        samples=2,
        confidence=0.9,
        confidence_source="Signal Amplitude",
        record_duration=0.5,
        measuring_duration=5.0,
        wiggle_y_sigma_mm=0.4,
        sweeping_wiggle_span_mm=0.0,
        focus_wiggle_sigma_quarter_us=50.0,
        use_manual_focus=True,
        use_harmonic_comb_trigger=True,
        plot_audio=True,
        suppress_wire_preview=False,
        legacy_tension_condition="t<7",
    )

    actions.create_tensiometer(ctx, inputs)

    assert len(build_calls) == 1
    assert build_calls[0]["confidence_source"] == "signal_amplitude"
    assert build_calls[0]["runtime_bundle"] is runtime
    assert build_calls[0]["use_manual_focus"] is True
    assert build_calls[0]["use_harmonic_comb_trigger"] is True
    assert build_calls[0]["manual_focus_target"] is None
    assert build_calls[0]["legacy_tension_condition"] == "t<7"
    assert callable(build_calls[0]["wire_preview_callback"])


def test_create_tensiometer_can_suppress_wire_preview(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    build_calls = []

    monkeypatch.setitem(
        sys.modules,
        "dune_tension.tensiometer",
        types.SimpleNamespace(
            build_tensiometer=lambda **kwargs: build_calls.append(kwargs) or kwargs,
            Tensiometer=object,
        ),
    )

    requested_previews = []
    monkeypatch.setattr(
        actions,
        "_request_uv_wire_preview",
        lambda *_args, **_kwargs: requested_previews.append(True),
    )
    monkeypatch.setattr(actions, "get_laser_offset", lambda _side: {"x": 0.0, "y": 0.0})

    ctx = types.SimpleNamespace(
        runtime=object(),
        stop_event=threading.Event(),
        strum=lambda: None,
        servo_controller=types.SimpleNamespace(
            focus_position=4100,
            nudge_focus=lambda _delta: None,
        ),
        widgets=types.SimpleNamespace(),
    )
    inputs = types.SimpleNamespace(
        apa_name="APA",
        layer="U",
        side="A",
        flipped=False,
        a_taped=False,
        b_taped=False,
        samples=2,
        confidence=0.9,
        confidence_source="Signal Amplitude",
        record_duration=0.5,
        measuring_duration=5.0,
        wiggle_y_sigma_mm=0.4,
        sweeping_wiggle_span_mm=0.0,
        focus_wiggle_sigma_quarter_us=50.0,
        use_manual_focus=True,
        plot_audio=True,
        suppress_wire_preview=True,
        legacy_tension_condition="4<t",
    )

    actions.create_tensiometer(ctx, inputs)
    build_calls[0]["wire_preview_callback"](1151, 11.0, 2.0)

    assert requested_previews == []
    assert build_calls[0]["legacy_tension_condition"] == "4<t"


def test_measure_calibrate_dispatches_to_streaming_controller(monkeypatch):
    actions = _load_actions_module(monkeypatch)
    monkeypatch.setattr(actions, "save_state", lambda _ctx: None)

    inputs = types.SimpleNamespace(
        measurement_mode="stream_rescue",
        wire_number="7",
    )
    monkeypatch.setattr(actions, "_capture_worker_inputs", lambda _ctx: inputs)

    calls = []
    monkeypatch.setattr(
        actions,
        "_run_streaming_for_wires",
        lambda _ctx, stream_inputs, wire_numbers: calls.append(
            (stream_inputs.measurement_mode, wire_numbers)
        ),
    )

    ctx = types.SimpleNamespace(
        stop_event=threading.Event(),
        measurement_lock=threading.Lock(),
        measurement_active=False,
        active_measurement_name="",
    )

    actions.measure_calibrate(ctx)

    assert _wait_for(lambda: len(calls) == 1)
    assert calls == [("stream_rescue", [7])]


def test_erase_distribution_outliers_uses_bulk_detector(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    class DummyGetter:
        def __init__(self, value):
            self._value = value

        def get(self):
            return self._value

    cfg = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="G",
        side="A",
    )
    monkeypatch.setattr(actions, "_make_config_from_widgets", lambda _ctx: cfg)

    detector_calls = []
    clear_calls = []

    def fake_find(*args, **kwargs):
        detector_calls.append((args, kwargs))
        return [7, 9]

    def fake_clear(*args):
        clear_calls.append(args)

    monkeypatch.setattr(actions, "find_distribution_outliers", fake_find)
    monkeypatch.setattr(actions, "clear_wire_numbers", fake_clear)

    ctx = types.SimpleNamespace(
        widgets=types.SimpleNamespace(
            entry_confidence=DummyGetter("0.85"),
            entry_times_sigma=DummyGetter("2.5"),
        ),
        live_plot_manager=None,
    )

    actions.erase_distribution_outliers(ctx)

    assert detector_calls == [
        (
            ("db.sqlite", "APA", "G", "A"),
            {"times_sigma": 2.5, "confidence_threshold": 0.85},
        )
    ]
    assert clear_calls == [("db.sqlite", "APA", "G", "A", [7, 9])]


def test_measure_outliers_triggers_measurement(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    cfg = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="G",
        side="A",
    )
    monkeypatch.setattr(actions, "_make_config_from_inputs", lambda _inputs: cfg)

    detector_calls = []
    measured_wires = []

    def fake_find(*args, **kwargs):
        detector_calls.append((args, kwargs))
        return [10, 20]

    class DummyTensiometer:
        def measure_list(self, wire_list, preserve_order=False):
            measured_wires.append((wire_list, preserve_order))

        def close(self):
            pass

    monkeypatch.setattr(actions, "find_outliers", fake_find)
    monkeypatch.setattr(
        actions, "create_tensiometer", lambda _ctx, _inputs: DummyTensiometer()
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )

    inputs = types.SimpleNamespace(
        times_sigma="3.0",
        confidence=0.75,
        measurement_mode="legacy",
        apa_name="APA",
        layer="G",
        side="A",
    )

    actions.measure_outliers.__wrapped__(types.SimpleNamespace(), inputs)

    assert detector_calls == [
        (
            ("db.sqlite", "APA", "G", "A"),
            {"times_sigma": 3.0, "confidence_threshold": 0.75},
        )
    ]
    assert measured_wires == [([10, 20], False)]


def test_measure_distribution_outliers_triggers_measurement(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    cfg = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="G",
        side="A",
    )
    monkeypatch.setattr(actions, "_make_config_from_inputs", lambda _inputs: cfg)

    detector_calls = []
    measured_wires = []

    def fake_find(*args, **kwargs):
        detector_calls.append((args, kwargs))
        return [30, 40]

    class DummyTensiometer:
        def measure_list(self, wire_list, preserve_order=False):
            measured_wires.append((wire_list, preserve_order))

        def close(self):
            pass

    monkeypatch.setattr(actions, "find_distribution_outliers", fake_find)
    monkeypatch.setattr(
        actions, "create_tensiometer", lambda _ctx, _inputs: DummyTensiometer()
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )

    inputs = types.SimpleNamespace(
        times_sigma="2.0",
        confidence=0.9,
        measurement_mode="legacy",
        apa_name="APA",
        layer="G",
        side="A",
    )

    actions.measure_distribution_outliers.__wrapped__(types.SimpleNamespace(), inputs)

    assert detector_calls == [
        (
            ("db.sqlite", "APA", "G", "A"),
            {"times_sigma": 2.0, "confidence_threshold": 0.9},
        )
    ]
    assert measured_wires == [([30, 40], False)]


def test_measure_refine_outliers_remeasures_union(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    cfg = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="G",
        side="A",
    )
    monkeypatch.setattr(actions, "_make_config_from_inputs", lambda _inputs: cfg)

    residual_calls = []
    bulk_calls = []
    measured_wires = []

    def fake_residual(*args, **kwargs):
        residual_calls.append((args, kwargs))
        return [10, 20, 30]

    def fake_bulk(*args, **kwargs):
        bulk_calls.append((args, kwargs))
        return [20, 30, 40]

    class DummyTensiometer:
        def measure_list(self, wire_list, preserve_order=False):
            measured_wires.append((wire_list, preserve_order))

        def close(self):
            pass

    monkeypatch.setattr(actions, "find_outliers", fake_residual)
    monkeypatch.setattr(actions, "find_distribution_outliers", fake_bulk)
    monkeypatch.setattr(
        actions, "create_tensiometer", lambda _ctx, _inputs: DummyTensiometer()
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )

    inputs = types.SimpleNamespace(
        times_sigma="2.0",
        confidence=0.8,
        measurement_mode="legacy",
        apa_name="APA",
        layer="G",
        side="A",
    )

    actions.measure_refine_outliers.__wrapped__(types.SimpleNamespace(), inputs)

    expected_kwargs = {"times_sigma": 2.0, "confidence_threshold": 0.8}
    assert residual_calls == [(("db.sqlite", "APA", "G", "A"), expected_kwargs)]
    assert bulk_calls == [(("db.sqlite", "APA", "G", "A"), expected_kwargs)]
    assert measured_wires == [([10, 20, 30, 40], False)]


def test_measure_refine_outliers_skips_when_empty(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    cfg = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="G",
        side="A",
    )
    monkeypatch.setattr(actions, "_make_config_from_inputs", lambda _inputs: cfg)

    monkeypatch.setattr(actions, "find_outliers", lambda *_a, **_k: [])
    monkeypatch.setattr(actions, "find_distribution_outliers", lambda *_a, **_k: [])

    tensiometer_built = []
    monkeypatch.setattr(
        actions,
        "create_tensiometer",
        lambda _ctx, _inputs: tensiometer_built.append(1) or object(),
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )

    inputs = types.SimpleNamespace(
        times_sigma="2.0",
        confidence=0.8,
        measurement_mode="legacy",
        apa_name="APA",
        layer="G",
        side="A",
    )

    actions.measure_refine_outliers.__wrapped__(types.SimpleNamespace(), inputs)

    assert tensiometer_built == []


def test_calibrate_background_noise_accepts_float_like_samplerate(monkeypatch):
    actions = _load_actions_module(monkeypatch)
    calls = []
    monkeypatch.setattr(actions, "_capture_worker_inputs", lambda _ctx: object())
    monkeypatch.setattr(actions, "save_state", lambda _ctx: None)

    monkeypatch.setitem(
        sys.modules,
        "dune_tension.audio_runtime",
        types.SimpleNamespace(
            get_samplerate=lambda: "44100.0",
            calibrate_background_noise=lambda samplerate: calls.append(samplerate),
        ),
    )

    ctx = types.SimpleNamespace(
        stop_event=threading.Event(),
        measurement_lock=threading.Lock(),
        measurement_active=False,
        active_measurement_name="",
    )

    actions.calibrate_background_noise(ctx)

    assert _wait_for(lambda: calls == [44100])


def test_clear_range_accepts_tension_expression(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    class DummyGetter:
        def __init__(self, value):
            self._value = value

        def get(self):
            return self._value

    summaries = cast(Any, types.ModuleType("dune_tension.summaries"))
    summaries.get_tension_series = lambda _config: {
        "A": {1: 6.9, 2: 7.0, 3: 7.1, 5: 8.4}
    }
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries)

    cfg = types.SimpleNamespace(
        data_path="db.sqlite",
        apa_name="APA",
        layer="G",
        side="A",
    )
    monkeypatch.setattr(actions, "_make_config_from_widgets", lambda _ctx: cfg)

    clear_calls = []
    monkeypatch.setattr(
        actions, "clear_wire_numbers", lambda *args: clear_calls.append(args)
    )

    ctx = types.SimpleNamespace(
        widgets=types.SimpleNamespace(entry_clear_range=DummyGetter("t>7")),
        live_plot_manager=None,
    )

    actions.clear_range(ctx)

    assert clear_calls == [("db.sqlite", "APA", "G", "A", [3, 5])]


def test_measure_list_button_skips_already_measured_wires_when_enabled(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    measured_wires = []

    class DummyTensiometer:
        def measure_list(self, wire_list, preserve_order=False):
            measured_wires.append((wire_list, preserve_order))

        def close(self):
            pass

    summaries = cast(Any, types.ModuleType("dune_tension.summaries"))
    summaries.get_tension_series = lambda _config: {"A": {3: 5.8, 6: 6.1}}
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries)
    monkeypatch.setattr(
        actions, "create_tensiometer", lambda _ctx, _inputs: DummyTensiometer()
    )
    monkeypatch.setattr(
        actions,
        "_make_config_from_inputs",
        lambda _inputs: types.SimpleNamespace(side="A"),
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )

    inputs = types.SimpleNamespace(wire_list="3,5-7", skip_measured=True)

    actions.measure_list_button.__wrapped__(types.SimpleNamespace(), inputs)

    assert measured_wires == [([5, 7], False)]


def test_measure_list_button_keeps_requested_wires_when_skip_disabled(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    measured_wires = []

    class DummyTensiometer:
        def measure_list(self, wire_list, preserve_order=False):
            measured_wires.append((wire_list, preserve_order))

        def close(self):
            pass

    monkeypatch.setattr(
        actions, "create_tensiometer", lambda _ctx, _inputs: DummyTensiometer()
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )

    inputs = types.SimpleNamespace(wire_list="3,5-7", skip_measured=False)

    actions.measure_list_button.__wrapped__(types.SimpleNamespace(), inputs)

    assert measured_wires == [([3, 5, 6, 7], False)]


def test_measure_list_button_skips_requested_wires_when_all_are_measured(
    monkeypatch,
):
    actions = _load_actions_module(monkeypatch)

    measured_wires = []

    class DummyTensiometer:
        def measure_list(self, wire_list, preserve_order=False):
            measured_wires.append((wire_list, preserve_order))

        def close(self):
            pass

    summaries = cast(Any, types.ModuleType("dune_tension.summaries"))
    summaries.get_tension_series = lambda _config: {
        "A": {3: 5.8, 5: 6.0, 6: 6.1, 7: 6.2}
    }
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries)
    monkeypatch.setattr(
        actions, "create_tensiometer", lambda _ctx, _inputs: DummyTensiometer()
    )
    monkeypatch.setattr(
        actions,
        "_make_config_from_inputs",
        lambda _inputs: types.SimpleNamespace(side="A"),
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )

    inputs = types.SimpleNamespace(wire_list="3,5-7", skip_measured=True)

    actions.measure_list_button.__wrapped__(types.SimpleNamespace(), inputs)

    assert measured_wires == []


def test_measure_zone_button_skips_requested_wires_when_all_are_measured(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    measured_wires = []

    class DummyTensiometer:
        def measure_list(self, wire_list, preserve_order=False):
            measured_wires.append((wire_list, preserve_order))

        def close(self):
            pass

    summaries = cast(Any, types.ModuleType("dune_tension.summaries"))
    summaries.get_tension_series = lambda _config: {"A": {11: 5.8, 12: 6.1, 13: 6.2}}
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries)
    monkeypatch.setattr(
        actions, "create_tensiometer", lambda _ctx, _inputs: DummyTensiometer()
    )
    monkeypatch.setattr(
        actions,
        "_make_config_from_inputs",
        lambda _inputs: types.SimpleNamespace(side="A"),
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        actions,
        "_get_wires_in_zones",
        lambda _layer, _side, _zones, *, taped: [11, 12, 13],
    )

    inputs = types.SimpleNamespace(
        layer="U",
        side="A",
        a_taped=False,
        b_taped=False,
        wire_zone="1",
        skip_measured_zone=True,
    )

    actions.measure_zone_button.__wrapped__(types.SimpleNamespace(), inputs)

    assert measured_wires == []


def test_get_wires_in_zones_uses_zone_only_planner(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    layout = types.SimpleNamespace(wire_min=8, wire_max=10)
    monkeypatch.setattr(actions, "LAYER_LAYOUTS", {"U": layout})

    plan_calls = []
    monkeypatch.setattr(
        actions,
        "plan_uv_wire",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("full planner should not be used")
        ),
    )
    monkeypatch.setattr(
        actions,
        "plan_uv_wire_zone",
        lambda layer, side, wire_number: (
            plan_calls.append((layer, side, wire_number))
            or (5 if wire_number != 9 else 3)
        ),
    )

    wires = actions._get_wires_in_zones("U", "A", {5}, taped=False)

    assert wires == [8, 10]
    assert plan_calls == [("U", "A", 8), ("U", "A", 9), ("U", "A", 10)]


def test_selected_laser_offset_pin_uses_side_specific_pin_family(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    monkeypatch.setattr(
        actions,
        "get_bottom_pin_options",
        lambda _layer, side: (
            [("Bottom first (A400)", "A400"), ("Bottom last (A1199)", "A1199")]
            if side == "A"
            else [("Bottom first (B400)", "B400"), ("Bottom last (B1199)", "B1199")]
        ),
    )

    assert actions._selected_laser_offset_pin("V", "A", "B400") == "A400"
    assert actions._selected_laser_offset_pin("V", "B", "A400") == "B400"


def test_move_laser_to_pin_uses_saved_offset(monkeypatch):
    actions = _load_actions_module(monkeypatch)
    monkeypatch.setattr(
        actions, "get_laser_offset", lambda _side: {"x": 2.5, "y": -1.0}
    )
    monkeypatch.setattr(
        actions,
        "get_calibrated_pin_xy_for_side",
        lambda _layer, _side, _pin: (100.0, 200.0),
    )

    moves = []
    ctx = types.SimpleNamespace(
        runtime=types.SimpleNamespace(
            motion=types.SimpleNamespace(
                goto_xy=lambda x, y, **_kwargs: moves.append((x, y)) or True
            )
        ),
        goto_xy=lambda x, y, **_kwargs: moves.append((x, y)) or True,
    )

    assert actions._move_laser_to_pin(ctx, "V", "A", "A2399") is True
    assert moves == [(97.5, 201.0)]


def test_measure_list_button_enables_route_optimization_for_descending_ranges(
    monkeypatch,
):
    actions = _load_actions_module(monkeypatch)

    measured_wires = []

    class DummyTensiometer:
        def measure_list(self, wire_list, preserve_order=False):
            measured_wires.append((wire_list, preserve_order))

        def close(self):
            pass

    monkeypatch.setattr(
        actions, "create_tensiometer", lambda _ctx, _inputs: DummyTensiometer()
    )
    monkeypatch.setattr(
        actions, "_cleanup_after_measurement", lambda *_args, **_kwargs: None
    )

    inputs = types.SimpleNamespace(wire_list="480-478,300", skip_measured=False)

    actions.measure_list_button.__wrapped__(types.SimpleNamespace(), inputs)

    assert measured_wires == [([480, 479, 478, 300], False)]


def test_adjust_focus_with_x_compensation_side_a(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    focus_targets = []
    moves = []
    servo_controller = types.SimpleNamespace(
        focus_position=4000,
        focus_target=lambda target: (
            focus_targets.append(target),
            setattr(servo_controller, "focus_position", target),
        ),
    )
    ctx = types.SimpleNamespace(
        servo_controller=servo_controller,
        get_xy=lambda: (1000.0, 2000.0),
        goto_xy=lambda x, y: moves.append((x, y)) or True,
        widgets=types.SimpleNamespace(
            side_var=types.SimpleNamespace(get=lambda: "A"),
            disable_x_compensation_var=types.SimpleNamespace(get=lambda: False),
        ),
    )

    actions.adjust_focus_with_x_compensation(ctx, 4400)

    assert focus_targets == [4400]
    assert moves == [(998.8, 2000.0)]


def test_adjust_focus_with_x_compensation_side_b(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    focus_targets = []
    moves = []
    servo_controller = types.SimpleNamespace(
        focus_position=4000,
        focus_target=lambda target: (
            focus_targets.append(target),
            setattr(servo_controller, "focus_position", target),
        ),
    )
    ctx = types.SimpleNamespace(
        servo_controller=servo_controller,
        get_xy=lambda: (1000.0, 2000.0),
        goto_xy=lambda x, y: moves.append((x, y)) or True,
        widgets=types.SimpleNamespace(
            side_var=types.SimpleNamespace(get=lambda: "B"),
            disable_x_compensation_var=types.SimpleNamespace(get=lambda: False),
        ),
    )

    actions.adjust_focus_with_x_compensation(ctx, 4200)

    assert focus_targets == [4200]
    assert moves == [(1000.6, 2000.0)]


class _FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, Any]] = []
        self.cancelled: list[Any] = []
        self._counter = 0

    def after(self, delay_ms: int, func: Any) -> str:
        self._counter += 1
        token = f"after-{self._counter}"
        self.after_calls.append((int(delay_ms), func))
        return token

    def after_cancel(self, token: Any) -> None:
        self.cancelled.append(token)


def _make_uv_ctx(layer: str = "U", side: str = "A", mode: str = "legacy") -> Any:
    laser_offset_frame = types.SimpleNamespace(
        grid=lambda **_kwargs: None,
        grid_remove=lambda: None,
    )
    laser_offset_pin_menu = {
        "menu": types.SimpleNamespace(
            delete=lambda *_a, **_kw: None,
            add_command=lambda **_kwargs: None,
        )
    }
    widgets = types.SimpleNamespace(
        layer_var=types.SimpleNamespace(get=lambda: layer),
        side_var=types.SimpleNamespace(get=lambda: side),
        measurement_mode_var=types.SimpleNamespace(get=lambda: mode),
        laser_offset_frame=laser_offset_frame,
        laser_offset_pin_var=types.SimpleNamespace(
            get=lambda: "", set=lambda _value: None
        ),
        laser_offset_pin_menu=laser_offset_pin_menu,
        laser_offset_readout_var=types.SimpleNamespace(set=lambda _value: None),
        btn_seek_pin=types.SimpleNamespace(configure=lambda **_kwargs: None),
        btn_capture_laser_offset=types.SimpleNamespace(
            configure=lambda **_kwargs: None
        ),
    )
    return types.SimpleNamespace(root=_FakeRoot(), widgets=widgets)


def test_refresh_uv_laser_offset_controls_debounces_rapid_calls(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    ctx = _make_uv_ctx()
    actions.refresh_uv_laser_offset_controls(ctx)
    actions.refresh_uv_laser_offset_controls(ctx)
    actions.refresh_uv_laser_offset_controls(ctx)

    assert len(ctx.root.after_calls) == 3
    # Each subsequent call cancels the previous after_id.
    assert ctx.root.cancelled == ["after-1", "after-2"]
    assert ctx.widgets is not None  # sanity


def test_dispatch_uv_offset_refresh_offloads_io_to_thread(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    started_threads: list[Any] = []

    class _SyncThread:
        def __init__(self, target: Any, args: tuple = (), **_kwargs: Any) -> None:
            self._target = target
            self._args = args
            self._kwargs = _kwargs

        def start(self) -> None:
            started_threads.append(self._kwargs)
            self._target(*self._args)

    monkeypatch.setattr(actions, "Thread", _SyncThread)

    bottom_calls: list[tuple[str, str]] = []
    sync_calls: list[str] = []

    monkeypatch.setattr(
        actions,
        "get_bottom_pin_options",
        lambda layer, side: (
            bottom_calls.append((layer, side)) or [("Bottom (B400)", "B400")]
        ),
    )
    monkeypatch.setattr(
        actions,
        "ensure_layer_calibration_ready",
        lambda layer: sync_calls.append(layer),
    )
    monkeypatch.setattr(actions, "get_laser_offset", lambda _side: None)

    ctx = _make_uv_ctx(layer="V", side="A", mode="legacy")
    ctx._uv_refresh_generation = 7

    actions._dispatch_uv_offset_refresh(ctx, 7)

    assert started_threads, "expected a worker thread to be started"
    assert bottom_calls == [("V", "A")]
    assert sync_calls == ["V"]
    # Worker schedules the UI-update via root.after(0, ...).
    assert ctx.root.after_calls
    delay_ms, _func = ctx.root.after_calls[-1]
    assert delay_ms == 0


def test_dispatch_uv_offset_refresh_skips_when_layer_not_uv(monkeypatch):
    actions = _load_actions_module(monkeypatch)
    started: list[Any] = []
    monkeypatch.setattr(
        actions,
        "Thread",
        lambda **kwargs: types.SimpleNamespace(start=lambda: started.append(kwargs)),
    )

    ctx = _make_uv_ctx(layer="X", mode="legacy")
    ctx._uv_refresh_generation = 1
    actions._dispatch_uv_offset_refresh(ctx, 1)

    assert started == []  # X layer ⇒ no I/O work


def test_apply_uv_offset_results_drops_stale_generation(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    set_calls: list[Any] = []
    ctx = _make_uv_ctx()
    ctx.widgets.laser_offset_readout_var = types.SimpleNamespace(
        set=lambda value: set_calls.append(value)
    )
    ctx._uv_refresh_generation = 9

    # Generation 5 was superseded by 9 — must not write any UI state.
    actions._apply_uv_offset_results(
        ctx,
        generation=5,
        layer="V",
        side="A",
        options=[("L", "B400")],
        readout="Side A: x=0.0",
        sync_error=None,
    )

    assert set_calls == []
