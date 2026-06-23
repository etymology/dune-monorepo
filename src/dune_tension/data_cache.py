from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from dune_tension.results import EXPECTED_COLUMNS
from dune_tension.tension_calculation import tension_plausible

TABLE_TENSION_DATA = "tension_data"
TABLE_TENSION_SAMPLES = "tension_samples"

# In-process DataFrame cache.
_dataframe_cache: dict[str, pd.DataFrame] = {}


def _table_columns_sql() -> str:
    return ", ".join(f"{col} TEXT" for col in EXPECTED_COLUMNS)


def _get_table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(row[1]) for row in rows]


def _normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for col in EXPECTED_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = None
    return normalized.loc[:, EXPECTED_COLUMNS]


def _ensure_table_schema(conn: sqlite3.Connection, table: str) -> None:
    if not _table_exists(conn, table):
        conn.execute(f"CREATE TABLE {table} ({_table_columns_sql()})")
        return

    existing_columns = set(_get_table_columns(conn, table))
    for col in EXPECTED_COLUMNS:
        if col not in existing_columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")


def _ensure_tables(conn: sqlite3.Connection) -> None:
    _ensure_table_schema(conn, TABLE_TENSION_DATA)
    _ensure_table_schema(conn, TABLE_TENSION_SAMPLES)
    conn.commit()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _read_table(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    if not _table_exists(conn, table):
        return pd.DataFrame(columns=EXPECTED_COLUMNS)
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    return _normalize_dataframe_columns(df)


def _cache_key(file_path: str, table: str) -> str:
    return f"{file_path}::{table}"


def _invalidate_cached_table(file_path: str, table: str) -> None:
    _dataframe_cache.pop(_cache_key(file_path, table), None)


def connect_write_database(file_path: str) -> sqlite3.Connection:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def ensure_tables(conn: sqlite3.Connection) -> None:
    _ensure_tables(conn)


def _get_table_dataframe(file_path: str, table: str) -> pd.DataFrame:
    key = _cache_key(file_path, table)
    if key in _dataframe_cache:
        return _dataframe_cache[key]

    if not Path(file_path).exists():
        df = pd.DataFrame(columns=EXPECTED_COLUMNS)
        _dataframe_cache[key] = df
        return df

    with sqlite3.connect(file_path) as conn:
        _ensure_tables(conn)
        df = _read_table(conn, table)
    _dataframe_cache[key] = df
    return df


def _select_table_dataframe(
    file_path: str,
    table: str,
    *,
    where_clause: str = "",
    params: Iterable[Any] = (),
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    if not Path(file_path).exists():
        return pd.DataFrame(
            columns=list(columns) if columns is not None else EXPECTED_COLUMNS
        )

    selected_columns = list(columns) if columns is not None else EXPECTED_COLUMNS
    normalized_columns = [col for col in EXPECTED_COLUMNS if col in selected_columns]
    if not normalized_columns:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    sql = f"SELECT {', '.join(normalized_columns)} FROM {table}"
    if where_clause.strip():
        sql = f"{sql} WHERE {where_clause}"

    with sqlite3.connect(file_path) as conn:
        _ensure_tables(conn)
        if not _table_exists(conn, table):
            return pd.DataFrame(columns=normalized_columns)
        df = pd.read_sql_query(sql, conn, params=tuple(params))

    return _normalize_dataframe_columns(df)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for col in EXPECTED_COLUMNS:
        value = row.get(col)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, list):
            value = str(value)
        normalized[col] = value
    return normalized


def _append_rows(
    file_path: str,
    table: str,
    rows: Iterable[dict[str, Any]],
    *,
    conn: sqlite3.Connection | None = None,
    ensure_schema: bool = True,
    commit: bool = True,
) -> None:
    normalized_rows = [_normalize_row(row) for row in rows]
    if not normalized_rows:
        return

    columns = ", ".join(EXPECTED_COLUMNS)
    placeholders = ", ".join("?" for _ in EXPECTED_COLUMNS)
    values = [
        tuple(normalized[col] for col in EXPECTED_COLUMNS)
        for normalized in normalized_rows
    ]

    owns_connection = conn is None
    active_conn = conn or connect_write_database(file_path)
    try:
        if ensure_schema:
            _ensure_tables(active_conn)
        active_conn.executemany(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            values,
        )
        if commit:
            active_conn.commit()
    finally:
        if owns_connection:
            active_conn.close()

    _invalidate_cached_table(file_path, table)


def _append_row(file_path: str, table: str, row: dict[str, Any]) -> None:
    _append_rows(file_path, table, [row])


def get_dataframe(file_path: str) -> pd.DataFrame:
    """Return the summary measurement DataFrame (``tension_data``)."""

    return _get_table_dataframe(file_path, TABLE_TENSION_DATA)


def select_dataframe(
    file_path: str,
    *,
    where_clause: str = "",
    params: Iterable[Any] = (),
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return selected ``tension_data`` rows without caching the full table."""

    return _select_table_dataframe(
        file_path,
        TABLE_TENSION_DATA,
        where_clause=where_clause,
        params=params,
        columns=columns,
    )


def update_dataframe(file_path: str, df: pd.DataFrame) -> None:
    """Replace ``tension_data`` with ``df`` and refresh cache."""

    normalized_df = _normalize_dataframe_columns(df)
    key = _cache_key(file_path, TABLE_TENSION_DATA)
    _dataframe_cache[key] = normalized_df.copy()
    with connect_write_database(file_path) as conn:
        _ensure_tables(conn)
        normalized_df.to_sql(TABLE_TENSION_DATA, conn, if_exists="replace", index=False)


def append_dataframe_row(file_path: str, row: dict[str, Any]) -> None:
    """Append one row to ``tension_data`` without rewriting the full table."""

    _append_row(file_path, TABLE_TENSION_DATA, row)


def append_dataframe_rows(
    file_path: str,
    rows: Iterable[dict[str, Any]],
    *,
    conn: sqlite3.Connection | None = None,
    ensure_schema: bool = True,
    commit: bool = True,
) -> None:
    """Append multiple rows to ``tension_data`` efficiently."""

    _append_rows(
        file_path,
        TABLE_TENSION_DATA,
        rows,
        conn=conn,
        ensure_schema=ensure_schema,
        commit=commit,
    )


def get_results_dataframe(file_path: str) -> pd.DataFrame:
    """Return raw samples from ``tension_samples``.

    For backward compatibility with older databases, this falls back to
    ``tension_data`` when ``tension_samples`` is empty.
    """

    samples = _get_table_dataframe(file_path, TABLE_TENSION_SAMPLES)
    if not samples.empty:
        return samples

    # Backward-compatibility path for historical DBs that stored samples in
    # tension_data only.
    return _get_table_dataframe(file_path, TABLE_TENSION_DATA)


def select_results_dataframe(
    file_path: str,
    *,
    where_clause: str = "",
    params: Iterable[Any] = (),
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return selected ``tension_samples`` rows without caching the full table."""

    return _select_table_dataframe(
        file_path,
        TABLE_TENSION_SAMPLES,
        where_clause=where_clause,
        params=params,
        columns=columns,
    )


def update_results_dataframe(file_path: str, df: pd.DataFrame) -> None:
    """Replace ``tension_samples`` with ``df`` and refresh cache."""

    normalized_df = _normalize_dataframe_columns(df)
    key = _cache_key(file_path, TABLE_TENSION_SAMPLES)
    _dataframe_cache[key] = normalized_df.copy()
    with connect_write_database(file_path) as conn:
        _ensure_tables(conn)
        normalized_df.to_sql(
            TABLE_TENSION_SAMPLES, conn, if_exists="replace", index=False
        )


def append_results_row(file_path: str, row: dict[str, Any]) -> None:
    """Append one row to ``tension_samples`` without rewriting the full table."""

    _append_row(file_path, TABLE_TENSION_SAMPLES, row)


def append_results_rows(
    file_path: str,
    rows: Iterable[dict[str, Any]],
    *,
    conn: sqlite3.Connection | None = None,
    ensure_schema: bool = True,
    commit: bool = True,
) -> None:
    """Append multiple rows to ``tension_samples`` efficiently."""

    _append_rows(
        file_path,
        TABLE_TENSION_SAMPLES,
        rows,
        conn=conn,
        ensure_schema=ensure_schema,
        commit=commit,
    )


def _drop_wire_numbers(
    df: pd.DataFrame,
    apa_name: str,
    layer: str,
    side: str,
    wire_numbers: Iterable[int],
) -> pd.DataFrame:
    """Return ``df`` with the selected wires removed for one APA/layer/side."""

    numbers = {int(wire) for wire in wire_numbers}
    if df.empty or not numbers:
        return df.reset_index(drop=True)

    wire_series = pd.to_numeric(df["wire_number"], errors="coerce")
    mask = ~(
        (df["apa_name"] == apa_name)
        & (df["layer"] == layer)
        & (df["side"] == side)
        & wire_series.isin(numbers)
    )
    return df[mask].reset_index(drop=True)


def clear_wire_numbers(
    file_path: str,
    apa_name: str,
    layer: str,
    side: str,
    wire_numbers: Iterable[int],
) -> None:
    """Remove all rows matching ``wire_numbers`` from both DB tables."""

    numbers = sorted({int(wire) for wire in wire_numbers})
    if not numbers:
        return

    df = get_dataframe(file_path)
    update_dataframe(file_path, _drop_wire_numbers(df, apa_name, layer, side, numbers))

    samples_df = _get_table_dataframe(file_path, TABLE_TENSION_SAMPLES)
    update_results_dataframe(
        file_path,
        _drop_wire_numbers(samples_df, apa_name, layer, side, numbers),
    )


def clear_wire_range(
    file_path: str,
    apa_name: str,
    layer: str,
    side: str,
    start: int,
    end: int,
) -> None:
    """Remove all rows matching the given wire range from both DB tables."""

    clear_wire_numbers(file_path, apa_name, layer, side, range(start, end + 1))


def latest_plausible_per_wire(subset: pd.DataFrame) -> pd.DataFrame:
    """Collapse measurements to the final tension reported for each wire.

    ``subset`` must already be filtered to a single apa/layer/side. Returns the
    latest plausible measurement per wire, sorted by wire number — the same
    selection used for the summary CSVs and plots (see
    ``summaries._select_summary_rows``).

    Outlier detection runs on this collapsed series rather than on every raw
    measurement row; otherwise wires measured many times contribute many rows and
    distort the per-wire statistics (e.g. a single wire's repeats can fill an
    entire rolling-average window, masking real outliers and flagging innocent
    neighbours).
    """

    subset = subset.copy()
    subset["wire_number"] = pd.to_numeric(subset["wire_number"], errors="coerce")
    subset["tension"] = pd.to_numeric(subset["tension"], errors="coerce")
    subset["time"] = pd.to_datetime(subset["time"], errors="coerce")
    subset = subset.dropna(subset=["wire_number", "tension"])
    if subset.empty:
        return subset

    subset["wire_number"] = subset["wire_number"].astype(int)
    subset = subset[subset["tension"].apply(tension_plausible)]
    if subset.empty:
        return subset

    return (
        subset.sort_values("time")
        .drop_duplicates(subset="wire_number", keep="last")
        .sort_values("wire_number")
        .reset_index(drop=True)
    )


def moving_average_residuals(tension: pd.Series) -> pd.Series:
    """Return tension residuals against a centred moving average.

    ``tension`` must be ordered by wire number (one value per wire). The moving
    average is held flat past the first and last fully-populated window so edge
    wires still receive a residual. This is the exact series shown as
    "Residuals from Moving Average" / the residual histogram in the GUI summary
    plot, and the basis for residual-outlier detection — the two must agree, so
    they share this function.

    The result is index-aligned to ``tension`` and computed positionally, so it
    is correct regardless of how ``tension`` is indexed.
    """

    rolling_mean = tension.rolling(window=20, center=True, min_periods=20).mean()
    valid = rolling_mean.notna().to_numpy()
    if valid.any():
        first = int(valid.argmax())
        last = len(valid) - 1 - int(valid[::-1].argmax())
        filled = rolling_mean.to_numpy(dtype=float).copy()
        filled[:first] = filled[first]
        filled[last + 1 :] = filled[last]
        rolling_mean = pd.Series(filled, index=tension.index)
    return tension - rolling_mean


def _select_side_measurements(
    file_path: str,
    apa_name: str,
    layer: str,
    side: str,
) -> pd.DataFrame:
    """Return the final per-wire tensions for one apa/layer/side.

    Collapses to the latest plausible measurement per wire — the exact selection
    behind the summary CSV and the GUI residual plot. Confidence is deliberately
    *not* filtered here: the summary/plots ignore it, so applying a confidence
    gate would make outlier detection disagree with the residual plot the user is
    looking at.
    """

    df = get_dataframe(file_path)
    mask = (
        (df["apa_name"] == apa_name)
        & (df["layer"] == layer)
        & (df["side"] == side)
    )
    return latest_plausible_per_wire(df[mask])


def find_outliers(
    file_path: str,
    apa_name: str,
    layer: str,
    side: str,
    times_sigma: float = 2.5,
) -> list[int]:
    """Find wire numbers whose tension residual exceeds ``times_sigma`` std.

    The residual is measured against a moving average of the *final* per-wire
    tensions (the values written to the summary and plots), not the individual
    repeated measurements that produced them.

    Wires are returned ordered worst-first — by descending residual magnitude
    (distance from the moving average) — so callers can remeasure the most
    egregious outliers first.
    """

    subset = _select_side_measurements(file_path, apa_name, layer, side)
    if subset.empty:
        return []

    residuals = moving_average_residuals(subset["tension"])
    resid_std = residuals.std(skipna=True)

    if pd.isna(resid_std) or resid_std == 0:
        return []

    abs_residuals = residuals.abs()
    is_outlier = abs_residuals > times_sigma * resid_std
    ordered = (
        subset.loc[is_outlier]
        .assign(_abs_residual=abs_residuals[is_outlier])
        .sort_values("_abs_residual", ascending=False, kind="stable")
    )
    return ordered["wire_number"].astype(int).tolist()


def find_distribution_outliers(
    file_path: str,
    apa_name: str,
    layer: str,
    side: str,
    times_sigma: float = 2.5,
) -> list[int]:
    """Find wires whose tension lies far from the bulk tension distribution.

    Operates on the *final* per-wire tensions (the values written to the summary
    and plots), not the individual repeated measurements that produced them.

    Wires are returned ordered worst-first — by descending distance from the
    mean tension — so callers can remeasure the most egregious outliers first.
    """

    subset = _select_side_measurements(file_path, apa_name, layer, side)
    if subset.empty:
        return []

    tension_mean = subset["tension"].mean(skipna=True)
    tension_std = subset["tension"].std(skipna=True)
    if pd.isna(tension_mean) or pd.isna(tension_std) or tension_std == 0:
        return []

    deviation = (subset["tension"] - tension_mean).abs()
    is_outlier = deviation > times_sigma * tension_std
    ordered = (
        subset.loc[is_outlier]
        .assign(_deviation=deviation[is_outlier])
        .sort_values("_deviation", ascending=False, kind="stable")
    )
    return ordered["wire_number"].astype(int).tolist()
