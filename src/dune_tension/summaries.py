import os
from typing import Dict, List

import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.figure import Figure

from dune_tension.data_cache import select_dataframe
from dune_tension.paths import data_path
from dune_tension.tension_calculation import tension_plausible
from dune_tension.tensiometer_functions import TensiometerConfig


def get_expected_range(layer: str) -> range:
    """Return the expected wire range for a given layer."""
    ranges = {
        "U": range(8, 1147),
        "V": range(8, 1147),
        "X": range(1, 481),
        "G": range(1, 482),
    }
    return ranges.get(layer, range(0))


def _select_summary_rows(
    config: TensiometerConfig, measurements: pd.DataFrame
) -> Dict[str, pd.DataFrame]:
    """Return the latest plausible measurement per wire for each side."""

    selected_rows: Dict[str, pd.DataFrame] = {
        "A": measurements.iloc[0:0].copy(),
        "B": measurements.iloc[0:0].copy(),
    }
    expected_set = set(get_expected_range(config.layer))

    for side in ["A", "B"]:
        side_df = measurements[measurements["side"] == side].copy()
        if side_df.empty:
            continue

        side_df["wire_number"] = pd.to_numeric(side_df["wire_number"], errors="coerce")
        side_df["tension"] = pd.to_numeric(side_df["tension"], errors="coerce")
        side_df["time"] = pd.to_datetime(side_df["time"], errors="coerce")
        side_df = side_df.dropna(subset=["wire_number", "tension"])
        if side_df.empty:
            continue

        side_df["wire_number"] = side_df["wire_number"].astype(int)
        side_df = side_df[side_df["wire_number"].isin(expected_set)]
        side_df = side_df[side_df["tension"].apply(tension_plausible)]
        if side_df.empty:
            continue

        selected_rows[side] = (
            side_df.sort_values("time")
            .drop_duplicates(subset="wire_number", keep="last")
            .sort_values("wire_number")
        )

    return selected_rows


def _compute_tensions(
    config: TensiometerConfig, measurements: pd.DataFrame
) -> tuple[
    Dict[str, Dict[int, float]],
    List[pd.DataFrame],
    List[pd.DataFrame],
    Dict[str, List[int]],
]:
    """Return tension series and plotting DataFrames grouped by side."""
    tension_series: Dict[str, Dict[int, float]] = {"A": {}, "B": {}}
    line_data: List[pd.DataFrame] = []
    histogram_data: List[pd.DataFrame] = []
    missing_wires: Dict[str, List[int]] = {"A": [], "B": []}

    expected = get_expected_range(config.layer)
    expected_set = set(expected)
    selected_rows = _select_summary_rows(config, measurements)

    for side in ["A", "B"]:
        selected = selected_rows[side]
        if selected.empty:
            tension_series[side] = {}
            missing_wires[side] = sorted(expected_set)
            continue

        measured_wire_tensions = (
            selected.set_index("wire_number")["tension"].astype(float).to_dict()
        )
        tension_series[side] = measured_wire_tensions
        missing_wires[side] = sorted(expected_set - set(measured_wire_tensions))

        side_label = f"Side {side}"
        line_data.append(
            selected[["wire_number", "tension"]].assign(side_label=side_label)
        )
        histogram_data.append(selected[["tension"]].assign(side_label=side_label))
    return tension_series, line_data, histogram_data, missing_wires


def _compute_tension_stats(tensions: np.ndarray) -> dict:
    """Return mean, sigma, and PDF mode (KDE peak) for a tension array."""
    tensions = tensions[np.isfinite(tensions)]
    if tensions.size < 2:
        return {"mean": np.nan, "sigma": np.nan, "mode": np.nan}
    mean = float(np.mean(tensions))
    sigma = float(np.std(tensions, ddof=1))
    from scipy.stats import gaussian_kde
    kde = gaussian_kde(tensions)
    # Evaluate KDE on fine grid between min and max
    x_grid = np.linspace(tensions.min(), tensions.max(), 1000)
    mode = float(x_grid[np.argmax(kde(x_grid))])
    return {"mean": mean, "sigma": sigma, "mode": mode}


def _load_summary_measurements(config: TensiometerConfig) -> pd.DataFrame:
    """Return summary measurements for one APA/layer."""

    return select_dataframe(
        config.data_path,
        where_clause="apa_name = ? AND layer = ?",
        params=(config.apa_name, config.layer),
    )


def get_tension_series(config: TensiometerConfig) -> Dict[str, Dict[int, float]]:
    """Return the per-wire tension series used for summaries and condition scans."""

    measurements = _load_summary_measurements(config)
    tension_series, _, _, _ = _compute_tensions(config, measurements)
    return tension_series


