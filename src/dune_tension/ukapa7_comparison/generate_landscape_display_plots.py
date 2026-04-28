from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dune_tension.ukapa7_comparison.compare_b_index_models import build_model_comparison
from dune_tension.ukapa7_comparison.compare_partial_b_offsets import (
    evaluate_shift,
    find_best_shift,
    load_partial_b,
)
from dune_tension.ukapa7_comparison.compare_tension_sources import (
    build_comparison_frame,
)


def _rolling_mean(series: pd.Series, window: int = 15) -> pd.Series:
    return series.rolling(window=window, center=True, min_periods=1).mean()


def _kde_mode(values: np.ndarray) -> float:
    cleaned = values[np.isfinite(values)]
    if cleaned.size < 2:
        return float("nan")

    try:
        from scipy.stats import gaussian_kde
    except Exception:
        # Fallback: use the center of the most-populated histogram bin.
        counts, edges = np.histogram(cleaned, bins=30)
        if not counts.size:
            return float("nan")
        idx = int(np.argmax(counts))
        return float((edges[idx] + edges[idx + 1]) / 2.0)

    kde = gaussian_kde(cleaned)
    x_grid = np.linspace(cleaned.min(), cleaned.max(), 1000)
    return float(x_grid[int(np.argmax(kde(x_grid)))])


def _stats_text(values: pd.Series) -> str:
    arr = values.to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return "μ=nan, σ=nan, mode=nan, min=nan, max=nan"
    mean = float(np.mean(arr))
    sigma = float(np.std(arr, ddof=1))
    mode = _kde_mode(arr)
    return f"μ={mean:.2f}, σ={sigma:.2f}, mode={mode:.2f}, min={arr.min():.2f}, max={arr.max():.2f}"


def _plot_side_raw(
    axes: np.ndarray,
    wire_numbers: pd.Series,
    chicago: pd.Series,
    uk: pd.Series,
    *,
    side: str,
    layer: str,
) -> None:
    top_ax = axes[0]
    bottom_ax = axes[1]

    pairs = [
        ("tab:blue", f"Chicago {side}", chicago),
        ("tab:orange", f"UK {side}", uk),
    ]
    for color, name, values in pairs:
        label = f"{name} ({_stats_text(values)})"
        top_ax.scatter(wire_numbers, values, s=10, alpha=0.4, color=color)
        top_ax.plot(
            wire_numbers,
            _rolling_mean(values.reset_index(drop=True), window=3),
            linewidth=1.2,
            color=color,
            label=label,
        )
        bottom_ax.hist(values, bins=30, alpha=0.35, color=color, label=label)
        bottom_ax.axvline(float(values.mean()), color=color, linewidth=1.5)

    top_ax.set_title(f"UKAPA7 Layer {layer} Side {side} Raw Tensions")
    top_ax.set_xlabel("Wire Number")
    top_ax.set_ylabel("Tension (N)")
    top_ax.grid(True, linestyle=":", linewidth=0.5, color="gray")
    top_ax.legend(fontsize=8, loc="upper right")

    bottom_ax.set_title("Distribution")
    bottom_ax.set_xlabel("Tension (N)")
    bottom_ax.set_ylabel("Count")
    bottom_ax.grid(True, linestyle=":", linewidth=0.5, color="gray")
    bottom_ax.legend(fontsize=8, loc="upper left")


