"""Standalone GUI for exercising and tuning pitched-sound trigger capture.

Arms the microphone with either the harmonic comb trigger (HCT) or a
PESTO-confidence trigger, records from sound onset to cessation, then runs
PESTO on the capture and shows the same diagnostics plots as the tensiometer
GUI (waveform, FFT, autocorrelation, PESTO activation map).

For tuning, every listen also produces a trigger trace — the per-frame
trigger score against the on/off thresholds, with the recorded span shaded —
shown even when the trigger never fires, so threshold headroom over
background noise is visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import queue
import threading
import time
import tkinter as tk

import numpy as np

from spectrum_analysis.comb_trigger import HarmonicCombConfig, record_with_harmonic_comb
from spectrum_analysis.pesto_analysis import (
    PestoAnalysisResult,
    analyze_audio_with_pesto,
)
from spectrum_analysis.pesto_trigger import (
    PestoTriggerConfig,
    record_with_pesto_trigger,
    warm_up_pesto,
)

LOGGER = logging.getLogger(__name__)

MODE_COMB = "Harmonic Comb"
MODE_PESTO = "PESTO"

LIVE_READOUT_PERIOD_S = 0.2


@dataclass
class TriggerTrace:
    """Per-frame trigger scores collected during one listen."""

    mode: str
    on_threshold: float
    off_threshold: float
    times: list[float] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)  # comb score / confidence
    extras: list[float] = field(default_factory=list)  # SFM / frequency (Hz)
    triggered: list[bool] = field(default_factory=list)


@dataclass(frozen=True)
class CaptureSettings:
    """Snapshot of the GUI controls taken when the trigger is armed."""

    mode: str
    expected_f0: float
    sample_rate: int
    max_record_seconds: float
    timeout_seconds: float
    continuous: bool
    comb_cfg: HarmonicCombConfig
    pesto_cfg: PestoTriggerConfig


@dataclass(frozen=True)
class CaptureResult:
    """One completed listen: trace always, audio/analysis when triggered."""

    trace: TriggerTrace
    sample_rate: int
    audio: np.ndarray | None
    analysis: PestoAnalysisResult | None
    analysis_error: str | None


class TriggerCaptureApp:
    """Tkinter app that arms a pitched-sound trigger and plots captures."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Trigger Capture Test")
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._results: queue.Queue[CaptureResult] = queue.Queue()
        self._trace_canvas = None
        self._plot_canvas = None

        controls = tk.LabelFrame(root, text="Trigger")
        controls.grid(row=0, column=0, padx=6, pady=6, sticky="new")
        controls.columnconfigure(1, weight=1)

        self._entries: dict[str, tk.Entry] = {}

        tk.Label(controls, text="Trigger Mode:").grid(row=0, column=0, sticky="e")
        self.mode_var = tk.StringVar(controls, value=MODE_COMB)
        tk.OptionMenu(controls, self.mode_var, MODE_COMB, MODE_PESTO).grid(
            row=0, column=1, sticky="ew", padx=(3, 6)
        )
        self.mode_var.trace_add("write", lambda *_args: self._on_mode_change())

        common_fields = [
            ("Expected f0 (Hz):", "expected_f0", "75"),
            ("Sample Rate (Hz):", "sample_rate", "44100"),
            ("Max Record (s):", "max_record_seconds", "2.0"),
            ("Listen Timeout (s):", "timeout_seconds", "30"),
        ]
        for offset, (label, key, default) in enumerate(common_fields):
            self._add_field(controls, 1 + offset, label, key, default)
        next_row = 1 + len(common_fields)

        self.comb_frame = tk.LabelFrame(controls, text="Harmonic Comb Trigger")
        self.comb_frame.grid(
            row=next_row, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        self.comb_frame.columnconfigure(1, weight=1)
        comb_fields = [
            ("On rmax:", "on_rmax", str(HarmonicCombConfig.on_rmax)),
            ("Off rmax:", "off_rmax", str(HarmonicCombConfig.off_rmax)),
            ("On Frames:", "on_frames", str(HarmonicCombConfig.on_frames)),
            ("Off Frames:", "off_frames", str(HarmonicCombConfig.off_frames)),
            ("SFM Max:", "sfm_max", str(HarmonicCombConfig.sfm_max)),
            ("Min Harmonics:", "min_harmonics", str(HarmonicCombConfig.min_harmonics)),
        ]
        for row, (label, key, default) in enumerate(comb_fields):
            self._add_field(self.comb_frame, row, label, key, default)

        self.pesto_frame = tk.LabelFrame(controls, text="PESTO Trigger")
        self.pesto_frame.grid(
            row=next_row + 1, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        self.pesto_frame.columnconfigure(1, weight=1)
        pesto_fields = [
            ("On Confidence:", "on_confidence", str(PestoTriggerConfig.on_confidence)),
            (
                "Off Confidence:",
                "off_confidence",
                str(PestoTriggerConfig.off_confidence),
            ),
            ("On Windows:", "on_windows", str(PestoTriggerConfig.on_windows)),
            ("Off Windows:", "off_windows", str(PestoTriggerConfig.off_windows)),
            ("Window (s):", "window_seconds", str(PestoTriggerConfig.window_seconds)),
            (
                "Eval Period (s):",
                "eval_period_seconds",
                str(PestoTriggerConfig.eval_period_seconds),
            ),
        ]
        for row, (label, key, default) in enumerate(pesto_fields):
            self._add_field(self.pesto_frame, row, label, key, default)

        row = next_row + 2
        self.continuous_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            controls,
            text="Re-arm after each capture",
            variable=self.continuous_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w")

        self.btn_arm = tk.Button(controls, text="Arm Trigger", command=self._arm)
        self.btn_arm.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.btn_stop = tk.Button(
            controls, text="Stop", command=self._request_stop, state="disabled"
        )
        self.btn_stop.grid(
            row=row + 2, column=0, columnspan=2, sticky="ew", pady=(3, 0)
        )

        self.status_var = tk.StringVar(root, value="Idle")
        tk.Label(controls, textvariable=self.status_var, anchor="w").grid(
            row=row + 3, column=0, columnspan=2, sticky="ew", pady=(6, 0)
        )
        self.live_var = tk.StringVar(root, value="")
        tk.Label(controls, textvariable=self.live_var, anchor="w").grid(
            row=row + 4, column=0, columnspan=2, sticky="ew"
        )
        self.result_var = tk.StringVar(root, value="No capture yet.")
        tk.Label(
            controls, textvariable=self.result_var, anchor="w", justify="left"
        ).grid(row=row + 5, column=0, columnspan=2, sticky="ew")

        plots = tk.Frame(root)
        plots.grid(row=0, column=1, padx=(0, 6), pady=6, sticky="nsew")
        plots.columnconfigure(0, weight=1)
        plots.rowconfigure(0, weight=2)
        plots.rowconfigure(1, weight=5)

        self.trace_frame = tk.LabelFrame(plots, text="Trigger Trace")
        self.trace_frame.grid(row=0, column=0, sticky="nsew")
        self.trace_frame.columnconfigure(0, weight=1)
        self.trace_frame.rowconfigure(0, weight=1)

        self.plot_frame = tk.LabelFrame(plots, text="Capture Diagnostics")
        self.plot_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.plot_frame.columnconfigure(0, weight=1)
        self.plot_frame.rowconfigure(0, weight=1)

        self._on_mode_change()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI

    def _add_field(
        self, parent: tk.Misc, row: int, label: str, key: str, default: str
    ) -> None:
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="e")
        entry = tk.Entry(parent, width=12)
        entry.grid(row=row, column=1, sticky="ew", padx=(3, 6))
        entry.insert(0, default)
        self._entries[key] = entry

    def _on_mode_change(self) -> None:
        if self.mode_var.get() == MODE_PESTO:
            self.comb_frame.grid_remove()
            self.pesto_frame.grid()
        else:
            self.pesto_frame.grid_remove()
            self.comb_frame.grid()

    def _set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def _set_live(self, message: str) -> None:
        self.root.after(0, lambda: self.live_var.set(message))

    def _read_settings(self) -> CaptureSettings:
        def value(key: str) -> str:
            return self._entries[key].get().strip()

        comb_cfg = HarmonicCombConfig(
            on_rmax=float(value("on_rmax")),
            off_rmax=float(value("off_rmax")),
            on_frames=int(value("on_frames")),
            off_frames=int(value("off_frames")),
            sfm_max=float(value("sfm_max")),
            min_harmonics=int(value("min_harmonics")),
        )
        pesto_cfg = PestoTriggerConfig(
            on_confidence=float(value("on_confidence")),
            off_confidence=float(value("off_confidence")),
            on_windows=int(value("on_windows")),
            off_windows=int(value("off_windows")),
            window_seconds=float(value("window_seconds")),
            eval_period_seconds=float(value("eval_period_seconds")),
        )
        return CaptureSettings(
            mode=self.mode_var.get(),
            expected_f0=float(value("expected_f0")),
            sample_rate=int(value("sample_rate")),
            max_record_seconds=float(value("max_record_seconds")),
            timeout_seconds=float(value("timeout_seconds")),
            continuous=bool(self.continuous_var.get()),
            comb_cfg=comb_cfg,
            pesto_cfg=pesto_cfg,
        )

    def _arm(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        try:
            settings = self._read_settings()
        except ValueError as exc:
            self.status_var.set(f"Invalid settings: {exc}")
            return

        self._stop_event = threading.Event()
        self.btn_arm.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._worker = threading.Thread(
            target=self._capture_loop,
            args=(settings, self._stop_event),
            daemon=True,
        )
        self._worker.start()

    def _request_stop(self) -> None:
        self._stop_event.set()
        self.status_var.set("Stopping...")

    def _on_close(self) -> None:
        self._stop_event.set()
        self.root.destroy()

    # -------------------------------------------------------------- worker

    def _capture_loop(
        self, settings: CaptureSettings, stop_event: threading.Event
    ) -> None:
        try:
            if settings.mode == MODE_PESTO:
                self._set_status("Loading PESTO model...")
                warm_up_pesto(
                    settings.expected_f0,
                    settings.sample_rate,
                    settings.pesto_cfg.window_seconds,
                )
            while not stop_event.is_set():
                self._set_status(
                    f"[{settings.mode}] Listening for pitched sound near "
                    f"{settings.expected_f0:.1f} Hz..."
                )
                trace, audio = self._listen_once(settings, stop_event)
                self._set_live("")
                if stop_event.is_set():
                    break

                analysis: PestoAnalysisResult | None = None
                analysis_error: str | None = None
                if audio is not None:
                    self._set_status(
                        f"Captured {audio.size / settings.sample_rate:.2f} s; "
                        "running PESTO..."
                    )
                    try:
                        analysis = analyze_audio_with_pesto(
                            audio,
                            settings.sample_rate,
                            expected_frequency=settings.expected_f0,
                            include_activations=True,
                        )
                    except Exception as exc:
                        LOGGER.exception("PESTO analysis failed.")
                        analysis_error = str(exc)

                self._results.put(
                    CaptureResult(
                        trace=trace,
                        sample_rate=settings.sample_rate,
                        audio=audio,
                        analysis=analysis,
                        analysis_error=analysis_error,
                    )
                )
                self.root.after(0, self._drain_results)
                if audio is None:
                    self._set_status(_timeout_message(trace))
                    if not settings.continuous:
                        break
                elif not settings.continuous:
                    self._set_status("Capture complete.")
                    break
        except Exception as exc:
            LOGGER.exception("Trigger capture failed.")
            self._set_status(f"Error: {exc}")
        finally:
            self.root.after(0, self._on_worker_done)

    def _listen_once(
        self, settings: CaptureSettings, stop_event: threading.Event
    ) -> tuple[TriggerTrace, np.ndarray | None]:
        last_live = [0.0]

        if settings.mode == MODE_PESTO:
            cfg = settings.pesto_cfg
            trace = TriggerTrace(
                mode=MODE_PESTO,
                on_threshold=cfg.on_confidence,
                off_threshold=cfg.off_confidence,
            )

            def on_pesto_frame(
                t: float, confidence: float, frequency: float, triggered: bool
            ) -> None:
                trace.times.append(t)
                trace.scores.append(confidence)
                trace.extras.append(frequency)
                trace.triggered.append(triggered)
                now = time.monotonic()
                if now - last_live[0] >= LIVE_READOUT_PERIOD_S:
                    last_live[0] = now
                    self._set_live(
                        f"conf={confidence:.2f}  f={frequency:.1f} Hz"
                        f"  triggered={triggered}"
                    )

            audio = record_with_pesto_trigger(
                expected_f0=settings.expected_f0,
                sample_rate=settings.sample_rate,
                max_record_seconds=settings.max_record_seconds,
                timeout_seconds=settings.timeout_seconds,
                cfg=cfg,
                recording_started_callback=lambda: self._set_status("Recording..."),
                stop_event=stop_event,
                frame_callback=on_pesto_frame,
            )
            return trace, audio

        comb_cfg = settings.comb_cfg
        trace = TriggerTrace(
            mode=MODE_COMB,
            on_threshold=comb_cfg.harmonicity_threshold(),
            off_threshold=comb_cfg.off_rmax,
        )

        def on_comb_frame(
            t: float, score: float, sfm: float, valid: bool, triggered: bool
        ) -> None:
            trace.times.append(t)
            trace.scores.append(score)
            trace.extras.append(sfm)
            trace.triggered.append(triggered)
            now = time.monotonic()
            if now - last_live[0] >= LIVE_READOUT_PERIOD_S:
                last_live[0] = now
                self._set_live(
                    f"score={score:.3g}  sfm={sfm:.2f}  valid={valid}"
                    f"  triggered={triggered}"
                )

        audio = record_with_harmonic_comb(
            expected_f0=settings.expected_f0,
            sample_rate=settings.sample_rate,
            max_record_seconds=settings.max_record_seconds,
            timeout_seconds=settings.timeout_seconds,
            comb_cfg=comb_cfg,
            recording_started_callback=lambda: self._set_status("Recording..."),
            stop_event=stop_event,
            frame_callback=on_comb_frame,
        )
        return trace, audio

    # ---------------------------------------------------------- Tk thread

    def _on_worker_done(self) -> None:
        self.btn_arm.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        if self.status_var.get().startswith(("[", "Stopping")):
            self.status_var.set("Idle")

    def _drain_results(self) -> None:
        try:
            while True:
                self._show_result(self._results.get_nowait())
        except queue.Empty:
            pass

    def _show_result(self, result: CaptureResult) -> None:
        # Imported lazily so the controls appear before matplotlib loads.
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        trace_figure = _build_trace_figure(result.trace)
        if self._trace_canvas is not None:
            self._trace_canvas.get_tk_widget().destroy()
        trace_canvas = FigureCanvasTkAgg(trace_figure, master=self.trace_frame)
        trace_canvas.draw()
        trace_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._trace_canvas = trace_canvas

        if result.audio is None:
            self.result_var.set(_timeout_message(result.trace))
            return

        duration = result.audio.size / result.sample_rate
        if result.analysis is not None and np.isfinite(result.analysis.frequency):
            self.result_var.set(
                f"Duration: {duration:.2f} s\n"
                f"PESTO pitch: {result.analysis.frequency:.2f} Hz\n"
                f"Confidence: {result.analysis.confidence:.3f}"
            )
        elif result.analysis_error is not None:
            self.result_var.set(
                f"Duration: {duration:.2f} s\nPESTO failed: {result.analysis_error}"
            )
        else:
            self.result_var.set(
                f"Duration: {duration:.2f} s\nPESTO found no voiced frames."
            )

        from dune_tension.gui.live_plots import LivePlotManager

        figure = LivePlotManager._build_audio_diagnostics_figure(
            result.audio, result.sample_rate, result.analysis
        )
        if self._plot_canvas is not None:
            self._plot_canvas.get_tk_widget().destroy()
        canvas = FigureCanvasTkAgg(figure, master=self.plot_frame)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._plot_canvas = canvas


def _timeout_message(trace: TriggerTrace) -> str:
    if not trace.scores:
        return "No trigger; no frames analyzed."
    peak = max(trace.scores)
    return (
        f"No trigger. Peak {_score_name(trace.mode)} {peak:.3g} "
        f"vs on-threshold {trace.on_threshold:.3g}."
    )


def _score_name(mode: str) -> str:
    return "confidence" if mode == MODE_PESTO else "comb score"


def _build_trace_figure(trace: TriggerTrace):
    """Plot the trigger score timeline with thresholds and recorded span."""

    from matplotlib.figure import Figure

    figure = Figure(figsize=(11.2, 2.6), constrained_layout=True)
    axis = figure.add_subplot(111)
    times = np.asarray(trace.times, dtype=np.float64)
    scores = np.asarray(trace.scores, dtype=np.float64)

    if times.size == 0:
        axis.text(
            0.5,
            0.5,
            "No trigger frames analyzed.",
            ha="center",
            va="center",
            transform=axis.transAxes,
        )
        axis.set_title("Trigger Trace")
        return figure

    if trace.mode == MODE_COMB:
        floor = max(trace.off_threshold * 1e-3, 1e-30)
        axis.semilogy(
            times, np.clip(scores, floor, None), linewidth=1.0, color="#1f77b4"
        )
        axis.set_ylabel("Comb Score")
        sfm_axis = axis.twinx()
        sfm_axis.plot(
            times,
            np.asarray(trace.extras, dtype=np.float64),
            linewidth=0.8,
            linestyle=":",
            color="#7f7f7f",
        )
        sfm_axis.set_ylabel("SFM", color="#7f7f7f")
        sfm_axis.set_ylim(0.0, 1.05)
    else:
        axis.plot(times, scores, linewidth=1.0, color="#1f77b4")
        axis.set_ylabel("PESTO Confidence")
        axis.set_ylim(-0.02, 1.05)

    axis.axhline(
        trace.on_threshold, color="green", linewidth=0.9, linestyle="--", label="on"
    )
    axis.axhline(
        trace.off_threshold, color="red", linewidth=0.9, linestyle="--", label="off"
    )
    for start, end in _triggered_spans(times, trace.triggered):
        axis.axvspan(start, end, color="orange", alpha=0.18)
    axis.set_xlabel("Time (s)")
    axis.set_title(f"Trigger Trace ({trace.mode})")
    axis.legend(loc="upper right", fontsize=7)
    axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
    return figure


def _triggered_spans(
    times: np.ndarray, triggered: list[bool]
) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    start: float | None = None
    for t, active in zip(times, triggered):
        if active and start is None:
            start = float(t)
        elif not active and start is not None:
            spans.append((start, float(t)))
            start = None
    if start is not None:
        spans.append((start, float(times[-1])))
    return spans


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    root = tk.Tk()
    TriggerCaptureApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