def write_summary_csv(tension_series: Dict[str, Dict[int, float]], path: str) -> None:
    """Write tension summary CSV for both sides."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    all_wires = sorted(
        set(tension_series["A"].keys()) | set(tension_series["B"].keys())
    )
    df = pd.DataFrame(
        {
            "wire_number": all_wires,
            "A": [tension_series["A"].get(w, np.nan) for w in all_wires],
            "B": [tension_series["B"].get(w, np.nan) for w in all_wires],
        }
    )
    df.to_csv(path, index=False)


def save_plot(
    line_data: List[pd.DataFrame],
    histogram_data: List[pd.DataFrame],
    apa_name: str,
    layer: str,
    output_dir: str,
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    figure = build_summary_plot_figure(
        line_data,
        histogram_data,
        apa_name,
        layer,
    )
    if figure is None:
        return
    figure.savefig(
        os.path.join(output_dir, f"tension_plot_{apa_name}_{layer}.png"),
        dpi=300,
    )


def build_summary_plot_figure(
    line_data: List[pd.DataFrame],
    histogram_data: List[pd.DataFrame],
    apa_name: str,
    layer: str,
    *,
    figsize: tuple[float, float] = (14, 10),
) -> Figure | None:
    """Build the summary plot figure used by both saved images and the live GUI."""

    if not line_data or not histogram_data:
        return None

    line_df = pd.concat(line_data)
    hist_df = pd.concat(histogram_data)

    figure = Figure(figsize=figsize)
    scatter_axis = figure.add_subplot(2, 2, 1)
    hist_axis = figure.add_subplot(2, 2, 2)
    resid_axis = figure.add_subplot(2, 2, 3)
    resid_hist_axis = figure.add_subplot(2, 2, 4)

    resid_data: List[pd.DataFrame] = []

    for side_label, group in line_df.groupby("side_label"):
        scatter_axis.scatter(
            group["wire_number"],
            group["tension"],
            label=side_label,
            alpha=0.5,
            s=10,
        )
        sorted_group = group.sort_values("wire_number")
        moving_average = sorted_group["tension"].rolling(window=15, center=True).mean()
        scatter_axis.plot(
            sorted_group["wire_number"],
            moving_average,
            alpha=0.4,
            linewidth=2,
        )

        rolling_mean = sorted_group["tension"].rolling(window=20, center=True, min_periods=20).mean()
        if rolling_mean.notna().any():
            first_valid = rolling_mean.first_valid_index()
            last_valid = rolling_mean.last_valid_index()
            rolling_mean = rolling_mean.copy()
            rolling_mean.loc[:first_valid] = rolling_mean.loc[first_valid]
            rolling_mean.loc[last_valid:] = rolling_mean.loc[last_valid]
        residuals = sorted_group["tension"] - rolling_mean

        resid_axis.scatter(
            sorted_group["wire_number"],
            residuals,
            label=side_label,
            alpha=0.5,
            s=10,
        )
        resid_data.append(
            pd.DataFrame({"residual": residuals, "side_label": side_label})
        )

    scatter_axis.set_title(
        f"{apa_name} - Tension Scatter Plot with Trendline - Layer {layer}"
    )
    scatter_axis.set_xlabel("Wire Number")
    scatter_axis.set_ylabel("Tension")
    scatter_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
    scatter_axis.legend()

    sns.histplot(
        data=hist_df,
        x="tension",
        hue="side_label",
        element="step",
        stat="count",
        common_norm=False,
        ax=hist_axis,
    )
    hist_axis.set_title(f"{apa_name} - Tension Histogram - Layer {layer}")
    hist_axis.set_xlabel("Tension")
    hist_axis.set_ylabel("Count")
    hist_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")

    # Add mean, sigma, and PDF mode statistics per side
    import matplotlib.pyplot as plt
    stats_text_parts = []
    for side_label, group in hist_df.groupby("side_label"):
        stats = _compute_tension_stats(group["tension"].values)
        if np.isfinite(stats["mean"]):
            # Build stats text for this side
            stats_text_parts.append(
                f"{side_label}: μ={stats['mean']:.2f}, σ={stats['sigma']:.2f}, mode={stats['mode']:.2f}"
            )

    # Add a text box with all stats in the upper right
    if stats_text_parts:
        stats_text = "\n".join(stats_text_parts)
        hist_axis.text(
            0.98,
            0.97,
            stats_text,
            transform=hist_axis.transAxes,
            fontsize=7,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

    resid_axis.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    resid_axis.set_title(f"{apa_name} - Residuals from Moving Average - Layer {layer}")
    resid_axis.set_xlabel("Wire Number")
    resid_axis.set_ylabel("Residual")
    resid_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
    resid_axis.legend()

    if resid_data:
        resid_df = pd.concat(resid_data)
        sns.histplot(
            data=resid_df,
            x="residual",
            hue="side_label",
            element="step",
            stat="count",
            common_norm=False,
            ax=resid_hist_axis,
        )

        # Add sigma statistics for residuals per side (mean is always 0 by construction)
        resid_stats_text_parts = []
        for side_label, group in resid_df.groupby("side_label"):
            resid_stats = _compute_tension_stats(group["residual"].values)
            if np.isfinite(resid_stats["sigma"]):
                # Build stats text for this side (only sigma, as mean is 0 by construction)
                resid_stats_text_parts.append(
                    f"{side_label}: σ={resid_stats['sigma']:.2f}"
                )

        # Add a text box with residual stats in the upper right
        if resid_stats_text_parts:
            resid_stats_text = "\n".join(resid_stats_text_parts)
            resid_hist_axis.text(
                0.98,
                0.97,
                resid_stats_text,
                transform=resid_hist_axis.transAxes,
                fontsize=7,
                verticalalignment="top",
                horizontalalignment="right",
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
            )

    resid_hist_axis.axvline(0, color="gray", linewidth=0.8, linestyle="--")
    resid_hist_axis.set_title(f"{apa_name} - Residual Histogram - Layer {layer}")
    resid_hist_axis.set_xlabel("Residual")
    resid_hist_axis.set_ylabel("Count")
    resid_hist_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")

    figure.tight_layout()
    return figure


def build_summary_plot_figure_for_config(
    config: TensiometerConfig,
    *,
    figsize: tuple[float, float] = (14, 5),
) -> Figure | None:
    """Build the current summary figure for ``config`` from persisted results."""

    measurements = _load_summary_measurements(config)
    _, line_data, histogram_data, _ = _compute_tensions(config, measurements)
    return build_summary_plot_figure(
        line_data,
        histogram_data,
        config.apa_name,
        config.layer,
        figsize=figsize,
    )


def write_missing_wires(
    path: str, apa: str, layer: str, missing: Dict[str, List[int]]
) -> None:
    """Write a simple log of wires with no measurements."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for side in ["A", "B"]:
            wires = missing.get(side, [])
            f.write(f"{apa} - Layer {layer}, Side {side}:\n")
            if wires:
                f.write("  Missing wire_numbers: " + ", ".join(map(str, wires)) + "\n")
            else:
                f.write("  All wires measured\n")
        f.write("\n")


