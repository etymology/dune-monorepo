from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

try:
    import numpy as np
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - dependency optional in tests
    pytest.skip("numpy+pandas are required for average profile tests", allow_module_level=True)

from dune_tension.average_profile_clouds import (
    AverageProfileCloudOptions,
    DUNEDB_SOURCE,
    LayerAnalysisResult,
    compute_scale_factor,
    compute_layer_analysis,
    compute_average_profile_results,
    export_layer_analysis,
    _make_cloud_dataframe,
    _side_legend_label,
    _load_dunedb_layer_measurements,
    kde_mode,
    expected_wire_range,
    _build_output_tag,
    load_average_side_series_from_csv,
    load_average_side_series,
    load_latest_side_series_from_csv,
    load_latest_side_series,
    mode_scale_factor,
    parse_args,
    save_layer_plot,
)


def test_compute_scale_factor_recovers_inverse_constant() -> None:
    target = {
        "A": pd.Series([4.0, 5.0, 6.0], index=[1, 2, 3], dtype="float64"),
        "B": pd.Series([3.0, 3.5, 4.0], index=[1, 2, 3], dtype="float64"),
    }
    scale = 2.5
    series = {
        "A": target["A"] * scale,
        "B": target["B"] * scale,
    }

    k = compute_scale_factor(series, target)
    assert k is not None
    assert np.isclose(k, 1.0 / scale)


def test_joint_scaling_preserves_ab_ratio() -> None:
    raw_a = pd.Series([2.0, 3.0, 4.0], index=[1, 2, 3], dtype="float64")
    ratio = 1.7
    raw_b = raw_a * ratio

    target = {
        "A": pd.Series([4.0, 5.0, 6.0], index=[1, 2, 3], dtype="float64"),
        "B": pd.Series([4.4, 5.5, 6.6], index=[1, 2, 3], dtype="float64"),
    }
    series = {"A": raw_a, "B": raw_b}

    k = compute_scale_factor(series, target)
    assert k is not None

    scaled_a = raw_a * k
    scaled_b = raw_b * k
    assert np.allclose((scaled_b / scaled_a).values, (raw_b / raw_a).values)


def test_load_latest_side_series_from_csv_parses_legacy_time(tmp_path) -> None:
    csv_path = tmp_path / "tension_data_USAPA4_U.csv"
    csv_path.write_text(
        "\n".join(
            [
                "layer,side,wire_number,tension,time",
                "U,A,8,6.0,2024-11-21_10-00-00",
                "U,A,8,7.0,2024-11-21_10-10-00",
                "this,is,a,bad,line,with,too,many,commas,that,should,be,skipped",
                "U,A,9,1.0,2024-11-21_10-00-00",  # implausible (too low)
                "U,B,8,6.5,2024-11-21_10-00-00",
            ]
        ),
        encoding="utf-8",
    )

    result = load_latest_side_series_from_csv(
        csv_path,
        layer="U",
        side="A",
        expected_wires=range(8, 10),
    )
    assert result.wire_count == 1
    assert np.isclose(result.series.loc[8], 7.0)


def test_kde_mode_singleton() -> None:
    assert np.isclose(kde_mode(np.array([6.25])), 6.25)


def test_mode_scale_factor_simple() -> None:
    k = mode_scale_factor(apa_values=np.array([3.0]), global_mode_value=6.0)
    assert k is not None
    assert np.isclose(k, 2.0)


def test_parse_args_supports_no_scaling() -> None:
    args = parse_args(["--no-scaling"])
    assert args.no_scaling is True


def test_parse_args_supports_average_per_wire() -> None:
    args = parse_args(["--average-per-wire"])
    assert args.average_per_wire is True


def test_parse_args_supports_show_all_locations() -> None:
    args = parse_args(["--show-all-locations"])
    assert args.show_all_locations is True


