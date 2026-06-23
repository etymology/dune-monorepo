from __future__ import annotations

import math
import sqlite3

import pytest

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - dependency optional in tests
    pytest.skip("pandas is required for data_cache tests", allow_module_level=True)

from dune_tension.data_cache import (
    append_dataframe_row,
    append_results_row,
    clear_wire_numbers,
    find_outliers,
    find_distribution_outliers,
    get_dataframe,
    get_results_dataframe,
    select_dataframe,
    select_results_dataframe,
)
from dune_tension.results import EXPECTED_COLUMNS


LEGACY_COLUMNS = [
    "apa_name",
    "layer",
    "side",
    "wire_number",
    "frequency",
    "confidence",
    "x",
    "y",
    "wires",
    "ttf",
    "time",
    "zone",
    "wire_length",
    "tension",
    "tension_pass",
    "t_sigma",
]


def _create_legacy_table(conn: sqlite3.Connection, table: str) -> None:
    columns_sql = ", ".join(f"{col} TEXT" for col in LEGACY_COLUMNS)
    conn.execute(f"CREATE TABLE {table} ({columns_sql})")


def test_append_row_migrates_legacy_db_schema(tmp_path) -> None:
    db_path = tmp_path / "legacy_tension_data.db"

    legacy_row = {
        "apa_name": "APA",
        "layer": "G",
        "side": "A",
        "wire_number": "4",
        "frequency": "74.1",
        "confidence": "0.95",
        "x": "1.0",
        "y": "2.0",
        "wires": "[]",
        "ttf": "0.0",
        "time": "2026-03-10T10:00:00",
        "zone": "1",
        "wire_length": "1200.0",
        "tension": "5.5",
        "tension_pass": "1",
        "t_sigma": "0.2",
    }

    with sqlite3.connect(db_path) as conn:
        _create_legacy_table(conn, "tension_data")
        _create_legacy_table(conn, "tension_samples")
        placeholders = ", ".join("?" for _ in LEGACY_COLUMNS)
        columns = ", ".join(LEGACY_COLUMNS)
        values = [legacy_row[col] for col in LEGACY_COLUMNS]
        conn.execute(
            f"INSERT INTO tension_data ({columns}) VALUES ({placeholders})", values
        )
        conn.execute(
            f"INSERT INTO tension_samples ({columns}) VALUES ({placeholders})", values
        )
        conn.commit()

    new_row = {
        "apa_name": "APA",
        "layer": "G",
        "side": "A",
        "wire_number": 5,
        "frequency": 75.9,
        "confidence": 1.0,
        "x": 6307.1064453125,
        "y": 352.9916076660156,
        "taped": True,
        "time": "2026-03-10T10:01:00",
        "zone": 1,
        "wire_length": 1285.0,
        "tension": 5.9,
        "tension_pass": True,
    }

    append_dataframe_row(str(db_path), new_row)
    append_results_row(str(db_path), new_row)

    with sqlite3.connect(db_path) as conn:
        tension_data_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(tension_data)")
        ]
        tension_samples_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(tension_samples)")
        ]

    assert "taped" in tension_data_columns
    assert "taped" in tension_samples_columns

    data_df = get_dataframe(str(db_path))
    results_df = get_results_dataframe(str(db_path))

    assert list(data_df.columns) == EXPECTED_COLUMNS
    assert list(results_df.columns) == EXPECTED_COLUMNS
    assert len(data_df) == 2
    assert len(results_df) == 2
    assert bool(data_df.iloc[-1]["taped"]) is True
    assert bool(results_df.iloc[-1]["taped"]) is True


def test_clear_wire_numbers_removes_selected_rows_from_both_tables(tmp_path) -> None:
    db_path = tmp_path / "tension_data.db"

    def make_row(wire_number: int, side: str = "A", time: str = "2026-03-10T10:00:00"):
        return {
            "apa_name": "APA",
            "layer": "G",
            "side": side,
            "wire_number": wire_number,
            "frequency": 75.0 + wire_number,
            "confidence": 0.95,
            "x": 100.0,
            "y": 200.0,
            "taped": False,
            "time": time,
            "zone": 1,
            "wire_length": 1200.0,
            "tension": 6.0 + wire_number,
            "tension_pass": True,
        }

    append_dataframe_row(str(db_path), make_row(1))
    append_dataframe_row(str(db_path), make_row(2))
    append_dataframe_row(str(db_path), make_row(3))
    append_dataframe_row(str(db_path), make_row(4, side="B"))

    append_results_row(str(db_path), make_row(1, time="2026-03-10T10:00:01"))
    append_results_row(str(db_path), make_row(2, time="2026-03-10T10:00:02"))
    append_results_row(str(db_path), make_row(2, time="2026-03-10T10:00:03"))
    append_results_row(str(db_path), make_row(3, time="2026-03-10T10:00:04"))
    append_results_row(str(db_path), make_row(4, side="B", time="2026-03-10T10:00:05"))

    clear_wire_numbers(str(db_path), "APA", "G", "A", [2, 99])

    data_df = get_dataframe(str(db_path))
    results_df = get_results_dataframe(str(db_path))

    remaining_data = sorted(
        (int(row.wire_number), row.side) for row in data_df.itertuples(index=False)
    )
    remaining_results = sorted(
        (int(row.wire_number), row.side) for row in results_df.itertuples(index=False)
    )

    assert remaining_data == [(1, "A"), (3, "A"), (4, "B")]
    assert remaining_results == [(1, "A"), (3, "A"), (4, "B")]


