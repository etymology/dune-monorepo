from __future__ import annotations

import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, Iterator, Mapping, Iterable

from dune_tension.results import TensionResult, EXPECTED_COLUMNS
import dune_tension.data_cache as data_cache


@dataclass
class ExperimentMetadata:
    experiment_id: str
    experiment_name: str
    experiment_type: str  # e.g. "single_wire_single_zone", "single_wire_multi_zone"
    known_tension: float | None = None
    measurement_position_x: float | None = None
    measurement_position_y: float | None = None
    zone: int | None = None
    capos_on_combs: str | None = (
        None  # Comma separated list of comb indices, e.g. "1,2"
    )
    capo_left: bool = False
    capo_right: bool = False
    raw_audio_path: str | None = None
    notes: str | None = None
    sample_index: int = 0


EXPERIMENT_COLUMNS = [f.name for f in fields(ExperimentMetadata)]
ALL_EXPERIMENT_COLUMNS = list(dict.fromkeys(EXPECTED_COLUMNS + EXPERIMENT_COLUMNS))


def _ensure_experiment_tables(conn: sqlite3.Connection) -> None:
    # We use the same table names but in a different DB file
    # and with more columns.
    for table in [data_cache.TABLE_TENSION_DATA, data_cache.TABLE_TENSION_SAMPLES]:
        if not data_cache._table_exists(conn, table):
            cols_sql = ", ".join(f"{col} TEXT" for col in ALL_EXPERIMENT_COLUMNS)
            conn.execute(f"CREATE TABLE {table} ({cols_sql})")
        else:
            existing_columns = set(data_cache._get_table_columns(conn, table))
            for col in ALL_EXPERIMENT_COLUMNS:
                if col not in existing_columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
    conn.commit()


class ExperimentResultRepository:
    """Repository for persisting experimental tension results with metadata."""

    def __init__(
        self, data_path: str, metadata: ExperimentMetadata, sample_batch_size: int = 25
    ) -> None:
        self.data_path = data_path
        self.metadata = metadata
        self.sample_batch_size = max(1, int(sample_batch_size))
        self._conn: sqlite3.Connection | None = None
        self._scope_depth = 0
        self._schema_ready = False
        self._sample_buffer: list[dict[str, Any]] = []

    def _row_for(self, result: TensionResult) -> dict[str, Any]:
        row = {col: getattr(result, col, None) for col in EXPECTED_COLUMNS}
        for col in EXPERIMENT_COLUMNS:
            row[col] = getattr(self.metadata, col, None)
        return row

    def _ensure_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = data_cache.connect_write_database(self.data_path)
            self._schema_ready = False
        if not self._schema_ready:
            _ensure_experiment_tables(self._conn)
            self._schema_ready = True
        return self._conn

    def run_scope(self) -> Iterator["ExperimentResultRepository"]:
        # Mocking contextmanager behavior for simplicity in this bridge
        from contextlib import contextmanager

        @contextmanager
        def _scope():
            self._scope_depth += 1
            if self._scope_depth == 1:
                self._ensure_connection()
            try:
                yield self
            finally:
                self._scope_depth -= 1
                if self._scope_depth == 0:
                    self.close()

        return _scope()

    def _flush_samples(self, *, commit: bool) -> None:
        if not self._sample_buffer:
            return

        rows = self._sample_buffer
        self._sample_buffer = []

        normalized_rows = [self._normalize_row(row) for row in rows]

        columns = ", ".join(ALL_EXPERIMENT_COLUMNS)
        placeholders = ", ".join("?" for _ in ALL_EXPERIMENT_COLUMNS)
        values = [
            tuple(normalized[col] for col in ALL_EXPERIMENT_COLUMNS)
            for normalized in normalized_rows
        ]

        conn = self._ensure_connection()
        conn.executemany(
            f"INSERT INTO {data_cache.TABLE_TENSION_SAMPLES} ({columns}) VALUES ({placeholders})",
            values,
        )
        if commit:
            conn.commit()

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for col in ALL_EXPERIMENT_COLUMNS:
            value = row.get(col)
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, list):
                value = str(value)
            normalized[col] = value
        return normalized

    def append_sample(self, result: TensionResult) -> None:
        self.metadata.sample_index += 1
        row = self._row_for(result)
        if self._scope_depth > 0:
            self._sample_buffer.append(row)
            if len(self._sample_buffer) >= self.sample_batch_size:
                self._flush_samples(commit=False)
            return

        normalized = self._normalize_row(row)
        columns = ", ".join(ALL_EXPERIMENT_COLUMNS)
        placeholders = ", ".join("?" for _ in ALL_EXPERIMENT_COLUMNS)
        val = tuple(normalized[col] for col in ALL_EXPERIMENT_COLUMNS)

        conn = self._ensure_connection()
        conn.execute(
            f"INSERT INTO {data_cache.TABLE_TENSION_SAMPLES} ({columns}) VALUES ({placeholders})",
            val,
        )
        conn.commit()

    def append_result(self, result: TensionResult) -> None:
        # For experiments we often want all samples, but we can also store the "best" one in tension_data
        row = self._row_for(result)
        normalized = self._normalize_row(row)
        columns = ", ".join(ALL_EXPERIMENT_COLUMNS)
        placeholders = ", ".join("?" for _ in ALL_EXPERIMENT_COLUMNS)
        val = tuple(normalized[col] for col in ALL_EXPERIMENT_COLUMNS)

        conn = self._ensure_connection()
        conn.execute(
            f"INSERT INTO {data_cache.TABLE_TENSION_DATA} ({columns}) VALUES ({placeholders})",
            val,
        )
        conn.commit()

    def close(self) -> None:
        try:
            if self._conn is not None:
                self._flush_samples(commit=False)
                self._conn.commit()
        finally:
            if self._conn is not None:
                self._conn.close()
            self._conn = None
            self._schema_ready = False
            self._sample_buffer = []
