"""Shared layout helpers for tensiometer GUI variants."""

from __future__ import annotations

import tkinter as tk

from dune_tension.gui.live_plots import LIVE_SUMMARY_FIGSIZE, LIVE_WAVEFORM_FIGSIZE


def safe_screen_dimension(root: tk.Misc, method_name: str) -> int | None:
    """Best-effort screen size lookup for sizing constraints."""

    method = getattr(root, method_name, None)
    if method is None:
        return None
    try:
        value = int(method())
    except Exception:
        return None
    return value if value > 0 else None


def fit_column_widths_to_available_space(
    main_width: int,
    plots_width: int,
    log_width: int,
    available_width: int,
) -> tuple[int, int, int]:
    """Shrink column minimums so the root can fit on screen when maximized."""

    desired_width = main_width + plots_width + log_width
    if desired_width <= available_width:
        return main_width, plots_width, log_width

    overflow = desired_width - available_width

    log_reduction = min(overflow, max(log_width - 100, 0))
    log_width -= log_reduction
    overflow -= log_reduction

    if overflow > 0:
        plots_reduction = min(overflow, max(plots_width - 200, 0))
        plots_width -= plots_reduction
        overflow -= plots_reduction

    if overflow > 0:
        main_width = max(main_width - overflow, 1)

    return main_width, plots_width, log_width


def configure_root_minimum_size(
    root: tk.Misc,
    main_frame: tk.Misc,
    plots_frame: tk.Misc,
    log_frame: tk.Misc,
) -> None:
    """Keep the three-column layout wide enough for controls, plots, and logs."""

    if not hasattr(root, "update_idletasks"):
        return

    try:
        root.update_idletasks()
    except Exception:
        return

    try:
        main_width = int(main_frame.winfo_reqwidth())
        plots_width = int(plots_frame.winfo_reqwidth())
        log_width = int(log_frame.winfo_reqwidth())
        main_height = int(main_frame.winfo_reqheight())
        plots_height = int(plots_frame.winfo_reqheight())
        log_height = int(log_frame.winfo_reqheight())
    except Exception:
        return

    estimated_plot_width = int(
        max(LIVE_SUMMARY_FIGSIZE[0], LIVE_WAVEFORM_FIGSIZE[0]) * 100
    )
    plots_width = max(plots_width, estimated_plot_width)

    screen_width = safe_screen_dimension(root, "winfo_screenwidth")
    screen_height = safe_screen_dimension(root, "winfo_screenheight")

    available_width = max(screen_width - 30, 1) if screen_width is not None else None
    if available_width is not None:
        main_width, plots_width, log_width = fit_column_widths_to_available_space(
            main_width,
            plots_width,
            log_width,
            available_width,
        )

    if hasattr(root, "columnconfigure"):
        try:
            root.columnconfigure(0, weight=0, minsize=max(main_width, 1))
            root.columnconfigure(1, weight=1, minsize=max(plots_width, 1))
            root.columnconfigure(2, weight=1, minsize=max(log_width, 1))
        except Exception:
            pass

    total_width = main_width + plots_width + log_width + 40
    total_height = max(main_height, plots_height, log_height) + 20
    if screen_width is not None:
        total_width = min(total_width, screen_width)
    if screen_height is not None:
        total_height = min(total_height, screen_height)
    if total_width <= 0 or total_height <= 0:
        return

    minsize = getattr(root, "minsize", None)
    if callable(minsize):
        try:
            minsize(total_width, total_height)
        except Exception:
            return
