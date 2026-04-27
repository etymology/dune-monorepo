from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
from pandas.errors import ParserError
from scipy.ndimage import gaussian_filter1d
from scipy.stats import gaussian_kde, pearsonr, spearmanr

from dune_tension.data_cache import select_dataframe
from dune_tension.paths import data_path, tension_data_db_path
from dune_tension.uv_wire_recipe_map import build_uv_wire_recipe_maps


# Trim all tension values outside this band.
# This replaces the broader "plausible" filter for this analysis.
MIN_PLAUSIBLE_TENSION = 2
MAX_PLAUSIBLE_TENSION = 10
OLD_CSV_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"
SIDES = ("A", "B")
LEGACY_SOURCE = "legacy"
DUNEDB_SOURCE = "dunedb"
DUNEDB_LOCATIONS = ("chicago", "daresbury")
DEFAULT_DUNEDB_SQLITE = data_path(
    "tension_data",
    "dunedb_all_locations_all_apas_tension_data.sqlite",
)
PLOT_MODE_WIRE_NUMBER = "wire_number"
PLOT_MODE_WRAP_NUMBER = "wrap_number"
PLOT_MODE_APPLIED_LENGTH = "applied_length_mm"
PLOT_MODE_ENDPOINT_MAPPING = "endpoint_side_mapping"
PLOT_MODE_ENDPOINT_CATEGORIES = "endpoint_categories"
PLOT_MODE_LABELS = {
    PLOT_MODE_WIRE_NUMBER: "Wire Number",
    PLOT_MODE_WRAP_NUMBER: "Wrap Number",
    PLOT_MODE_APPLIED_LENGTH: "Applied Length (mm)",
    PLOT_MODE_ENDPOINT_MAPPING: "Endpoint Side Mapping",
    PLOT_MODE_ENDPOINT_CATEGORIES: "Endpoint Categories",
}
UV_METADATA_COLUMNS = (
    "wrap_number",
    "applied_length_mm",
    "start_side",
    "end_side",
    "endpoint_side_mapping",
    "start_endpoint_kind",
    "end_endpoint_kind",
    "uv_path_family",
    "uv_terminal_group",
)


def _should_reverse_dunedb_wire_order(
    *, db_path: str, layer: str, side: str, location: str | None
) -> bool:
    db_name = Path(db_path).name
    return (
        db_name == "dunedb_all_locations_all_apas_tension_data.sqlite"
        and str(location).strip().lower() == "chicago"
        and side.upper() == "B"
        and layer.upper() in {"X", "G"}
    )


def expected_wire_range(layer: str) -> range:
    ranges = {
        "U": range(8, 1147),
        "V": range(8, 1147),
        "X": range(1, 481),
        "G": range(1, 482),
    }
    try:
        return ranges[layer]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported layer {layer!r}; expected one of {sorted(ranges)}"
        ) from exc


@dataclass(frozen=True)
class SideLoadResult:
    series: pd.Series
    wire_count: int
    coverage: float


@dataclass(frozen=True)
class AverageProfileCloudOptions:
    source: str = LEGACY_SOURCE
    db_path: str | None = None
    layers: tuple[str, ...] = ("X", "V", "U", "G")
    min_coverage: float = 0.5
    iterations: int = 3
    exclude_apa_regex: str = "(?i)TEST"
    csv_dir: str = str(data_path("tension_data"))
    output_dir: str = str(data_path("tension_plots"))
    bins: int = 40
    moving_average_window: int = 15
    no_scaling: bool = False
    average_per_wire: bool = False
    split_by_location: bool = False
    show_all_locations: bool = False
    split_by_side: bool = False


@dataclass(frozen=True)
class LayerAnalysisResult:
    layer: str
    location_filter: str | None
    location_label: str | None
    location_output_tag: str
    global_mode_value: float
    cloud: pd.DataFrame
    mu_by_side: dict[str, pd.Series]
    n_by_side: dict[str, pd.Series]
    profile_df: pd.DataFrame
    scale_df: pd.DataFrame
    output_path: Path
    profile_summary_path: Path
    scale_summary_path: Path
    status_message: str
    overlay_results: tuple["LayerAnalysisResult", ...] | None = None


def kde_mode(values: np.ndarray) -> float:
    values = np.asarray(values, dtype="float64")
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan")
    if values.size == 1:
        return float(values[0])
    if np.allclose(values, values[0]):
        return float(values[0])

    # For large arrays the direct KDE evaluation is O(N*M) — too slow.
    # Use a histogram + Gaussian smoothing instead: O(N + M log M).
    # The bandwidth follows Scott's rule, converted to histogram-bin units.
    if values.size > 5_000:
        n_bins = 512
        hist, edges = np.histogram(values, bins=n_bins)
        centers = (edges[:-1] + edges[1:]) / 2.0
        bin_width = edges[1] - edges[0]
        std = float(np.std(values))
        if std > 0.0:
            bw = 1.06 * std * (values.size**-0.2)  # Scott's rule
            sigma_bins = max(bw / bin_width, 0.5)
            smoothed = gaussian_filter1d(hist.astype("float64"), sigma=sigma_bins)
        else:
            smoothed = hist.astype("float64")
        return float(centers[int(np.argmax(smoothed))])

    try:
        kde = gaussian_kde(values)
    except Exception:
        return float(np.median(values))

    x_grid = np.linspace(float(values.min()), float(values.max()), 512)
    y = kde(x_grid)
    if y.size == 0 or not np.isfinite(y).any():
        return float(np.median(values))
    return float(x_grid[int(np.nanargmax(y))])


def mode_scale_factor(
    *, apa_values: np.ndarray, global_mode_value: float
) -> float | None:
    if not np.isfinite(global_mode_value):
        return None
    apa_mode_value = kde_mode(apa_values)
    if not np.isfinite(apa_mode_value) or apa_mode_value <= 0.0:
        return None
    return float(global_mode_value / apa_mode_value)


def _parse_layers(value: str) -> list[str]:
    layers = [part.strip().upper() for part in str(value).split(",") if part.strip()]
    if not layers:
        raise ValueError("No layers provided")
    return layers


