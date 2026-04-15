from __future__ import annotations

import json
import sqlite3

import pytest

try:
    import numpy as np
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - dependency optional in tests
    pytest.skip("numpy+pandas are required for average profile tests", allow_module_level=True)

from dune_tension.average_profile_clouds import (
    AverageProfileCloudOptions,
    DUNEDB_SOURCE,
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
    assert np.isclose(latest_daresbury.series.loc[1], 5.0)
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
