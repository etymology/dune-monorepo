"""Application bootstrap for the tensiometer GUI."""

from __future__ import annotations

from functools import partial
import logging
from typing import Any
import tkinter as tk
import tkinter.font as tkfont

from dune_tension.config import MEASUREMENT_WIGGLE_CONFIG
from dune_tension.gui.actions import (
    adjust_focus_with_x_compensation,
    calibrate_background_noise,
    capture_laser_offset_button,
    clear_range,
    erase_distribution_outliers,
    erase_outliers,
    handle_close,
    interrupt,
    manual_goto,
    manual_increment,
    measure_auto,
    measure_calibrate,
    measure_condition,
    measure_list_button,
    measure_zone_button,
    monitor_tension_logs,
    move_laser_to_pin_button,
    refresh_tension_logs,
    refresh_uv_laser_offset_controls,
    seek_camera_to_pin,
    set_manual_tension,
    update_focus_command_indicator,
)
from dune_tension.gui.crash_logging import (
    format_process_stats,
    install_gui_crash_logging,
    install_tk_exception_logging,
)
from dune_tension.gui.context import GUIContext, GUIWidgets, create_context
from dune_tension.gui.live_plots import (
    LIVE_SUMMARY_FIGSIZE,
    LIVE_WAVEFORM_FIGSIZE,
    LivePlotManager,
)
from dune_tension.gui.logging_panel import configure_gui_logging
from dune_tension.gui.state import load_state
from dune_tension.services import build_runtime_bundle, resolve_runtime_options
from dune_tension.tensiometer_functions import make_config

LOGGER = logging.getLogger(__name__)


def run_app(state_file: str = "gui_state.json", root: tk.Misc | None = None) -> None:
    """Launch the Tkinter GUI."""

    crash_logging = install_gui_crash_logging()
    LOGGER.info(
        "Launching tensiometer GUI. state_file=%s root_provided=%s log_path=%s fault_log_path=%s",
        state_file,
        root is not None,
        crash_logging.log_path,
        crash_logging.fault_log_path,
    )

    try:
        if root is None:
            LOGGER.info("Creating Tk root window.")
        root = root or tk.Tk()
        install_tk_exception_logging(root)
        root.title("Tensiometer GUI")
        for font_name in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont"):
            try:
                tkfont.nametofont(font_name).configure(size=8)
            except Exception:
                pass
        if hasattr(root, "columnconfigure"):
            root.columnconfigure(0, weight=0)
            root.columnconfigure(1, weight=1)
        if hasattr(root, "rowconfigure"):
            root.rowconfigure(0, weight=1)
        LOGGER.info("Tk root ready. %s", format_process_stats())

        focus_command_var = tk.StringVar(master=root, value="4000")
        estimated_time_var = tk.StringVar(master=root, value="Not running")
        LOGGER.info("Creating GUI widgets.")
        (
            widgets,
            focus_canvas,
            focus_dot,
            buttons,
            pad_buttons,
            log_text,
            summary_plot_frame,
            waveform_plot_frame,
        ) = _create_widgets(
            root, focus_command_var, estimated_time_var
        )
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
            "Runtime bundle ready. motion=%s audio_samplerate=%s servo=%s valve=%s",
            type(runtime_bundle.motion).__name__,
            getattr(runtime_bundle.audio, "samplerate", "unknown"),
            type(runtime_bundle.servo_controller).__name__,
            type(runtime_bundle.valve_controller).__name__
            if runtime_bundle.valve_controller is not None
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

        _configure_commands(ctx, buttons, pad_buttons)
        LOGGER.info("GUI commands configured.")

        load_state(ctx)
        LOGGER.info("Loaded GUI state from %s", state_file)
        refresh_uv_laser_offset_controls(ctx)
        if ctx.live_plot_manager is not None:
            LOGGER.info("Requesting initial live summary refresh.")
            ctx.live_plot_manager.request_summary_refresh(
                make_config(
                    apa_name=ctx.widgets.entry_apa.get(),
                    layer=ctx.widgets.layer_var.get(),
                    side=ctx.widgets.side_var.get(),
                    flipped=bool(ctx.widgets.flipped_var.get()),
                )
            )
        _initialise_servo(ctx)
        _schedule_health_logging(ctx)

        ctx.root.protocol("WM_DELETE_WINDOW", lambda: handle_close(ctx))
        ctx.root.after(1000, lambda: monitor_tension_logs(ctx))
        LOGGER.info("Entering Tk mainloop.")
        ctx.root.mainloop()
        LOGGER.info("Tk mainloop exited.")
    except Exception:
        LOGGER.exception(
            "Tensiometer GUI crashed during startup or runtime. persistent_log=%s fault_log=%s",
            crash_logging.log_path,
            crash_logging.fault_log_path,
        )
        raise
    finally:
        crash_logging.flush()


