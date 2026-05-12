"""Simplified Tkinter GUI for routine APA tensiometer measurements.

Exposes only Measure Calibrate, Measure All, Refine, and Interrupt actions.
All other measurement parameters are fixed at known-good defaults.
"""

from __future__ import annotations

import logging
from tkinter import messagebox
from typing import Any, cast
import tkinter as tk
import tkinter.font as tkfont

from dune_tension import apa_naming
from dune_tension.config import MEASUREMENT_WIGGLE_CONFIG
from dune_tension.gui._layout import configure_root_minimum_size
from dune_tension.gui.actions import (
    adjust_focus_with_x_compensation,
    handle_close,
    interrupt,
    measure_auto,
    measure_calibrate,
    measure_list_button,
    measure_refine_outliers,
    monitor_tension_logs,
    refresh_connections,
    refresh_tension_logs,
    refresh_uv_laser_offset_controls,
)
from dune_tension.gui.app import _initialise_servo, _schedule_health_logging
from dune_tension.gui.context import GUIContext, GUIWidgets, create_context
from dune_tension.gui.crash_logging import (
    format_process_stats,
    install_gui_crash_logging,
    install_tk_exception_logging,
)
from dune_tension.gui.live_plots import LivePlotManager
from dune_tension.gui.logging_panel import configure_gui_logging
from dune_tension.gui.state import load_state
from dune_tension.services import build_runtime_bundle, resolve_runtime_options
from dune_tension.tensiometer_functions import make_config

LOGGER = logging.getLogger(__name__)


def run_simple_app(
    state_file: str = "simple_gui_state.json", root: tk.Misc | None = None
) -> None:
    """Launch the simplified Tkinter GUI."""

    crash_logging = install_gui_crash_logging()
    LOGGER.info(
        "Launching simplified tensiometer GUI. state_file=%s root_provided=%s log_path=%s fault_log_path=%s",
        state_file,
        root is not None,
        crash_logging.log_path,
        crash_logging.fault_log_path,
    )

    try:
        if root is None:
            LOGGER.info("Creating Tk root window.")
        root = cast(tk.Tk, root or tk.Tk())
        install_tk_exception_logging(root)
        root.title("Tensiometer GUI (simplified)")
        for font_name in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont"):
            try:
                tkfont.nametofont(font_name).configure(size=8)
            except Exception:
                pass
        if hasattr(root, "columnconfigure"):
            root.columnconfigure(0, weight=0)
            root.columnconfigure(1, weight=1)
            root.columnconfigure(2, weight=1)
        if hasattr(root, "rowconfigure"):
            root.rowconfigure(0, weight=1)
        LOGGER.info("Tk root ready. %s", format_process_stats())

        focus_command_var = tk.StringVar(master=root, value="4000")
        estimated_time_var = tk.StringVar(master=root, value="Not running")
        LOGGER.info("Creating simplified GUI widgets.")
        (
            widgets,
            focus_canvas,
            focus_dot,
            buttons,
            log_text,
            summary_plot_frame,
            waveform_plot_frame,
        ) = _create_widgets(root, estimated_time_var)
        log_binding = configure_gui_logging(root, log_text)
        LOGGER.info(
            "GUI log panel attached. persistent_log=%s fault_log=%s",
            crash_logging.log_path,
            crash_logging.fault_log_path,
        )

        runtime_options = resolve_runtime_options()
        LOGGER.info("Resolved runtime options: %s", runtime_options)
        runtime_bundle = build_runtime_bundle(runtime_options)
        LOGGER.info(
            "Runtime bundle ready. motion=%s audio_samplerate=%s servo=%s relay=%s",
            type(runtime_bundle.motion).__name__,
            getattr(runtime_bundle.audio, "samplerate", "unknown"),
            type(runtime_bundle.servo_controller).__name__,
            type(runtime_bundle.relay_controller).__name__
            if runtime_bundle.relay_controller is not None
            else "None",
        )
        ctx = create_context(
            root,
            widgets,
            state_file,
            focus_command_var=focus_command_var,
            estimated_time_var=estimated_time_var,
            runtime_bundle=runtime_bundle,
        )
        ctx.focus_command_canvas = focus_canvas
        ctx.focus_command_dot = focus_dot
        ctx.log_binding = log_binding
        ctx.live_plot_manager = LivePlotManager(
            root,
            summary_plot_frame,
            waveform_plot_frame,
        )

        _configure_commands(ctx, buttons)
        LOGGER.info("Simplified GUI commands configured.")

        load_state(ctx)
        LOGGER.info("Loaded GUI state from %s", state_file)
        refresh_uv_laser_offset_controls(ctx)
        if ctx.live_plot_manager is not None:
            LOGGER.info("Requesting initial live summary refresh.")
            ctx.live_plot_manager.request_summary_refresh(
                make_config(
                    apa_name=apa_naming.compose(
                        ctx.widgets.apa_location_var.get(),
                        int(ctx.widgets.apa_number_var.get()),
                    ),
                    layer=ctx.widgets.layer_var.get(),
                    side=ctx.widgets.side_var.get(),
                    flipped=bool(ctx.widgets.flipped_var.get()),
                )
            )
        _initialise_servo(ctx)
        _schedule_health_logging(ctx)

        cast(tk.Tk, ctx.root).protocol("WM_DELETE_WINDOW", lambda: handle_close(ctx))
        ctx.root.after(1000, lambda: monitor_tension_logs(ctx))
        LOGGER.info("Entering Tk mainloop.")
        ctx.root.mainloop()
        LOGGER.info("Tk mainloop exited.")
    except Exception:
        LOGGER.exception(
            "Simplified tensiometer GUI crashed during startup or runtime. persistent_log=%s fault_log=%s",
            crash_logging.log_path,
            crash_logging.fault_log_path,
        )
        raise
    finally:
        crash_logging.flush()


