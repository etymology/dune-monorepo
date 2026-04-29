from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def find_repo_root(start: Path) -> Path:
    for path in (start, *start.parents):
        if (path / "pyproject.toml").exists() and (path / "src/dune_tension").exists():
            return path
    raise RuntimeError("Could not find dune-monorepo root")


ROOT = find_repo_root(Path(__file__).resolve())
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dune_tension.ukapa7_comparison.compare_b_index_models import (  # noqa: E402
    build_model_comparison,
)
from dune_tension.ukapa7_comparison.compare_partial_b_offsets import (  # noqa: E402
    evaluate_shift,
    find_best_shift,
    load_partial_b,
)
from dune_tension.ukapa7_comparison.compare_tension_sources import (  # noqa: E402
    build_comparison_frame,
    load_summary_csv,
)


EXPERIMENT_DIR = ROOT / "dune_tension/experiments/UKAPA7_comparison"
G_ACTION_JSON = ROOT / "dune_tension/apa_uk7g.json"
U_ACTION_JSON = ROOT / "dune_tension/UKAPA7U.json"
G_SUMMARY_CSV = (
    ROOT / "dune_tension/data/tension_summaries/tension_summary_UKAPA7_G.csv"
)
U_SUMMARY_CSV = (
    ROOT / "dune_tension/data/tension_summaries/tension_summary_UKAPA7_U.csv"
)

SPEC_LOW = 4.0
SPEC_HIGH = 8.5


@dataclass(frozen=True)
class ResidualGroup:
    label: str
    layer: str
    side: str
    wire_number: pd.Series
    residual: pd.Series
    chicago_tension: pd.Series


def _best_g_b_mapping() -> pd.DataFrame:
    model_df, stats_df = build_model_comparison(G_ACTION_JSON, G_SUMMARY_CSV, -60, 60)
    shifted_model = next(
        model
        for model in stats_df["model"].tolist()
        if model.startswith("reversed_shift_")
    )
    return (
        model_df[model_df["model"] == shifted_model]
        .sort_values("wire_number")
        .reset_index(drop=True)
    )


def _best_u_b_mapping() -> pd.DataFrame:
    merged, json_values = load_partial_b(U_ACTION_JSON, U_SUMMARY_CSV)
    _stats_df, _baseline_row, best_shift = find_best_shift(merged, json_values, -80, 80)
    shifted_df, _stats = evaluate_shift(merged, json_values, best_shift)
    return shifted_df.sort_values("wire_number").reset_index(drop=True)


def build_residual_groups() -> list[ResidualGroup]:
    g_comp = build_comparison_frame(G_ACTION_JSON, G_SUMMARY_CSV)
    u_comp = build_comparison_frame(U_ACTION_JSON, U_SUMMARY_CSV)
    g_b = _best_g_b_mapping()
    u_b = _best_u_b_mapping()

    groups: list[ResidualGroup] = []
    for label, layer, side, frame, residual_col, chicago_col in [
        ("G A", "G", "A", g_comp, "diff_A", "summary_A"),
        ("U A", "U", "A", u_comp, "diff_A", "summary_A"),
    ]:
        subset = frame[["wire_number", residual_col, chicago_col]].dropna().copy()
        groups.append(
            ResidualGroup(
                label=label,
                layer=layer,
                side=side,
                wire_number=subset["wire_number"],
                residual=subset[residual_col],
                chicago_tension=subset[chicago_col],
            )
        )

    groups.insert(
        1,
        ResidualGroup(
            label="G B",
            layer="G",
            side="B",
            wire_number=g_b["wire_number"],
            residual=g_b["residual_B"],
            chicago_tension=g_b["summary_B"],
        ),
    )
    groups.append(
        ResidualGroup(
            label="U B",
            layer="U",
            side="B",
            wire_number=u_b["wire_number"],
            residual=u_b["residual_B"],
            chicago_tension=u_b["summary_B"],
        )
    )
    return groups


def _rolling_median(values: pd.Series, window: int = 21) -> pd.Series:
    return values.rolling(window=window, center=True, min_periods=1).median()


def _group_stats(group: ResidualGroup) -> dict[str, float | int | str]:
    residual = group.residual.dropna()
    return {
        "group": group.label,
        "n": int(residual.size),
        "mean": float(residual.mean()),
        "median": float(residual.median()),
        "std": float(residual.std(ddof=0)),
        "percent_lower": float((residual < 0).mean() * 100.0),
        "min_current": float(group.chicago_tension.min()),
        "max_current": float(group.chicago_tension.max()),
    }


