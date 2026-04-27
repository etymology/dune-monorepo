"""Plot the latest tension measurement per wire from the SQLite export."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import matplotlib
import pandas as pd

from dune_tension.paths import data_path
from dune_tension.tension_calculation import tension_plausible


DEFAULT_LAYER = "X"
DEFAULT_DB_PATH = data_path(
    "tension_data",
    "dunedb_all_locations_all_apas_tension_data.sqlite",
)
DEFAULT_OUTPUT_DIR = data_path("tension_plots")

matplotlib.use("Agg", force=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to the SQLite database exported by dune-tension-download-m2m.",
    )
    parser.add_argument(
        "--apa-name",
        help=(
            "APA name to plot. If omitted, the newest APA with data for the selected "
            "layer is used."
        ),
    )
    parser.add_argument(
        "--layer",
        default=DEFAULT_LAYER,
        choices=["X", "U", "V", "G"],
        help="APA layer to plot (default: X).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for the generated PNG file.",
    )
    return parser.parse_args()


def get_expected_range(layer: str) -> range:
    ranges = {
        "U": range(8, 1147),
        "V": range(8, 1147),
        "X": range(1, 481),
        "G": range(1, 482),
    }
    return ranges.get(layer.upper(), range(0))


def _parse_action_time(action_json: str) -> pd.Timestamp:
    try:
        payload = json.loads(action_json)
    except json.JSONDecodeError:
        return pd.NaT

    insert_date = ((payload or {}).get("insertion") or {}).get("insertDate")
    if not insert_date:
        return pd.NaT
    return pd.to_datetime(insert_date, errors="coerce")


def _load_action_rows(
    conn: sqlite3.Connection,
    *,
    layer: str,
    apa_name: str | None = None,
) -> pd.DataFrame:
    params: list[Any] = [layer.lower()]
    sql = """
        SELECT
            a.apa_name,
            a.layer,
            a.action_id,
            a.action_version,
            a.action_json,
            m.side,
            m.wire_index,
            m.tension
        FROM tension_actions a
        JOIN tension_measurements m ON m.action_id = a.action_id
        WHERE a.layer = ?
    """
    if apa_name:
        sql += " AND a.apa_name = ?"
        params.append(apa_name)

    df = pd.read_sql_query(sql, conn, params=params)
    if df.empty:
        return df

    df["action_time"] = df["action_json"].map(_parse_action_time)
    df["side"] = df["side"].astype(str).str.upper()
    df["wire_number"] = pd.to_numeric(df["wire_index"], errors="coerce")
    df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
    df = df.dropna(subset=["wire_number", "tension"])
    df["wire_number"] = df["wire_number"].astype(int)
    return df


def _resolve_default_apa_name(conn: sqlite3.Connection, layer: str) -> str:
    df = pd.read_sql_query(
        """
        SELECT apa_name, action_json
        FROM tension_actions
        WHERE layer = ?
        """,
        conn,
        params=[layer.lower()],
    )
    if df.empty:
        raise RuntimeError(f"No tension actions found for layer {layer}")

    df["action_time"] = df["action_json"].map(_parse_action_time)
    df = df.sort_values(["action_time", "apa_name"]).dropna(subset=["apa_name"])
    if df.empty:
        raise RuntimeError(f"Could not resolve a default APA name for layer {layer}")
    return str(df.iloc[-1]["apa_name"])


def _select_latest_per_wire(
    df: pd.DataFrame, layer: str
) -> tuple[list[pd.DataFrame], str]:
    expected_wires = set(get_expected_range(layer))
    line_data: list[pd.DataFrame] = []
    apa_name = str(df["apa_name"].iloc[0]) if not df.empty else ""

    for side in ("A", "B"):
        side_df = df[df["side"] == side].copy()
        if side_df.empty:
            continue

        side_df = side_df[side_df["wire_number"].isin(expected_wires)]
        side_df = side_df[
            side_df["tension"].apply(lambda value: tension_plausible(float(value)))
        ]
        if side_df.empty:
            continue

        side_df = side_df.sort_values(["action_time", "action_version", "action_id"])
        side_df = side_df.drop_duplicates(
            subset="wire_number", keep="last"
        ).sort_values("wire_number")
        if side_df.empty:
            continue

        line_data.append(
            side_df[["wire_number", "tension"]].assign(side_label=f"Side {side}")
        )

    if not apa_name and not df.empty:
        apa_name = str(df["apa_name"].iloc[0])

    return line_data, apa_name


def _build_figure(
    line_data: list[pd.DataFrame],
    histogram_data: list[pd.DataFrame],
    apa_name: str,
    layer: str,
):
    import matplotlib.pyplot as plt

    figure, (scatter_axis, hist_axis) = plt.subplots(1, 2, figsize=(15, 6))
    colors = {"Side A": "tab:blue", "Side B": "tab:orange"}

    for frame in line_data:
        if frame.empty:
            continue
        side_label = str(frame["side_label"].iloc[0])
        color = colors.get(side_label, "tab:blue")
        scatter_axis.scatter(
            frame["wire_number"],
            frame["tension"],
            s=10,
            alpha=0.5,
            color=color,
            label=side_label,
        )
        sorted_frame = frame.sort_values("wire_number")
        moving_average = sorted_frame["tension"].rolling(window=15, center=True).mean()
        scatter_axis.plot(
            sorted_frame["wire_number"],
            moving_average,
            linewidth=2.0,
            alpha=0.8,
            color=color,
        )

    scatter_axis.set_title(f"{apa_name} - Latest Tension Scatter - Layer {layer}")
    scatter_axis.set_xlabel("Wire Number")
    scatter_axis.set_ylabel("Tension")
    scatter_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
    scatter_axis.legend(fontsize=8, loc="upper right")

    stats_lines: list[str] = []
    for frame in histogram_data:
        if frame.empty:
            continue
        side_label = str(frame["side_label"].iloc[0])
        color = colors.get(side_label, "tab:blue")
        values = pd.to_numeric(frame["tension"], errors="coerce").dropna().to_numpy()
        if values.size == 0:
            continue
        hist_axis.hist(values, bins=40, histtype="step", linewidth=1.6, color=color)
        stats_lines.append(
            f"{side_label}: μ={float(values.mean()):.3f}, σ={float(values.std(ddof=0)):.3f}, n={int(values.size)}"
        )

    hist_axis.set_title(f"{apa_name} - Latest Tension Distribution - Layer {layer}")
    hist_axis.set_xlabel("Tension")
    hist_axis.set_ylabel("Count")
    hist_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")

    if stats_lines:
        hist_axis.text(
            0.98,
            0.97,
            "\n".join(stats_lines),
            transform=hist_axis.transAxes,
            fontsize=8,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

    figure.tight_layout()
    return figure


def plot_from_sqlite(
    db_path: Path,
    output_dir: Path,
    *,
    apa_name: str | None = None,
    layer: str = DEFAULT_LAYER,
) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    with sqlite3.connect(db_path) as conn:
        resolved_apa = apa_name or _resolve_default_apa_name(conn, layer)
        df = _load_action_rows(conn, layer=layer, apa_name=resolved_apa)

    if df.empty:
        raise RuntimeError(
            f"No tension measurements found for APA {resolved_apa!r} layer {layer}"
        )

    line_data, apa_name_for_plot = _select_latest_per_wire(df, layer)
    if not line_data:
        raise RuntimeError(
            f"No plausible latest measurements found for APA {apa_name_for_plot!r} layer {layer}"
        )

    histogram_data = [
        frame[["tension"]].assign(side_label=frame["side_label"].iloc[0])
        for frame in line_data
    ]

    figure = _build_figure(
        line_data,
        histogram_data,
        apa_name_for_plot,
        layer,
    )
    if figure is None:
        raise RuntimeError("Failed to build a tension plot figure")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"tension_plot_{apa_name_for_plot}_{layer}.png"
    figure.savefig(output_path, dpi=300)
    return output_path


def main() -> None:
    args = _parse_args()
    output_path = plot_from_sqlite(
        args.db_path,
        args.output_dir,
        apa_name=args.apa_name,
        layer=args.layer,
    )
    print(f"Wrote {output_path}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
