"""Download DUNE APA tension data into a SQLite database.

This uses the existing M2M client in :mod:`dune_tension.m2m.common` to
enumerate all assembled APAs and all tension actions, then stores both the
action-level records and the per-wire measurements in SQLite.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dune_tension.m2m.common import (
    ConnectToAPI,
    GetAction,
    GetComponent,
    GetListOfActions,
    GetListOfComponents,
)
from dune_tension.paths import data_path


LAYERS = ("x", "u", "v", "g")
TENSION_ACTION_TYPE = "x_tension_testing"
APA_COMPONENT_TYPE = "AssembledAPA"


@dataclass(frozen=True)
class WireRow:
    apa_uuid: str
    apa_name: str
    layer: str
    action_id: str
    action_version: int
    side: str
    wire_index: int
    tension: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=data_path(
            "tension_data",
            "dunedb_all_locations_all_apas_tension_data.sqlite",
        ),
        help="Path to the SQLite database to create or replace.",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Keep zero-valued wire rows instead of dropping them.",
    )
    return parser.parse_args()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return list(value)


def _normalize_layer(value: Any) -> str:
    return str(value or "").strip().lower()


def _extract_wire_rows(
    action: dict[str, Any], apa_uuid: str, apa_name: str
) -> list[WireRow]:
    data = action.get("data") or {}
    layer = _normalize_layer(data.get("apaLayer"))
    action_id = str(action.get("actionId") or "")
    action_version = int((action.get("validity") or {}).get("version") or 0)

    rows: list[WireRow] = []
    for side_key, side_name in (
        ("measuredTensions_sideA", "a"),
        ("measuredTensions_sideB", "b"),
    ):
        tensions = _as_list(data.get(side_key))
        for index, tension in enumerate(tensions, start=1):
            try:
                tension_value = float(tension)
            except (TypeError, ValueError):
                continue
            rows.append(
                WireRow(
                    apa_uuid=apa_uuid,
                    apa_name=apa_name,
                    layer=layer,
                    action_id=action_id,
                    action_version=action_version,
                    side=side_name,
                    wire_index=index,
                    tension=tension_value,
                )
            )

    return rows


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(
        """
      DROP TABLE IF EXISTS tension_measurements;
      DROP TABLE IF EXISTS tension_actions;
      DROP TABLE IF EXISTS tension_apas;

      CREATE TABLE tension_apas (
        apa_uuid TEXT PRIMARY KEY,
        apa_name TEXT NOT NULL,
        short_uuid TEXT,
        component_json TEXT NOT NULL
      );

      CREATE TABLE tension_actions (
        action_id TEXT PRIMARY KEY,
        apa_uuid TEXT NOT NULL,
        apa_name TEXT NOT NULL,
        layer TEXT NOT NULL,
        action_version INTEGER NOT NULL,
        action_json TEXT NOT NULL,
        FOREIGN KEY (apa_uuid) REFERENCES tension_apas(apa_uuid)
      );

      CREATE TABLE tension_measurements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_id TEXT NOT NULL,
        apa_uuid TEXT NOT NULL,
        apa_name TEXT NOT NULL,
        layer TEXT NOT NULL,
        action_version INTEGER NOT NULL,
        side TEXT NOT NULL,
        wire_index INTEGER NOT NULL,
        tension REAL NOT NULL,
        FOREIGN KEY (action_id) REFERENCES tension_actions(action_id),
        FOREIGN KEY (apa_uuid) REFERENCES tension_apas(apa_uuid)
      );

      CREATE INDEX idx_tension_measurements_apa_layer ON tension_measurements(apa_name, layer);
      CREATE INDEX idx_tension_measurements_action ON tension_measurements(action_id);
      """
    )


def _insert_apa(conn: sqlite3.Connection, apa: dict[str, Any]) -> tuple[str, str]:
    apa_uuid = str(apa.get("componentUuid") or "")
    apa_name = str(
        (apa.get("data") or {}).get("componentName")
        or apa.get("componentName")
        or apa_uuid
    )
    conn.execute(
        """
      INSERT OR REPLACE INTO tension_apas (apa_uuid, apa_name, short_uuid, component_json)
      VALUES (?, ?, ?, ?)
      """,
        (
            apa_uuid,
            apa_name,
            apa.get("shortUuid"),
            json.dumps(apa, default=str),
        ),
    )
    return apa_uuid, apa_name


def download(output_path: Path, include_empty: bool = False) -> dict[str, int]:
    connection, headers = ConnectToAPI()
    try:
        apa_uuids = [
            apa
            for apa in GetListOfComponents(APA_COMPONENT_TYPE, connection, headers)
            if apa
        ]
        tension_action_ids = [
            action_id
            for action_id in GetListOfActions(TENSION_ACTION_TYPE, connection, headers)
            if action_id
        ]
        tension_actions_by_apa: dict[str, list[dict[str, Any]]] = {}
        for action_id in tension_action_ids:
            action = GetAction(action_id, connection, headers)
            if not action:
                continue

            action_data = action.get("data") or {}
            if _normalize_layer(action_data.get("apaLayer")) not in LAYERS:
                continue

            component_uuid = str(action.get("componentUuid") or "")
            tension_actions_by_apa.setdefault(component_uuid, []).append(action)

        with sqlite3.connect(output_path) as conn:
            _init_db(conn)
            counts = {"apas": 0, "actions": 0, "measurements": 0}

            for apa_uuid in apa_uuids:
                apa = GetComponent(apa_uuid, connection, headers)
                if not apa:
                    continue

                apa_uuid, apa_name = _insert_apa(conn, apa)
                counts["apas"] += 1

                for action in tension_actions_by_apa.get(apa_uuid, []):
                    action_data = action.get("data") or {}
                    action_row = (
                        str(action.get("actionId") or ""),
                        apa_uuid,
                        apa_name,
                        _normalize_layer(action_data.get("apaLayer")),
                        int((action.get("validity") or {}).get("version") or 0),
                        json.dumps(action, default=str),
                    )
                    conn.execute(
                        """
              INSERT OR REPLACE INTO tension_actions
              (action_id, apa_uuid, apa_name, layer, action_version, action_json)
              VALUES (?, ?, ?, ?, ?, ?)
              """,
                        action_row,
                    )
                    counts["actions"] += 1

                    rows = _extract_wire_rows(action, apa_uuid, apa_name)
                    if not include_empty:
                        rows = [row for row in rows if row.tension != 0.0]

                    conn.executemany(
                        """
              INSERT INTO tension_measurements
              (action_id, apa_uuid, apa_name, layer, action_version, side, wire_index, tension)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)
              """,
                        [
                            (
                                row.action_id,
                                row.apa_uuid,
                                row.apa_name,
                                row.layer,
                                row.action_version,
                                row.side,
                                row.wire_index,
                                row.tension,
                            )
                            for row in rows
                        ],
                    )
                    counts["measurements"] += len(rows)

            conn.commit()
            return counts
    finally:
        connection.close()


def main() -> None:
    args = _parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stats = download(args.output, include_empty=args.include_empty)
    print(
        "Downloaded "
        f"{stats['apas']} APAs, {stats['actions']} tension actions, "
        f"{stats['measurements']} wire measurements into {args.output}"
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