def test_parse_args_defaults_to_all_samples() -> None:
    args = parse_args([])
    assert args.average_per_wire is False


def test_parse_args_supports_moving_average_window() -> None:
    args = parse_args(["--moving-average-window", "31"])
    assert args.moving_average_window == 31


def test_build_output_tag_encodes_cli_switches() -> None:
    args = parse_args(
        ["--no-scaling", "--average-per-wire", "--bins", "20", "--moving-average-window", "31"]
    )
    tag = _build_output_tag(args)
    assert "noscale" in tag
    assert "avgwire" in tag
    assert "bins20" in tag
    assert "win31" in tag


def test_average_side_series_groups_repeated_wire_samples(tmp_path) -> None:
    csv_path = tmp_path / "tension_data_USAPA4_U.csv"
    csv_path.write_text(
        "\n".join(
            [
                "layer,side,wire_number,tension,time",
                "U,A,8,6.0,2024-11-21_10-00-00",
                "U,A,8,7.0,2024-11-21_10-10-00",
                "U,A,8,5.0,2024-11-21_10-20-00",
                "U,A,9,6.5,2024-11-21_10-00-00",
            ]
        ),
        encoding="utf-8",
    )

    result = load_average_side_series_from_csv(
        csv_path,
        layer="U",
        side="A",
        expected_wires=range(8, 10),
    )
    assert result.wire_count == 2
    assert np.isclose(result.series.loc[8], 6.0)
    assert np.isclose(result.series.loc[9], 6.5)


