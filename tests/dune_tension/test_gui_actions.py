import importlib.util
from pathlib import Path
import sys
import threading
import time
import types


MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "dune_tension" / "gui" / "actions.py"
)


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

    config = types.ModuleType("dune_tension.config")
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

    data_cache = types.ModuleType("dune_tension.data_cache")
    data_cache.clear_wire_numbers = lambda *args, **kwargs: None
    data_cache.clear_wire_range = lambda *args, **kwargs: None
    data_cache.find_distribution_outliers = lambda *args, **kwargs: []
    data_cache.find_outliers = lambda *args, **kwargs: []
    data_cache.get_dataframe = lambda *args, **kwargs: None
    data_cache.update_dataframe = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dune_tension.data_cache", data_cache)

    results = types.ModuleType("dune_tension.results")
    results.EXPECTED_COLUMNS = []
    monkeypatch.setitem(sys.modules, "dune_tension.results", results)

    tensiometer = types.ModuleType("dune_tension.tensiometer")
    tensiometer.Tensiometer = object
    tensiometer.build_tensiometer = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "dune_tension.tensiometer", tensiometer)

    tensiometer_functions = types.ModuleType("dune_tension.tensiometer_functions")
    tensiometer_functions.make_config = lambda **kwargs: types.SimpleNamespace(**kwargs)
    tensiometer_functions.normalize_confidence_source = lambda value: (
        str(value).strip().lower().replace(" ", "_")
    )
    monkeypatch.setitem(
        sys.modules,
        "dune_tension.tensiometer_functions",
        tensiometer_functions,
    )

    context = types.ModuleType("dune_tension.gui.context")
    context.GUIContext = object
    monkeypatch.setitem(sys.modules, "dune_tension.gui.context", context)

    state = types.ModuleType("dune_tension.gui.state")
    state.save_state = lambda _ctx: None
    monkeypatch.setitem(sys.modules, "dune_tension.gui.state", state)

    layer_calibration = types.ModuleType("dune_tension.layer_calibration")
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

    plc_desktop = types.ModuleType("dune_tension.plc_desktop")
    plc_desktop.desktop_seek_pin = lambda *_args, **_kwargs: True
    monkeypatch.setitem(sys.modules, "dune_tension.plc_desktop", plc_desktop)

    plc_io = types.ModuleType("dune_tension.plc_io")
    plc_io.get_plc_io_mode = lambda: "desktop"
    monkeypatch.setitem(sys.modules, "dune_tension.plc_io", plc_io)

    uv_wire_planner = types.ModuleType("dune_tension.uv_wire_planner")
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
        plot_audio=True,
        suppress_wire_preview=False,
        legacy_tension_condition="t<7",
    )

    actions.create_tensiometer(ctx, inputs)

    assert len(build_calls) == 1
    assert build_calls[0]["confidence_source"] == "signal_amplitude"
    assert build_calls[0]["runtime_bundle"] is runtime
    assert build_calls[0]["use_manual_focus"] is True
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

    ctx = types.SimpleNamespace(stop_event=threading.Event())

    actions.calibrate_background_noise(ctx)

    assert _wait_for(lambda: calls == [44100])


def test_clear_range_accepts_tension_expression(monkeypatch):
    actions = _load_actions_module(monkeypatch)

    class DummyGetter:
        def __init__(self, value):
            self._value = value

        def get(self):
            return self._value

    summaries = types.ModuleType("dune_tension.summaries")
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

    summaries = types.ModuleType("dune_tension.summaries")
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

    assert measured_wires == [([5, 7], True)]


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

    assert measured_wires == [([3, 5, 6, 7], True)]


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

    summaries = types.ModuleType("dune_tension.summaries")
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

    summaries = types.ModuleType("dune_tension.summaries")
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


def test_measure_list_button_preserves_descending_range_order(monkeypatch):
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

    assert measured_wires == [([480, 479, 478, 300], True)]


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
