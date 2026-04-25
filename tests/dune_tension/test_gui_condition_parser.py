import importlib.util
from pathlib import Path
import sys
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

    summaries = types.ModuleType("dune_tension.summaries")
    summaries.get_tension_series = lambda _config: {}
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries)

    context = types.ModuleType("dune_tension.gui.context")
    context.GUIContext = object
    monkeypatch.setitem(sys.modules, "dune_tension.gui.context", context)

    state = types.ModuleType("dune_tension.gui.state")
    state.save_state = lambda _ctx: None
    monkeypatch.setitem(sys.modules, "dune_tension.gui.state", state)

    module_name = "gui_actions_condition_under_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def test_condition_parser_supports_and_and_or(monkeypatch):
    actions = _load_actions_module(monkeypatch)
    monkeypatch.setattr(
        sys.modules["dune_tension.summaries"],
        "get_tension_series",
        lambda _config: {"A": {"1": 3.5, "2": 4.5, "3": 5.5, "4": 3.0}},
    )

    cfg = types.SimpleNamespace(side="A", layer="X")

    assert actions._get_wires_matching_tension_condition(cfg, "t<4 AND n<4") == [1]
    assert actions._get_wires_matching_tension_condition(cfg, "t<4 OR t>5") == [1, 3, 4]


def test_condition_parser_keeps_comma_as_and(monkeypatch):
    actions = _load_actions_module(monkeypatch)
    monkeypatch.setattr(
        sys.modules["dune_tension.summaries"],
        "get_tension_series",
        lambda _config: {"A": {"1": 3.5, "2": 4.5, "3": 5.5, "4": 3.0}},
    )

    cfg = types.SimpleNamespace(side="A", layer="X")

    assert actions._get_wires_matching_tension_condition(cfg, "t<4, n<4") == [1]