def _list_layer_apas(db_path: str, layer: str, *, source: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        if source == DUNEDB_SOURCE:
            rows = conn.execute(
                """
                select distinct apa_name
                from tension_actions
                where upper(layer) = ?
                order by apa_name
                """,
                (layer.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                "select distinct apa_name from tension_data where layer = ? order by apa_name",
                (layer,),
            ).fetchall()
    return [str(row[0]) for row in rows]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _batch_parse_action_json(
    action_json_series: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Parse all action_json values in a single Python pass.

    Returns ``(locations, action_times)`` as aligned Series, avoiding the
    overhead of calling ``map()`` twice with separate per-row functions.
    """
    locations: list[str | None] = []
    raw_times: list[str | None] = []
    for json_str in action_json_series:
        if not json_str:
            locations.append(None)
            raw_times.append(None)
            continue
        try:
            payload = json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            locations.append(None)
            raw_times.append(None)
            continue
        data = payload or {}
        loc = (data.get("data") or {}).get("location")
        loc_str = str(loc).strip().lower() if loc is not None else ""
        locations.append(loc_str or None)
        insert_date = (data.get("insertion") or {}).get("insertDate")
        raw_times.append(insert_date or None)
    return (
        pd.Series(locations, index=action_json_series.index, dtype=object),
        pd.to_datetime(
            pd.Series(raw_times, index=action_json_series.index), errors="coerce"
        ),
    )


def _empty_dunedb_measurements() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "apa_name",
            "action_version",
            "action_time",
            "location",
            "side",
            "wire_number",
            "tension",
        ]
    )


@lru_cache(maxsize=1)
def _load_dunedb_layer_measurements(db_path: str, layer: str) -> pd.DataFrame:
    """Load all measurements for one layer from the dunedb SQLite export.

    ``maxsize=1`` ensures that only the most recently requested layer's DataFrame
    is retained in the LRU cache — once the analysis moves to the next layer the
    previous one becomes GC-eligible.  Using ``maxsize=None`` (the old value)
    kept every layer's DataFrame alive for the entire process lifetime.
    """
    layer_key = layer.upper()
    expected_wires = expected_wire_range(layer_key)
    min_wire = int(expected_wires.start)
    max_wire = int(expected_wires.stop - 1)

    with sqlite3.connect(db_path) as conn:
        # Tune SQLite for read-heavy workloads: larger page cache, WAL mode,
        # and in-memory temp storage.  Avoid mmap_size on memory-constrained
        # machines — mapping large files into virtual address space competes
        # with Python's heap and can push total VM above physical RAM.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA cache_size=-65536")  # 64 MB page cache
        conn.execute("PRAGMA temp_store=MEMORY")

        # Single JOIN query replaces two round-trips (actions fetch + large IN
        # clause).  action_id is omitted — it is unique per row and creates one
        # Python string object per measurement, adding significant heap pressure
        # for no downstream benefit.
        df = pd.read_sql_query(
            """
            SELECT a.apa_name, a.action_version, a.action_json,
                   m.side, m.wire_index AS wire_number, m.tension
            FROM tension_actions a
            JOIN tension_measurements m ON a.action_id = m.action_id
            WHERE upper(a.layer) = ?
              AND m.wire_index BETWEEN ? AND ?
              AND m.tension BETWEEN ? AND ?
            """,
            conn,
            params=(
                layer_key,
                min_wire,
                max_wire,
                MIN_PLAUSIBLE_TENSION,
                MAX_PLAUSIBLE_TENSION,
            ),
        )

    if df.empty:
        return _empty_dunedb_measurements()

    # Single-pass JSON parse: extract location + action_time in one Python loop
    # instead of two separate .map() calls.
    locations, action_times = _batch_parse_action_json(df["action_json"])
    df = df.drop(columns=["action_json"])
    df["location"] = locations.values
    df["action_time"] = action_times.values

    # Use categorical dtypes for low-cardinality string columns.  With many
    # hundreds of thousands of rows, object columns store one Python string
    # object per row (50+ bytes each).  Categoricals store a small lookup table
    # plus one integer code per row, cutting string-column memory by ~20–50×.
    df["apa_name"] = df["apa_name"].astype("category")
    df["location"] = df["location"].astype("category")
    df["side"] = df["side"].astype(str).str.upper().astype("category")

    df["wire_number"] = df["wire_number"].astype("int32")
    df["tension"] = df["tension"].astype("float32")

    # Vectorized reverse-index correction — avoids row-by-row apply().
    # Chicago X-B and G-B rows in this export have wire indices stored backwards.
    db_name = Path(db_path).name
    if db_name == "dunedb_all_locations_all_apas_tension_data.sqlite" and layer_key in {
        "X",
        "G",
    }:
        reverse_mask = (df["location"] == "chicago") & (df["side"] == "B")
        if reverse_mask.any():
            df.loc[reverse_mask, "wire_number"] = (
                max_wire + min_wire - df.loc[reverse_mask, "wire_number"]
            )

    return df


def _select_layer_side_measurements(
    db_path: str,
    *,
    apa_name: str,
    layer: str,
    side: str,
    source: str,
    location_filter: str | None = None,
) -> pd.DataFrame:
    if source == DUNEDB_SOURCE:
        layer_measurements = _load_dunedb_layer_measurements(db_path, layer)
        if layer_measurements.empty:
            return layer_measurements.copy()

        mask = (layer_measurements["apa_name"] == apa_name) & (
            layer_measurements["side"] == side.upper()
        )
        if location_filter is not None:
            normalized_location = location_filter.strip().lower()
            mask &= layer_measurements["location"] == normalized_location
        return layer_measurements.loc[mask].copy()

    return select_dataframe(
        db_path,
        where_clause="apa_name = ? AND layer = ? AND side = ?",
        params=(apa_name, layer, side),
        columns=("wire_number", "tension", "time"),
    )


def _parse_apa_layer_from_csv_name(path: Path) -> tuple[str, str] | None:
    stem = path.stem
    if not stem.startswith("tension_data_"):
        return None
    suffix = stem.removeprefix("tension_data_")
    if "_" not in suffix:
        return None
    apa_name, layer = suffix.rsplit("_", 1)
    layer = layer.upper().strip()
    apa_name = apa_name.strip()
    if not apa_name or layer not in {"U", "V", "X", "G"}:
        return None
    return apa_name, layer


def _index_csv_files(csv_dir: Path) -> dict[tuple[str, str], Path]:
    if not csv_dir.exists():
        return {}
    mapping: dict[tuple[str, str], Path] = {}
    for path in csv_dir.glob("tension_data_*.csv"):
        parsed = _parse_apa_layer_from_csv_name(path)
        if parsed is None:
            continue
        mapping[parsed] = path
    return mapping


def _build_output_tag(args: argparse.Namespace) -> str:
    return _build_output_tag_from_options(normalize_options(args))


def normalize_options(
    options: AverageProfileCloudOptions | argparse.Namespace | Mapping[str, object],
) -> AverageProfileCloudOptions:
    if isinstance(options, AverageProfileCloudOptions):
        normalized = options
    elif isinstance(options, argparse.Namespace):
        normalized = AverageProfileCloudOptions(
            source=str(options.source),
            db_path=None if options.db_path is None else str(options.db_path),
            layers=tuple(_parse_layers(str(options.layers))),
            min_coverage=float(options.min_coverage),
            iterations=int(options.iterations),
            exclude_apa_regex=str(options.exclude_apa_regex),
            csv_dir=str(options.csv_dir),
            output_dir=str(options.output_dir),
            bins=int(options.bins),
            moving_average_window=int(options.moving_average_window),
            no_scaling=bool(options.no_scaling),
            average_per_wire=bool(options.average_per_wire),
            split_by_location=bool(options.split_by_location),
            show_all_locations=bool(options.show_all_locations),
            split_by_side=bool(options.split_by_side),
        )
    else:
        data = dict(options)
        normalized = AverageProfileCloudOptions(
            source=str(data.get("source", LEGACY_SOURCE)),
            db_path=None if data.get("db_path") in (None, "") else str(data["db_path"]),
            layers=tuple(_parse_layers(str(data.get("layers", "X,V,U,G")))),
            min_coverage=float(cast(Any, data.get("min_coverage", 0.5))),
            iterations=int(cast(Any, data.get("iterations", 3))),
            exclude_apa_regex=str(data.get("exclude_apa_regex", "(?i)TEST")),
            csv_dir=str(data.get("csv_dir", data_path("tension_data"))),
            output_dir=str(data.get("output_dir", data_path("tension_plots"))),
            bins=int(cast(Any, data.get("bins", 40))),
            moving_average_window=int(cast(Any, data.get("moving_average_window", 15))),
            no_scaling=bool(data.get("no_scaling", False)),
            average_per_wire=bool(data.get("average_per_wire", False)),
            split_by_location=bool(data.get("split_by_location", False)),
            show_all_locations=bool(data.get("show_all_locations", False)),
            split_by_side=bool(data.get("split_by_side", False)),
        )

    if normalized.source not in {LEGACY_SOURCE, DUNEDB_SOURCE}:
        raise ValueError(f"Unsupported source {normalized.source!r}")
    if normalized.min_coverage < 0.0:
        raise ValueError("min_coverage must be non-negative")
    if normalized.bins <= 0:
        raise ValueError("bins must be positive")
    if normalized.moving_average_window <= 0:
        raise ValueError("moving_average_window must be positive")
    if normalized.iterations <= 0:
        raise ValueError("iterations must be positive")
    if normalized.split_by_location and normalized.source != DUNEDB_SOURCE:
        raise ValueError("--split-by-location is only supported with --source dunedb")
    if normalized.show_all_locations and not normalized.split_by_location:
        raise ValueError("--show-all-locations requires --split-by-location")
    return normalized


def _build_output_tag_from_options(options: AverageProfileCloudOptions) -> str:
    parts: list[str] = []
    if options.no_scaling:
        parts.append("noscale")
    else:
        parts.append("mode")
    if options.average_per_wire:
        parts.append("avgwire")
    else:
        parts.append("allsamples")
    parts.append(f"cov{str(options.min_coverage).replace('.', 'p')}")
    parts.append(f"it{options.iterations}")
    parts.append(f"bins{options.bins}")
    parts.append(f"win{options.moving_average_window}")
    return "_".join(parts)


def _resolve_db_path(options: AverageProfileCloudOptions) -> str:
    if options.db_path:
        return str(options.db_path)
    if options.source == DUNEDB_SOURCE:
        return str(DEFAULT_DUNEDB_SQLITE)
    return str(tension_data_db_path())


def _location_filters(options: AverageProfileCloudOptions) -> list[str | None]:
    if not options.split_by_location:
        return [None]
    return list(DUNEDB_LOCATIONS)


def _location_line_style(location_index: int) -> str:
    styles = ("solid", "dashed", "dotted", "dashdot")
    return styles[location_index % len(styles)]


def _stack_location_frames(
    location_results: list[LayerAnalysisResult],
    attr: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for location_result in location_results:
        frame = getattr(location_result, attr)
        if frame.empty:
            continue
        labeled = frame.copy()
        labeled["location"] = location_result.location_label or ""
        frames.append(labeled)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _build_all_locations_result(
    *,
    layer: str,
    location_results: list[LayerAnalysisResult],
    options: AverageProfileCloudOptions,
) -> LayerAnalysisResult:
    output_tag = f"{options.source}_{_build_output_tag_from_options(options)}"
    location_output_tag = f"{output_tag}_all_locations"
    output_path = (
        Path(options.output_dir)
        / f"tension_profile_cloud_{layer}_{location_output_tag}.png"
    )
    summary_dir = data_path("tension_summaries")
    profile_summary_path = (
        summary_dir / f"average_profile_{layer}_{location_output_tag}.csv"
    )
    scale_summary_path = (
        summary_dir / f"average_profile_scales_{layer}_{location_output_tag}.csv"
    )

    cloud_frames: list[pd.DataFrame] = []
    for location_result in location_results:
        if location_result.cloud.empty:
            continue
        cloud = location_result.cloud.copy()
        cloud["location"] = location_result.location_label or ""
        cloud_frames.append(cloud)
    cloud = (
        pd.concat(cloud_frames, ignore_index=True) if cloud_frames else pd.DataFrame()
    )

    global_mode_value = (
        kde_mode(cloud["tension"].to_numpy(dtype="float64"))
        if not cloud.empty
        else float("nan")
    )
    profile_df = _stack_location_frames(location_results, "profile_df")
    scale_df = _stack_location_frames(location_results, "scale_df")

    status_message = (
        f"Layer {layer} [All locations]: wrote {output_path} + {profile_summary_path}"
        if not cloud.empty
        else f"Layer {layer} [All locations]: computed empty cloud"
    )
    return LayerAnalysisResult(
        layer=layer,
        location_filter=None,
        location_label="All locations",
        location_output_tag=location_output_tag,
        global_mode_value=global_mode_value,
        cloud=cloud,
        mu_by_side=_empty_side_series(),
        n_by_side=_empty_side_counts(),
        profile_df=profile_df,
        scale_df=scale_df,
        output_path=output_path,
        profile_summary_path=profile_summary_path,
        scale_summary_path=scale_summary_path,
        status_message=status_message,
        overlay_results=tuple(location_results),
    )


def _coerce_time_series(time_series: pd.Series) -> pd.Series:
    legacy = pd.to_datetime(time_series, errors="coerce", format=OLD_CSV_TIME_FORMAT)
    if legacy.notna().any():
        parsed = legacy
        missing = parsed.isna()
        if missing.any():
            parsed.loc[missing] = pd.to_datetime(time_series[missing], errors="coerce")
        return parsed
    return pd.to_datetime(time_series, errors="coerce")


def load_latest_side_series_from_csv(
    csv_path: Path,
    *,
    layer: str,
    side: str,
    expected_wires: range,
) -> SideLoadResult:
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except FileNotFoundError:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)
    except ParserError:
        # Some legacy exports contain rows with extra commas/unescaped fields.
        # We only need a handful of columns, so skip malformed rows rather than failing.
        df = pd.read_csv(
            csv_path,
            encoding="utf-8",
            engine="python",
            on_bad_lines="skip",
        )
    except UnicodeDecodeError:
        df = pd.read_csv(
            csv_path,
            encoding="latin-1",
            engine="python",
            on_bad_lines="skip",
        )

    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    if (
        "side" not in df.columns
        or "wire_number" not in df.columns
        or "tension" not in df.columns
    ):
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df = df.copy()
    df = df[df["side"].astype(str).str.upper() == side.upper()]
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df["wire_number"] = pd.to_numeric(df["wire_number"], errors="coerce")
    df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
    if "time" in df.columns:
        df["time"] = _coerce_time_series(df["time"])
    else:
        df["time"] = pd.NaT

    df["_row"] = np.arange(len(df), dtype="int64")
    df = df.dropna(subset=["wire_number", "tension"])
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df["wire_number"] = df["wire_number"].astype(int)
    expected_set = set(expected_wires)
    df = df[df["wire_number"].isin(expected_set)]
    df = df[
        (df["tension"] >= MIN_PLAUSIBLE_TENSION)
        & (df["tension"] <= MAX_PLAUSIBLE_TENSION)
    ]
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    sort_cols = ["time"] if df["time"].notna().any() else ["_row"]
    df = (
        df.sort_values(sort_cols)
        .drop_duplicates(subset="wire_number", keep="last")
        .sort_values("wire_number")
    )
    series = df.set_index("wire_number")["tension"].astype("float64")
    wire_count = int(series.size)
    expected_count = len(expected_wires)
    coverage = float(wire_count / expected_count) if expected_count else 0.0
    return SideLoadResult(series, wire_count, coverage)


def load_average_side_series_from_csv(
    csv_path: Path,
    *,
    layer: str,
    side: str,
    expected_wires: range,
) -> SideLoadResult:
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except FileNotFoundError:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)
    except ParserError:
        df = pd.read_csv(
            csv_path,
            encoding="utf-8",
            engine="python",
            on_bad_lines="skip",
        )
    except UnicodeDecodeError:
        df = pd.read_csv(
            csv_path,
            encoding="latin-1",
            engine="python",
            on_bad_lines="skip",
        )

    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    if (
        "side" not in df.columns
        or "wire_number" not in df.columns
        or "tension" not in df.columns
    ):
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df = df.copy()
    df = df[df["side"].astype(str).str.upper() == side.upper()]
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df["wire_number"] = pd.to_numeric(df["wire_number"], errors="coerce")
    df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
    df = df.dropna(subset=["wire_number", "tension"])
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df["wire_number"] = df["wire_number"].astype(int)
    expected_set = set(expected_wires)
    df = df[df["wire_number"].isin(expected_set)]
    df = df[
        (df["tension"] >= MIN_PLAUSIBLE_TENSION)
        & (df["tension"] <= MAX_PLAUSIBLE_TENSION)
    ]
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    series = df.groupby("wire_number")["tension"].mean().sort_index().astype("float64")
    wire_count = int(series.size)
    expected_count = len(expected_wires)
    coverage = float(wire_count / expected_count) if expected_count else 0.0
    return SideLoadResult(series, wire_count, coverage)


def load_latest_side_series(
    db_path: str,
    *,
    apa_name: str,
    layer: str,
    side: str,
    expected_wires: range,
    source: str,
    location_filter: str | None = None,
) -> SideLoadResult:
    measurements = _select_layer_side_measurements(
        db_path,
        apa_name=apa_name,
        layer=layer,
        side=side,
        source=source,
        location_filter=location_filter,
    )
    if measurements.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df = measurements.copy()
    if "wire_number" not in df.columns and "wire_index" in df.columns:
        df["wire_number"] = df["wire_index"]
    df["wire_number"] = pd.to_numeric(df["wire_number"], errors="coerce")
    df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
    else:
        df["time"] = pd.NaT
    if "action_time" in df.columns:
        df["action_time"] = pd.to_datetime(df["action_time"], errors="coerce")
    else:
        df["action_time"] = pd.NaT
    df = df.dropna(subset=["wire_number", "tension"])
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df["wire_number"] = df["wire_number"].astype(int)
    expected_set = set(expected_wires)
    df = df[df["wire_number"].isin(expected_set)]
    df = df[
        (df["tension"] >= MIN_PLAUSIBLE_TENSION)
        & (df["tension"] <= MAX_PLAUSIBLE_TENSION)
    ]
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    sort_cols = ["action_time", "time"] if df["action_time"].notna().any() else ["time"]
    if not df["time"].notna().any() and "action_version" in df.columns:
        sort_cols = ["action_version"]
    df = (
        df.sort_values(sort_cols)
        .drop_duplicates(subset="wire_number", keep="last")
        .sort_values("wire_number")
    )
    series = df.set_index("wire_number")["tension"].astype("float64")
    wire_count = int(series.size)
    expected_count = len(expected_wires)
    coverage = float(wire_count / expected_count) if expected_count else 0.0
    return SideLoadResult(series, wire_count, coverage)


def load_average_side_series(
    db_path: str,
    *,
    apa_name: str,
    layer: str,
    side: str,
    expected_wires: range,
    source: str,
    location_filter: str | None = None,
) -> SideLoadResult:
    measurements = _select_layer_side_measurements(
        db_path,
        apa_name=apa_name,
        layer=layer,
        side=side,
        source=source,
        location_filter=location_filter,
    )
    if measurements.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df = measurements.copy()
    if "wire_number" not in df.columns and "wire_index" in df.columns:
        df["wire_number"] = df["wire_index"]
    df["wire_number"] = pd.to_numeric(df["wire_number"], errors="coerce")
    df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
    df = df.dropna(subset=["wire_number", "tension"])
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df["wire_number"] = df["wire_number"].astype(int)
    expected_set = set(expected_wires)
    df = df[df["wire_number"].isin(expected_set)]
    df = df[
        (df["tension"] >= MIN_PLAUSIBLE_TENSION)
        & (df["tension"] <= MAX_PLAUSIBLE_TENSION)
    ]
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    series = df.groupby("wire_number")["tension"].mean().sort_index().astype("float64")
    wire_count = int(series.size)
    expected_count = len(expected_wires)
    coverage = float(wire_count / expected_count) if expected_count else 0.0
    return SideLoadResult(series, wire_count, coverage)


def compute_scale_factor(
    series_by_side: dict[str, pd.Series],
    target_by_side: dict[str, pd.Series],
) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for side, series in series_by_side.items():
        target = target_by_side.get(side)
        if target is None or series.empty or target.empty:
            continue

        aligned = pd.concat([series, target], axis=1, join="inner").dropna()
        if aligned.empty:
            continue

        tensions = aligned.iloc[:, 0].astype("float64")
        target_values = aligned.iloc[:, 1].astype("float64")
        numerator += float((tensions * target_values).sum())
        denominator += float((tensions * tensions).sum())

    if denominator <= 0.0 or not np.isfinite(numerator) or not np.isfinite(denominator):
        return None
    return float(numerator / denominator)


def _compute_target_profiles(
    series_by_apa: dict[str, dict[str, pd.Series]],
    scale_factors: dict[str, float],
) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    mu_by_side: dict[str, pd.Series] = {}
    n_by_side: dict[str, pd.Series] = {}

    for side in SIDES:
        columns: dict[str, pd.Series] = {}
        for apa_name, sides in series_by_apa.items():
            series = sides.get(side)
            if series is None or series.empty:
                continue
            k = float(scale_factors.get(apa_name, np.nan))
            if not np.isfinite(k):
                continue
            columns[apa_name] = series * k

        if not columns:
            mu_by_side[side] = pd.Series(dtype="float64")
            n_by_side[side] = pd.Series(dtype="int64")
            continue

        df = pd.concat(columns, axis=1).sort_index()
        mu_by_side[side] = df.median(axis=1, skipna=True)
        n_by_side[side] = df.notna().sum(axis=1).astype("int64")

    return mu_by_side, n_by_side


def _make_cloud_dataframe(
    series_by_apa: dict[str, dict[str, pd.Series]],
    scale_factors: dict[str, float],
    *,
    average_per_wire: bool,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for apa_name, sides in series_by_apa.items():
        k = float(scale_factors.get(apa_name, np.nan))
        if not np.isfinite(k):
            continue
        for side, series in sides.items():
            if series.empty:
                continue
            scaled = (series * k).rename("tension").reset_index()
            scaled.columns = ["wire_number", "tension"]
            scaled["side"] = side
            scaled["apa_name"] = apa_name
            frames.append(scaled)
    if not frames:
        return pd.DataFrame(columns=["wire_number", "tension", "side", "apa_name"])
    cloud = pd.concat(frames, ignore_index=True)
    if average_per_wire:
        cloud = (
            cloud.groupby(["side", "wire_number"], as_index=False)
            .agg(
                tension=("tension", "mean"),
                apa_count=("apa_name", "nunique"),
            )
            .sort_values(["side", "wire_number"])
            .reset_index(drop=True)
        )
    return cloud


def _side_legend_label(
    side: str, subset: pd.DataFrame, *, average_per_wire: bool
) -> str:
    point_count = int(len(subset))
    side_values = subset["tension"].astype("float64").to_numpy()
    side_mean = float(np.mean(side_values)) if side_values.size else float("nan")
    side_mode = kde_mode(side_values) if side_values.size else float("nan")

    count_label = "wires" if average_per_wire else "points"
    label = f"Side {side} ({count_label}={point_count}"
    if average_per_wire and "apa_count" in subset.columns and point_count:
        samples_per_wire = float(subset["apa_count"].astype("float64").mean())
        label += f", samples/wire={samples_per_wire:.2f}"
    label += f", μ={side_mean:.3f}, mode={side_mode:.3f})"
    return label


def _rolling_mean(values: pd.Series, window: int = 15) -> pd.Series:
    return values.rolling(window=window, center=True, min_periods=1).mean()


def plot_mode_supported_for_layer(layer: str, plot_mode: str) -> bool:
    if str(plot_mode).strip() == PLOT_MODE_WIRE_NUMBER:
        return True
    return str(layer).strip().upper() in {"U", "V"}


def _normalize_endpoint_kind(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _normalize_measurement_side(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _classify_uv_endpoint_path(
    start_side: str | None,
    end_side: str | None,
) -> tuple[str | None, str | None]:
    start_kind = _normalize_endpoint_kind(start_side)
    end_kind = _normalize_endpoint_kind(end_side)
    if start_kind is None or end_kind is None:
        return None, None

    endpoint_kinds = {start_kind, end_kind}
    if endpoint_kinds == {"top", "bottom"}:
        if end_kind == "top":
            return "top_bottom", "ends_at_top"
        if end_kind == "bottom":
            return "top_bottom", "ends_at_bottom"
        return "top_bottom", None

    if "head" in endpoint_kinds or "foot" in endpoint_kinds:
        if start_kind in {"head", "foot"}:
            return "head_foot", "starts_on_head_or_foot"
        if end_kind in {"head", "foot"}:
            return "head_foot", "ends_on_head_or_foot"
        return "head_foot", None

    return None, None


def _canonical_endpoint_side_mapping(
    start_side: str | None,
    end_side: str | None,
) -> tuple[str, ...] | None:
    if None in {start_side, end_side}:
        return None
    ordered = []
    for side in (start_side, end_side):
        normalized = str(side).strip().lower()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return tuple(ordered) or None


@lru_cache(maxsize=2)
def _uv_recipe_maps(layer: str):
    return build_uv_wire_recipe_maps(layer)


def _enrich_cloud_with_uv_recipe_metadata(
    cloud: pd.DataFrame, *, layer: str
) -> pd.DataFrame:
    enriched = cloud.copy()
    if enriched.empty:
        for column in UV_METADATA_COLUMNS:
            enriched[column] = pd.Series(
                dtype="float64"
                if column in {"wrap_number", "applied_length_mm"}
                else "object"
            )
        return enriched

    if str(layer).strip().upper() not in {"U", "V"}:
        enriched["wrap_number"] = np.nan
        enriched["applied_length_mm"] = np.nan
        enriched["start_side"] = None
        enriched["end_side"] = None
        enriched["endpoint_side_mapping"] = None
        enriched["start_endpoint_kind"] = None
        enriched["end_endpoint_kind"] = None
        enriched["uv_path_family"] = None
        enriched["uv_terminal_group"] = None
        return enriched

    recipe_maps = _uv_recipe_maps(layer)
    wrap_numbers: list[float] = []
    applied_lengths: list[float] = []
    start_sides: list[str | None] = []
    end_sides: list[str | None] = []
    endpoint_mappings: list[tuple[str, ...] | None] = []
    start_endpoint_kinds: list[str | None] = []
    end_endpoint_kinds: list[str | None] = []
    uv_path_families: list[str | None] = []
    uv_terminal_groups: list[str | None] = []
    measurement_sides = (
        enriched["side"]
        if "side" in enriched.columns
        else pd.Series([None] * len(enriched), index=enriched.index, dtype="object")
    )
    for raw_wire_number, raw_measurement_side in zip(
        pd.to_numeric(enriched["wire_number"], errors="coerce"),
        measurement_sides,
        strict=False,
    ):
        if not np.isfinite(raw_wire_number):
            wrap_numbers.append(float("nan"))
            applied_lengths.append(float("nan"))
            start_sides.append(None)
            end_sides.append(None)
            endpoint_mappings.append(None)
            start_endpoint_kinds.append(None)
            end_endpoint_kinds.append(None)
            uv_path_families.append(None)
            uv_terminal_groups.append(None)
            continue
        wire_number = int(raw_wire_number)
        wrap_ref = recipe_maps.wire_to_wrap.get(wire_number)
        endpoint_sides = recipe_maps.wire_to_endpoint_sides.get(wire_number)
        wrap_numbers.append(
            float("nan") if wrap_ref is None else float(wrap_ref.wrap_number)
        )
        applied_lengths.append(
            float(recipe_maps.wire_to_applied_length_mm.get(wire_number, float("nan")))
        )
        if endpoint_sides is None:
            start_sides.append(None)
            end_sides.append(None)
            endpoint_mappings.append(None)
            start_endpoint_kinds.append(None)
            end_endpoint_kinds.append(None)
            uv_path_families.append(None)
            uv_terminal_groups.append(None)
            continue
        start_side, end_side = endpoint_sides
        measurement_side = _normalize_measurement_side(raw_measurement_side)
        if measurement_side == "A":
            start_side, end_side = end_side, start_side
        start_kind = _normalize_endpoint_kind(start_side)
        end_kind = _normalize_endpoint_kind(end_side)
        path_family, terminal_group = _classify_uv_endpoint_path(start_kind, end_kind)
        start_sides.append(start_side)
        end_sides.append(end_side)
        endpoint_mappings.append(_canonical_endpoint_side_mapping(start_side, end_side))
        start_endpoint_kinds.append(start_kind)
        end_endpoint_kinds.append(end_kind)
        uv_path_families.append(path_family)
        uv_terminal_groups.append(terminal_group)

    enriched["wrap_number"] = pd.Series(
        wrap_numbers, index=enriched.index, dtype="float64"
    )
    enriched["applied_length_mm"] = pd.Series(
        applied_lengths, index=enriched.index, dtype="float64"
    )
    enriched["start_side"] = pd.Series(
        start_sides, index=enriched.index, dtype="object"
    )
    enriched["end_side"] = pd.Series(end_sides, index=enriched.index, dtype="object")
    enriched["endpoint_side_mapping"] = pd.Series(
        endpoint_mappings, index=enriched.index, dtype="object"
    )
    enriched["start_endpoint_kind"] = pd.Series(
        start_endpoint_kinds, index=enriched.index, dtype="object"
    )
    enriched["end_endpoint_kind"] = pd.Series(
        end_endpoint_kinds, index=enriched.index, dtype="object"
    )
    enriched["uv_path_family"] = pd.Series(
        uv_path_families, index=enriched.index, dtype="object"
    )
    enriched["uv_terminal_group"] = pd.Series(
        uv_terminal_groups, index=enriched.index, dtype="object"
    )
    return enriched


def _aggregate_cloud_for_endpoint_categories(
    cloud: pd.DataFrame,
    *,
    average_per_wire: bool,
) -> pd.DataFrame:
    aggregated = cloud.copy()
    if aggregated.empty:
        return aggregated
    if not average_per_wire:
        return aggregated

    group_columns = [
        "wire_number",
        "wrap_number",
        "applied_length_mm",
        "start_side",
        "end_side",
        "endpoint_side_mapping",
        "start_endpoint_kind",
        "end_endpoint_kind",
        "uv_path_family",
        "uv_terminal_group",
    ]
    present_group_columns = [
        column for column in group_columns if column in aggregated.columns
    ]
    if not present_group_columns:
        return aggregated
    return (
        aggregated.groupby(present_group_columns, as_index=False, dropna=False)
        .agg(tension=("tension", "mean"))
        .sort_values(
            ["uv_path_family", "uv_terminal_group", "wire_number"], na_position="last"
        )
        .reset_index(drop=True)
    )


def _render_endpoint_categories_view(
    figure,
    *,
    result: LayerAnalysisResult,
    average_per_wire: bool,
    moving_average_window: int,
):
    colors = {
        "ends_at_top": "tab:blue",
        "ends_at_bottom": "tab:orange",
        "starts_on_head_or_foot": "tab:green",
        "ends_on_head_or_foot": "tab:red",
    }
    labels = {
        "ends_at_top": "Ends At Top",
        "ends_at_bottom": "Ends At Bottom",
        "starts_on_head_or_foot": "Starts On Head/Foot",
        "ends_on_head_or_foot": "Ends On Head/Foot",
    }
    title_prefix = (
        f"Layer {result.layer}"
        if result.location_label is None
        else f"Layer {result.layer} ({result.location_label})"
    )

    grid = figure.add_gridspec(2, 2)
    top_bottom_axis = figure.add_subplot(grid[0, 0])
    head_foot_wrap_axis = figure.add_subplot(grid[0, 1])
    head_foot_length_axis = figure.add_subplot(grid[1, 0])
    summary_axis = figure.add_subplot(grid[1, 1])

    aggregated = _aggregate_cloud_for_endpoint_categories(
        result.cloud,
        average_per_wire=average_per_wire,
    )
    numeric_columns = ["wrap_number", "applied_length_mm", "tension"]
    for column in numeric_columns:
        if column in aggregated.columns:
            aggregated[column] = pd.to_numeric(aggregated[column], errors="coerce")

    panels = [
        (
            top_bottom_axis,
            aggregated[
                (aggregated["uv_path_family"] == "top_bottom")
                & (
                    aggregated["uv_terminal_group"].isin(
                        ["ends_at_top", "ends_at_bottom"]
                    )
                )
            ],
            "wrap_number",
            ["ends_at_top", "ends_at_bottom"],
            "Top-Bottom Wires vs Wrap Number",
            "Wrap Number",
        ),
        (
            head_foot_wrap_axis,
            aggregated[
                (aggregated["uv_path_family"] == "head_foot")
                & (
                    aggregated["uv_terminal_group"].isin(
                        ["starts_on_head_or_foot", "ends_on_head_or_foot"]
                    )
                )
            ],
            "wrap_number",
            ["starts_on_head_or_foot", "ends_on_head_or_foot"],
            "Head/Foot Wires vs Wrap Number",
            "Wrap Number",
        ),
        (
            head_foot_length_axis,
            aggregated[
                (aggregated["uv_path_family"] == "head_foot")
                & (
                    aggregated["uv_terminal_group"].isin(
                        ["starts_on_head_or_foot", "ends_on_head_or_foot"]
                    )
                )
            ],
            "applied_length_mm",
            ["starts_on_head_or_foot", "ends_on_head_or_foot"],
            "Head/Foot Wires vs Applied Length",
            "Applied Length (mm)",
        ),
    ]

    summary_lines = [
        f"{title_prefix}: Endpoint Categories",
        f"Global raw mode={result.global_mode_value:.3f}"
        if np.isfinite(result.global_mode_value)
        else "Global raw mode=nan",
    ]

    for axis, panel_df, x_column, groups, title, xlabel in panels:
        plotted_groups = 0
        for group in groups:
            subset = panel_df[panel_df["uv_terminal_group"] == group].copy()
            subset = subset[[x_column, "tension"]].dropna()
            if subset.empty:
                continue
            plotted_groups += 1
            subset = subset.sort_values(x_column)
            color = colors[group]
            axis.scatter(
                subset[x_column].to_numpy(dtype="float64", copy=False),
                subset["tension"].to_numpy(dtype="float64", copy=False),
                s=10 if average_per_wire else 7,
                alpha=0.55 if average_per_wire else 0.18,
                color=color,
                edgecolors="none",
                label=labels[group],
            )
            axis.plot(
                subset[x_column],
                _rolling_mean(subset["tension"], window=moving_average_window),
                linewidth=2.0,
                alpha=0.9,
                color=color,
                label=f"{labels[group]} Trend",
            )
            pearson_value, spearman_value = _correlation_stats(
                subset, x_column=x_column
            )
            summary_lines.append(
                f"{labels[group]} ({xlabel}): "
                f"Pearson={pearson_value:.3f}, Spearman={spearman_value:.3f}, n={len(subset)}"
            )

        axis.set_title(f"{title_prefix}: {title}")
        axis.set_xlabel(xlabel)
        axis.set_ylabel("Scaled Tension (N)")
        axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
        if plotted_groups:
            axis.legend(loc="upper right", fontsize=8, frameon=True)

    summary_axis.set_axis_off()
    summary_axis.text(
        0.02,
        0.98,
        "\n".join(summary_lines),
        transform=summary_axis.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.9},
    )

    return figure


def _correlation_stats(subset: pd.DataFrame, *, x_column: str) -> tuple[float, float]:
    numeric = (
        subset[[x_column, "tension"]].apply(pd.to_numeric, errors="coerce").dropna()
    )
    if len(numeric) < 2:
        return float("nan"), float("nan")
    if numeric[x_column].nunique() < 2 or numeric["tension"].nunique() < 2:
        return float("nan"), float("nan")
    return (
        float(pearsonr(numeric[x_column], numeric["tension"]).statistic),
        float(spearmanr(numeric[x_column], numeric["tension"]).statistic),
    )


def _render_numeric_profile_cloud(
    axis,
    *,
    subset: pd.DataFrame,
    color: str,
    average_per_wire: bool,
    x_column: str,
) -> None:
    numeric = (
        subset[[x_column, "tension"]].apply(pd.to_numeric, errors="coerce").dropna()
    )
    if numeric.empty:
        return

    marker_size = 10 if average_per_wire else 7
    marker_alpha = 0.55 if average_per_wire else 0.12
    axis.scatter(
        numeric[x_column].to_numpy(dtype="float64", copy=False),
        numeric["tension"].to_numpy(dtype="float64", copy=False),
        s=marker_size,
        alpha=marker_alpha,
        color=color,
        edgecolors="none",
    )


def _render_profile_cloud(
    axis,
    *,
    subset: pd.DataFrame,
    color: str,
    average_per_wire: bool,
) -> None:
    _render_numeric_profile_cloud(
        axis,
        subset=subset,
        color=color,
        average_per_wire=average_per_wire,
        x_column="wire_number",
    )


def _render_endpoint_mapping_view(
    axis,
    *,
    overlay_results: list[LayerAnalysisResult],
    sides_to_plot: tuple[str, ...],
    average_per_wire: bool,
    side_filter: str | None,
    title_prefix: str,
) -> list[str]:
    colors = {"A": "tab:blue", "B": "tab:orange"}
    entries: list[tuple[str, str, str, pd.DataFrame]] = []
    for location_index, location_result in enumerate(overlay_results):
        location_label = (
            location_result.location_label or f"Location {location_index + 1}"
        )
        for side in sides_to_plot:
            subset = location_result.cloud[location_result.cloud["side"] == side].copy()
            subset = subset.dropna(subset=["tension"])
            if subset.empty:
                continue
            category_rows: list[pd.DataFrame] = []
            for endpoint_column in ("start_side", "end_side"):
                endpoint_subset = subset.dropna(subset=[endpoint_column]).copy()
                if endpoint_subset.empty:
                    continue
                endpoint_subset["plot_category"] = (
                    endpoint_subset[endpoint_column].astype(str).str.strip().str.lower()
                )
                category_rows.append(endpoint_subset)
            if not category_rows:
                continue
            subset = pd.concat(category_rows, ignore_index=True)
            if len(overlay_results) > 1:
                subset["plot_category"] = (
                    subset["plot_category"] + "\n" + location_label
                )
            entries.append((location_label, side, colors[side], subset))

    categories = sorted(
        {
            str(category)
            for _location, _side, _color, subset in entries
            for category in subset["plot_category"].unique()
        }
    )
    if not categories:
        axis.set_title(f"{title_prefix}: Endpoint Side Mapping")
        return []

    category_positions = {label: index + 1 for index, label in enumerate(categories)}
    side_offsets = {"A": -0.18, "B": 0.18}
    plotted_sides: list[str] = []
    for location_label, side, color, subset in entries:
        grouped = subset.groupby("plot_category")["tension"]
        plotted_sides.append(side)
        for category, values in grouped:
            values_array = values.astype("float64").to_numpy()
            if values_array.size == 0:
                continue
            position = category_positions[str(category)] + side_offsets.get(side, 0.0)
            axis.boxplot(
                [values_array.tolist()],
                positions=[position],
                widths=0.28,
                patch_artist=True,
                boxprops={"facecolor": color, "alpha": 0.25, "edgecolor": color},
                medianprops={"color": color},
                whiskerprops={"color": color},
                capprops={"color": color},
            )
            jitter = (
                np.linspace(-0.04, 0.04, num=values_array.size)
                if values_array.size > 1
                else np.asarray([0.0])
            )
            marker_alpha = 0.55 if average_per_wire else 0.18
            axis.scatter(
                np.full(values_array.size, position, dtype="float64") + jitter,
                values_array,
                s=12 if average_per_wire else 8,
                alpha=marker_alpha,
                color=color,
                edgecolors="none",
                label=location_label
                if side_filter is not None
                else f"{location_label} {side}",
            )

    axis.set_xticks([category_positions[label] for label in categories])
    axis.set_xticklabels(categories, rotation=20, ha="right")
    axis.set_xlabel(PLOT_MODE_LABELS[PLOT_MODE_ENDPOINT_MAPPING])
    axis.set_ylabel("Scaled Tension (N)")
    axis.set_title(
        f"{title_prefix}: {'Wire-Average' if average_per_wire else 'Sample'} Endpoint Mapping"
    )
    axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
    axis.legend(loc="upper right", fontsize=8, frameon=True)
    return plotted_sides


def build_layer_figure(
    result: LayerAnalysisResult,
    *,
    bins: int,
    average_per_wire: bool,
    moving_average_window: int,
    side_filter: str | None = None,
    plot_mode: str = PLOT_MODE_WIRE_NUMBER,
):
    from matplotlib.figure import Figure

    side_filter = None if side_filter is None else str(side_filter).strip().upper()
    if side_filter is not None and side_filter not in SIDES:
        raise ValueError(f"Unsupported side {side_filter!r}; expected one of {SIDES}")
    plot_mode = str(plot_mode).strip()

    if plot_mode == PLOT_MODE_ENDPOINT_CATEGORIES:
        fig = Figure(figsize=(16, 10), constrained_layout=True)
        return _render_endpoint_categories_view(
            fig,
            result=result,
            average_per_wire=average_per_wire,
            moving_average_window=moving_average_window,
        )

    sides_to_plot = (side_filter,) if side_filter is not None else SIDES

    fig = Figure(figsize=(16, 8), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, width_ratios=[1.25, 1.0])
    profile_axis = fig.add_subplot(grid[:, 0])
    hist_axis = fig.add_subplot(grid[:, 1])

    colors = {"A": "tab:blue", "B": "tab:orange"}
    overlay_results = list(result.overlay_results or (result,))
    title_prefix = (
        f"Layer {result.layer}"
        if result.location_label is None
        else f"Layer {result.layer} ({result.location_label})"
    )
    if side_filter is not None:
        title_prefix = f"{title_prefix} Side {side_filter}"
    plotted_sides: list[str] = []
    profile_stats_lines: list[str] = []
    if plot_mode == PLOT_MODE_ENDPOINT_MAPPING:
        plotted_sides = _render_endpoint_mapping_view(
            profile_axis,
            overlay_results=overlay_results,
            sides_to_plot=sides_to_plot,
            average_per_wire=average_per_wire,
            side_filter=side_filter,
            title_prefix=title_prefix,
        )
    else:
        x_column = "wire_number" if plot_mode == PLOT_MODE_WIRE_NUMBER else plot_mode
        for location_index, location_result in enumerate(overlay_results):
            location_label = (
                location_result.location_label or f"Location {location_index + 1}"
            )
            linestyle = _location_line_style(location_index)
            for side in sides_to_plot:
                subset = location_result.cloud[
                    location_result.cloud["side"] == side
                ].copy()
                if subset.empty:
                    continue

                plotted_sides.append(side)
                _render_numeric_profile_cloud(
                    profile_axis,
                    subset=subset,
                    color=colors[side],
                    average_per_wire=average_per_wire,
                    x_column=x_column,
                )

                numeric_subset = (
                    subset[[x_column, "tension"]]
                    .apply(pd.to_numeric, errors="coerce")
                    .dropna()
                )
                numeric_subset = numeric_subset.sort_values(x_column)
                if not numeric_subset.empty:
                    profile_axis.plot(
                        numeric_subset[x_column],
                        _rolling_mean(
                            numeric_subset["tension"], window=moving_average_window
                        ),
                        linewidth=2.0,
                        alpha=0.9,
                        color=colors[side],
                        linestyle=linestyle,
                        label=location_label
                        if side_filter is not None
                        else f"{location_label} {side}",
                    )
                if plot_mode != PLOT_MODE_WIRE_NUMBER:
                    pearson_value, spearman_value = _correlation_stats(
                        subset, x_column=x_column
                    )
                    profile_stats_lines.append(
                        (
                            f"{location_label}: Pearson={pearson_value:.3f}, Spearman={spearman_value:.3f}"
                            if side_filter is not None
                            else f"{location_label} {side}: Pearson={pearson_value:.3f}, Spearman={spearman_value:.3f}"
                        )
                    )
    if plotted_sides:
        if plot_mode != PLOT_MODE_ENDPOINT_MAPPING:
            profile_axis.set_xlabel(PLOT_MODE_LABELS.get(plot_mode, "Wire Number"))
            profile_axis.set_ylabel("Scaled Tension (N)")
            profile_axis.set_title(
                f"{title_prefix}: {'Wire-Average' if average_per_wire else 'Sample'} "
                f"{PLOT_MODE_LABELS.get(plot_mode, 'Wire Number')} Correlation (location overlay)"
            )
            profile_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
            profile_axis.legend(loc="upper right", fontsize=8, frameon=True)
        profile_axis.text(
            0.015,
            0.98,
            (
                f"{title_prefix}: {'Wire-Average' if average_per_wire else 'Sample'} {PLOT_MODE_LABELS.get(plot_mode, 'Wire Number')} View"
                + (
                    f"\nGlobal raw mode={result.global_mode_value:.3f}"
                    if np.isfinite(result.global_mode_value)
                    else ""
                )
                + ("\n" + "\n".join(profile_stats_lines) if profile_stats_lines else "")
            ),
            transform=profile_axis.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.9},
        )
    else:
        profile_axis.set_title(
            f"{title_prefix}: {'Wire-Average' if average_per_wire else 'Sample'} "
            f"{PLOT_MODE_LABELS.get(plot_mode, 'Wire Number')} View"
        )

    values_by_location_and_side: dict[tuple[str, str], np.ndarray] = {}
    for location_index, location_result in enumerate(overlay_results):
        location_label = (
            location_result.location_label or f"Location {location_index + 1}"
        )
        for side in sides_to_plot:
            values = location_result.cloud.loc[
                location_result.cloud["side"] == side, "tension"
            ].astype("float64")
            values_by_location_and_side[(location_label, side)] = values.values

    all_values = np.concatenate(
        [values for values in values_by_location_and_side.values() if values.size]
    )
    if all_values.size:
        min_val = float(np.min(all_values))
        max_val = float(np.max(all_values))
    else:
        min_val = 0.0
        max_val = 1.0

    edges: int | list[float] = (
        np.linspace(min_val, max_val, bins + 1).tolist() if bins > 0 else 40
    )
    stats_lines: list[str] = []
    for location_index, location_result in enumerate(overlay_results):
        location_label = (
            location_result.location_label or f"Location {location_index + 1}"
        )
        linestyle = _location_line_style(location_index)
        for side in sides_to_plot:
            values = values_by_location_and_side.get(
                (location_label, side), np.asarray([], dtype="float64")
            )
            if values.size == 0:
                continue
            hist_axis.hist(
                values,
                bins=edges,
                histtype="step",
                linewidth=1.6,
                color=colors[side],
                linestyle=linestyle,
                label=location_label
                if side_filter is not None
                else f"{location_label} {side}",
            )
            mean = float(np.mean(values))
            std = float(np.std(values, ddof=0))
            mode = kde_mode(values)
            stats_lines.append(
                (
                    f"{location_label}: μ={mean:.3f}, mode={mode:.3f}, σ={std:.3f}, n={int(values.size)}"
                    if side_filter is not None
                    else f"{location_label} {side}: μ={mean:.3f}, mode={mode:.3f}, σ={std:.3f}, n={int(values.size)}"
                )
            )

    hist_axis.set_title(f"{title_prefix}: Scaled Tension Distribution")
    hist_axis.set_xlabel("Scaled Tension (N)")
    hist_axis.set_ylabel("Count")
    hist_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
    if stats_lines:
        hist_axis.legend(loc="upper right", fontsize=7, frameon=True)

    if stats_lines:
        hist_axis.text(
            0.98,
            0.97,
            "\n".join(stats_lines),
            transform=hist_axis.transAxes,
            fontsize=8,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9),
        )

    return fig


def _save_figure_with_padding(
    figure, destination, *, dpi: int, format: str | None = None
) -> None:
    figure.savefig(
        destination,
        dpi=dpi,
        format=format,
        bbox_inches="tight",
        pad_inches=0.2,
    )


def save_layer_plot(
    *,
    result: LayerAnalysisResult,
    bins: int,
    average_per_wire: bool,
    moving_average_window: int,
    side_filter: str | None = None,
    output_path: Path | None = None,
    plot_mode: str = PLOT_MODE_WIRE_NUMBER,
) -> None:
    if result.cloud.empty:
        return

    destination = result.output_path if output_path is None else output_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig = build_layer_figure(
        result,
        bins=bins,
        average_per_wire=average_per_wire,
        moving_average_window=moving_average_window,
        side_filter=side_filter,
        plot_mode=plot_mode,
    )
    _save_figure_with_padding(fig, destination, dpi=300)


def _layer_side_output_path(base_output_path: Path, side: str) -> Path:
    side = str(side).strip().upper()
    suffix = base_output_path.suffix or ".png"
    stem = (
        base_output_path.name[: -len(suffix)]
        if base_output_path.name.endswith(suffix)
        else base_output_path.stem
    )
    return base_output_path.with_name(f"{stem}_side{side}{suffix}")


def _empty_side_series() -> dict[str, pd.Series]:
    return {side: pd.Series(dtype="float64") for side in SIDES}


def _empty_side_counts() -> dict[str, pd.Series]:
    return {side: pd.Series(dtype="int64") for side in SIDES}


def compute_layer_analysis(
    options: AverageProfileCloudOptions,
    *,
    layer: str,
    location_filter: str | None = None,
) -> LayerAnalysisResult:
    options = normalize_options(options)
    layer = layer.upper()
    expected = expected_wire_range(layer)
    expected_wires = list(expected)
    db_path = _resolve_db_path(options)
    csv_files = (
        _index_csv_files(Path(options.csv_dir))
        if options.source == LEGACY_SOURCE
        else {}
    )
    exclude_re = (
        re.compile(options.exclude_apa_regex) if options.exclude_apa_regex else None
    )
    output_tag = f"{options.source}_{_build_output_tag_from_options(options)}"
    is_all_locations_view = bool(
        options.split_by_location
        and options.show_all_locations
        and location_filter is None
    )
    location_label = (
        "All locations"
        if is_all_locations_view
        else (None if location_filter is None else location_filter.title())
    )
    location_tag = (
        "all_locations"
        if is_all_locations_view
        else (None if location_filter is None else location_filter.replace(" ", "_"))
    )
    location_output_tag = (
        output_tag if location_tag is None else f"{output_tag}_{location_tag}"
    )

    summary_dir = data_path("tension_summaries")
    output_path = (
        Path(options.output_dir)
        / f"tension_profile_cloud_{layer}_{location_output_tag}.png"
    )
    profile_summary_path = (
        summary_dir / f"average_profile_{layer}_{location_output_tag}.csv"
    )
    scale_summary_path = (
        summary_dir / f"average_profile_scales_{layer}_{location_output_tag}.csv"
    )

    series_by_apa: dict[str, dict[str, pd.Series]] = {}
    load_stats: dict[str, dict[str, SideLoadResult]] = {}
    sources: dict[str, dict[str, str]] = {}

    db_apas = set(_list_layer_apas(db_path, layer, source=options.source))
    csv_apas = {apa for (apa, file_layer) in csv_files if file_layer == layer}
    for apa_name in sorted(db_apas | csv_apas):
        if exclude_re is not None and exclude_re.search(apa_name):
            continue

        csv_path = csv_files.get((apa_name, layer))
        side_results: dict[str, SideLoadResult] = {}
        included_sides: dict[str, pd.Series] = {}
        side_sources: dict[str, str] = {}

        for side in SIDES:
            db_result = SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)
            if apa_name in db_apas:
                if options.average_per_wire:
                    db_result = load_average_side_series(
                        db_path,
                        apa_name=apa_name,
                        layer=layer,
                        side=side,
                        expected_wires=expected,
                        source=options.source,
                        location_filter=location_filter,
                    )
                else:
                    db_result = load_latest_side_series(
                        db_path,
                        apa_name=apa_name,
                        layer=layer,
                        side=side,
                        expected_wires=expected,
                        source=options.source,
                        location_filter=location_filter,
                    )

            chosen = db_result
            chosen_source = options.source
            if (
                options.source == LEGACY_SOURCE
                and db_result.coverage < float(options.min_coverage)
                and csv_path is not None
            ):
                if options.average_per_wire:
                    csv_result = load_average_side_series_from_csv(
                        csv_path,
                        layer=layer,
                        side=side,
                        expected_wires=expected,
                    )
                else:
                    csv_result = load_latest_side_series_from_csv(
                        csv_path,
                        layer=layer,
                        side=side,
                        expected_wires=expected,
                    )
                if csv_result.coverage >= db_result.coverage:
                    chosen = csv_result
                    chosen_source = "csv"

            side_results[side] = chosen
            if chosen.coverage >= float(options.min_coverage):
                included_sides[side] = chosen.series
                side_sources[side] = chosen_source

        if not included_sides:
            continue

        series_by_apa[apa_name] = included_sides
        load_stats[apa_name] = side_results
        sources[apa_name] = side_sources

    if not series_by_apa:
        location_msg = "" if location_label is None else f" [{location_label}]"
        return LayerAnalysisResult(
            layer=layer,
            location_filter=location_filter,
            location_label=location_label,
            location_output_tag=location_output_tag,
            global_mode_value=float("nan"),
            cloud=pd.DataFrame(columns=["wire_number", "tension", "side", "apa_name"]),
            mu_by_side=_empty_side_series(),
            n_by_side=_empty_side_counts(),
            profile_df=pd.DataFrame(
                {
                    "wire_number": expected_wires,
                    "mu_A": np.nan,
                    "mu_B": np.nan,
                    "n_A": 0,
                    "n_B": 0,
                }
            ),
            scale_df=pd.DataFrame(
                columns=[
                    "apa_name",
                    "k",
                    "raw_mode",
                    "global_raw_mode",
                    "coverage_A",
                    "coverage_B",
                    "n_A",
                    "n_B",
                    "source_A",
                    "source_B",
                ]
            ),
            output_path=output_path,
            profile_summary_path=profile_summary_path,
            scale_summary_path=scale_summary_path,
            status_message=(
                f"Layer {layer}{location_msg}: no APA sides met min coverage {options.min_coverage}"
            ),
        )

    scale_factors: dict[str, float] = {}
    raw_mode_by_apa: dict[str, float] = {}
    if options.no_scaling:
        global_mode_value = float("nan")
        for apa_name in series_by_apa:
            scale_factors[apa_name] = 1.0
            raw_mode_by_apa[apa_name] = float("nan")
    else:
        raw_layer_parts = [
            result.series.to_numpy(dtype="float64")
            for apa_name in series_by_apa
            for result in load_stats[apa_name].values()
            if not result.series.empty
        ]
        if not raw_layer_parts:
            global_mode_value = float("nan")
            for apa_name in series_by_apa:
                scale_factors[apa_name] = 1.0
                raw_mode_by_apa[apa_name] = float("nan")
        else:
            raw_layer_values = np.concatenate(raw_layer_parts)
            global_mode_value = kde_mode(raw_layer_values)

            for apa_name in series_by_apa:
                apa_parts = [
                    result.series.to_numpy(dtype="float64")
                    for result in load_stats[apa_name].values()
                    if not result.series.empty
                ]
                if not apa_parts:
                    raw_mode_by_apa[apa_name] = float("nan")
                    scale_factors[apa_name] = 1.0
                    continue
                apa_values = np.concatenate(apa_parts)
                raw_mode_by_apa[apa_name] = kde_mode(apa_values)
                k = mode_scale_factor(
                    apa_values=apa_values,
                    global_mode_value=global_mode_value,
                )
                scale_factors[apa_name] = float("nan") if k is None else k

    mu_by_side, n_by_side = _compute_target_profiles(series_by_apa, scale_factors)

    for side in SIDES:
        mu_by_side[side] = mu_by_side.get(side, pd.Series(dtype="float64")).reindex(
            expected_wires
        )
        counts = n_by_side.get(side, pd.Series(dtype="int64")).reindex(expected_wires)
        n_by_side[side] = counts.fillna(0).astype("int64")

    profile_df = pd.DataFrame({"wire_number": expected_wires})
    profile_df["mu_A"] = mu_by_side["A"].values
    profile_df["mu_B"] = mu_by_side["B"].values
    profile_df["n_A"] = n_by_side["A"].values
    profile_df["n_B"] = n_by_side["B"].values

    scale_rows: list[dict[str, object]] = []
    for apa_name in sorted(series_by_apa):
        stats = load_stats[apa_name]
        scale_rows.append(
            {
                "apa_name": apa_name,
                "k": scale_factors.get(apa_name, float("nan")),
                "raw_mode": raw_mode_by_apa.get(apa_name, float("nan")),
                "global_raw_mode": global_mode_value,
                "coverage_A": stats["A"].coverage,
                "coverage_B": stats["B"].coverage,
                "n_A": stats["A"].wire_count,
                "n_B": stats["B"].wire_count,
                "source_A": sources.get(apa_name, {}).get("A", ""),
                "source_B": sources.get(apa_name, {}).get("B", ""),
            }
        )
    scale_df = pd.DataFrame(scale_rows)

    cloud = _make_cloud_dataframe(
        series_by_apa,
        scale_factors,
        average_per_wire=options.average_per_wire,
    )
    cloud = _enrich_cloud_with_uv_recipe_metadata(cloud, layer=layer)
    location_msg = "" if location_label is None else f" [{location_label}]"
    sides_present = tuple(
        sorted({str(side).strip().upper() for side in cloud.get("side", [])})
    )
    if options.split_by_side and sides_present:
        plot_paths = ", ".join(
            str(_layer_side_output_path(output_path, side))
            for side in sides_present
            if side in SIDES
        )
        status_message = (
            f"Layer {layer}{location_msg}: wrote {plot_paths} + {profile_summary_path}"
        )
    else:
        status_message = (
            f"Layer {layer}{location_msg}: wrote {output_path} + {profile_summary_path}"
            if not cloud.empty
            else f"Layer {layer}{location_msg}: computed empty cloud"
        )
    return LayerAnalysisResult(
        layer=layer,
        location_filter=location_filter,
        location_label=location_label,
        location_output_tag=location_output_tag,
        global_mode_value=global_mode_value,
        cloud=cloud,
        mu_by_side=mu_by_side,
        n_by_side=n_by_side,
        profile_df=profile_df,
        scale_df=scale_df,
        output_path=output_path,
        profile_summary_path=profile_summary_path,
        scale_summary_path=scale_summary_path,
        status_message=status_message,
    )


def compute_average_profile_results(
    options: AverageProfileCloudOptions | argparse.Namespace | Mapping[str, object],
) -> dict[str, list[LayerAnalysisResult]]:
    normalized = normalize_options(options)
    location_filters = _location_filters(normalized)
    # Process layers sequentially so that only one layer's measurement DataFrame
    # is live in the LRU cache at a time.  Parallel processing would load every
    # layer simultaneously, multiplying peak memory by the number of layers.
    results: dict[str, list[LayerAnalysisResult]] = {}
    for layer in normalized.layers:
        location_results = [
            compute_layer_analysis(normalized, layer=layer, location_filter=loc)
            for loc in location_filters
        ]
        if normalized.split_by_location and normalized.show_all_locations:
            results[layer] = [
                _build_all_locations_result(
                    layer=layer,
                    location_results=location_results,
                    options=normalized,
                ),
                *location_results,
            ]
        else:
            results[layer] = location_results
    return results


def export_layer_analysis(
    result: LayerAnalysisResult, options: AverageProfileCloudOptions
) -> None:
    options = normalize_options(options)
    result.profile_summary_path.parent.mkdir(parents=True, exist_ok=True)
    result.profile_df.to_csv(result.profile_summary_path, index=False)
    result.scale_df.to_csv(result.scale_summary_path, index=False)
    if not result.cloud.empty:
        if options.split_by_side:
            for side in SIDES:
                if not (result.cloud["side"] == side).any():
                    continue
                save_layer_plot(
                    result=result,
                    bins=int(options.bins),
                    average_per_wire=options.average_per_wire,
                    moving_average_window=int(options.moving_average_window),
                    side_filter=side,
                    output_path=_layer_side_output_path(result.output_path, side),
                )
        else:
            save_layer_plot(
                result=result,
                bins=int(options.bins),
                average_per_wire=options.average_per_wire,
                moving_average_window=int(options.moving_average_window),
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create anonymized average tension-profile point clouds by layer."
    )
    parser.add_argument(
        "--source",
        choices=[LEGACY_SOURCE, DUNEDB_SOURCE],
        default=LEGACY_SOURCE,
        help=(
            "Data source to use: 'legacy' reads tension_data.db plus CSV fallbacks, "
            "and 'dunedb' reads the downloaded SQLite export."
        ),
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "Optional override for the SQLite database path. Defaults to tension_data.db "
            "for legacy mode and the DUNE-db export for dunedb mode."
        ),
    )
    parser.add_argument(
        "--layers",
        default="X,V,U,G",
        help="Comma-separated list of layers to process (default: X,V,U,G).",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.5,
        help="Minimum per-side wire coverage required to include an APA side (default: 0.5).",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of target/scale refinement iterations (default: 3).",
    )
    parser.add_argument(
        "--exclude-apa-regex",
        default="(?i)TEST",
        help="Regex used to exclude APA names (default: (?i)TEST).",
    )
    parser.add_argument(
        "--csv-dir",
        default=str(data_path("tension_data")),
        help=(
            "Directory containing legacy tension_data_*.csv exports "
            "(used in legacy mode, default: dune_tension/data/tension_data)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str(data_path("tension_plots")),
        help="Directory for output PNGs (default: dune_tension/data/tension_plots).",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=40,
        help="Histogram bin count (default: 40).",
    )
    parser.add_argument(
        "--moving-average-window",
        type=int,
        default=15,
        help="Rolling window size for the trendline smoothing (default: 15).",
    )
    parser.add_argument(
        "--no-scaling",
        action="store_true",
        help="Skip average/mode normalization and plot the raw trimmed tensions.",
    )
    parser.add_argument(
        "--average-per-wire",
        action="store_true",
        help="Average repeated samples for each wire/side pair before plotting.",
    )
    parser.add_argument(
        "--split-by-location",
        action="store_true",
        help=(
            "For --source dunedb, write separate plot and summary files for the "
            "Chicago and Daresbury measuring locations."
        ),
    )
    parser.add_argument(
        "--show-all-locations",
        action="store_true",
        help=(
            "When used with --split-by-location, also add a combined view that overlays "
            "all locations on the same plot."
        ),
    )
    parser.add_argument(
        "--split-by-side",
        action="store_true",
        help="When set, write separate plot PNGs for sides A and B instead of a combined plot.",
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    options = normalize_options(parse_args(argv if argv is not None else sys.argv[1:]))
    for layer_results in compute_average_profile_results(options).values():
        for result in layer_results:
            if result.cloud.empty:
                print(result.status_message, file=sys.stderr)
                continue
            export_layer_analysis(result, options)
            print(result.status_message, file=sys.stderr)
    return 0


def main() -> None:
    raise SystemExit(run())
