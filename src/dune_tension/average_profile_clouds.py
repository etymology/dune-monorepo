from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.errors import ParserError
from scipy.stats import gaussian_kde

from dune_tension.data_cache import select_dataframe
from dune_tension.paths import data_path, tension_data_db_path


# Trim all tension values outside this band.
# This replaces the broader "plausible" filter for this analysis.
MIN_PLAUSIBLE_TENSION = 4.0
MAX_PLAUSIBLE_TENSION = 8.5
OLD_CSV_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"
SIDES = ("A", "B")


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
        raise ValueError(f"Unsupported layer {layer!r}; expected one of {sorted(ranges)}") from exc


@dataclass(frozen=True)
class SideLoadResult:
    series: pd.Series
    wire_count: int
    coverage: float


def kde_mode(values: np.ndarray) -> float:
    values = np.asarray(values, dtype="float64")
    values = values[np.isfinite(values)]
    if values.size == 0:
        return float("nan")
    if values.size == 1:
        return float(values[0])
    if np.allclose(values, values[0]):
        return float(values[0])

    try:
        kde = gaussian_kde(values)
    except Exception:
        return float(np.median(values))

    x_grid = np.linspace(float(values.min()), float(values.max()), 512)
    y = kde(x_grid)
    if y.size == 0 or not np.isfinite(y).any():
        return float(np.median(values))
    return float(x_grid[int(np.nanargmax(y))])


def mode_scale_factor(*, apa_values: np.ndarray, global_mode_value: float) -> float | None:
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


def _list_layer_apas(db_path: str, layer: str) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "select distinct apa_name from tension_data where layer = ? order by apa_name",
            (layer,),
        ).fetchall()
    return [str(row[0]) for row in rows]


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

    if "side" not in df.columns or "wire_number" not in df.columns or "tension" not in df.columns:
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
    df = df[(df["tension"] >= MIN_PLAUSIBLE_TENSION) & (df["tension"] <= MAX_PLAUSIBLE_TENSION)]
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    sort_cols = ["time"] if df["time"].notna().any() else ["_row"]
    df = df.sort_values(sort_cols).drop_duplicates(subset="wire_number", keep="last").sort_values("wire_number")
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

    if "side" not in df.columns or "wire_number" not in df.columns or "tension" not in df.columns:
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
    df = df[(df["tension"] >= MIN_PLAUSIBLE_TENSION) & (df["tension"] <= MAX_PLAUSIBLE_TENSION)]
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
) -> SideLoadResult:
    measurements = select_dataframe(
        db_path,
        where_clause="apa_name = ? AND layer = ? AND side = ?",
        params=(apa_name, layer, side),
        columns=("wire_number", "tension", "time"),
    )
    if measurements.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df = measurements.copy()
    df["wire_number"] = pd.to_numeric(df["wire_number"], errors="coerce")
    df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["wire_number", "tension", "time"])
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df["wire_number"] = df["wire_number"].astype(int)
    expected_set = set(expected_wires)
    df = df[df["wire_number"].isin(expected_set)]
    df = df[(df["tension"] >= MIN_PLAUSIBLE_TENSION) & (df["tension"] <= MAX_PLAUSIBLE_TENSION)]
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df = (
        df.sort_values("time")
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
) -> SideLoadResult:
    measurements = select_dataframe(
        db_path,
        where_clause="apa_name = ? AND layer = ? AND side = ?",
        params=(apa_name, layer, side),
        columns=("wire_number", "tension"),
    )
    if measurements.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df = measurements.copy()
    df["wire_number"] = pd.to_numeric(df["wire_number"], errors="coerce")
    df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
    df = df.dropna(subset=["wire_number", "tension"])
    if df.empty:
        return SideLoadResult(pd.Series(dtype="float64"), 0, 0.0)

    df["wire_number"] = df["wire_number"].astype(int)
    expected_set = set(expected_wires)
    df = df[df["wire_number"].isin(expected_set)]
    df = df[(df["tension"] >= MIN_PLAUSIBLE_TENSION) & (df["tension"] <= MAX_PLAUSIBLE_TENSION)]
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
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for apa_name, sides in series_by_apa.items():
        k = float(scale_factors.get(apa_name, np.nan))
        if not np.isfinite(k):
            continue
        for side, series in sides.items():
            if series.empty:
                continue
            scaled = (series * k).groupby(level=0).mean().rename("tension").reset_index()
            scaled.columns = ["wire_number", "tension"]
            scaled["side"] = side
            scaled["apa_name"] = apa_name
            frames.append(scaled)
    if not frames:
        return pd.DataFrame(columns=["wire_number", "tension", "side", "apa_name"])
    return pd.concat(frames, ignore_index=True)


