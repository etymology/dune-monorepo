import sys
import types
from typing import Any, cast

from _gui_test_support import (
    REPO_SRC,
    install_dune_tension_pkg_shell,
    load_module_from_path,
)


MODULE_PATH = REPO_SRC / "gui" / "actions.py"
APA_NAMING_PATH = REPO_SRC / "apa_naming.py"


def _load_actions_module(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "sounddevice", types.SimpleNamespace(stop=lambda: None)
    )
    dune_pkg, _gui_pkg = install_dune_tension_pkg_shell(monkeypatch)

    apa_module = load_module_from_path(
        monkeypatch, "dune_tension.apa_naming", APA_NAMING_PATH
    )
    cast(Any, dune_pkg).apa_naming = apa_module

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

    summaries = cast(Any, types.ModuleType("dune_tension.summaries"))
    summaries.get_tension_series = lambda _config: {}
    monkeypatch.setitem(sys.modules, "dune_tension.summaries", summaries)

    context = cast(Any, types.ModuleType("dune_tension.gui.context"))
    context.GUIContext = object
    monkeypatch.setitem(sys.modules, "dune_tension.gui.context", context)

    state = cast(Any, types.ModuleType("dune_tension.gui.state"))
    state.save_state = lambda _ctx: None
    monkeypatch.setitem(sys.modules, "dune_tension.gui.state", state)

    return load_module_from_path(
        monkeypatch, "gui_actions_condition_under_test", MODULE_PATH
    )


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