def _initialise_servo(ctx: GUIContext) -> None:
    try:
        value = int(ctx.widgets.focus_slider.get())
    except Exception:
        value = 4000
    LOGGER.info("Initialising servo focus command to %s", value)
    ctx.servo_controller.on_focus_command = partial(update_focus_command_indicator, ctx)
    ctx.servo_controller.focus_position = value
    try:
        ctx.servo_controller.focus_target(value)
    except Exception as exc:
        LOGGER.warning("Servo focus_target(%s) failed: %s", value, exc)
        update_focus_command_indicator(ctx, value)
    else:
        update_focus_command_indicator(ctx, value)


def _schedule_health_logging(ctx: GUIContext, *, interval_ms: int = 15000) -> None:
    """Emit periodic breadcrumbs so abrupt exits have a recent last-known state."""

    def emit() -> None:
        try:
            LOGGER.info(
                "GUI heartbeat. measurement_active=%s active_measurement=%s focus=%s %s",
                ctx.measurement_active,
                ctx.active_measurement_name or "idle",
                _current_focus_value(ctx),
                format_process_stats(),
            )
        finally:
            try:
                ctx.root.after(interval_ms, emit)
            except Exception:
                pass

    try:
        ctx.root.after(interval_ms, emit)
    except Exception:
        LOGGER.exception("Failed to schedule GUI heartbeat logging.")


def _current_focus_value(ctx: GUIContext) -> int | str:
    try:
        return int(ctx.widgets.focus_slider.get())
    except Exception:
        return "unknown"


