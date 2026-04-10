"""Tkinter command callbacks used by the tensiometer GUI."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
import logging
import math
import os
import re
import threading
from threading import Thread
from typing import TYPE_CHECKING, Any
import tkinter as tk

from tkinter import messagebox

from dune_tension.data_cache import (
    clear_wire_numbers,
    clear_wire_range,
    find_distribution_outliers,
    find_outliers,
    get_dataframe,
    update_dataframe,
)
from dune_tension.results import EXPECTED_COLUMNS
from dune_tension.layer_calibration import (
    capture_laser_offset as save_captured_laser_offset,
    ensure_layer_calibration_ready,
    get_bottom_pin_options,
    get_calibrated_pin_xy,
    get_laser_offset,
)
from dune_tension.plc_desktop import desktop_seek_pin
from dune_tension.plc_io import get_plc_io_mode
from dune_tension.tensiometer_functions import make_config, normalize_confidence_source
from dune_tension.gui.context import GUIContext
from dune_tension.gui.state import save_state

if TYPE_CHECKING:
    from dune_tension.tensiometer import Tensiometer

LOGGER = logging.getLogger(__name__)
FOCUS_X_MM_PER_QUARTER_US = (20.0 / 4000.0) / math.sqrt(3.0)
DEFAULT_PIN_SEEK_VELOCITY = 25.0


def _safe_int(value: Any, default: int) -> int:
    """Best-effort integer parsing for UI and device numeric values."""

    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(str(value).strip()))
        except (TypeError, ValueError):
            return default


def _focus_side_sign(side: str) -> float:
    """Return focus/X coupling sign: A is negative, B is positive."""

    return -1.0 if str(side).upper() == "A" else 1.0


def adjust_focus_with_x_compensation(
    ctx: GUIContext,
    target: int,
    *,
    side: str | None = None,
) -> None:
    """Command focus and compensate X using the configured focus-to-mm scale."""

    try:
        target_int = int(target)
    except (TypeError, ValueError):
        LOGGER.warning("Invalid focus target: %s", target)
        return

    current_focus = int(ctx.servo_controller.focus_position)
    delta_focus = target_int - current_focus
    ctx.servo_controller.focus_target(target_int)
    if delta_focus == 0:
        return

    if ctx.widgets.disable_x_compensation_var.get():
        return

    side_name = str(side or ctx.widgets.side_var.get()).upper()
    delta_x_mm = _focus_side_sign(side_name) * delta_focus * FOCUS_X_MM_PER_QUARTER_US

    try:
        cur_x, cur_y = ctx.get_xy()
    except Exception as exc:
        LOGGER.warning("Unable to read XY for focus compensation: %s", exc)
        return

    new_x = round(cur_x + delta_x_mm, 1)
    try:
        moved = ctx.goto_xy(new_x, cur_y)
    except Exception as exc:
        LOGGER.warning("Focus compensation move failed: %s", exc)
        return
    if moved is False:
        LOGGER.warning("Focus compensation move to %s,%s failed.", new_x, cur_y)


def _set_estimated_time(ctx: GUIContext, value: str) -> None:
    """Update the ETA label on the Tk thread."""

    def apply() -> None:
        ctx.estimated_time_var.set(value)

    try:
        if threading.current_thread() is threading.main_thread():
            apply()
            return
        ctx.root.after(0, apply)
    except Exception:
        return


def _publish_live_waveform(
    ctx: GUIContext,
    audio_sample: Any,
    samplerate: int,
    analysis: Any | None,
) -> None:
    manager = getattr(ctx, "live_plot_manager", None)
    if manager is None:
        return
    manager.publish_waveform(audio_sample, samplerate, analysis)


def _request_live_summary_refresh(ctx: GUIContext, config: Any) -> None:
    manager = getattr(ctx, "live_plot_manager", None)
    if manager is None:
        return
    manager.request_summary_refresh(config)


@dataclass(frozen=True)
class WorkerInputs:
    apa_name: str
    measurement_mode: str
    layer: str
    side: str
    flipped: bool
    a_taped: bool
    b_taped: bool
    confidence: float
    confidence_source: str
    record_duration: float
    measuring_duration: float
    wiggle_y_sigma_mm: float
    sweeping_wiggle_enabled: bool
    sweeping_wiggle_span_mm: float
    focus_wiggle_sigma_quarter_us: float
    use_manual_focus: bool
    plot_audio: bool
    skip_measured: bool
    wire_number: str
    wire_list: str
    condition: str
    times_sigma: str
    set_tension: str
    clear_range: str
    xy_text: str
    laser_offset_pin: str


def _show_input_error(ctx: GUIContext, message: str) -> None:
    messagebox.showerror("Input Error", message)


def _capture_worker_inputs(ctx: GUIContext) -> WorkerInputs:
    """Capture all widget values on the Tk thread before background work."""

    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("_capture_worker_inputs must run on the main Tk thread.")

    w = ctx.widgets
    try:
        confidence = float(w.entry_confidence.get())
    except ValueError as exc:
        _show_input_error(ctx, str(exc))
        raise

    try:
        record_duration = float(w.entry_record_duration.get())
        measuring_duration = float(w.entry_measuring_duration.get())
    except ValueError as exc:
        _show_input_error(ctx, str(exc))
        raise

    try:
        wiggle_y_sigma_mm = float(w.entry_wiggle_y_sigma.get())
        sweeping_wiggle_span_mm = float(w.entry_sweeping_wiggle_span_mm.get())
        focus_wiggle_sigma_quarter_us = float(w.entry_focus_wiggle_sigma.get())
    except ValueError as exc:
        _show_input_error(ctx, str(exc))
        raise
    if wiggle_y_sigma_mm < 0:
        msg = "Y wiggle sigma must be non-negative"
        _show_input_error(ctx, msg)
        raise ValueError(msg)
    if sweeping_wiggle_span_mm < 0:
        msg = "Sweeping wiggle span must be non-negative"
        _show_input_error(ctx, msg)
        raise ValueError(msg)
    if focus_wiggle_sigma_quarter_us < 0:
        msg = "Focus wiggle sigma must be non-negative"
        _show_input_error(ctx, msg)
        raise ValueError(msg)

    return WorkerInputs(
        apa_name=w.entry_apa.get(),
        measurement_mode=w.measurement_mode_var.get(),
        layer=w.layer_var.get(),
        side=w.side_var.get(),
        flipped=bool(w.flipped_var.get()),
        a_taped=bool(w.a_taped_var.get()),
        b_taped=bool(w.b_taped_var.get()),
        confidence=confidence,
        confidence_source=str(w.confidence_source_var.get()),
        record_duration=record_duration,
        measuring_duration=measuring_duration,
        wiggle_y_sigma_mm=wiggle_y_sigma_mm,
        sweeping_wiggle_enabled=bool(w.sweeping_wiggle_var.get()),
        sweeping_wiggle_span_mm=sweeping_wiggle_span_mm,
        focus_wiggle_sigma_quarter_us=focus_wiggle_sigma_quarter_us,
        use_manual_focus=bool(w.use_manual_focus_var.get()),
        plot_audio=bool(w.plot_audio_var.get()),
        skip_measured=bool(w.skip_measured_var.get()),
        wire_number=w.entry_wire.get(),
        wire_list=w.entry_wire_list.get(),
        condition=w.entry_condition.get(),
        times_sigma=w.entry_times_sigma.get(),
        set_tension=w.entry_set_tension.get(),
        clear_range=w.entry_clear_range.get(),
        xy_text=w.entry_xy.get(),
        laser_offset_pin=str(getattr(w.laser_offset_pin_var, "get", lambda: "")()),
    )


def create_tensiometer(ctx: GUIContext, inputs: WorkerInputs) -> "Tensiometer":
    """Instantiate a :class:`Tensiometer` from captured UI inputs."""

    from dune_tension.tensiometer import build_tensiometer

    try:
        confidence = float(inputs.confidence)
        confidence_source = normalize_confidence_source(
            str(getattr(inputs, "confidence_source", "Neural Net")).strip()
            or "Neural Net"
        )
        record_duration = float(inputs.record_duration)
        measuring_duration = float(inputs.measuring_duration)
        wiggle_y_sigma_mm = float(inputs.wiggle_y_sigma_mm)
        sweeping_wiggle_span_mm = float(inputs.sweeping_wiggle_span_mm)
        focus_wiggle_sigma_quarter_us = float(
            inputs.focus_wiggle_sigma_quarter_us
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid measurement inputs: {exc}") from exc

    if _measurement_mode(inputs) == "legacy" and str(inputs.layer).upper() in {"U", "V"}:
        ensure_layer_calibration_ready(inputs.layer)
        if get_laser_offset(inputs.side) is None:
            raise ValueError(
                f"No saved laser offset exists for side {str(inputs.side).upper()}."
            )

    return build_tensiometer(
        apa_name=inputs.apa_name,
        layer=inputs.layer,
        side=inputs.side,
        flipped=inputs.flipped,
        a_taped=inputs.a_taped,
        b_taped=inputs.b_taped,
        stop_event=ctx.stop_event,
        samples_per_wire=1,
        confidence_threshold=confidence,
        confidence_source=confidence_source,
        record_duration=record_duration,
        measuring_duration=measuring_duration,
        wiggle_y_sigma_mm=wiggle_y_sigma_mm,
        sweeping_wiggle=bool(getattr(inputs, "sweeping_wiggle_enabled", False)),
        sweeping_wiggle_span_mm=sweeping_wiggle_span_mm,
        focus_wiggle_sigma_quarter_us=focus_wiggle_sigma_quarter_us,
        plot_audio=inputs.plot_audio,
        strum=ctx.strum,
        focus_wiggle=ctx.servo_controller.nudge_focus,
        focus_position_getter=lambda: int(ctx.servo_controller.focus_position),
        use_manual_focus=bool(getattr(inputs, "use_manual_focus", False)),
        manual_focus_target=None,
        estimated_time_callback=lambda value: _set_estimated_time(ctx, value),
        audio_sample_callback=lambda audio_sample, samplerate, analysis: _publish_live_waveform(
            ctx,
            audio_sample,
            samplerate,
            analysis,
        ),
        summary_refresh_callback=lambda config: _request_live_summary_refresh(
            ctx,
            config,
        ),
        runtime_bundle=ctx.runtime,
    )


def _measurement_mode(inputs: WorkerInputs) -> str:
    return str(getattr(inputs, "measurement_mode", "legacy")).strip().lower() or "legacy"


def _selected_laser_offset_pin(layer: str, side: str, current_value: str | None) -> str | None:
    options = get_bottom_pin_options(layer, side)
    if not options:
        return None
    allowed_values = {value for _label, value in options}
    normalized = str(current_value or "").strip().upper()
    if normalized in allowed_values:
        return normalized
    return options[0][1]


def _laser_offset_readout_text(side: str) -> str:
    offset = get_laser_offset(side)
    if offset is None:
        return f"Side {str(side).upper()}: not set"
    return (
        f"Side {str(side).upper()}: "
        f"x={float(offset['x']):.3f} mm, "
        f"y={float(offset['y']):.3f} mm, "
        f"pin={offset.get('captured_pin')}, "
        f"layer={offset.get('captured_layer')}"
    )


def refresh_uv_laser_offset_controls(ctx: GUIContext) -> None:
    widgets = ctx.widgets
    layer = str(widgets.layer_var.get()).upper()
    side = str(widgets.side_var.get()).upper()
    mode = str(widgets.measurement_mode_var.get()).strip().lower() or "legacy"
    show_controls = mode == "legacy" and layer in {"U", "V"}

    if show_controls:
        try:
            widgets.laser_offset_frame.grid()
        except Exception:
            pass
        options = get_bottom_pin_options(layer, side)
        selected = _selected_laser_offset_pin(layer, side, widgets.laser_offset_pin_var.get())
        menu = widgets.laser_offset_pin_menu["menu"]
        menu.delete(0, "end")
        for label, value in options:
            menu.add_command(
                label=label,
                command=tk._setit(widgets.laser_offset_pin_var, value),
            )
        if selected is not None:
            widgets.laser_offset_pin_var.set(selected)

        sync_error: str | None = None
        try:
            ensure_layer_calibration_ready(layer)
        except Exception as exc:
            sync_error = str(exc)
            LOGGER.warning("Layer calibration sync failed for %s: %s", layer, exc)

        readout = _laser_offset_readout_text(side)
        if sync_error:
            readout = f"{readout} | sync error: {sync_error}"
        widgets.laser_offset_readout_var.set(readout)
        button_state = "normal" if sync_error is None else "disabled"
        try:
            widgets.btn_seek_pin.configure(state=button_state)
            widgets.btn_capture_laser_offset.configure(state=button_state)
        except Exception:
            pass
        return

    try:
        widgets.laser_offset_frame.grid_remove()
    except Exception:
        pass


def _move_to_local_pin(ctx: GUIContext, layer: str, pin_name: str, velocity: float) -> bool:
    pin_x, pin_y = get_calibrated_pin_xy(layer, pin_name)
    goto_xy = getattr(ctx.runtime.motion, "goto_xy", ctx.goto_xy)
    try:
        result = goto_xy(pin_x, pin_y, speed=float(velocity))
    except TypeError:
        result = goto_xy(pin_x, pin_y)
    return result is not False


def _current_stage_xy(ctx: GUIContext) -> tuple[float, float]:
    get_live_xy = getattr(ctx.runtime.motion, "get_live_xy", None)
    if callable(get_live_xy):
        return tuple(map(float, get_live_xy()))
    return tuple(map(float, ctx.get_xy()))


def _publish_streaming_status(ctx: GUIContext, payload: dict[str, object]) -> None:
    def apply() -> None:
        if "segment_id" in payload:
            ctx.widgets.stream_segment_var.set(str(payload["segment_id"]))
        if "comb_score" in payload:
            try:
                ctx.widgets.stream_comb_var.set(f"{float(payload['comb_score']):.2f}")
            except (TypeError, ValueError):
                ctx.widgets.stream_comb_var.set(str(payload["comb_score"]))
        if "focus_prediction" in payload:
            try:
                ctx.widgets.stream_focus_var.set(f"{float(payload['focus_prediction']):.1f}")
            except (TypeError, ValueError):
                ctx.widgets.stream_focus_var.set(str(payload["focus_prediction"]))
        if "pitch_backlog" in payload:
            ctx.widgets.stream_pitch_backlog_var.set(str(payload["pitch_backlog"]))
        if "rescue_queue_depth" in payload:
            ctx.widgets.stream_rescue_queue_var.set(str(payload["rescue_queue_depth"]))

    try:
        if threading.current_thread() is threading.main_thread():
            apply()
            return
        ctx.root.after(0, apply)
    except Exception:
        return


def _reset_streaming_status(ctx: GUIContext) -> None:
    _publish_streaming_status(
        ctx,
        {
            "segment_id": "Idle",
            "comb_score": 0.0,
            "focus_prediction": "--",
            "pitch_backlog": 0,
            "rescue_queue_depth": 0,
        },
    )


def create_streaming_controller(ctx: GUIContext, inputs: WorkerInputs):
    from dune_tension.streaming import (
        StreamingControllerConfig,
        StreamingMeasurementController,
        build_measurement_runtime,
    )

    try:
        confidence = float(inputs.confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid streaming inputs: {exc}") from exc

    runtime = build_measurement_runtime(runtime_bundle=ctx.runtime)
    config = StreamingControllerConfig(
        apa_name=inputs.apa_name,
        layer=inputs.layer,
        side=inputs.side,
        flipped=inputs.flipped,
        sample_rate=int(getattr(ctx.runtime.audio, "samplerate", 44100)),
        direct_accept_confidence=confidence,
        direct_accept_support=1,
        use_manual_focus=bool(getattr(inputs, "use_manual_focus", False)),
        manual_focus_target=None,
    )
    return StreamingMeasurementController(
        runtime=runtime,
        config=config,
        status_callback=lambda payload: _publish_streaming_status(ctx, payload),
        stop_event=ctx.stop_event,
    )


def _run_streaming_for_wires(
    ctx: GUIContext,
    inputs: WorkerInputs,
    wire_numbers: list[int],
) -> None:
    from dune_tension.streaming import build_corridors_for_wire_numbers

    if not wire_numbers:
        LOGGER.info("No wires available for streaming measurement.")
        return

    controller = None
    try:
        controller = create_streaming_controller(ctx, inputs)
        _reset_streaming_status(ctx)
        mode = _measurement_mode(inputs)
        if mode == "stream_rescue":
            for wire_number in wire_numbers:
                if ctx.stop_event.is_set():
                    break
                summary = controller.run_rescue(int(wire_number))
                LOGGER.info("Streaming rescue summary for wire %s: %s", wire_number, summary)
            return

        corridors = build_corridors_for_wire_numbers(
            provider=controller.runtime.wire_positions,
            apa_name=inputs.apa_name,
            layer=inputs.layer,
            side=inputs.side,
            flipped=inputs.flipped,
            wire_numbers=wire_numbers,
        )
        summary = controller.run_sweep(corridors)
        LOGGER.info("Streaming sweep summary: %s", summary)
    finally:
        _cleanup_after_measurement(ctx, controller)


def _begin_measurement(ctx: GUIContext, name: str) -> bool:
    """Mark a measurement as active, returning ``False`` if one is already running."""

    with ctx.measurement_lock:
        if ctx.measurement_active:
            active_name = ctx.active_measurement_name or "another measurement"
            LOGGER.warning(
                "Ignoring %s request because %s is already running.",
                name,
                active_name,
            )
            return False
        ctx.measurement_active = True
        ctx.active_measurement_name = name
        return True


def _end_measurement(ctx: GUIContext) -> None:
    """Clear the active measurement marker."""

    with ctx.measurement_lock:
        ctx.measurement_active = False
        ctx.active_measurement_name = ""


def _run_in_thread(func=None, *, measurement: bool = False):
    """Decorator to execute ``func`` in a daemon thread."""

    def decorator(func):
        @wraps(func)
        def wrapper(ctx: GUIContext, *args: Any, **kwargs: Any) -> None:
            try:
                inputs = _capture_worker_inputs(ctx)
            except ValueError:
                return

            save_state(ctx)

            measurement_name = func.__name__.replace("_", " ")
            if measurement and not _begin_measurement(ctx, measurement_name):
                return

            def run() -> None:
                ctx.stop_event.clear()
                LOGGER.info(
                    "Worker thread starting: %s measurement=%s",
                    measurement_name,
                    measurement,
                )
                try:
                    func(ctx, inputs, *args, **kwargs)
                finally:
                    ctx.stop_event.clear()
                    if measurement:
                        _end_measurement(ctx)
                    LOGGER.info("Worker thread finished: %s", measurement_name)

            try:
                Thread(
                    target=run,
                    name=f"gui-{func.__name__}",
                    daemon=True,
                ).start()
            except Exception:
                if measurement:
                    _end_measurement(ctx)
                raise

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


@_run_in_thread(measurement=True)
def measure_calibrate(ctx: GUIContext, inputs: WorkerInputs) -> None:
    """Measure and calibrate a single wire."""

    if _measurement_mode(inputs) != "legacy":
        wire_number = int(inputs.wire_number)
        _run_streaming_for_wires(ctx, inputs, [wire_number])
        LOGGER.info("Done streaming measurement for wire %s", wire_number)
        return

    tensiometer: Tensiometer | None = None
    try:
        tensiometer = create_tensiometer(ctx, inputs)
        wire_number = int(inputs.wire_number)
        tensiometer.measure_calibrate(wire_number)
        LOGGER.info("Done calibrating wire %s", wire_number)
    except ValueError as exc:
        LOGGER.warning("%s", exc)
    finally:
        _cleanup_after_measurement(ctx, tensiometer)


@_run_in_thread(measurement=True)
def measure_auto(ctx: GUIContext, inputs: WorkerInputs) -> None:
    """Automatically measure the full APA."""
    LOGGER.info("Starting automatic measurement of full APA")

    if _measurement_mode(inputs) != "legacy":
        from dune_tension.summaries import get_missing_wires

        config = _make_config_from_inputs(inputs)
        wires_to_measure = get_missing_wires(config).get(inputs.side, [])
        _run_streaming_for_wires(ctx, inputs, list(map(int, wires_to_measure)))
        if ctx.stop_event.is_set():
            _set_estimated_time(ctx, "Interrupted")
        return

    tensiometer: Tensiometer | None = None
    try:
        _set_estimated_time(ctx, "--")
        tensiometer = create_tensiometer(ctx, inputs)
        tensiometer.measure_auto()
        if ctx.stop_event.is_set():
            _set_estimated_time(ctx, "Interrupted")
    except ValueError as exc:
        LOGGER.warning("%s", exc)
        _set_estimated_time(ctx, "Not running")
    except Exception:
        _set_estimated_time(ctx, "Not running")
        raise
    finally:
        _cleanup_after_measurement(ctx, tensiometer, reset_estimated_time=False)


def _parse_ranges(text: str) -> list[tuple[int, int]]:
    """Return list of ``(start, end)`` tuples parsed from ``text``."""

    ranges: list[tuple[int, int]] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start_str, end_str = part.split("-", 1)
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                continue
        else:
            try:
                start = end = int(part)
            except ValueError:
                continue
        ranges.append((start, end))
    return ranges


@_run_in_thread(measurement=True)
def measure_list_button(ctx: GUIContext, inputs: WorkerInputs) -> None:
    """Measure a comma separated list of wire ranges."""

    ranges = _parse_ranges(inputs.wire_list)
    wire_list: list[int] = []
    for start, end in ranges:
        step = 1 if end >= start else -1
        wire_list.extend(range(start, end + step, step))
    if inputs.skip_measured:
        filtered_wire_list = _filter_unmeasured_wires(inputs, wire_list)
        if filtered_wire_list:
            wire_list = filtered_wire_list
        elif wire_list:
            LOGGER.info(
                "All requested wires are already measured; keeping the requested list so the winder still seeks those wire positions."
            )

    if _measurement_mode(inputs) != "legacy":
        LOGGER.info("Streaming measurement wires: %s", wire_list)
        _run_streaming_for_wires(ctx, inputs, wire_list)
        return

    tensiometer: Tensiometer | None = None
    try:
        tensiometer = create_tensiometer(ctx, inputs)
        LOGGER.info("Measuring wires: %s", wire_list)
        tensiometer.measure_list(wire_list, preserve_order=True)
    except ValueError as exc:
        LOGGER.warning("%s", exc)
    finally:
        _cleanup_after_measurement(ctx, tensiometer)


def _filter_unmeasured_wires(inputs: WorkerInputs, wire_list: list[int]) -> list[int]:
    """Return ``wire_list`` with already measured wires removed."""

    from dune_tension.summaries import get_tension_series

    config = _make_config_from_inputs(inputs)
    side = str(config.side).upper()
    measured_wires = set(get_tension_series(config).get(side, {}))
    if not measured_wires:
        return wire_list

    skipped_wires = [wire for wire in wire_list if wire in measured_wires]
    if skipped_wires:
        LOGGER.info("Skipping already measured wires: %s", skipped_wires)

    remaining_wires = [wire for wire in wire_list if wire not in measured_wires]
    if not remaining_wires:
        LOGGER.info("All requested wires are already measured.")
    return remaining_wires


@_run_in_thread
def calibrate_background_noise(ctx: GUIContext, _inputs: WorkerInputs) -> None:
    """Record background noise for filtering future recordings."""

    try:
        from dune_tension.audio_runtime import (
            calibrate_background_noise,
            get_samplerate,
        )

        samplerate = get_samplerate()
        if samplerate is None:
            LOGGER.warning("Unable to access audio device")
            return
        calibrate_background_noise(_safe_int(samplerate, 44100))
        LOGGER.info("Background noise calibrated")
    finally:
        ctx.stop_event.clear()


@_run_in_thread(measurement=True)
def measure_condition(ctx: GUIContext, inputs: WorkerInputs) -> None:
    """Measure wires whose tension satisfies the configured expression."""

    tensiometer: Tensiometer | None = None
    expr = inputs.condition.strip()
    if not expr:
        LOGGER.warning("No condition specified")
        return

    try:
        config = _make_config_from_inputs(inputs)
        wires = _get_wires_matching_tension_condition(config, expr)
        if not wires:
            LOGGER.info("No wires satisfy: %s", expr)
            return
        if _measurement_mode(inputs) != "legacy":
            LOGGER.info("Streaming measurement wires %s matching %r", wires, expr)
            _run_streaming_for_wires(ctx, inputs, wires)
            return
        tensiometer = create_tensiometer(ctx, inputs)
        LOGGER.info("Measuring wires %s matching %r", wires, expr)
        tensiometer.measure_list(wires, preserve_order=False)
    except ValueError as exc:
        LOGGER.warning("%s", exc)
    finally:
        _cleanup_after_measurement(ctx, tensiometer)


@_run_in_thread
def seek_camera_to_pin(ctx: GUIContext, inputs: WorkerInputs) -> None:
    layer = str(inputs.layer).upper()
    side = str(inputs.side).upper()
    pin_name = _selected_laser_offset_pin(layer, side, inputs.laser_offset_pin)
    if pin_name is None:
        LOGGER.warning("No laser-offset pin is available for layer %s side %s.", layer, side)
        return

    try:
        ensure_layer_calibration_ready(layer)
        if get_plc_io_mode() == "desktop":
            moved = desktop_seek_pin(pin_name, DEFAULT_PIN_SEEK_VELOCITY)
        else:
            moved = _move_to_local_pin(ctx, layer, pin_name, DEFAULT_PIN_SEEK_VELOCITY)
        if not moved:
            LOGGER.warning("Failed to seek to pin %s.", pin_name)
            return
        LOGGER.info("Seeked camera to %s.", pin_name)
    except Exception as exc:
        LOGGER.warning("Failed to seek camera to pin %s: %s", pin_name, exc)
    finally:
        try:
            ctx.root.after(0, lambda: refresh_uv_laser_offset_controls(ctx))
        except Exception:
            pass


@_run_in_thread
def capture_laser_offset_button(ctx: GUIContext, inputs: WorkerInputs) -> None:
    layer = str(inputs.layer).upper()
    side = str(inputs.side).upper()
    pin_name = _selected_laser_offset_pin(layer, side, inputs.laser_offset_pin)
    if pin_name is None:
        LOGGER.warning("No laser-offset pin is available for layer %s side %s.", layer, side)
        return

    try:
        ensure_layer_calibration_ready(layer)
        live_x, live_y = _current_stage_xy(ctx)
        focus_position = int(getattr(ctx.servo_controller, "focus_position", 0))
        entry = save_captured_laser_offset(
            layer=layer,
            side=side,
            pin_name=pin_name,
            captured_stage_xy=(live_x, live_y),
            captured_focus=focus_position,
        )
        LOGGER.info(
            "Captured laser offset for side %s from %s: x=%0.3f mm y=%0.3f mm",
            side,
            pin_name,
            float(entry["x"]),
            float(entry["y"]),
        )
    except Exception as exc:
        LOGGER.warning("Failed to capture laser offset from %s: %s", pin_name, exc)
    finally:
        try:
            ctx.root.after(0, lambda: refresh_uv_laser_offset_controls(ctx))
        except Exception:
            pass


def _parse_pairs(text: str) -> list[tuple[int, float]]:
    pair_re = re.compile(r"\(?\s*(\d+)\s*[,:]\s*([+-]?\d+(?:\.\d*)?)\s*\)?")
    pairs: list[tuple[int, float]] = []
    for match in pair_re.finditer(text):
        try:
            wire = int(match.group(1))
            tension = float(match.group(2))
        except ValueError:
            continue
        pairs.append((wire, tension))
    return pairs


def _compile_tension_condition(expr: str):
    """Compile a safe condition expression using variables ``t`` (tension) and ``n`` (wire number)."""

    allowed_nodes = (
        ast.Expression,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
    )

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid syntax: {exc.msg}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"disallowed expression node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in ("t", "n"):
            raise ValueError("only variables 't' (tension) and 'n' (wire number) are allowed")

    code = compile(tree, "<tension-condition>", "eval")

    def predicate(wire_number: int, tension: float) -> bool:
        result = eval(code, {"__builtins__": {}}, {"t": float(tension), "n": int(wire_number)})
        return bool(result)

    return predicate


def _normalize_tension_condition(expr: str) -> str:
    """Normalize GUI-friendly boolean syntax into a Python expression."""

    normalized = re.sub(r"\bAND\b", "and", expr, flags=re.IGNORECASE)
    normalized = re.sub(r"\bOR\b", "or", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bNOT\b", "not", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace(",", " and ")
    return normalized


def _get_wires_matching_tension_condition(config: Any, expr: str) -> list[int]:
    from dune_tension.summaries import get_tension_series

    normalized_expr = _normalize_tension_condition(expr)
    try:
        predicate = _compile_tension_condition(normalized_expr)
    except ValueError as exc:
        LOGGER.warning("Invalid expression %r: %s", expr, exc)
        return []

    wires: list[int] = []
    tension_series = get_tension_series(config)
    for wire_number, tension in sorted(
        tension_series.get(str(config.side).upper(), {}).items()
    ):
        try:
            if predicate(int(wire_number), float(tension)):
                wires.append(int(wire_number))
        except Exception as exc:
            LOGGER.warning("Error evaluating condition for wire %s: %s", wire_number, exc)
            return []
    return wires


def clear_range(ctx: GUIContext) -> None:
    raw_text = ctx.widgets.entry_clear_range.get().strip()
    cfg = _make_config_from_widgets(ctx)
    ranges = _parse_ranges(raw_text)
    if ranges:
        for start, end in ranges:
            clear_wire_range(
                cfg.data_path,
                cfg.apa_name,
                cfg.layer,
                cfg.side,
                start,
                end,
            )
        LOGGER.info("Cleared ranges: %s", raw_text)
        _request_live_summary_refresh(ctx, cfg)
        return

    wires = _get_wires_matching_tension_condition(cfg, raw_text)
    if not wires:
        LOGGER.warning("No valid range or condition specified")
        return

    clear_wire_numbers(cfg.data_path, cfg.apa_name, cfg.layer, cfg.side, wires)
    LOGGER.info("Cleared wires %s matching %r", wires, raw_text)
    _request_live_summary_refresh(ctx, cfg)


def erase_outliers(ctx: GUIContext) -> None:
    _erase_detected_outliers(ctx, find_outliers, "residual")


def erase_distribution_outliers(ctx: GUIContext) -> None:
    _erase_detected_outliers(ctx, find_distribution_outliers, "bulk-distribution")


def _parse_outlier_erase_expression(expr: str) -> tuple[float, list[str]]:
    """Parse sigma and optional wire-number predicates from a GUI text field.

    Supported forms include:
    - ``2.5``
    - ``2.5, n<1000``
    - ``n<1000, 2.5``
    - ``n<1000, n>2000, 3``

    The first numeric token is treated as the sigma multiplier. Remaining
    non-numeric clauses are treated as wire-number conditions.
    """

    sigma = 2.0
    predicates: list[str] = []
    for clause in (part.strip() for part in expr.split(",")):
        if not clause:
            continue
        try:
            sigma = float(clause)
            continue
        except ValueError:
            predicates.append(clause)
    return sigma, predicates


def _erase_detected_outliers(
    ctx: GUIContext,
    detector,
    detector_name: str,
) -> None:
    cfg = _make_config_from_widgets(ctx)
    try:
        conf = float(ctx.widgets.entry_confidence.get())
    except ValueError:
        conf = 0.5
    raw_expr = ctx.widgets.entry_times_sigma.get().strip()
    times_sigma, wire_predicates = _parse_outlier_erase_expression(raw_expr)

    outliers = sorted(
        detector(
            cfg.data_path,
            cfg.apa_name,
            cfg.layer,
            cfg.side,
            times_sigma=times_sigma,
            confidence_threshold=conf,
        )
    )
    if wire_predicates:
        filtered_outliers: list[int] = []
        for wire in outliers:
            try:
                wire_number = int(wire)
                if all(
                    _compile_tension_condition(pred)(wire_number, 0.0)
                    for pred in wire_predicates
                ):
                    filtered_outliers.append(wire_number)
            except Exception as exc:
                LOGGER.warning("Error evaluating outlier filter for wire %s: %s", wire, exc)
                return
        outliers = filtered_outliers

    if outliers:
        clear_wire_numbers(
            cfg.data_path,
            cfg.apa_name,
            cfg.layer,
            cfg.side,
            outliers,
        )
        LOGGER.info("Erased %s outlier wires: %s", detector_name, outliers)
        _request_live_summary_refresh(ctx, cfg)
    else:
        LOGGER.info("No %s outlier wires found", detector_name)


def set_manual_tension(ctx: GUIContext) -> None:
    pairs = _parse_pairs(ctx.widgets.entry_set_tension.get())
    if not pairs:
        LOGGER.warning("No valid tension pairs specified")
        return

    cfg = _make_config_from_widgets(ctx)
    df = get_dataframe(cfg.data_path)
    for wire, tension in pairs:
        mask = (
            (df["apa_name"] == cfg.apa_name)
            & (df["layer"] == cfg.layer)
            & (df["side"] == cfg.side)
            & (df["wire_number"].astype(int) == wire)
        )
        if mask.any():
            df.loc[mask, "tension"] = tension
            if "time" in df.columns:
                df.loc[mask, "time"] = datetime.now().isoformat()
        else:
            row = {col: "" for col in EXPECTED_COLUMNS}
            row.update(
                {
                    "apa_name": cfg.apa_name,
                    "layer": cfg.layer,
                    "side": cfg.side,
                    "wire_number": wire,
                    "frequency": 0.0,
                    "confidence": 1,
                    "tension": tension,
                    "tension_pass": 1,
                    "x": 0.0,
                    "y": 0.0,
                    "time": datetime.now().isoformat(),
                    "zone": 1,
                    "wire_length": 0.0,
                }
            )
            df.loc[len(df)] = row
    update_dataframe(cfg.data_path, df)
    LOGGER.info("Updated tensions: %s", pairs)
    _request_live_summary_refresh(ctx, cfg)


def interrupt(ctx: GUIContext) -> None:
    ctx.stop_event.set()
    ctx.servo_controller.stop_loop()
    _set_estimated_time(ctx, "Interrupted")


def monitor_tension_logs(ctx: GUIContext) -> None:
    """Check for updates to the tension data file and refresh logs."""

    cfg = _make_config_from_widgets(ctx)

    try:
        mtime = os.path.getmtime(cfg.data_path)
    except OSError:
        mtime = None

    if ctx.monitor_last_path != cfg.data_path or ctx.monitor_last_mtime != mtime:
        ctx.monitor_last_path = cfg.data_path
        ctx.monitor_last_mtime = mtime

        def run() -> None:
            try:
                from dune_tension.summaries import update_tension_logs

                update_tension_logs(cfg)
                _request_live_summary_refresh(ctx, cfg)
                LOGGER.info(
                    "Updated tension logs for %s layer %s",
                    cfg.apa_name,
                    cfg.layer,
                )
            except Exception as exc:
                LOGGER.warning("Failed to update logs: %s", exc)

        if ctx.monitor_thread is None or not ctx.monitor_thread.is_alive():
            ctx.monitor_thread = Thread(
                target=run,
                name="gui-monitor-tension-logs",
                daemon=True,
            )
            ctx.monitor_thread.start()

    ctx.root.after(1000, lambda: monitor_tension_logs(ctx))


@_run_in_thread
def refresh_tension_logs(ctx: GUIContext, inputs: WorkerInputs) -> None:
    """Force an update of the tension logs regardless of file changes."""

    cfg = _make_config_from_inputs(inputs)

    try:
        from dune_tension.summaries import update_tension_logs

        update_tension_logs(cfg)
        _request_live_summary_refresh(ctx, cfg)
        try:
            ctx.monitor_last_path = cfg.data_path
            ctx.monitor_last_mtime = os.path.getmtime(cfg.data_path)
        except OSError:
            ctx.monitor_last_mtime = None
        LOGGER.info(
            "Manually refreshed tension logs for %s layer %s",
            cfg.apa_name,
            cfg.layer,
        )
    except Exception as exc:
        LOGGER.warning("Failed to refresh logs: %s", exc)


def manual_goto(ctx: GUIContext) -> None:
    text = ctx.widgets.entry_xy.get()
    try:
        x_str, y_str = text.split(",")
        x_val = float(x_str.strip())
        y_val = float(y_str.strip())
    except ValueError:
        LOGGER.warning("Invalid coordinates: %s", text)
        return
    try:
        moved = ctx.goto_xy(x_val, y_val)
    except Exception as exc:
        LOGGER.warning("Manual goto failed: %s", exc)
        return
    if moved is False:
        LOGGER.warning("Manual goto to %s,%s failed: PLC not available.", x_val, y_val)


def manual_increment(ctx: GUIContext, dx: float, dy: float) -> None:
    try:
        cur_x, cur_y = ctx.get_xy()
    except Exception as exc:
        LOGGER.warning("Cannot increment: failed to read position: %s", exc)
        return
    w = ctx.widgets
    if (w.side_var.get() == "A" and not w.flipped_var.get()) or (
        w.side_var.get() == "B" and w.flipped_var.get()
    ):
        x_sign = 1.0
    else:
        x_sign = -1.0

    new_x = cur_x + x_sign * dx * 0.1
    new_y = cur_y + dy * 0.1
    new_x = round(new_x, 1)
    new_y = round(new_y, 1)

    try:
        moved = ctx.goto_xy(new_x, new_y)
    except Exception as exc:
        LOGGER.warning("Manual increment failed: %s", exc)
        return
    if moved is False:
        LOGGER.warning("Manual increment to %s,%s failed: PLC not available.", new_x, new_y)


def update_focus_command_indicator(ctx: GUIContext, value: int) -> None:
    ctx.focus_command_var.set(str(value))
    canvas = ctx.focus_command_canvas
    dot = ctx.focus_command_dot
    if not canvas or not dot:
        return
    length = canvas.winfo_width()
    slider = ctx.widgets.focus_slider
    low = int(slider["from"])
    high = int(slider["to"])
    if high == low:
        x_pos = 0
    else:
        x_pos = (value - low) / (high - low) * length
    radius = 3
    canvas.coords(dot, x_pos - radius, 5 - radius, x_pos + radius, 5 + radius)


def handle_close(ctx: GUIContext) -> None:
    LOGGER.info("GUI shutdown requested.")
    ctx.stop_event.set()
    try:
        ctx.servo_controller.stop_loop()
    except Exception as exc:
        LOGGER.warning("Failed to stop servo loop during shutdown: %s", exc)
    if ctx.log_binding is not None:
        try:
            ctx.log_binding.close()
        except Exception:
            LOGGER.exception("Failed to close GUI log binding during shutdown.")
    if ctx.valve_controller is not None:
        try:
            ctx.valve_controller.close()
        except Exception:
            LOGGER.exception("Failed to close valve controller during shutdown.")
    try:
        import sounddevice as sd  # type: ignore

        sd.stop()
    except Exception:
        pass
    try:
        ctx.root.destroy()
    except Exception:
        LOGGER.exception("Failed to destroy Tk root during shutdown.")


def _make_config_from_widgets(ctx: GUIContext):
    w = ctx.widgets
    try:
        conf = float(w.entry_confidence.get())
    except ValueError:
        conf = 0.5

    return make_config(
        apa_name=w.entry_apa.get(),
        layer=w.layer_var.get(),
        side=w.side_var.get(),
        flipped=w.flipped_var.get(),
        samples_per_wire=1,
        confidence_threshold=conf,
        plot_audio=w.plot_audio_var.get(),
    )


def _make_config_from_inputs(inputs: WorkerInputs):
    return make_config(
        apa_name=inputs.apa_name,
        layer=inputs.layer,
        side=inputs.side,
        flipped=inputs.flipped,
        samples_per_wire=1,
        confidence_threshold=inputs.confidence,
        plot_audio=inputs.plot_audio,
    )


def _cleanup_after_measurement(
    ctx: GUIContext,
    measurement_obj: Any | None,
    *,
    reset_estimated_time: bool = True,
) -> None:
    if measurement_obj is not None:
        try:
            measurement_obj.close()
        except Exception:
            pass
    try:
        from dune_tension.plc_io import reset_plc

        reset_plc()
    except Exception:
        pass
    if reset_estimated_time:
        _set_estimated_time(ctx, "Not running")
    ctx.stop_event.clear()