def _create_widgets(
    root: tk.Misc,
    estimated_time_var: tk.StringVar,
) -> tuple[
    GUIWidgets,
    tk.Canvas | None,
    Any | None,
    dict[str, tk.Button],
    Any | None,
    tk.Misc,
    tk.Misc,
]:
    """Build and lay out the simplified GUI widgets."""

    main_frame = tk.Frame(root)
    main_frame.grid(row=0, column=0, padx=(6, 3), pady=6, sticky="nsew")
    if hasattr(main_frame, "columnconfigure"):
        main_frame.columnconfigure(0, weight=1)
    if hasattr(main_frame, "rowconfigure"):
        main_frame.rowconfigure(0, weight=1)

    plots_frame = tk.Frame(root)
    plots_frame.grid(row=0, column=1, padx=3, pady=6, sticky="nsew")
    if hasattr(plots_frame, "columnconfigure"):
        plots_frame.columnconfigure(0, weight=1)
    if hasattr(plots_frame, "rowconfigure"):
        plots_frame.rowconfigure(0, weight=1)

    log_container_frame = tk.Frame(root)
    log_container_frame.grid(row=0, column=2, padx=(3, 6), pady=6, sticky="nsew")
    if hasattr(log_container_frame, "columnconfigure"):
        log_container_frame.columnconfigure(0, weight=1)
    if hasattr(log_container_frame, "rowconfigure"):
        log_container_frame.rowconfigure(0, weight=1)

    live_plots_frame = tk.LabelFrame(plots_frame, text="Live Plots")
    live_plots_frame.grid(row=0, column=0, sticky="nsew")
    if hasattr(live_plots_frame, "columnconfigure"):
        live_plots_frame.columnconfigure(0, weight=1)
    if hasattr(live_plots_frame, "rowconfigure"):
        live_plots_frame.rowconfigure(0, weight=3)
        live_plots_frame.rowconfigure(1, weight=2)

    log_frame = tk.LabelFrame(log_container_frame, text="Log")
    log_frame.grid(row=0, column=0, sticky="nsew")
    if hasattr(log_frame, "columnconfigure"):
        log_frame.columnconfigure(0, weight=1)
    if hasattr(log_frame, "rowconfigure"):
        log_frame.rowconfigure(0, weight=1)

    summary_plot_frame = tk.Frame(live_plots_frame)
    summary_plot_frame.grid(row=0, column=0, sticky="nsew")
    if hasattr(summary_plot_frame, "columnconfigure"):
        summary_plot_frame.columnconfigure(0, weight=1)
    if hasattr(summary_plot_frame, "rowconfigure"):
        summary_plot_frame.rowconfigure(0, weight=1)

    waveform_plot_frame = tk.Frame(live_plots_frame)
    waveform_plot_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
    if hasattr(waveform_plot_frame, "columnconfigure"):
        waveform_plot_frame.columnconfigure(0, weight=1)
    if hasattr(waveform_plot_frame, "rowconfigure"):
        waveform_plot_frame.rowconfigure(0, weight=1)

    log_text: Any | None = None
    if hasattr(tk, "Text"):
        log_text = tk.Text(log_frame, wrap="word", state="disabled", width=44, height=5)
        log_text.grid(row=0, column=0, sticky="nsew")
        if hasattr(tk, "Scrollbar"):
            scrollbar = tk.Scrollbar(
                log_frame, orient="vertical", command=log_text.yview
            )
            scrollbar.grid(row=0, column=1, sticky="ns")
            log_text.configure(yscrollcommand=scrollbar.set)

    if hasattr(main_frame, "columnconfigure"):
        main_frame.columnconfigure(0, weight=1)

    apa_frame = tk.LabelFrame(main_frame, text="APA")
    apa_frame.grid(row=0, column=0, sticky="ew", pady=3)

    measure_frame = tk.LabelFrame(main_frame, text="Measurement")
    measure_frame.grid(row=1, column=0, sticky="ew", pady=3)
    if hasattr(measure_frame, "columnconfigure"):
        measure_frame.columnconfigure(1, weight=1)

    btn_refresh_plots = tk.Button(main_frame, text="Refresh Plots")
    btn_refresh_plots.grid(row=2, column=0, sticky="ew", pady=(6, 0))

    btn_refresh_connections = tk.Button(main_frame, text="Refresh Connections")
    btn_refresh_connections.grid(row=3, column=0, sticky="ew", pady=(3, 0))

    # APA controls
    tk.Label(apa_frame, text="APA Location:").grid(row=0, column=0, sticky="e")
    apa_location_var = tk.StringVar(apa_frame, value="US")
    tk.OptionMenu(apa_frame, apa_location_var, *apa_naming.LOCATIONS).grid(
        row=0, column=1
    )

    tk.Label(apa_frame, text="APA Number:").grid(row=0, column=2, sticky="e")
    apa_number_var = tk.StringVar(apa_frame, value=apa_naming.NUMBER_LABELS[0])
    tk.OptionMenu(apa_frame, apa_number_var, *apa_naming.NUMBER_LABELS).grid(
        row=0, column=3
    )

    tk.Label(apa_frame, text="Layer:").grid(row=1, column=0, sticky="e")
    layer_var = tk.StringVar(apa_frame, value="X")
    tk.OptionMenu(apa_frame, layer_var, "X", "V", "U", "G").grid(row=1, column=1)

    tk.Label(apa_frame, text="Side:").grid(row=2, column=0, sticky="e")
    side_var = tk.StringVar(apa_frame, value="A")
    tk.OptionMenu(apa_frame, side_var, "A", "B").grid(row=2, column=1)

    a_taped_var = tk.BooleanVar(value=False)
    tk.Checkbutton(apa_frame, text="A taped", variable=a_taped_var).grid(
        row=3, column=0, sticky="w"
    )
    b_taped_var = tk.BooleanVar(value=False)
    tk.Checkbutton(apa_frame, text="B taped", variable=b_taped_var).grid(
        row=3, column=1, sticky="w"
    )

    # Measurement controls
    tk.Label(measure_frame, text="Wire(s):").grid(row=0, column=0, sticky="e")
    entry_wire = tk.Entry(measure_frame)
    entry_wire.grid(row=0, column=1, columnspan=2, sticky="ew")

    skip_measured_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        measure_frame, text="Skip measured", variable=skip_measured_var
    ).grid(row=1, column=0, columnspan=3, sticky="w")

    btn_measure_calibrate = tk.Button(measure_frame, text="Measure Calibrate")
    btn_measure_calibrate.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))

    btn_measure_wires = tk.Button(measure_frame, text="Measure Wires")
    btn_measure_wires.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(3, 0))

    btn_measure_all = tk.Button(measure_frame, text="Measure All")
    btn_measure_all.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(3, 0))

    btn_refine = tk.Button(measure_frame, text="Refine")
    btn_refine.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(3, 0))

    btn_interrupt = tk.Button(measure_frame, text="Interrupt")
    btn_interrupt.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(3, 0))

    tk.Label(measure_frame, text="ETA:").grid(row=7, column=0, sticky="e", pady=(6, 0))
    tk.Label(measure_frame, textvariable=estimated_time_var).grid(
        row=7, column=1, columnspan=2, sticky="w", pady=(6, 0)
    )

    # Hidden host frame: every widget here is required by GUIWidgets but not
    # exposed in the simplified UI. The frame is never gridded, so its children
    # carry their fixed values invisibly.
    hidden = tk.Frame(root)

    flipped_var = tk.BooleanVar(value=False)
    measurement_mode_var = tk.StringVar(hidden, value="legacy")
    confidence_source_var = tk.StringVar(hidden, value="Neural Net")
    use_harmonic_comb_trigger_var = tk.BooleanVar(value=True)

    entry_confidence = tk.Entry(hidden)
    entry_confidence.insert(0, "0.5")

    entry_record_duration = tk.Entry(hidden)
    entry_record_duration.insert(0, "0.5")

    entry_measuring_duration = tk.Entry(hidden)
    entry_measuring_duration.insert(0, "10")

    entry_wiggle_y_sigma = tk.Entry(hidden)
    entry_wiggle_y_sigma.insert(0, str(MEASUREMENT_WIGGLE_CONFIG.y_sigma_mm))

    sweeping_wiggle_var = tk.BooleanVar(value=True)

    entry_sweeping_wiggle_span_mm = tk.Entry(hidden)
    entry_sweeping_wiggle_span_mm.insert(0, "1.5")

    entry_focus_wiggle_sigma = tk.Entry(hidden)
    entry_focus_wiggle_sigma.insert(
        0, str(MEASUREMENT_WIGGLE_CONFIG.focus_sigma_quarter_us)
    )

    use_manual_focus_var = tk.BooleanVar(value=False)
    plot_audio_var = tk.BooleanVar(value=False)
    suppress_wire_preview_var = tk.BooleanVar(value=False)
    skip_measured_zone_var = tk.BooleanVar(value=True)
    disable_x_compensation_var = tk.BooleanVar(value=False)

    # entry_wire is reused for both single-wire calibration and list/range measurement.
    entry_wire_list = entry_wire
    entry_wire_zone = tk.Entry(hidden)
    entry_clear_range = tk.Entry(hidden)
    entry_condition = tk.Entry(hidden)
    entry_legacy_tension_condition = tk.Entry(hidden)

    entry_times_sigma = tk.Entry(hidden)
    entry_times_sigma.insert(0, "2.0")

    entry_set_tension = tk.Entry(hidden)
    entry_xy = tk.Entry(hidden)

    focus_slider = tk.Scale(hidden, from_=4000, to=8000, orient=tk.HORIZONTAL)
    focus_slider.set(4000)

    focus_command_canvas: tk.Canvas | None = None
    focus_command_dot: Any | None = None
    if hasattr(tk, "Canvas"):
        focus_command_canvas = tk.Canvas(hidden, height=8)
        focus_command_canvas.create_line(0, 5, int(focus_slider.cget("length")), 5)
        focus_command_dot = focus_command_canvas.create_oval(
            0, 0, 0, 0, fill="blue", outline=""
        )

    stream_segment_var = tk.StringVar(hidden, value="Idle")
    stream_comb_var = tk.StringVar(hidden, value="0.00")
    stream_focus_var = tk.StringVar(hidden, value="--")
    stream_pitch_backlog_var = tk.StringVar(hidden, value="0")
    stream_rescue_queue_var = tk.StringVar(hidden, value="0")

    laser_offset_frame = tk.LabelFrame(hidden, text="Laser Offset")
    laser_offset_pin_var = tk.StringVar(laser_offset_frame, value="")
    laser_offset_pin_menu = tk.OptionMenu(laser_offset_frame, laser_offset_pin_var, "")
    btn_seek_pin = tk.Button(laser_offset_frame, text="Seek Camera To Pin")
    btn_move_laser_to_pin = tk.Button(laser_offset_frame, text="Move Laser To Pin")
    btn_capture_laser_offset = tk.Button(
        laser_offset_frame, text="Capture Laser Offset"
    )
    laser_offset_readout_var = tk.StringVar(laser_offset_frame, value="Side A: not set")

    widgets = GUIWidgets(
        apa_location_var=apa_location_var,
        apa_number_var=apa_number_var,
        measurement_mode_var=measurement_mode_var,
        layer_var=layer_var,
        side_var=side_var,
        flipped_var=flipped_var,
        a_taped_var=a_taped_var,
        b_taped_var=b_taped_var,
        entry_wire=entry_wire,
        entry_wire_list=entry_wire_list,
        entry_confidence=entry_confidence,
        confidence_source_var=confidence_source_var,
        use_harmonic_comb_trigger_var=use_harmonic_comb_trigger_var,
        entry_record_duration=entry_record_duration,
        entry_measuring_duration=entry_measuring_duration,
        entry_wiggle_y_sigma=entry_wiggle_y_sigma,
        sweeping_wiggle_var=sweeping_wiggle_var,
        entry_sweeping_wiggle_span_mm=entry_sweeping_wiggle_span_mm,
        entry_focus_wiggle_sigma=entry_focus_wiggle_sigma,
        use_manual_focus_var=use_manual_focus_var,
        plot_audio_var=plot_audio_var,
        suppress_wire_preview_var=suppress_wire_preview_var,
        skip_measured_var=skip_measured_var,
        entry_wire_zone=entry_wire_zone,
        skip_measured_zone_var=skip_measured_zone_var,
        entry_clear_range=entry_clear_range,
        entry_condition=entry_condition,
        entry_legacy_tension_condition=entry_legacy_tension_condition,
        entry_times_sigma=entry_times_sigma,
        entry_set_tension=entry_set_tension,
        focus_slider=focus_slider,
        disable_x_compensation_var=disable_x_compensation_var,
        entry_xy=entry_xy,
        stream_segment_var=stream_segment_var,
        stream_comb_var=stream_comb_var,
        stream_focus_var=stream_focus_var,
        stream_pitch_backlog_var=stream_pitch_backlog_var,
        stream_rescue_queue_var=stream_rescue_queue_var,
        laser_offset_frame=laser_offset_frame,
        laser_offset_pin_var=laser_offset_pin_var,
        laser_offset_pin_menu=laser_offset_pin_menu,
        laser_offset_readout_var=laser_offset_readout_var,
        btn_seek_pin=btn_seek_pin,
        btn_move_laser_to_pin=btn_move_laser_to_pin,
        btn_capture_laser_offset=btn_capture_laser_offset,
    )

    buttons = {
        "measure_calibrate": btn_measure_calibrate,
        "measure_wires": btn_measure_wires,
        "measure_all": btn_measure_all,
        "refine": btn_refine,
        "interrupt": btn_interrupt,
        "refresh_plots": btn_refresh_plots,
        "refresh_connections": btn_refresh_connections,
    }

    configure_root_minimum_size(root, main_frame, plots_frame, log_container_frame)

    return (
        widgets,
        focus_command_canvas,
        focus_command_dot,
        buttons,
        log_text,
        summary_plot_frame,
        waveform_plot_frame,
    )