def _create_widgets(
    root: tk.Misc,
    focus_command_var: tk.StringVar,
    estimated_time_var: tk.StringVar,
) -> tuple[
    GUIWidgets,
    tk.Canvas | None,
    Any | None,
    dict[str, tk.Button],
    list[tuple[tk.Button, int, int]],
    Any | None,
    tk.Misc,
    tk.Misc,
]:
    """Build and layout the GUI widgets."""

    main_frame = tk.Frame(root)
    main_frame.grid(row=0, column=0, padx=(6, 3), pady=6, sticky="nsew")
    if hasattr(main_frame, "columnconfigure"):
        main_frame.columnconfigure(0, weight=1)
    if hasattr(main_frame, "rowconfigure"):
        main_frame.rowconfigure(0, weight=1)

    side_frame = tk.Frame(root)
    side_frame.grid(row=0, column=1, padx=(3, 6), pady=6, sticky="nsew")
    if hasattr(side_frame, "columnconfigure"):
        side_frame.columnconfigure(0, weight=1)
    if hasattr(side_frame, "rowconfigure"):
        side_frame.rowconfigure(0, weight=1)
        side_frame.rowconfigure(1, weight=1)

    log_frame = tk.LabelFrame(side_frame, text="Log")
    log_frame.grid(row=0, column=0, sticky="nsew")
    if hasattr(log_frame, "columnconfigure"):
        log_frame.columnconfigure(0, weight=1)
    if hasattr(log_frame, "rowconfigure"):
        log_frame.rowconfigure(0, weight=1)

    live_plots_frame = tk.LabelFrame(side_frame, text="Live Plots")
    live_plots_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
    if hasattr(live_plots_frame, "columnconfigure"):
        live_plots_frame.columnconfigure(0, weight=1)
    if hasattr(live_plots_frame, "rowconfigure"):
        live_plots_frame.rowconfigure(0, weight=3)
        live_plots_frame.rowconfigure(1, weight=2)

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
            scrollbar = tk.Scrollbar(log_frame, orient="vertical", command=log_text.yview)
            scrollbar.grid(row=0, column=1, sticky="ns")
            log_text.configure(yscrollcommand=scrollbar.set)

    bottom_frame = tk.Frame(main_frame)
    bottom_frame.grid(row=0, column=0, sticky="nsew")
    if hasattr(bottom_frame, "columnconfigure"):
        bottom_frame.columnconfigure(0, weight=1)

    apa_frame = tk.LabelFrame(bottom_frame, text="APA")
    apa_frame.grid(row=0, column=0, sticky="ew", pady=3)

    measure_frame = tk.LabelFrame(bottom_frame, text="Measurement")
    measure_frame.grid(row=1, column=0, sticky="ew", pady=3)
    if hasattr(measure_frame, "columnconfigure"):
        measure_frame.columnconfigure(1, weight=1)
        measure_frame.columnconfigure(4, weight=1)

    servo_frame = tk.LabelFrame(bottom_frame, text="Servo")
    servo_frame.grid(row=2, column=0, sticky="ew", pady=3)
    if hasattr(servo_frame, "columnconfigure"):
        servo_frame.columnconfigure(1, weight=1)

    manual_move_frame = tk.LabelFrame(bottom_frame, text="Manual Move")
    manual_move_frame.grid(row=3, column=0, sticky="ew", pady=3)

    btn_refresh_plots = tk.Button(bottom_frame, text="Refresh Plots")
    btn_refresh_plots.grid(row=4, column=0, sticky="ew", pady=(6, 0))

    tk.Label(apa_frame, text="APA Name:").grid(row=0, column=0, sticky="e")
    entry_apa = tk.Entry(apa_frame)
    entry_apa.grid(row=0, column=1)

    tk.Label(apa_frame, text="Mode:").grid(row=1, column=0, sticky="e")
    measurement_mode_var = tk.StringVar(apa_frame, value="legacy")
    tk.OptionMenu(
        apa_frame,
        measurement_mode_var,
        "legacy",
        "stream_sweep",
        "stream_rescue",
    ).grid(row=1, column=1)

    tk.Label(apa_frame, text="Layer:").grid(row=2, column=0, sticky="e")
    layer_var = tk.StringVar(apa_frame, value="X")
    tk.OptionMenu(apa_frame, layer_var, "X", "V", "U", "G").grid(row=2, column=1)

    tk.Label(apa_frame, text="Side:").grid(row=3, column=0, sticky="e")
    side_var = tk.StringVar(apa_frame, value="A")
    tk.OptionMenu(apa_frame, side_var, "A", "B").grid(row=3, column=1)

    flipped_var = tk.BooleanVar(value=False)
    tk.Checkbutton(apa_frame, text="Flipped", variable=flipped_var).grid(
        row=4, column=1, sticky="w"
    )

    a_taped_var = tk.BooleanVar(value=False)
    tk.Checkbutton(apa_frame, text="A taped", variable=a_taped_var).grid(
        row=5, column=0, sticky="w"
    )
    b_taped_var = tk.BooleanVar(value=False)
    tk.Checkbutton(apa_frame, text="B taped", variable=b_taped_var).grid(
        row=5, column=1, sticky="w"
    )

    tk.Label(measure_frame, text="Confidence Threshold:").grid(
        row=0, column=0, sticky="e"
    )
    entry_confidence = tk.Entry(measure_frame)
    entry_confidence.grid(row=0, column=1)
    entry_confidence.insert(0, "0.5")
    tk.Label(measure_frame, text="Confidence Source:").grid(
        row=0, column=2, sticky="e"
    )
    confidence_source_var = tk.StringVar(measure_frame, value="Neural Net")
    tk.OptionMenu(
        measure_frame,
        confidence_source_var,
        "Neural Net",
        "Signal Amplitude",
    ).grid(row=0, column=3, sticky="w")

    tk.Label(measure_frame, text="Record Duration (s):").grid(
        row=9, column=0, sticky="e"
    )
    entry_record_duration = tk.Entry(measure_frame)
    entry_record_duration.grid(row=9, column=1)
    entry_record_duration.insert(0, "1")

    tk.Label(measure_frame, text="Measuring Duration (s):").grid(
        row=10, column=0, sticky="e"
    )
    entry_measuring_duration = tk.Entry(measure_frame)
    entry_measuring_duration.grid(row=10, column=1)
    entry_measuring_duration.insert(0, "10")

    tk.Label(measure_frame, text="Y Wiggle σ (mm):").grid(
        row=11, column=0, sticky="e"
    )
    entry_wiggle_y_sigma = tk.Entry(measure_frame)
    entry_wiggle_y_sigma.grid(row=11, column=1)
    entry_wiggle_y_sigma.insert(0, str(MEASUREMENT_WIGGLE_CONFIG.y_sigma_mm))
    sweeping_wiggle_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        measure_frame,
        text="Sweeping Wiggle",
        variable=sweeping_wiggle_var,
    ).grid(row=11, column=2, sticky="w")
    tk.Label(measure_frame, text="Sweep +/- (mm):").grid(
        row=11, column=3, sticky="e"
    )
    entry_sweeping_wiggle_span_mm = tk.Entry(measure_frame, width=8)
    entry_sweeping_wiggle_span_mm.grid(row=11, column=4, sticky="w")
    entry_sweeping_wiggle_span_mm.insert(0, "1.0")

    tk.Label(measure_frame, text="Focus Wiggle σ:").grid(
        row=12, column=0, sticky="e"
    )
    entry_focus_wiggle_sigma = tk.Entry(measure_frame)
    entry_focus_wiggle_sigma.grid(row=12, column=1)
    entry_focus_wiggle_sigma.insert(
        0, str(MEASUREMENT_WIGGLE_CONFIG.focus_sigma_quarter_us)
    )
    use_manual_focus_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        measure_frame,
        text="Manual Focus",
        variable=use_manual_focus_var,
    ).grid(row=12, column=2, columnspan=2, sticky="w")

    tk.Label(measure_frame, text="Wire Number:").grid(row=1, column=0, sticky="e")
    entry_wire = tk.Entry(measure_frame)
    entry_wire.grid(row=1, column=1)
    btn_calibrate = tk.Button(measure_frame, text="Calibrate")
    btn_calibrate.grid(row=1, column=2)

    tk.Label(measure_frame, text="Wire List:").grid(row=2, column=0, sticky="e")
    entry_wire_list = tk.Entry(measure_frame)
    entry_wire_list.grid(row=2, column=1)
    btn_measure_list = tk.Button(measure_frame, text="Seek Wire(s)")
    btn_measure_list.grid(row=2, column=2)
    skip_measured_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        measure_frame,
        text="Skip Measured",
        variable=skip_measured_var,
    ).grid(row=2, column=3, sticky="w")

    tk.Label(measure_frame, text="Zone:").grid(row=3, column=0, sticky="e")
    entry_wire_zone = tk.Entry(measure_frame)
    entry_wire_zone.grid(row=3, column=1)
    btn_measure_zone = tk.Button(measure_frame, text="Seek Zone(s)")
    btn_measure_zone.grid(row=3, column=2)
    skip_measured_zone_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        measure_frame,
        text="Skip Measured",
        variable=skip_measured_zone_var,
    ).grid(row=3, column=3, sticky="w")

    plot_audio_var = tk.BooleanVar(value=False)
    tk.Checkbutton(measure_frame, text="Plot Audio", variable=plot_audio_var).grid(
        row=4, column=2, sticky="w"
    )
    suppress_wire_preview_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        measure_frame,
        text="Suppress Wire Preview",
        variable=suppress_wire_preview_var,
    ).grid(row=4, column=3, columnspan=2, sticky="w")

    btn_measure_auto = tk.Button(measure_frame, text="Measure Auto")
    btn_measure_auto.grid(row=4, column=0)
    btn_interrupt = tk.Button(measure_frame, text="Interrupt")
    btn_interrupt.grid(row=4, column=1)
    tk.Label(measure_frame, text="ETA:").grid(row=13, column=0, sticky="e")
    tk.Label(measure_frame, textvariable=estimated_time_var).grid(
        row=13, column=1, sticky="w"
    )
    stream_segment_var = tk.StringVar(measure_frame, value="Idle")
    stream_comb_var = tk.StringVar(measure_frame, value="0.00")
    stream_focus_var = tk.StringVar(measure_frame, value="--")
    stream_pitch_backlog_var = tk.StringVar(measure_frame, value="0")
    stream_rescue_queue_var = tk.StringVar(measure_frame, value="0")
    tk.Label(measure_frame, text="Stream Segment:").grid(row=14, column=0, sticky="e")
    tk.Label(measure_frame, textvariable=stream_segment_var).grid(
        row=14, column=1, sticky="w"
    )
    tk.Label(measure_frame, text="Comb Score:").grid(row=15, column=0, sticky="e")
    tk.Label(measure_frame, textvariable=stream_comb_var).grid(
        row=15, column=1, sticky="w"
    )
    tk.Label(measure_frame, text="Focus Pred:").grid(row=16, column=0, sticky="e")
    tk.Label(measure_frame, textvariable=stream_focus_var).grid(
        row=16, column=1, sticky="w"
    )
    tk.Label(measure_frame, text="Pitch Backlog:").grid(row=17, column=0, sticky="e")
    tk.Label(measure_frame, textvariable=stream_pitch_backlog_var).grid(
        row=17, column=1, sticky="w"
    )
    tk.Label(measure_frame, text="Rescue Queue:").grid(row=18, column=0, sticky="e")
    tk.Label(measure_frame, textvariable=stream_rescue_queue_var).grid(
        row=18, column=1, sticky="w"
    )

    laser_offset_frame = tk.LabelFrame(measure_frame, text="Laser Offset")
    laser_offset_frame.grid(row=19, column=0, columnspan=5, sticky="ew", pady=(6, 0))
    if hasattr(laser_offset_frame, "columnconfigure"):
        laser_offset_frame.columnconfigure(1, weight=1)
    tk.Label(laser_offset_frame, text="Bottom Pin:").grid(row=0, column=0, sticky="e")
    laser_offset_pin_var = tk.StringVar(laser_offset_frame, value="")
    laser_offset_pin_menu = tk.OptionMenu(laser_offset_frame, laser_offset_pin_var, "")
    laser_offset_pin_menu.grid(row=0, column=1, sticky="ew")
    btn_seek_pin = tk.Button(laser_offset_frame, text="Seek Camera To Pin")
    btn_seek_pin.grid(row=0, column=2, padx=(6, 0))
    btn_move_laser_to_pin = tk.Button(laser_offset_frame, text="Move Laser To Pin")
    btn_move_laser_to_pin.grid(row=0, column=3, padx=(6, 0))
    btn_capture_laser_offset = tk.Button(laser_offset_frame, text="Capture Laser Offset")
    btn_capture_laser_offset.grid(row=0, column=4, padx=(6, 0))
    laser_offset_readout_var = tk.StringVar(laser_offset_frame, value="Side A: not set")
    tk.Label(laser_offset_frame, textvariable=laser_offset_readout_var).grid(
        row=1, column=0, columnspan=5, sticky="w"
    )
    laser_offset_frame.grid_remove()

    tk.Label(measure_frame, text="Clear Range:").grid(row=5, column=0, sticky="e")
    entry_clear_range = tk.Entry(measure_frame)
    entry_clear_range.grid(row=5, column=1)
    btn_clear_range = tk.Button(measure_frame, text="Clear")
    btn_clear_range.grid(row=5, column=2)

    tk.Label(measure_frame, text="Condition (AND/OR):").grid(
        row=6, column=0, sticky="e"
    )
    entry_condition = tk.Entry(measure_frame)
    entry_condition.grid(row=6, column=1)
    btn_measure_condition = tk.Button(measure_frame, text="Measure Condition")
    btn_measure_condition.grid(row=6, column=2)
    # Legacy mode can keep sampling until the measured tension satisfies a simple
    # expression such as `t<7`, `4<t`, or `4<t<7`.
    tk.Label(measure_frame, text="Legacy Tension:").grid(row=6, column=3, sticky="e")
    entry_legacy_tension_condition = tk.Entry(measure_frame)
    entry_legacy_tension_condition.grid(row=6, column=4, sticky="ew")

    tk.Label(measure_frame, text="Outlier σ Multiplier:").grid(
        row=7, column=0, sticky="e"
    )
    entry_times_sigma = tk.Entry(measure_frame)
    entry_times_sigma.grid(row=7, column=1)
    entry_times_sigma.insert(0, "2.0")
    btn_erase_outliers = tk.Button(measure_frame, text="Erase Residual Outliers")
    btn_erase_outliers.grid(row=7, column=2)
    btn_erase_distribution_outliers = tk.Button(
        measure_frame, text="Erase Bulk Outliers"
    )
    btn_erase_distribution_outliers.grid(row=7, column=3)

    tk.Label(measure_frame, text="Set Tensions:").grid(row=8, column=0, sticky="e")
    entry_set_tension = tk.Entry(measure_frame)
    entry_set_tension.grid(row=8, column=1)
    btn_set_tension = tk.Button(measure_frame, text="Apply Tensions")
    btn_set_tension.grid(row=8, column=2)

    btn_calibrate_noise = tk.Button(measure_frame, text="Calibrate Noise")
    btn_calibrate_noise.grid(row=13, column=2)

    tk.Label(servo_frame, text="Focus:").grid(row=0, column=0, sticky="e")
    focus_slider = tk.Scale(servo_frame, from_=4000, to=8000, orient=tk.HORIZONTAL)
    focus_slider.set(4000)
    focus_slider.grid(row=0, column=1, sticky="ew")
    disable_x_compensation_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        servo_frame,
        text="Disable X Compensation",
        variable=disable_x_compensation_var,
    ).grid(row=0, column=2, sticky="w", padx=(6, 0))

    tk.Label(servo_frame, textvariable=focus_command_var).grid(
        row=1, column=0, sticky="e"
    )
    focus_command_canvas: tk.Canvas | None = None
    focus_command_dot: Any | None = None
    if hasattr(tk, "Canvas"):
        focus_command_canvas = tk.Canvas(servo_frame, height=8)
        focus_command_canvas.grid(row=1, column=1, sticky="ew")
        focus_command_canvas.create_line(0, 5, int(focus_slider.cget("length")), 5)
        focus_command_dot = focus_command_canvas.create_oval(
            0, 0, 0, 0, fill="blue", outline=""
        )

    tk.Label(manual_move_frame, text="X,Y:").grid(row=0, column=0, sticky="e")
    entry_xy = tk.Entry(manual_move_frame)
    entry_xy.grid(row=0, column=1)
    btn_manual_go = tk.Button(manual_move_frame, text="Go")
    btn_manual_go.grid(row=0, column=2)

    pad_frame = tk.Frame(manual_move_frame)
    pad_frame.grid(row=1, column=0, columnspan=3)

    pad_specs = [
        ("\u2196", -1, 1, 0, 0),
        ("\u2191", 0, 1, 0, 1),
        ("\u2197", 1, 1, 0, 2),
        ("\u2190", -1, 0, 1, 0),
        ("\u2192", 1, 0, 1, 2),
        ("\u2199", -1, -1, 2, 0),
        ("\u2193", 0, -1, 2, 1),
        ("\u2198", 1, -1, 2, 2),
    ]
    pad_buttons: list[tuple[tk.Button, int, int]] = []
    for label, dx, dy, row, col in pad_specs:
        button = tk.Button(pad_frame, text=label, width=2)
        button.grid(row=row, column=col)
        pad_buttons.append((button, dx, dy))

    widgets = GUIWidgets(
        entry_apa=entry_apa,
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
        "calibrate": btn_calibrate,
        "measure_list": btn_measure_list,
        "measure_zone": btn_measure_zone,
        "measure_auto": btn_measure_auto,
        "interrupt": btn_interrupt,
        "clear_range": btn_clear_range,
        "measure_condition": btn_measure_condition,
        "erase_outliers": btn_erase_outliers,
        "erase_distribution_outliers": btn_erase_distribution_outliers,
        "set_tension": btn_set_tension,
        "calibrate_noise": btn_calibrate_noise,
        "manual_go": btn_manual_go,
        "refresh_plots": btn_refresh_plots,
        "seek_pin": btn_seek_pin,
        "move_laser_to_pin": btn_move_laser_to_pin,
        "capture_laser_offset": btn_capture_laser_offset,
    }

    _configure_root_minimum_size(root, main_frame, side_frame)

    return (
        widgets,
        focus_command_canvas,
        focus_command_dot,
        buttons,
        pad_buttons,
        log_text,
        summary_plot_frame,
        waveform_plot_frame,
    )