def test_dunedb_loader_reuses_layer_data_and_respects_location_filters(tmp_path) -> None:
    db_path = tmp_path / "dunedb.sqlite"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE tension_actions (
            action_id TEXT PRIMARY KEY,
            apa_name TEXT NOT NULL,
            layer TEXT NOT NULL,
            action_version INTEGER NOT NULL,
            action_json TEXT NOT NULL
        );
        CREATE TABLE tension_measurements (
            action_id TEXT NOT NULL,
            side TEXT NOT NULL,
            wire_index INTEGER NOT NULL,
            tension REAL NOT NULL
        );
        """
    )

    def make_action_json(location: str, insert_date: str) -> str:
        return json.dumps(
            {
                "data": {"location": location},
                "insertion": {"insertDate": insert_date},
            }
        )

    actions = [
        (
            "chi-v1",
            "APA1",
            "x",
            1,
            make_action_json("chicago", "2026-04-01T10:00:00Z"),
        ),
        (
            "chi-v2",
            "APA1",
            "x",
            2,
            make_action_json("chicago", "2026-04-02T10:00:00Z"),
        ),
        (
            "dar-v1",
            "APA1",
            "x",
            3,
            make_action_json("daresbury", "2026-04-03T10:00:00Z"),
        ),
    ]
    conn.executemany(
        """
        INSERT INTO tension_actions(action_id, apa_name, layer, action_version, action_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        actions,
    )
    conn.executemany(
        """
        INSERT INTO tension_measurements(action_id, side, wire_index, tension)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("chi-v1", "a", 1, 6.0),
            ("chi-v1", "a", 2, 6.2),
            ("chi-v2", "a", 1, 7.0),
            ("chi-v2", "a", 2, 7.2),
            ("dar-v1", "a", 1, 5.0),
            ("dar-v1", "a", 2, 5.2),
            ("dar-v1", "a", 999, 6.0),
            ("dar-v1", "a", 1, 3.0),
        ],
    )
    conn.commit()
    conn.close()

    _load_dunedb_layer_measurements.cache_clear()
    try:
        latest_chicago = load_latest_side_series(
            str(db_path),
            apa_name="APA1",
            layer="X",
            side="A",
            expected_wires=expected_wire_range("X"),
            source=DUNEDB_SOURCE,
            location_filter="Chicago",
        )
        average_chicago = load_average_side_series(
            str(db_path),
            apa_name="APA1",
            layer="X",
            side="A",
            expected_wires=expected_wire_range("X"),
            source=DUNEDB_SOURCE,
            location_filter="chicago",
        )
        latest_daresbury = load_latest_side_series(
            str(db_path),
            apa_name="APA1",
            layer="X",
            side="A",
            expected_wires=expected_wire_range("X"),
            source=DUNEDB_SOURCE,
            location_filter="daresbury",
        )
    finally:
        _load_dunedb_layer_measurements.cache_clear()

    assert latest_chicago.wire_count == 2
    assert np.isclose(latest_chicago.series.loc[1], 7.0)
    assert np.isclose(latest_chicago.series.loc[2], 7.2)

    assert average_chicago.wire_count == 2
    assert np.isclose(average_chicago.series.loc[1], 6.5)
    assert np.isclose(average_chicago.series.loc[2], 6.7)

    assert latest_daresbury.wire_count == 2
    assert np.isclose(latest_daresbury.series.loc[1], 3.0)
    assert np.isclose(latest_daresbury.series.loc[2], 5.2)


def test_expected_wire_ranges_match_layer_geometry() -> None:
    assert len(expected_wire_range("G")) == 481
    assert len(expected_wire_range("X")) == 480
    assert list(expected_wire_range("U"))[0] == 8
    assert list(expected_wire_range("U"))[-1] == 1146
    assert list(expected_wire_range("V"))[0] == 8
    assert list(expected_wire_range("V"))[-1] == 1146


def test_make_cloud_dataframe_emits_one_point_per_wire(tmp_path) -> None:
    series_by_apa = {
        "APA1": {
            "A": pd.Series([6.0, 8.0], index=[1, 2], dtype="float64"),
            "B": pd.Series([5.0, 7.0], index=[1, 2], dtype="float64"),
        },
        "APA2": {
            "A": pd.Series([8.0, 10.0], index=[1, 2], dtype="float64"),
            "B": pd.Series([7.0, 9.0], index=[1, 2], dtype="float64"),
        }
    }
    cloud = _make_cloud_dataframe(
        series_by_apa,
        {"APA1": 1.0, "APA2": 1.0},
        average_per_wire=True,
    )
    subset_a = cloud[cloud["side"] == "A"]
    assert len(subset_a) == 2
    assert set(subset_a["wire_number"]) == {1, 2}
    assert np.isclose(subset_a.loc[subset_a["wire_number"] == 1, "tension"].iloc[0], 7.0)
    assert np.isclose(subset_a.loc[subset_a["wire_number"] == 2, "tension"].iloc[0], 9.0)


def test_make_cloud_dataframe_keeps_all_samples_when_not_averaging() -> None:
    series_by_apa = {
        "APA1": {
            "A": pd.Series([6.0, 8.0], index=[1, 1], dtype="float64"),
        }
    }
    cloud = _make_cloud_dataframe(series_by_apa, {"APA1": 1.0}, average_per_wire=False)
    assert len(cloud) == 2


def test_side_legend_label_includes_samples_per_wire_when_averaging() -> None:
    subset = pd.DataFrame(
        {
            "wire_number": [1, 2, 3],
            "tension": [6.0, 7.0, 8.0],
            "apa_count": [2, 4, 6],
        }
    )

    label = _side_legend_label("A", subset, average_per_wire=True)
    assert "wires=3" in label
    assert "samples/wire=4.00" in label
    assert "points=" not in label


def _write_minimal_dunedb(db_path, *, apa_name: str = "APA1", layer: str = "x") -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE tension_actions (
            action_id TEXT PRIMARY KEY,
            apa_name TEXT NOT NULL,
            layer TEXT NOT NULL,
            action_version INTEGER NOT NULL,
            action_json TEXT NOT NULL
        );
        CREATE TABLE tension_measurements (
            action_id TEXT NOT NULL,
            side TEXT NOT NULL,
            wire_index INTEGER NOT NULL,
            tension REAL NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO tension_actions(action_id, apa_name, layer, action_version, action_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            "act-1",
            apa_name,
            layer,
            1,
            json.dumps(
                {
                    "data": {"location": "chicago"},
                    "insertion": {"insertDate": "2026-04-01T00:00:00Z"},
                }
            ),
        ),
    )
    conn.executemany(
        """
        INSERT INTO tension_measurements(action_id, side, wire_index, tension)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("act-1", "a", 1, 6.0),
            ("act-1", "a", 2, 6.5),
            ("act-1", "b", 1, 6.2),
            ("act-1", "b", 2, 6.6),
        ],
    )
    conn.commit()
    conn.close()