def save_residual_small_multiples(
    groups: list[ResidualGroup], output_path: Path
) -> None:
    residual_values = pd.concat([group.residual for group in groups]).dropna()
    y_low = min(-1.6, float(residual_values.quantile(0.005)) - 0.2)
    y_high = max(0.8, float(residual_values.quantile(0.995)) + 0.2)
    x_high = max(int(group.wire_number.max()) for group in groups) + 10

    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex=True, sharey=True)
    axes = axes.ravel()
    colors = {"G": "#2468a2", "U": "#b34a32"}

    for ax, group in zip(axes, groups, strict=True):
        order = np.argsort(group.wire_number.to_numpy())
        wires = group.wire_number.iloc[order].reset_index(drop=True)
        residual = group.residual.iloc[order].reset_index(drop=True)
        stats = _group_stats(group)
        color = colors[group.layer]

        ax.scatter(wires, residual, s=8, color="#4c5661", alpha=0.42, linewidths=0)
        ax.plot(wires, _rolling_median(residual), color=color, linewidth=1.6)
        ax.axhline(0.0, color="#202020", linewidth=0.9)
        ax.axhline(float(stats["median"]), color=color, linewidth=0.9, alpha=0.75)
        ax.set_title(group.label, loc="left", fontsize=15, fontweight="bold")
        ax.text(
            0.02,
            0.04,
            (
                f"n={stats['n']}\n"
                f"mean {stats['mean']:.2f} N\n"
                f"median {stats['median']:.2f} N\n"
                f"{stats['percent_lower']:.0f}% lower"
            ),
            transform=ax.transAxes,
            ha="left",
            va="bottom",
            fontsize=10,
            color="#202020",
        )
        ax.set_xlim(0, x_high)
        ax.set_ylim(y_low, y_high)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", color="#dddddd", linewidth=0.6)

    axes[0].set_ylabel("Chicago - UK tension (N)")
    axes[2].set_ylabel("Chicago - UK tension (N)")
    axes[2].set_xlabel("Wire number")
    axes[3].set_xlabel("Wire number")
    fig.suptitle("APA-UK007 change in tension by layer and side", fontsize=18, y=0.98)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def _current_summary_groups() -> dict[str, pd.Series]:
    g_summary = load_summary_csv(G_SUMMARY_CSV)
    u_summary = load_summary_csv(U_SUMMARY_CSV)
    return {
        "G A": g_summary["summary_A"].dropna(),
        "G B": g_summary["summary_B"].dropna(),
        "U A": u_summary["summary_A"].dropna(),
        "U B": u_summary["summary_B"].dropna(),
    }


def save_current_tension_vs_spec(output_path: Path) -> None:
    groups = _current_summary_groups()
    labels = list(groups)
    y_positions = np.arange(len(labels))[::-1]

    fig, ax = plt.subplots(figsize=(12, 5.8))
    ax.axvspan(SPEC_LOW, SPEC_HIGH, color="#dbe9d8", alpha=0.8)
    ax.axvline(SPEC_LOW, color="#597a52", linewidth=1.0)
    ax.axvline(SPEC_HIGH, color="#597a52", linewidth=1.0)
    ax.text(
        SPEC_LOW, len(labels) - 0.45, "4.0 N", ha="center", va="bottom", fontsize=10
    )
    ax.text(
        SPEC_HIGH, len(labels) - 0.45, "8.5 N", ha="center", va="bottom", fontsize=10
    )

    for y, label in zip(y_positions, labels, strict=True):
        values = groups[label].sort_values().reset_index(drop=True)
        offsets = np.linspace(-0.16, 0.16, len(values)) if len(values) > 1 else [0.0]
        ax.scatter(values, y + offsets, s=9, color="#44515c", alpha=0.38, linewidths=0)
        median = values.median()
        ax.plot([values.min(), values.max()], [y, y], color="#202020", linewidth=1.2)
        ax.scatter([median], [y], s=42, color="#b34a32", zorder=4)
        ax.text(
            8.72,
            y,
            f"min {values.min():.2f}   median {median:.2f}   max {values.max():.2f}",
            ha="left",
            va="center",
            fontsize=10,
            color="#202020",
        )

    ax.set_yticks(y_positions, labels)
    ax.set_xlim(3.7, 10.6)
    ax.set_xlabel("Current Chicago tension (N)")
    ax.set_title(
        "Current Chicago summary tensions relative to specification", fontsize=16
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", color="#dddddd", linewidth=0.6)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def save_coverage_strip(groups: list[ResidualGroup], output_path: Path) -> None:
    labels = [group.label for group in groups]
    y_positions = np.arange(len(labels))[::-1]
    x_high = max(int(group.wire_number.max()) for group in groups) + 10

    fig, ax = plt.subplots(figsize=(12, 4.8))
    for y, group in zip(y_positions, groups, strict=True):
        wires = group.wire_number.sort_values()
        ax.hlines(
            y,
            float(wires.min()),
            float(wires.max()),
            color="#e2e2e2",
            linewidth=7,
            zorder=1,
        )
        ax.scatter(
            wires,
            np.full(len(wires), y),
            s=15,
            color="#2468a2",
            alpha=0.95,
            linewidths=0,
            zorder=3,
        )
        ax.text(
            x_high + 15,
            y,
            f"{len(wires)} aligned wires",
            ha="left",
            va="center",
            fontsize=10,
        )

    ax.text(
        0.02,
        0.06,
        "Blue marks show wires used in the Chicago - UK comparison.",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=10,
        color="#202020",
    )
    ax.set_yticks(y_positions, labels)
    ax.set_xlim(0, x_high + 190)
    ax.set_xlabel("Wire number")
    ax.set_title("Comparable wire coverage", fontsize=16)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color="#dddddd", linewidth=0.6)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)


def main() -> int:
    groups = build_residual_groups()
    save_residual_small_multiples(
        groups, EXPERIMENT_DIR / "ukapa7_revised_residual_small_multiples.png"
    )
    save_current_tension_vs_spec(
        EXPERIMENT_DIR / "ukapa7_revised_current_tension_vs_spec.png"
    )
    save_coverage_strip(groups, EXPERIMENT_DIR / "ukapa7_revised_coverage_strip.png")

    stats = pd.DataFrame([_group_stats(group) for group in groups])
    print(stats.to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