def _configure_root_minimum_size(
    root: tk.Misc,
    main_frame: tk.Misc,
    side_frame: tk.Misc,
) -> None:
    """Keep the two-column layout wide enough for controls and embedded plots."""

    if not hasattr(root, "update_idletasks"):
        return

    try:
        root.update_idletasks()
    except Exception:
        return

    try:
        main_width = int(main_frame.winfo_reqwidth())
        side_width = int(side_frame.winfo_reqwidth())
        main_height = int(main_frame.winfo_reqheight())
        side_height = int(side_frame.winfo_reqheight())
    except Exception:
        return

    estimated_plot_width = int(max(LIVE_SUMMARY_FIGSIZE[0], LIVE_WAVEFORM_FIGSIZE[0]) * 100)
    side_width = max(side_width, estimated_plot_width)

    screen_width = _safe_screen_dimension(root, "winfo_screenwidth")
    screen_height = _safe_screen_dimension(root, "winfo_screenheight")

    available_width = max(screen_width - 30, 1) if screen_width is not None else None
    if available_width is not None:
        main_width, side_width = _fit_column_widths_to_available_space(
            main_width,
            side_width,
            available_width,
        )

    if hasattr(root, "columnconfigure"):
        try:
            root.columnconfigure(0, weight=0, minsize=max(main_width, 1))
            root.columnconfigure(1, weight=1, minsize=max(side_width, 1))
        except Exception:
            pass

    if not hasattr(root, "minsize"):
        return

    total_width = main_width + side_width + 30
    total_height = max(main_height, side_height) + 20
    if screen_width is not None:
        total_width = min(total_width, screen_width)
    if screen_height is not None:
        total_height = min(total_height, screen_height)
    if total_width <= 0 or total_height <= 0:
        return

    try:
        root.minsize(total_width, total_height)
    except Exception:
        return