def test_find_distribution_outliers_uses_bulk_tension_distribution(tmp_path) -> None:
    db_path = tmp_path / "distribution_outliers.db"

    def make_row(wire_number: int, tension: float, confidence: float = 0.95) -> dict:
        return {
            "apa_name": "APA",
            "layer": "G",
            "side": "A",
            "wire_number": wire_number,
            "frequency": 75.0,
            "confidence": confidence,
            "x": 100.0,
            "y": 200.0,
            "taped": False,
            "time": "2026-03-10T10:00:00",
            "zone": 1,
            "wire_length": 1200.0,
            "tension": tension,
            "tension_pass": True,
        }

    for wire_number in range(1, 21):
        append_dataframe_row(str(db_path), make_row(wire_number, 5.0))
    # Wire 21 is a clear outlier; its low confidence must NOT exclude it, since
    # the summary/plot the detector mirrors ignore confidence entirely.
    append_dataframe_row(str(db_path), make_row(21, 9.0, confidence=0.1))

    outliers = find_distribution_outliers(
        str(db_path),
        "APA",
        "G",
        "A",
        times_sigma=2.0,
    )

    assert outliers == [21]


def _make_outlier_row(
    wire_number: int,
    tension: float,
    confidence: float = 0.95,
    when: str = "2026-03-10T10:00:00",
) -> dict:
    return {
        "apa_name": "APA",
        "layer": "G",
        "side": "A",
        "wire_number": wire_number,
        "frequency": 75.0,
        "confidence": confidence,
        "x": 100.0,
        "y": 200.0,
        "taped": False,
        "time": when,
        "zone": 1,
        "wire_length": 1200.0,
        "tension": tension,
        "tension_pass": True,
    }


def _run_find_outliers(tmp_path, name, tensions, *, times_sigma=2.0):
    """Write one row per ``tensions`` value (1-indexed) and return detected outliers."""

    db_path = tmp_path / f"{name}.db"
    for wire_number, tension in enumerate(tensions, start=1):
        append_dataframe_row(str(db_path), _make_outlier_row(wire_number, tension))
    return find_outliers(
        str(db_path),
        "APA",
        "G",
        "A",
        times_sigma=times_sigma,
    )


def test_find_outliers_flags_spikes_against_moving_average(tmp_path) -> None:
    """Residuals are measured against the local moving average, not the global mean.

    The baseline ramps from 5 to 8 across the wires, so the bulk distribution is
    wide. Outliers are obvious only relative to their neighbours: each spike sits
    far from the local moving average even though its absolute tension stays within
    the physically plausible band that summaries/plots report.
    """

    n = 60
    tensions = [5.0 + 3.0 * i / (n - 1) for i in range(n)]
    tensions[24] = 9.5  # wire 25: ~3.3 above its ~6.2 local average
    tensions[44] = 2.5  # wire 45: ~4.7 below its ~7.2 local average

    outliers = _run_find_outliers(tmp_path, "ramp_spikes", tensions)

    # Both flagged, returned worst-first: wire 45 deviates further than wire 25.
    assert outliers == [45, 25]


def test_find_outliers_orders_results_worst_first(tmp_path) -> None:
    """Outliers are returned ordered by descending distance from the moving average."""

    tensions = [5.0] * 60
    tensions[39] = 9.0  # wire 40: largest deviation from the ~5.0 baseline
    tensions[49] = 3.4  # wire 50: intermediate deviation
    tensions[19] = 6.8  # wire 20: smallest deviation

    outliers = _run_find_outliers(tmp_path, "ordered", tensions)

    # Returned worst-first, by descending distance from the moving average.
    assert outliers == [40, 50, 20]