def test_compute_layer_analysis_returns_non_empty_result(tmp_path) -> None:
    db_path = tmp_path / "layer.sqlite"
    _write_minimal_dunedb(db_path)

    _load_dunedb_layer_measurements.cache_clear()
    try:
        result = compute_layer_analysis(
            AverageProfileCloudOptions(
                source=DUNEDB_SOURCE,
                db_path=str(db_path),
                layers=("X",),
                min_coverage=0.0,
                output_dir=str(tmp_path / "plots"),
            ),
            layer="X",
        )
    finally:
        _load_dunedb_layer_measurements.cache_clear()

    assert not result.cloud.empty
    assert result.layer == "X"
    assert result.output_path.name.startswith("tension_profile_cloud_X_dunedb_")
    assert set(result.profile_df.columns) == {"wire_number", "mu_A", "mu_B", "n_A", "n_B"}


def test_compute_average_profile_results_preserves_layer_selection(tmp_path) -> None:
    db_path = tmp_path / "layer.sqlite"
    _write_minimal_dunedb(db_path)

    _load_dunedb_layer_measurements.cache_clear()
    try:
        results = compute_average_profile_results(
            AverageProfileCloudOptions(
                source=DUNEDB_SOURCE,
                db_path=str(db_path),
                layers=("X", "G"),
                min_coverage=0.0,
            )
        )
    finally:
        _load_dunedb_layer_measurements.cache_clear()

    assert set(results) == {"X", "G"}
    assert results["X"][0].layer == "X"
    assert results["G"][0].cloud.empty


def test_compute_average_profile_results_can_include_all_locations_view(tmp_path) -> None:
    db_path = tmp_path / "layer.sqlite"
    _write_minimal_dunedb(db_path)

    _load_dunedb_layer_measurements.cache_clear()
    try:
        results = compute_average_profile_results(
            AverageProfileCloudOptions(
                source=DUNEDB_SOURCE,
                db_path=str(db_path),
                layers=("X",),
                min_coverage=0.0,
                split_by_location=True,
                show_all_locations=True,
            )
        )
    finally:
        _load_dunedb_layer_measurements.cache_clear()

    layer_results = results["X"]
    assert [result.location_label for result in layer_results] == [
        "All locations",
        "Chicago",
        "Daresbury",
    ]
    assert layer_results[0].overlay_results is not None
    assert [result.location_label for result in layer_results[0].overlay_results] == [
        "Chicago",
        "Daresbury",
    ]
    assert not layer_results[0].cloud.empty
    assert layer_results[0].location_output_tag.endswith("all_locations")


def test_export_layer_analysis_writes_expected_files(tmp_path) -> None:
    db_path = tmp_path / "layer.sqlite"
    _write_minimal_dunedb(db_path)
    output_dir = tmp_path / "plots"

    _load_dunedb_layer_measurements.cache_clear()
    try:
        options = AverageProfileCloudOptions(
            source=DUNEDB_SOURCE,
            db_path=str(db_path),
            layers=("X",),
            min_coverage=0.0,
            output_dir=str(output_dir),
        )
        result = compute_layer_analysis(options, layer="X")
        export_layer_analysis(result, options)
    finally:
        _load_dunedb_layer_measurements.cache_clear()

    assert result.output_path.exists()
    assert result.profile_summary_path.exists()
    assert result.scale_summary_path.exists()


