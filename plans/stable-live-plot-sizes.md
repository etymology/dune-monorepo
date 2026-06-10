# Stabilize live plot sizes in the tensiometer GUIs

> CLAUDE.md requires plans to live in `plans/` inside the repo; this file is at the
> harness-mandated path. Copy it to `/home/ben/dune-monorepo/plans/` on execution if desired.

## Context

Both tensiometer GUIs (`src/dune_tension/gui/app.py` and `simple_app.py`) embed two
matplotlib plots (summary + waveform) via `LivePlotManager`
(`src/dune_tension/gui/live_plots.py`). On every refresh, `_show_canvas()` destroys the
old `FigureCanvasTkAgg` and creates a new one. Each new canvas widget requests its own
`figsize * dpi` pixel size, which propagates up through `summary_plot_frame` /
`waveform_plot_frame` → `live_plots_frame` → the root grid, forcing Tk to renegotiate
the whole layout. The result is plots (and the window) visibly resizing on every
regeneration. The user accepts a fixed, fullscreen, non-resizable window as the price of
stable plot sizes.

## Approach

Pin the window at fullscreen and freeze the two plot frames at their allocated size so
canvas swaps can no longer reflow anything.

### 1. `src/dune_tension/gui/_layout.py` — two new helpers (ALREADY APPLIED)

These edits were applied before plan mode activated; they are in the working tree now.

- `configure_fixed_fullscreen(root)`: reads screen size via the existing
  `safe_screen_dimension()`, sets `root.geometry(f"{w}x{h}+0+0")` and
  `root.resizable(False, False)`. Defensive `getattr`/`try` style matching the rest of
  the module (tests use fake roots).
- `freeze_frame_sizes(root, *frames)`: calls `root.update()` (full update, so the window
  maps and `winfo_width/height` report real allocations rather than 1), then for each
  frame sets `frame.configure(width=..., height=...)` to its allocated size and calls
  `frame.grid_propagate(False)`. With propagation off, replacing a frame's children
  (placeholder label ↔ regenerated canvas) no longer changes its requested size.

### 2. Wire into both apps (ALREADY APPLIED)

In `app.py` and `simple_app.py` `_create_widgets()`, immediately after the existing
`configure_root_minimum_size(...)` call:

```python
configure_fixed_fullscreen(root)
freeze_frame_sizes(root, summary_plot_frame, waveform_plot_frame)
```

Imports updated accordingly.

### 3. `src/dune_tension/gui/live_plots.py` — pre-size figures (REMAINING)

In `LivePlotManager._show_canvas()`, before constructing `FigureCanvasTkAgg`, resize the
figure to the (now-frozen) parent frame's pixel size so the first paint already matches
the frame instead of drawing at `LIVE_*_FIGSIZE` and then snapping on the `<Configure>`
resize event:

```python
try:
    width_px = int(parent.winfo_width())
    height_px = int(parent.winfo_height())
    if width_px > 1 and height_px > 1:
        dpi = float(figure.get_dpi())
        figure.set_size_inches(width_px / dpi, height_px / dpi, forward=False)
except Exception:
    pass
```

### 4. Tests (REMAINING)

Extend `tests/dune_tension/test_gui_layout.py` (it loads `_layout.py` with a stubbed
`tkinter` and fake root/frame objects — follow `_FakeRoot`/`_FakeFrame` patterns):

- `configure_fixed_fullscreen` sets geometry to `"{sw}x{sh}+0+0"` and calls
  `resizable(False, False)`; does nothing when screen dimensions are unavailable.
- `freeze_frame_sizes` configures each frame's width/height from `winfo_width/height`,
  falls back to `winfo_reqwidth/reqheight` when allocation is ≤ 1, and calls
  `grid_propagate(False)`.

## Verification

- `uv run pytest tests/dune_tension` — existing GUI tests plus new layout tests.
- `uv run ruff check src tests` and `uv run ty check` (required before completion).
- Manual: `uv run dune-tension-gui`, confirm the window opens fullscreen, cannot be
  resized, and the summary/waveform plots keep a constant size across "Refresh Plots"
  and live waveform updates.

## Files

- `src/dune_tension/gui/_layout.py` (helpers — done)
- `src/dune_tension/gui/app.py`, `src/dune_tension/gui/simple_app.py` (wiring — done)
- `src/dune_tension/gui/live_plots.py` (figure pre-sizing — to do)
- `tests/dune_tension/test_gui_layout.py` (new tests — to do)