def _best_b_mapping(
    *,
    layer: str,
    action_json: Path,
    summary_csv: Path,
) -> tuple[pd.DataFrame, str]:
    """Return the best-available B-side mapping dataframe and a short model label."""

    if layer.upper() == "G":
        b_models, b_stats = build_model_comparison(action_json, summary_csv, -60, 60)
        corrected_model = next(
            model
            for model in b_stats["model"].tolist()
            if model.startswith("reversed_shift_")
        )
        best_shift = int(
            b_stats.loc[b_stats["model"] == corrected_model, "best_shift"].iloc[0]
        )
        corrected_df = b_models[b_models["model"] == corrected_model].copy()
        corrected_df = corrected_df.sort_values("wire_number").reset_index(drop=True)
        return corrected_df, f"reversed+shift {best_shift:+d}"

    if layer.upper() == "U":
        merged, json_values = load_partial_b(action_json, summary_csv)
        _stats_df, _baseline_row, best_shift = find_best_shift(
            merged, json_values, -80, 80
        )
        corrected_df, _stats = evaluate_shift(merged, json_values, best_shift)
        corrected_df = corrected_df.sort_values("wire_number").reset_index(drop=True)
        return corrected_df, f"shift {best_shift:+d}"

    raise ValueError(f"Unsupported layer for best B mapping: {layer!r}")


def save_layer_landscape_plot(
    *,
    action_json: Path,
    summary_csv: Path,
    layer: str,
    output_path: Path,
) -> None:
    comparison = build_comparison_frame(action_json, summary_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(16, 9),
        sharex=False,
        sharey=False,
        constrained_layout=True,
    )

    for col, side in enumerate(("A", "B")):
        if side == "B":
            corrected_df, _model_label = _best_b_mapping(
                layer=layer, action_json=action_json, summary_csv=summary_csv
            )
            subset = corrected_df[["wire_number", "summary_B", "json_B"]].dropna()
            chicago_series = subset["summary_B"]
            uk_series = subset["json_B"]
        else:
            subset = comparison[["wire_number", "summary_A", "json_A"]].dropna()
            chicago_series = subset["summary_A"]
            uk_series = subset["json_A"]
        if subset.empty:
            axes[0, col].text(
                0.5,
                0.5,
                f"No overlapping data for side {side}",
                ha="center",
                va="center",
                transform=axes[0, col].transAxes,
                fontsize=12,
            )
            axes[0, col].set_axis_off()
            axes[1, col].set_axis_off()
            continue

        _plot_side_raw(
            axes[:, col],
            subset["wire_number"],
            chicago_series,
            uk_series,
            side=side,
            layer=layer,
        )

    fig.suptitle(f"UKAPA7 Layer {layer}: Chicago vs UK (A left, B right)")
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def _plot_layer_residuals(
    axes: np.ndarray,
    comparison: pd.DataFrame,
    *,
    layer: str,
    corrected_b: pd.DataFrame | None = None,
) -> None:
    top_ax = axes[0]
    bottom_ax = axes[1]
    colors = {"A": "tab:blue", "B": "tab:green"}

    plotted = False
    for side in ("A", "B"):
        if side == "B" and corrected_b is not None:
            subset = corrected_b[["wire_number", "residual_B"]].dropna().copy()
            subset = subset.rename(columns={"residual_B": "residual"})
        else:
            subset = comparison[["wire_number", f"diff_{side}"]].dropna().copy()
            subset = subset.rename(columns={f"diff_{side}": "residual"})
        if subset.empty:
            continue
        plotted = True
        residual = subset["residual"]
        label = f"Side {side} ({_stats_text(residual)})"
        top_ax.scatter(
            subset["wire_number"],
            residual,
            s=10,
            alpha=0.25,
            color=colors[side],
        )
        top_ax.plot(
            subset["wire_number"],
            _rolling_mean(residual.reset_index(drop=True)),
            linewidth=2,
            color=colors[side],
            label=label,
        )
        bottom_ax.hist(
            residual,
            bins=30,
            alpha=0.35,
            color=colors[side],
            label=label,
        )
        # Intentionally omit vertical reference lines for display clarity.

    if not plotted:
        top_ax.text(
            0.5,
            0.5,
            "No overlapping residual data",
            ha="center",
            va="center",
            transform=top_ax.transAxes,
            fontsize=12,
        )
        top_ax.set_axis_off()
        bottom_ax.set_axis_off()
        return

    top_ax.axhline(0.0, color="black", linestyle="--", linewidth=1)
    top_ax.set_title(f"Layer {layer} Change in Tension by Wire (Chicago - UK)")
    top_ax.set_xlabel("Wire Number")
    top_ax.set_ylabel("Change in Tension (N)")
    top_ax.grid(True, linestyle=":", linewidth=0.5, color="gray")
    top_ax.legend(fontsize=8, loc="upper right")

    bottom_ax.set_title("Change in Tension Distribution")
    bottom_ax.set_xlabel("Change in Tension (N)")
    bottom_ax.set_ylabel("Count")
    bottom_ax.grid(True, linestyle=":", linewidth=0.5, color="gray")
    bottom_ax.legend(fontsize=8, loc="upper left")