def _rolling_mean(values: pd.Series, window: int = 15) -> pd.Series:
    return values.rolling(window=window, center=True, min_periods=1).mean()


def save_layer_plot(
    *,
    layer: str,
    cloud: pd.DataFrame,
    mu_by_side: dict[str, pd.Series],
    output_path: Path,
    bins: int,
    global_mode_value: float,
) -> None:
    if cloud.empty:
        return

    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    scatter_axis, hist_axis = axes

    colors = {"A": "tab:blue", "B": "tab:orange"}

    for side in SIDES:
        subset = cloud[cloud["side"] == side].copy()
        if subset.empty:
            continue

        apa_count = int(subset["apa_name"].nunique())
        point_count = int(len(subset))
        side_values = subset["tension"].astype("float64").to_numpy()
        side_mean = float(np.mean(side_values)) if side_values.size else float("nan")
        side_mode = kde_mode(side_values) if side_values.size else float("nan")
        scatter_axis.scatter(
            subset["wire_number"],
            subset["tension"],
            s=10,
            alpha=0.15,
            color=colors[side],
            label=(
                f"Side {side} (APAs={apa_count}, points={point_count}, "
                f"μ={side_mean:.3f}, mode={side_mode:.3f})"
            ),
        )

        mu = mu_by_side.get(side, pd.Series(dtype="float64"))
        mu_frame = mu.rename("mu").reset_index()
        if not mu_frame.empty:
            mu_frame.columns = ["wire_number", "mu"]
            mu_frame = mu_frame.dropna(subset=["mu"]).sort_values("wire_number")
            if not mu_frame.empty:
                scatter_axis.plot(
                    mu_frame["wire_number"],
                    _rolling_mean(mu_frame["mu"]),
                    linewidth=2.0,
                    alpha=0.9,
                    color=colors[side],
                )

    scatter_axis.set_title(f"Layer {layer}: Normalized Tension Profile Cloud")
    scatter_axis.set_xlabel("Wire Number")
    scatter_axis.set_ylabel("Scaled Tension (N)")
    scatter_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
    scatter_axis.legend(fontsize=8, loc="upper right")
    if np.isfinite(global_mode_value):
        scatter_axis.text(
            0.015,
            0.98,
            f"Global raw mode={global_mode_value:.3f}",
            transform=scatter_axis.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.9},
        )

    values_by_side: dict[str, np.ndarray] = {}
    for side in SIDES:
        values = cloud.loc[cloud["side"] == side, "tension"].astype("float64")
        values_by_side[side] = values.values

    all_values = np.concatenate([values for values in values_by_side.values() if values.size])
    if all_values.size:
        min_val = float(np.min(all_values))
        max_val = float(np.max(all_values))
    else:
        min_val = 0.0
        max_val = 1.0

    edges = np.linspace(min_val, max_val, bins + 1) if bins > 0 else 40
    stats_lines: list[str] = []
    for side in SIDES:
        values = values_by_side[side]
        if values.size == 0:
            continue
        hist_axis.hist(values, bins=edges, histtype="step", linewidth=1.6, color=colors[side])
        mean = float(np.mean(values))
        std = float(np.std(values, ddof=0))
        mode = kde_mode(values)
        hist_axis.axvline(mean, color=colors[side], linewidth=1.2, alpha=0.8)
        stats_lines.append(
            f"{side}: μ={mean:.3f}, mode={mode:.3f}, σ={std:.3f}, n={int(values.size)}"
        )

    hist_axis.set_title("Scaled Tension Distribution")
    hist_axis.set_xlabel("Scaled Tension (N)")
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
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.9),
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create anonymized average tension-profile point clouds by layer."
    )
    parser.add_argument(
        "--db-path",
        default=str(tension_data_db_path()),
        help="Path to the SQLite database storing tension measurements.",
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
        help="Directory containing legacy tension_data_*.csv exports (default: dune_tension/data/tension_data).",
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
        "--no-scaling",
        action="store_true",
        help="Skip average/mode normalization and plot the raw trimmed tensions.",
    )
    parser.add_argument(
        "--average-per-wire",
        action="store_true",
        help="Average repeated samples for each wire/side pair before plotting.",
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    layers = _parse_layers(args.layers)
    exclude_re = re.compile(args.exclude_apa_regex) if args.exclude_apa_regex else None
    csv_dir = Path(args.csv_dir)
    csv_files = _index_csv_files(csv_dir)

    summary_dir = data_path("tension_summaries")
    summary_dir.mkdir(parents=True, exist_ok=True)

    for layer in layers:
        expected = expected_wire_range(layer)
        expected_wires = list(expected)

        series_by_apa: dict[str, dict[str, pd.Series]] = {}
        load_stats: dict[str, dict[str, SideLoadResult]] = {}
        sources: dict[str, dict[str, str]] = {}

        db_apas = set(_list_layer_apas(args.db_path, layer))
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
                    if args.average_per_wire:
                        db_result = load_average_side_series(
                            args.db_path,
                            apa_name=apa_name,
                            layer=layer,
                            side=side,
                            expected_wires=expected,
                        )
                    else:
                        db_result = load_latest_side_series(
                            args.db_path,
                            apa_name=apa_name,
                            layer=layer,
                            side=side,
                            expected_wires=expected,
                        )

                chosen = db_result
                chosen_source = "db"
                if db_result.coverage < float(args.min_coverage) and csv_path is not None:
                    if args.average_per_wire:
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
                if chosen.coverage >= float(args.min_coverage):
                    included_sides[side] = chosen.series
                    side_sources[side] = chosen_source

            if not included_sides:
                continue

            series_by_apa[apa_name] = included_sides
            load_stats[apa_name] = side_results
            sources[apa_name] = side_sources

        if not series_by_apa:
            print(f"Layer {layer}: no APA sides met min coverage {args.min_coverage}", file=sys.stderr)
            continue

        scale_factors: dict[str, float] = {}
        raw_mode_by_apa: dict[str, float] = {}
        if args.no_scaling:
            global_mode_value = float("nan")
            for apa_name in series_by_apa:
                scale_factors[apa_name] = 1.0
                raw_mode_by_apa[apa_name] = float("nan")
        else:
            # Scaling is intentionally computed once per (APA, layer) and then applied
            # to both sides, preserving any A/B tension differences after normalization.
            # To make that robust even when one side is partially scanned, we compute
            # KDE modes using *all available* raw samples from both sides for each APA
            # (even if a side is not included in the point cloud due to min-coverage).
            raw_layer_values = np.concatenate(
                [
                    result.series.to_numpy(dtype="float64")
                    for apa_name in series_by_apa
                    for result in load_stats[apa_name].values()
                    if not result.series.empty
                ]
            )
            global_mode_value = kde_mode(raw_layer_values)

            for apa_name in series_by_apa:
                apa_values = np.concatenate(
                    [
                        result.series.to_numpy(dtype="float64")
                        for result in load_stats[apa_name].values()
                        if not result.series.empty
                    ]
                )
                raw_mode_by_apa[apa_name] = kde_mode(apa_values)
                k = mode_scale_factor(
                    apa_values=apa_values,
                    global_mode_value=global_mode_value,
                )
                scale_factors[apa_name] = float("nan") if k is None else k

        mu_by_side, n_by_side = _compute_target_profiles(series_by_apa, scale_factors)

        for side in SIDES:
            mu_by_side[side] = mu_by_side.get(side, pd.Series(dtype="float64")).reindex(expected_wires)
            counts = n_by_side.get(side, pd.Series(dtype="int64")).reindex(expected_wires)
            n_by_side[side] = counts.fillna(0).astype("int64")

        profile_df = pd.DataFrame({"wire_number": expected_wires})
        profile_df["mu_A"] = mu_by_side["A"].values
        profile_df["mu_B"] = mu_by_side["B"].values
        profile_df["n_A"] = n_by_side["A"].values
        profile_df["n_B"] = n_by_side["B"].values
        profile_df.to_csv(summary_dir / f"average_profile_{layer}.csv", index=False)

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
        pd.DataFrame(scale_rows).to_csv(
            summary_dir / f"average_profile_scales_{layer}.csv",
            index=False,
        )

        cloud = _make_cloud_dataframe(series_by_apa, scale_factors)
        output_path = Path(args.output_dir) / f"tension_profile_cloud_{layer}.png"
        save_layer_plot(
            layer=layer,
            cloud=cloud,
            mu_by_side=mu_by_side,
            output_path=output_path,
            bins=int(args.bins),
            global_mode_value=global_mode_value,
        )

        print(
            f"Layer {layer}: wrote {output_path} + {summary_dir / f'average_profile_{layer}.csv'}",
            file=sys.stderr,
        )

    return 0


def main() -> None:
    raise SystemExit(run())
