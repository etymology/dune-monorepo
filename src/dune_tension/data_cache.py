from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from dune_tension.results import EXPECTED_COLUMNS
from dune_tension.tension_calculation import tension_plausible

TABLE_TENSION_DATA = "tension_data"
TABLE_TENSION_SAMPLES = "tension_samples"


@dataclass
class _CachedTable:
    """A materialised table plus the sqlite state it was read from.

    ``row_count`` and ``max_rowid`` let a read tell a plain append apart from a
    rewrite, so appends can be folded into ``frame`` instead of forcing the
    whole table to be read again. ``anchor_row`` is the row that sat at
    ``max_rowid``: sqlite reuses a freed maximum rowid, so deleting the last row
    and inserting another leaves the count and the rowid range unchanged, and
    only the row contents give it away.
    """

    frame: pd.DataFrame
    row_count: int
    max_rowid: int
    anchor_row: tuple[Any, ...] | None


# In-process DataFrame cache.
_dataframe_cache: dict[str, _CachedTable] = {}


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


def _table_state(
    conn: sqlite3.Connection, table: str
) -> tuple[int, int, tuple[Any, ...] | None]:
    """Return ``(row_count, max_rowid, anchor_row)`` for ``table``."""

    row = conn.execute(
        f"SELECT COUNT(*), COALESCE(MAX(rowid), 0) FROM {table}"
    ).fetchone()
    row_count, max_rowid = int(row[0]), int(row[1])
    anchor_row = None
    if row_count:
        anchor = conn.execute(
            f"SELECT * FROM {table} WHERE rowid = ?", (max_rowid,)
        ).fetchone()
        anchor_row = tuple(anchor) if anchor is not None else None
    return row_count, max_rowid, anchor_row


def _store_cached_table(
    file_path: str, table: str, frame: pd.DataFrame, conn: sqlite3.Connection
) -> None:
    row_count, max_rowid, anchor_row = _table_state(conn, table)
    _dataframe_cache[_cache_key(file_path, table)] = _CachedTable(
        frame, row_count, max_rowid, anchor_row
    )


def _refresh_cached_table(
    conn: sqlite3.Connection, table: str, cached: _CachedTable
) -> _CachedTable | None:
    """Bring ``cached`` up to date cheaply, or return None to force a re-read.

    Appending is the only mutation that leaves the cache behind -- every other
    writer replaces the cached frame outright -- so the usual case is that rows
    were added at the end. Those rows are read back out of sqlite rather than
    reconstructed from the values that were inserted, which keeps column
    affinity and dtype inference identical to a full re-read.

    Anything that is not a clean append (deletions, a replaced table, a row
    count that disagrees with the rowid range, a rewritten anchor row) returns
    None so the caller falls back to reading the whole table.
    """

    if not _table_exists(conn, table):
        return None

    row_count, max_rowid, anchor_row = _table_state(conn, table)
    if row_count == cached.row_count and max_rowid == cached.max_rowid:
        # Same shape, but the anchor catches a freed-and-reused maximum rowid.
        return cached if anchor_row == cached.anchor_row else None
    if row_count < cached.row_count or max_rowid < cached.max_rowid:
        return None

    previous_anchor = conn.execute(
        f"SELECT * FROM {table} WHERE rowid = ?", (cached.max_rowid,)
    ).fetchone()
    if cached.anchor_row is not None and (
        previous_anchor is None or tuple(previous_anchor) != cached.anchor_row
    ):
        return None

    appended = pd.read_sql_query(
        f"SELECT * FROM {table} WHERE rowid > ?",
        conn,
        params=(cached.max_rowid,),
    )
    if len(appended) != row_count - cached.row_count:
        return None

    normalized = _normalize_dataframe_columns(appended)
    # Reading a couple of rows can infer different column types than reading
    # the whole table does -- an all-NULL column in one new row comes back as
    # object where the full table reads as str -- so line the new rows up with
    # the cached frame before concatenating.
    try:
        normalized = normalized.astype(cached.frame.dtypes.to_dict())
    except (TypeError, ValueError):
        return None

    frame = pd.concat([cached.frame, normalized], ignore_index=True)
    if list(frame.dtypes) != list(cached.frame.dtypes):
        # Reading the whole table would have inferred different column types;
        # don't let the incremental path drift away from that.
        return None
    return _CachedTable(frame, row_count, max_rowid, anchor_row)


def connect_write_database(file_path: str) -> sqlite3.Connection:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def ensure_tables(conn: sqlite3.Connection) -> None:
    _ensure_tables(conn)


def _get_table_dataframe(file_path: str, table: str) -> pd.DataFrame:
    key = _cache_key(file_path, table)

    if not Path(file_path).exists():
        df = pd.DataFrame(columns=EXPECTED_COLUMNS)
        _dataframe_cache[key] = _CachedTable(df, 0, 0, None)
        return df

    cached = _dataframe_cache.get(key)
    with sqlite3.connect(file_path) as conn:
        _ensure_tables(conn)
        if cached is not None:
            refreshed = _refresh_cached_table(conn, table, cached)
            if refreshed is not None:
                _dataframe_cache[key] = refreshed
                return refreshed.frame

        # Take the frame and the state it corresponds to from one read
        # snapshot, so a concurrent writer cannot leave them disagreeing.
        conn.execute("BEGIN")
        try:
            df = _read_table(conn, table)
            state = (
                _table_state(conn, table)
                if _table_exists(conn, table)
                else (0, 0, None)
            )
        finally:
            conn.rollback()
    _dataframe_cache[key] = _CachedTable(df, *state)
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

    # Deliberately leave the cache in place: _get_table_dataframe notices the
    # new rows and folds them in, which is what avoids rebuilding the whole
    # table once per appended measurement.


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
    with connect_write_database(file_path) as conn:
        _ensure_tables(conn)
        normalized_df.to_sql(TABLE_TENSION_DATA, conn, if_exists="replace", index=False)
        _store_cached_table(file_path, TABLE_TENSION_DATA, normalized_df.copy(), conn)


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
    with connect_write_database(file_path) as conn:
        _ensure_tables(conn)
        normalized_df.to_sql(
            TABLE_TENSION_SAMPLES, conn, if_exists="replace", index=False
        )
        _store_cached_table(
            file_path, TABLE_TENSION_SAMPLES, normalized_df.copy(), conn
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
    mask = (df["apa_name"] == apa_name) & (df["layer"] == layer) & (df["side"] == side)
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


def find_low_confidence_wires(
    file_path: str,
    apa_name: str,
    layer: str,
    side: str,
    confidence_threshold: float,
) -> list[int]:
    """Find wires whose final-measurement confidence is below the threshold.

    Operates on the *final* per-wire measurement — the latest plausible row,
    which is the value (and confidence) written to the summary and plots — not
    the individual repeated measurements that produced it. A missing/NaN
    confidence is treated as low so the wire is remeasured.

    Wires are returned ordered lowest-confidence-first so callers can remeasure
    the least trustworthy wires first.
    """

    subset = _select_side_measurements(file_path, apa_name, layer, side)
    if subset.empty or "confidence" not in subset.columns:
        return []

    confidence = pd.to_numeric(subset["confidence"], errors="coerce")
    is_low = confidence.isna() | (confidence < confidence_threshold)
    if not is_low.any():
        return []

    ordered = (
        subset.loc[is_low]
        # NaN sorts first (treated as the lowest possible confidence).
        .assign(_confidence=confidence[is_low].fillna(float("-inf")))
        .sort_values("_confidence", ascending=True, kind="stable")
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