def test_find_outliers_uses_final_per_wire_tension_not_raw_measurements(
    tmp_path,
) -> None:
    """Residuals use the final per-wire tension, not every raw measurement.

    Reproduces the reported failure on large datasets: when a wire is measured
    many times, those repeated rows dominate the positional rolling window. The
    detector then masks the genuine outlier and flags its innocent neighbours.
    Collapsing to the final (latest plausible) value per wire — exactly what the
    summary CSV and residual plot use — leaves a single value per wire so only the
    true outlier is reported.
    """

    db_path = tmp_path / "duplicate_measurements.db"

    n = 160
    # Gentle ripple gives a realistic, non-zero residual spread.
    for wire_number in range(1, n + 1):
        tension = 5.0 + 0.05 * math.sin(wire_number / 5.0)
        append_dataframe_row(str(db_path), _make_outlier_row(wire_number, tension))

    # Wire 80 is a genuine, plausible outlier, re-measured 25 times (as an
    # operator would when a reading looks suspicious).
    for k in range(25):
        append_dataframe_row(
            str(db_path),
            _make_outlier_row(80, 8.5, when=f"2026-03-12T10:{k:02d}:00"),
        )
    # Wire 40 is perfectly normal but also heavily re-measured.
    for k in range(25):
        append_dataframe_row(
            str(db_path),
            _make_outlier_row(40, 5.0, when=f"2026-03-12T11:{k:02d}:00"),
        )

    outliers = find_outliers(
        str(db_path),
        "APA",
        "G",
        "A",
        times_sigma=2.5,
    )

    assert outliers == [80]


def test_find_outliers_ignores_implausible_measurements(tmp_path) -> None:
    """Implausible readings are excluded, matching the summary/plot selection.

    A wire whose latest reading is physically implausible is not part of the
    final tension series, so it must not appear as a residual outlier; its last
    plausible reading is what counts.
    """

    db_path = tmp_path / "implausible.db"
    for wire_number in range(1, 41):
        append_dataframe_row(str(db_path), _make_outlier_row(wire_number, 5.0))

    # Wire 20's latest reading is implausible (>10 N); an earlier reading agrees
    # with its neighbours. The plausible value should win and no outlier reported.
    append_dataframe_row(
        str(db_path), _make_outlier_row(20, 5.0, when="2026-03-11T09:00:00")
    )
    append_dataframe_row(
        str(db_path), _make_outlier_row(20, 50.0, when="2026-03-11T10:00:00")
    )

    outliers = find_outliers(
        str(db_path),
        "APA",
        "G",
        "A",
        times_sigma=2.0,
    )

    assert outliers == []


def test_find_outliers_uses_nearest_calculable_average_for_end_wires(tmp_path) -> None:
    db_path = tmp_path / "residual_outliers.db"

    for wire_number in range(1, 31):
        tension = 5.0
        if wire_number in {1, 30}:
            tension = 8.5  # plausible, but far from the ~5.0 neighbours
        append_dataframe_row(
            str(db_path), _make_outlier_row(wire_number, tension)
        )

    outliers = find_outliers(
        str(db_path),
        "APA",
        "G",
        "A",
        times_sigma=2.0,
    )

    assert outliers == [1, 30]


def test_select_dataframe_filters_without_loading_full_table(tmp_path) -> None:
    db_path = tmp_path / "filtered_tension_data.db"

    def make_row(apa_name: str, layer: str, side: str, wire_number: int) -> dict:
        return {
            "apa_name": apa_name,
            "layer": layer,
            "side": side,
            "wire_number": wire_number,
            "frequency": 75.0,
            "confidence": 0.95,
            "x": 100.0,
            "y": 200.0,
            "taped": False,
            "time": "2026-03-10T10:00:00",
            "zone": 1,
            "wire_length": 1200.0,
            "tension": 6.0,
            "tension_pass": True,
        }

    append_dataframe_row(str(db_path), make_row("APA1", "X", "A", 1))
    append_dataframe_row(str(db_path), make_row("APA1", "V", "A", 2))
    append_dataframe_row(str(db_path), make_row("APA2", "X", "B", 3))

    filtered = select_dataframe(
        str(db_path),
        where_clause="apa_name = ? AND layer = ?",
        params=("APA1", "X"),
    )

    assert filtered["apa_name"].tolist() == ["APA1"]
    assert filtered["layer"].tolist() == ["X"]
    assert filtered["wire_number"].tolist() == ["1"]


def test_select_results_dataframe_filters_samples_table(tmp_path) -> None:
    db_path = tmp_path / "filtered_tension_samples.db"

    def make_row(side: str, wire_number: int) -> dict:
        return {
            "apa_name": "APA",
            "layer": "G",
            "side": side,
            "wire_number": wire_number,
            "frequency": 75.0,
            "confidence": 0.95,
            "x": 100.0,
            "y": 200.0,
            "taped": False,
            "time": "2026-03-10T10:00:00",
            "zone": 1,
            "wire_length": 1200.0,
            "tension": 6.0,
            "tension_pass": True,
        }

    append_results_row(str(db_path), make_row("A", 1))
    append_results_row(str(db_path), make_row("B", 2))

    filtered = select_results_dataframe(
        str(db_path),
        where_clause="side = ?",
        params=("B",),
    )

    assert filtered["side"].tolist() == ["B"]
    assert filtered["wire_number"].tolist() == ["2"]