def _measure_calibrate_single(ctx: GUIContext) -> None:
    """Run measure_calibrate, rejecting list/range entries."""

    text = ctx.widgets.entry_wire.get().strip()
    try:
        int(text)
    except ValueError:
        messagebox.showerror(
            "Input Error",
            "Measure Calibrate requires a single wire number. "
            "Use Measure Wires for lists or ranges.",
        )
        return
    measure_calibrate(ctx)


def _configure_commands(ctx: GUIContext, buttons: dict[str, tk.Button]) -> None:
    """Attach the simplified-GUI callbacks."""

    buttons["measure_calibrate"].configure(
        command=lambda: _measure_calibrate_single(ctx)
    )
    buttons["measure_wires"].configure(command=lambda: measure_list_button(ctx))
    buttons["measure_all"].configure(command=lambda: measure_auto(ctx))
    buttons["refine"].configure(command=lambda: measure_refine_outliers(ctx))
    buttons["interrupt"].configure(command=lambda: interrupt(ctx))
    buttons["refresh_plots"].configure(command=lambda: refresh_tension_logs(ctx))
    buttons["refresh_connections"].configure(command=lambda: refresh_connections(ctx))

    widgets = ctx.widgets
    widgets.focus_slider.configure(
        command=lambda val: adjust_focus_with_x_compensation(ctx, int(float(val)))
    )
    for variable in (
        widgets.layer_var,
        widgets.side_var,
        widgets.measurement_mode_var,
    ):
        variable.trace_add(
            "write",
            lambda *_args: refresh_uv_laser_offset_controls(ctx),
        )