def save_layer_change_in_tension_plot(
    *,
    action_json: Path,
    summary_csv: Path,
    layer: str,
    output_path: Path,
) -> None:
    """Save a 2x1 change-in-tension plot for a single layer, using best B mapping."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    comp = build_comparison_frame(action_json, summary_csv)
    corrected_b, _model = _best_b_mapping(
        layer=layer, action_json=action_json, summary_csv=summary_csv
    )

    fig, axes = plt.subplots(2, 1, figsize=(16, 9), constrained_layout=True)
    _plot_layer_residuals(axes, comp, layer=layer, corrected_b=corrected_b)
    fig.suptitle(f"UKAPA7 Layer {layer}: Change in Tension (Chicago - UK)")
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def save_residuals_g_vs_u_landscape_plot(
    *,
    action_json_g: Path,
    summary_csv_g: Path,
    action_json_u: Path,
    summary_csv_u: Path,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    g_comp = build_comparison_frame(action_json_g, summary_csv_g)
    u_comp = build_comparison_frame(action_json_u, summary_csv_u)
    g_corrected_b, _g_model = _best_b_mapping(
        layer="G", action_json=action_json_g, summary_csv=summary_csv_g
    )
    u_corrected_b, _u_model = _best_b_mapping(
        layer="U", action_json=action_json_u, summary_csv=summary_csv_u
    )

    fig, axes = plt.subplots(
        2,
        2,
        figsize=(16, 9),
        constrained_layout=True,
    )
    _plot_layer_residuals(axes[:, 0], g_comp, layer="G", corrected_b=g_corrected_b)
    _plot_layer_residuals(axes[:, 1], u_comp, layer="U", corrected_b=u_corrected_b)

    fig.suptitle("UKAPA7 Residuals Comparison: Layer G (left) vs Layer U (right)")
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate UKAPA7 landscape-friendly 2x2 display plots."
    )
    parser.add_argument("--action-json-g", type=Path, required=True)
    parser.add_argument("--summary-csv-g", type=Path, required=True)
    parser.add_argument("--action-json-u", type=Path, required=True)
    parser.add_argument("--summary-csv-u", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    save_layer_landscape_plot(
        action_json=args.action_json_g,
        summary_csv=args.summary_csv_g,
        layer="G",
        output_path=output_dir / "ukapa7_landscape_G.png",
    )
    save_layer_landscape_plot(
        action_json=args.action_json_u,
        summary_csv=args.summary_csv_u,
        layer="U",
        output_path=output_dir / "ukapa7_landscape_U.png",
    )
    save_residuals_g_vs_u_landscape_plot(
        action_json_g=args.action_json_g,
        summary_csv_g=args.summary_csv_g,
        action_json_u=args.action_json_u,
        summary_csv_u=args.summary_csv_u,
        output_path=output_dir / "ukapa7_residuals_G_vs_U.png",
    )

    save_layer_change_in_tension_plot(
        action_json=args.action_json_g,
        summary_csv=args.summary_csv_g,
        layer="G",
        output_path=output_dir / "ukapa7_change_in_tension_G.png",
    )
    save_layer_change_in_tension_plot(
        action_json=args.action_json_u,
        summary_csv=args.summary_csv_u,
        layer="U",
        output_path=output_dir / "ukapa7_change_in_tension_U.png",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
