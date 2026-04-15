from __future__ import annotations

import pytest

try:
    import numpy as np
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - dependency optional in tests
    pytest.skip("numpy+pandas are required for average profile tests", allow_module_level=True)

from dune_tension.average_profile_clouds import (
    compute_scale_factor,
    kde_mode,
    expected_wire_range,
    _make_cloud_dataframe,
    load_average_side_series_from_csv,
    load_latest_side_series_from_csv,
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
            "A": pd.Series([6.0, 8.0, 10.0], index=[1, 1, 2], dtype="float64"),
            "B": pd.Series([5.0, 7.0], index=[1, 2], dtype="float64"),
        }
    }
    cloud = _make_cloud_dataframe(series_by_apa, {"APA1": 1.0})
    subset_a = cloud[cloud["side"] == "A"]
    assert len(subset_a) == 2
    assert set(subset_a["wire_number"]) == {1, 2}
    assert np.isclose(subset_a.loc[subset_a["wire_number"] == 1, "tension"].iloc[0], 7.0)