def _order_missing_wires(missing: List[int], measured: List[int]) -> List[int]:
    """Return ``missing`` ordered close to ``measured`` then by proximity."""
    if not missing:
        return []

    if measured:
        start = min(
            missing,
            key=lambda w: (min(abs(w - m) for m in measured), w),
        )
    else:
        start = min(missing)

    remaining = set(missing)
    ordered = [start]
    remaining.remove(start)
    current = start

    while remaining:
        next_wire = min(remaining, key=lambda w: (abs(w - current), w))
        ordered.append(next_wire)
        remaining.remove(next_wire)
        current = next_wire

    return ordered


def update_tension_logs(config: TensiometerConfig) -> Dict[str, str]:
    """Generate summary CSV, plot and missing wire log for ``config``."""
    measurements = _load_summary_measurements(config)

    tension_series, line_data, histogram_data, missing_wires = _compute_tensions(
        config, measurements
    )

    output_dir = str(data_path("tension_plots"))
    summary_path = str(
        data_path(
            "tension_summaries",
            f"tension_summary_{config.apa_name}_{config.layer}.csv",
        )
    )
    bad_path = str(
        data_path("badwires", f"badwires_{config.apa_name}_{config.layer}.txt")
    )

    write_summary_csv(tension_series, summary_path)
    save_plot(line_data, histogram_data, config.apa_name, config.layer, output_dir)
    write_missing_wires(bad_path, config.apa_name, config.layer, missing_wires)

    return {
        "badwires": bad_path,
        "tension_summary_csv": summary_path,
        "plot_image": os.path.join(
            output_dir, f"tension_plot_{config.apa_name}_{config.layer}.png"
        ),
    }


def get_missing_wires(config: TensiometerConfig) -> Dict[str, List[int]]:
    """Return missing wire numbers for each side for ``config``."""

    measurements = _load_summary_measurements(config)

    _, _, _, missing_wires = _compute_tensions(config, measurements)

    return missing_wires