def _safe_screen_dimension(root: tk.Misc, method_name: str) -> int | None:
    """Best-effort screen size lookup for sizing constraints."""

    method = getattr(root, method_name, None)
    if method is None:
        return None
    try:
        value = int(method())
    except Exception:
        return None
    return value if value > 0 else None


def _fit_column_widths_to_available_space(
    main_width: int,
    side_width: int,
    available_width: int,
) -> tuple[int, int]:
    """Shrink column minimums so the root can fit on screen when maximized."""

    desired_width = main_width + side_width
    if desired_width <= available_width:
        return main_width, side_width

    overflow = desired_width - available_width

    side_reduction = min(overflow, max(side_width - 1, 0))
    side_width -= side_reduction
    overflow -= side_reduction

    if overflow > 0:
        main_width = max(main_width - overflow, 1)

    return main_width, side_width


def _configure_commands(
    ctx: GUIContext,
    buttons: dict[str, tk.Button],
    pad_buttons: list[tuple[tk.Button, int, int]],
) -> None:
    """Attach the GUI callbacks to the Tkinter widgets."""

    buttons["calibrate"].configure(command=lambda: measure_calibrate(ctx))
    buttons["measure_list"].configure(command=lambda: measure_list_button(ctx))
    buttons["measure_zone"].configure(command=lambda: measure_zone_button(ctx))
    buttons["measure_auto"].configure(command=lambda: measure_auto(ctx))
    buttons["interrupt"].configure(command=lambda: interrupt(ctx))
    buttons["clear_range"].configure(command=lambda: clear_range(ctx))
    buttons["measure_condition"].configure(command=lambda: measure_condition(ctx))
    buttons["erase_outliers"].configure(command=lambda: erase_outliers(ctx))
    buttons["erase_distribution_outliers"].configure(
        command=lambda: erase_distribution_outliers(ctx)
    )
    buttons["set_tension"].configure(command=lambda: set_manual_tension(ctx))
    buttons["calibrate_noise"].configure(
        command=lambda: calibrate_background_noise(ctx)
    )
    buttons["manual_go"].configure(command=lambda: manual_goto(ctx))
    buttons["refresh_plots"].configure(command=lambda: refresh_tension_logs(ctx))
    buttons["seek_pin"].configure(command=lambda: seek_camera_to_pin(ctx))
    buttons["move_laser_to_pin"].configure(
        command=lambda: move_laser_to_pin_button(ctx)
    )
    buttons["capture_laser_offset"].configure(
        command=lambda: capture_laser_offset_button(ctx)
    )

    for button, dx, dy in pad_buttons:
        button.configure(command=partial(manual_increment, ctx, dx, dy))

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
