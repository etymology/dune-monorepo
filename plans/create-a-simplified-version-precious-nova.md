# Simplified Tensiometer GUI

## Context

The full tensiometer GUI (`src/dune_tension/gui/app.py`) exposes ~30 controls — many of which operators leave on default. The user wants a stripped-down variant for routine APA measurement runs that locks in known-good defaults and offers only three actions: **Measure Calibrate**, **Measure All**, and **Refine** (re-measure 2σ residual *or* bulk outliers).

Behavioural anchors (from clarifying questions):

- "Measure All" = the existing `measure_auto` action.
- "Refine" runs both outlier detectors at fixed 2σ and remeasures the union — no erase, no per-side disk wipe.
- APA controls visible: Location, Number, Layer, Side, A taped, B taped (no Flipped).
- Live plots **and** log panel both stay (three-column layout).

All measurement-related widget values are pulled fresh per action call (`_capture_worker_inputs` in `actions.py`), so fixed values can be set once at construction and never re-exposed.

## Approach

Add a new `simple_app.py` alongside the existing `app.py`. Reuse all existing context, actions, runtime-bundle, plot manager, and crash-logging plumbing — only the widget tree and command wiring differ. Add one new composite action so "Refine" runs as a single measurement worker rather than chained workers (which would race against `ctx.measurement_active`).

## Files to add / modify

### 1. New: `src/dune_tension/gui/simple_app.py`

`run_simple_app(state_file: str = "simple_gui_state.json", root: tk.Misc | None = None)` — mirrors the structure of `run_app` (app.py:59), but with a slimmer `_create_widgets`.

The `GUIWidgets` dataclass (`gui/context.py:15`, `slots=True`) requires all 64 fields. The plan: **construct every widget** but only `.grid()` the visible ones. Hidden widgets carry the fixed values; `_capture_worker_inputs` reads them transparently.

**Visible (gridded) widgets:**

APA frame (column 0, top):

- APA Location (`OptionMenu`, `apa_naming.LOCATIONS`)
- APA Number (`OptionMenu`, `apa_naming.NUMBER_LABELS`)
- Layer (`X/V/U/G`)
- Side (`A/B`)
- A taped checkbox
- B taped checkbox

Measurement frame (column 0, below APA):