def test_save_layer_plot_uses_tight_bounding_box(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class _FakeFigure:
        def savefig(self, destination, **kwargs):
            captured["destination"] = destination
            captured["kwargs"] = kwargs

    result = LayerAnalysisResult(
        layer="X",
        location_filter=None,
        location_label=None,
        location_output_tag="tag",
        global_mode_value=6.1,
        cloud=pd.DataFrame(
            {
                "wire_number": [1, 2],
                "tension": [6.0, 6.5],
                "side": ["A", "B"],
                "apa_name": ["APA1", "APA1"],
            }
        ),
        mu_by_side={"A": pd.Series([6.0], index=[1]), "B": pd.Series([6.4], index=[1])},
        n_by_side={"A": pd.Series([1], index=[1]), "B": pd.Series([1], index=[1])},
        profile_df=pd.DataFrame({"wire_number": [1], "mu_A": [6.0], "mu_B": [6.4]}),
        scale_df=pd.DataFrame({"apa_name": ["APA1"], "k": [1.0]}),
        output_path=tmp_path / "plot.png",
        profile_summary_path=tmp_path / "profile.csv",
        scale_summary_path=tmp_path / "scale.csv",
        status_message="ok",
    )

    monkeypatch.setattr(
        "dune_tension.average_profile_clouds.build_layer_figure",
        lambda *args, **kwargs: _FakeFigure(),
    )

    save_layer_plot(
        result=result,
        bins=40,
        average_per_wire=False,
        moving_average_window=15,
    )

    assert captured["destination"] == result.output_path
    assert captured["kwargs"]["dpi"] == 300
    assert captured["kwargs"]["bbox_inches"] == "tight"
    assert captured["kwargs"]["pad_inches"] == 0.2


def test_build_layer_figure_overlays_side_line_plots(monkeypatch) -> None:
    from dune_tension import average_profile_clouds as apc

    class _FakeAxis:
        def __init__(self) -> None:
            self.scatter_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.plot_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.hist_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.axvline_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.title = None
            self.xlabel = None
            self.ylabel = None
            self.legend_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.text_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.grid_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.tick_params_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.transAxes = object()

        def scatter(self, *args, **kwargs):
            self.scatter_calls.append((args, kwargs))

        def plot(self, *args, **kwargs):
            self.plot_calls.append((args, kwargs))

        def hist(self, *args, **kwargs):
            self.hist_calls.append((args, kwargs))

        def axvline(self, *args, **kwargs):
            self.axvline_calls.append((args, kwargs))

        def set_title(self, value):
            self.title = value

        def set_xlabel(self, value):
            self.xlabel = value

        def set_ylabel(self, value):
            self.ylabel = value

        def legend(self, *args, **kwargs):
            self.legend_calls.append((args, kwargs))

        def text(self, *args, **kwargs):
            self.text_calls.append((args, kwargs))

        def grid(self, *args, **kwargs):
            self.grid_calls.append((args, kwargs))

        def tick_params(self, *args, **kwargs):
            self.tick_params_calls.append((args, kwargs))

    class _FakeGrid:
        def __getitem__(self, _item):
            return object()

    class _FakeFigure:
        def __init__(self, *args, **kwargs) -> None:
            self.axes: list[_FakeAxis] = []

        def add_gridspec(self, *args, **kwargs):
            return _FakeGrid()

        def add_subplot(self, *args, **kwargs):
            axis = _FakeAxis()
            self.axes.append(axis)
            return axis

    monkeypatch.setattr("matplotlib.figure.Figure", _FakeFigure)

    result = LayerAnalysisResult(
        layer="X",
        location_filter=None,
        location_label=None,
        location_output_tag="tag",
        global_mode_value=6.1,
        cloud=pd.DataFrame(
            {
                "wire_number": [1, 2, 1, 2],
                "tension": [6.0, 6.2, 6.4, 6.6],
                "side": ["A", "A", "B", "B"],
                "apa_name": ["APA1", "APA1", "APA1", "APA1"],
            }
        ),
        mu_by_side={
            "A": pd.Series([6.0, 6.2], index=[1, 2]),
            "B": pd.Series([6.4, 6.6], index=[1, 2]),
        },
        n_by_side={"A": pd.Series([1, 1], index=[1, 2]), "B": pd.Series([1, 1], index=[1, 2])},
        profile_df=pd.DataFrame(
            {"wire_number": [1, 2], "mu_A": [6.0, 6.2], "mu_B": [6.4, 6.6], "n_A": [1, 1], "n_B": [1, 1]}
        ),
        scale_df=pd.DataFrame({"apa_name": ["APA1"], "k": [1.0]}),
        output_path=Path("/tmp/out.png"),
        profile_summary_path=Path("/tmp/profile.csv"),
        scale_summary_path=Path("/tmp/scales.csv"),
        status_message="ok",
    )

    figure = apc.build_layer_figure(
        result,
        bins=10,
        average_per_wire=False,
        moving_average_window=1,
    )

    assert len(figure.axes) == 2
    profile_axis = figure.axes[0]
    hist_axis = figure.axes[1]
    assert len(profile_axis.scatter_calls) == 2
    assert len(profile_axis.plot_calls) == 2
    assert {kwargs["label"] for _args, kwargs in profile_axis.plot_calls} == {
        "Location 1 A",
        "Location 1 B",
    }
    assert len(hist_axis.hist_calls) == 2


def test_build_layer_figure_overlays_all_locations(monkeypatch) -> None:
    from dune_tension import average_profile_clouds as apc

    class _FakeAxis:
        def __init__(self) -> None:
            self.scatter_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.plot_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.hist_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.axvline_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.legend_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.text_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.grid_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
            self.title = None
            self.xlabel = None
            self.ylabel = None
            self.transAxes = object()

        def scatter(self, *args, **kwargs):
            self.scatter_calls.append((args, kwargs))

        def plot(self, *args, **kwargs):
            self.plot_calls.append((args, kwargs))

        def hist(self, *args, **kwargs):
            self.hist_calls.append((args, kwargs))

        def axvline(self, *args, **kwargs):
            self.axvline_calls.append((args, kwargs))

        def legend(self, *args, **kwargs):
            self.legend_calls.append((args, kwargs))

        def text(self, *args, **kwargs):
            self.text_calls.append((args, kwargs))

        def grid(self, *args, **kwargs):
            self.grid_calls.append((args, kwargs))

        def set_title(self, value):
            self.title = value

        def set_xlabel(self, value):
            self.xlabel = value

        def set_ylabel(self, value):
            self.ylabel = value

    class _FakeGrid:
        def __getitem__(self, _item):
            return object()

    class _FakeFigure:
        def __init__(self, *args, **kwargs) -> None:
            self.axes: list[_FakeAxis] = []

        def add_gridspec(self, *args, **kwargs):
            return _FakeGrid()

        def add_subplot(self, *args, **kwargs):
            axis = _FakeAxis()
            self.axes.append(axis)
            return axis

    monkeypatch.setattr("matplotlib.figure.Figure", _FakeFigure)

    chicago = LayerAnalysisResult(
        layer="X",
        location_filter="chicago",
        location_label="Chicago",
        location_output_tag="tag_chicago",
        global_mode_value=6.1,
        cloud=pd.DataFrame(
            {
                "wire_number": [1, 2, 1, 2],
                "tension": [6.0, 6.2, 6.4, 6.6],
                "side": ["A", "A", "B", "B"],
                "apa_name": ["APA1", "APA1", "APA1", "APA1"],
                "location": ["Chicago"] * 4,
            }
        ),
        mu_by_side={"A": pd.Series([6.0, 6.2], index=[1, 2]), "B": pd.Series([6.4, 6.6], index=[1, 2])},
        n_by_side={"A": pd.Series([1, 1], index=[1, 2]), "B": pd.Series([1, 1], index=[1, 2])},
        profile_df=pd.DataFrame(
            {
                "wire_number": [1, 2],
                "mu_A": [6.0, 6.2],
                "mu_B": [6.4, 6.6],
                "n_A": [1, 1],
                "n_B": [1, 1],
                "location": ["Chicago", "Chicago"],
            }
        ),
        scale_df=pd.DataFrame({"apa_name": ["APA1"], "k": [1.0], "location": ["Chicago"]}),
        output_path=Path("/tmp/chicago.png"),
        profile_summary_path=Path("/tmp/chicago_profile.csv"),
        scale_summary_path=Path("/tmp/chicago_scale.csv"),
        status_message="ok",
    )
    daresbury = LayerAnalysisResult(
        layer="X",
        location_filter="daresbury",
        location_label="Daresbury",
        location_output_tag="tag_daresbury",
        global_mode_value=6.1,
        cloud=pd.DataFrame(
            {
                "wire_number": [1, 2, 1, 2],
                "tension": [6.1, 6.3, 6.5, 6.7],
                "side": ["A", "A", "B", "B"],
                "apa_name": ["APA1", "APA1", "APA1", "APA1"],
                "location": ["Daresbury"] * 4,
            }
        ),
        mu_by_side={"A": pd.Series([6.1, 6.3], index=[1, 2]), "B": pd.Series([6.5, 6.7], index=[1, 2])},
        n_by_side={"A": pd.Series([1, 1], index=[1, 2]), "B": pd.Series([1, 1], index=[1, 2])},
        profile_df=pd.DataFrame(
            {
                "wire_number": [1, 2],
                "mu_A": [6.1, 6.3],
                "mu_B": [6.5, 6.7],
                "n_A": [1, 1],
                "n_B": [1, 1],
                "location": ["Daresbury", "Daresbury"],
            }
        ),
        scale_df=pd.DataFrame({"apa_name": ["APA1"], "k": [1.0], "location": ["Daresbury"]}),
        output_path=Path("/tmp/daresbury.png"),
        profile_summary_path=Path("/tmp/daresbury_profile.csv"),
        scale_summary_path=Path("/tmp/daresbury_scale.csv"),
        status_message="ok",
    )
    combined = LayerAnalysisResult(
        layer="X",
        location_filter=None,
        location_label="All locations",
        location_output_tag="tag_all_locations",
        global_mode_value=6.1,
        cloud=pd.concat([chicago.cloud, daresbury.cloud], ignore_index=True),
        mu_by_side={},
        n_by_side={},
        profile_df=pd.concat([chicago.profile_df, daresbury.profile_df], ignore_index=True),
        scale_df=pd.concat([chicago.scale_df, daresbury.scale_df], ignore_index=True),
        output_path=Path("/tmp/all.png"),
        profile_summary_path=Path("/tmp/all_profile.csv"),
        scale_summary_path=Path("/tmp/all_scale.csv"),
        status_message="ok",
        overlay_results=(chicago, daresbury),
    )

    figure = apc.build_layer_figure(
        combined,
        bins=10,
        average_per_wire=False,
        moving_average_window=1,
    )

    assert len(figure.axes) == 2
    profile_axis = figure.axes[0]
    hist_axis = figure.axes[1]
    assert len(profile_axis.plot_calls) == 4
    assert {kwargs["label"] for _args, kwargs in profile_axis.plot_calls} == {
        "Chicago A",
        "Chicago B",
        "Daresbury A",
        "Daresbury B",
    }
    assert len(hist_axis.hist_calls) == 4