- Wire Number entry (`entry_wire`) — needed for Measure Calibrate
- **Measure Calibrate** button → `measure_calibrate(ctx)` (actions.py:865)
- **Measure All** button → `measure_auto(ctx)` (actions.py:887)
- **Refine** button → new `measure_refine_outliers(ctx)` action (see §2)
- **Interrupt** button → `interrupt(ctx)` (keep this — operators need to abort; user didn't list it but a no-abort GUI is a foot-gun)
- ETA label (`textvariable=estimated_time_var`) — populated by existing actions
- Refresh Plots / Refresh Connections buttons (small, useful, low risk)

Plots column (column 1): `live_plots_frame` containing `summary_plot_frame` + `waveform_plot_frame`, identical to app.py:262–289. Wired to `LivePlotManager` exactly as in `run_app` (app.py:133).

Log column (column 2): `log_frame` + scrolled `Text`, identical to app.py:270–300. Wired via `configure_gui_logging` like app.py:103.

**Hidden (instantiated, not gridded) widgets with fixed values:**

| Widget | Fixed value | Notes |
|---|---|---|
| `entry_confidence` | `"0.5"` | Confidence threshold |
| `entry_record_duration` | `"0.5"` | |
| `entry_measuring_duration` | `"10"` | Wire timeout |
| `sweeping_wiggle_var` | `True` | |
| `entry_sweeping_wiggle_span_mm` | `"1.5"` | |
| `entry_wiggle_y_sigma` | `MEASUREMENT_WIGGLE_CONFIG.y_sigma_mm` | |
| `entry_focus_wiggle_sigma` | `MEASUREMENT_WIGGLE_CONFIG.focus_sigma_quarter_us` | |
| `use_manual_focus_var` | `False` | |
| `disable_x_compensation_var` | `False` | X compensation enabled |
| `entry_times_sigma` | `"2.0"` | Used by Refine |
| `flipped_var` | `False` | |
| `measurement_mode_var` | `"legacy"` | |
| `confidence_source_var` | `"Neural Net"` | |
| `use_harmonic_comb_trigger_var` | `True` | |
| `skip_measured_var`, `skip_measured_zone_var` | `True` | |
| `plot_audio_var`, `suppress_wire_preview_var` | `False` | |
| `entry_wire_list`, `entry_wire_zone`, `entry_clear_range`, `entry_condition`, `entry_legacy_tension_condition`, `entry_set_tension`, `entry_xy` | empty `Entry` | unused by exposed buttons but required by dataclass |
| `focus_slider` | `Scale` set to `4000` | needed by `_initialise_servo` (app.py:177) |
| `laser_offset_*` widgets | created, `grid_remove()` immediately | `refresh_uv_laser_offset_controls` will leave them hidden |
| `stream_*_var` StringVars | created, never displayed | written-to by streaming pipeline; harmless |

Reuse from `app.py` verbatim:

- `_initialise_servo` — copy or import.
- `_schedule_health_logging`, `_current_focus_value`, `_safe_screen_dimension`, `_fit_column_widths_to_available_space`, `_configure_root_minimum_size` — all internal helpers, factor by importing from `app.py` (mark them as module-private but reused) **or** duplicate. **Recommend factoring**: move these helpers to a new `gui/_layout.py` module and import from both `app.py` and `simple_app.py`. Cleaner than duplication; no behaviour change.
- Crash logging install (`install_gui_crash_logging`, `install_tk_exception_logging`) — same calls.
- `runtime_bundle = build_runtime_bundle(resolve_runtime_options())`.
- `create_context(...)`, `LivePlotManager(...)` setup, `load_state`, `refresh_uv_laser_offset_controls`, initial summary refresh, `monitor_tension_logs(ctx)` after-call, `WM_DELETE_WINDOW` → `handle_close`.

**Command wiring** (small `_configure_simple_commands`):

```python
btn_calibrate.configure(command=lambda: measure_calibrate(ctx))
btn_measure_all.configure(command=lambda: measure_auto(ctx))
btn_refine.configure(command=lambda: measure_refine_outliers(ctx))
btn_interrupt.configure(command=lambda: interrupt(ctx))
btn_refresh_plots.configure(command=lambda: refresh_tension_logs(ctx))
btn_refresh_connections.configure(command=lambda: refresh_connections(ctx))
ctx.widgets.focus_slider.configure(
    command=lambda val: adjust_focus_with_x_compensation(ctx, int(float(val)))
)
for var in (ctx.widgets.layer_var, ctx.widgets.side_var, ctx.widgets.measurement_mode_var):
    var.trace_add("write", lambda *_: refresh_uv_laser_offset_controls(ctx))
```

### 2. Modify: `src/dune_tension/gui/actions.py`

Add a new action **`measure_refine_outliers`** that runs both detectors and remeasures the union in a *single* measurement worker. Sequencing two existing `@_run_in_thread(measurement=True)` actions back-to-back races against `ctx.measurement_active` (actions.py:795 — second worker bails out).

Pattern, modeled on `_measure_detected_outliers` (actions.py:1485):

```python
@_run_in_thread(measurement=True)
def measure_refine_outliers(ctx: GUIContext, inputs: WorkerInputs) -> None:
    config = _make_config_from_inputs(inputs)
    times_sigma, _ = _parse_outlier_erase_expression(inputs.times_sigma.strip())

    residual = set(find_outliers(
        config.data_path, config.apa_name, config.layer, config.side,
        times_sigma=times_sigma, confidence_threshold=inputs.confidence,
    ))
    bulk = set(find_distribution_outliers(
        config.data_path, config.apa_name, config.layer, config.side,
        times_sigma=times_sigma, confidence_threshold=inputs.confidence,
    ))
    outliers = sorted(residual | bulk)
    if not outliers:
        LOGGER.info("Refine: no residual or bulk outliers at %.2fσ", times_sigma)
        return

    if _measurement_mode(inputs) != "legacy":
        LOGGER.info("Refine streaming on union: %s", outliers)
        _run_streaming_for_wires(ctx, inputs, outliers)
        return

    tensiometer: Tensiometer | None = None
    try:
        tensiometer = create_tensiometer(ctx, inputs)
        LOGGER.info("Refine legacy on union: %s", outliers)
        tensiometer.measure_list(outliers, preserve_order=False)
    except ValueError as exc:
        LOGGER.warning("%s", exc)
    finally:
        _cleanup_after_measurement(ctx, tensiometer)
```

Place near `measure_distribution_outliers` (actions.py:1479). No other action needs to change.

### 3. Modify: `src/dune_tension/gui/__init__.py`

Export `run_simple_app`:

```python
from dune_tension.gui.simple_app import run_simple_app
# add to __all__
```

### 4. New: `src/dune_tension/main_simple.py`

```python
"""Entry point for the simplified tensiometer GUI."""
from __future__ import annotations
from dune_tension.gui import run_simple_app

def main() -> None:
    run_simple_app()

if __name__ == "__main__":
    main()
```

### 5. Modify: `pyproject.toml`

Add under `[project.scripts]` (next to line 39):

```
dune-tension-gui-simple = "dune_tension.main_simple:main"
```

Default state file `"simple_gui_state.json"` keeps simple-GUI state separate from the full GUI's `gui_state.json` — and the file already exists in the repo (`dune_tension/simple_gui_state.json`), so this isn't a new artifact.

## Verification

End-to-end smoke test (no real hardware needed if `resolve_runtime_options()` defaults to mocked motion/audio in this checkout — confirm in `services.py`):

1. Launch: `uv run dune-tension-gui-simple` (or `python -m dune_tension.main_simple`).
2. Confirm the window shows: APA frame (loc/number/layer/side/A taped/B taped), wire entry, four buttons (Calibrate, Measure All, Refine, Interrupt), live plots, log panel. **No** confidence / record-duration / wiggle / focus / laser-offset / outlier-sigma controls visible.
3. Click **Measure Calibrate** with a wire number — confirm it kicks off (log line `Worker thread starting: measure calibrate`).
4. Click **Measure All** — confirm `measure_auto` worker starts.
5. Click **Refine** — confirm new `measure_refine_outliers` worker starts and logs union of residual+bulk outliers.
6. Click **Interrupt** during a measurement — confirm `ctx.stop_event` triggers shutdown.
7. Quit via window close — confirm `handle_close` runs without exception.

Unit-style checks:

- `uv run pytest tests/dune_tension -k gui` (existing tests should still pass — we don't modify `app.py` semantics).
- Add a small test under `tests/dune_tension/gui/test_simple_app.py` that imports `run_simple_app`, builds widgets against a dummy Tk root (the existing GUI tests use a stub Tk — follow that pattern), asserts the visible buttons exist, and verifies the hidden widgets carry the fixed values listed above.
- For `measure_refine_outliers`: a unit test that monkeypatches `find_outliers` and `find_distribution_outliers` to return overlapping wire sets, monkeypatches `create_tensiometer`, and asserts the action calls `tensiometer.measure_list` with the **union** (not concatenation) of the two sets.

## Critical files

- Add: `src/dune_tension/gui/simple_app.py`
- Add: `src/dune_tension/main_simple.py`
- Modify: `src/dune_tension/gui/actions.py` (add `measure_refine_outliers` near line 1479)
- Modify: `src/dune_tension/gui/__init__.py` (export)
- Modify: `pyproject.toml` (script entry near line 39)
- Optional refactor: extract layout helpers from `gui/app.py` lines 769–878 into `src/dune_tension/gui/_layout.py` so both apps share them.
