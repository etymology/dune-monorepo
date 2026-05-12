"""Embedded live plot support for the Tkinter GUI.

Two design rules keep the GUI responsive while measurements run:

1. Worker threads **never** call into Tk directly. They push callables onto a
   ``queue.Queue`` that the Tk main thread drains via a periodic ``root.after``
   poller. This avoids contention on Tcl's global interpreter lock, which
   would otherwise stall the measurement worker when the Tk thread is busy.

2. Every plot job is bounded by a watchdog. If a build (or the
   ``figure_lock``) takes longer than the configured timeout we abandon the
   result by advancing a generation counter and show a "plot skipped"
   placeholder. The matplotlib worker thread keeps running until it returns
   — Python can't preempt threads — but the GUI moves on.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
import tkinter as tk

import numpy as np
from matplotlib.figure import Figure

from dune_tension._matplotlib_lock import figure_lock_or_skip
from dune_tension.summaries import build_summary_plot_figure_for_config
from spectrum_analysis.pitch_compare_config import PitchCompareConfig

LOGGER = logging.getLogger(__name__)

FigureCanvasTkAgg: Any = None
try:  # pragma: no cover - backend availability depends on the runtime environment
    from matplotlib.backends.backend_tkagg import (
        FigureCanvasTkAgg as _FigureCanvasTkAgg,
    )

    FigureCanvasTkAgg = _FigureCanvasTkAgg
except Exception:  # pragma: no cover - fall back to text placeholders in tests/headless
    pass

LIVE_SUMMARY_FIGSIZE = (6.0, 5.6)
LIVE_WAVEFORM_FIGSIZE = (11.2, 7.0)
WAVEFORM_MIN_RENDER_INTERVAL_S = 0.2

SUMMARY_PLOT_TIMEOUT_S = 5.0
WAVEFORM_PLOT_TIMEOUT_S = 3.0
TK_DRAW_LOCK_TIMEOUT_S = 2.0
TK_PUMP_INTERVAL_MS = 20
TK_PUMP_MAX_CALLBACKS_PER_TICK = 32


class LivePlotManager:
    """Own the embedded summary and waveform plot canvases."""

    def __init__(
        self,
        root: tk.Misc,
        summary_parent: tk.Misc,
        waveform_parent: tk.Misc,
    ) -> None:
        self.root = root
        self.summary_parent = summary_parent
        self.waveform_parent = waveform_parent
        self.summary_canvas: Any | None = None
        self.waveform_canvas: Any | None = None
        self.summary_placeholder = tk.Label(
            summary_parent,
            text="Waiting for summary data...",
            anchor="w",
            justify="left",
        )
        self.summary_placeholder.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.waveform_placeholder = tk.Label(
            waveform_parent,
            text="Waiting for audio capture...",
            anchor="w",
            justify="left",
        )
        self.waveform_placeholder.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self._summary_after_id: Any | None = None
        self._summary_generation = 0
        self._waveform_after_id: Any | None = None
        self._waveform_generation = 0
        self._waveform_pending: tuple[np.ndarray, int, Any | None] | None = None
        self._waveform_in_flight = False
        self._waveform_last_started_at: float | None = None

        self._tk_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._pump_running = True
        self._summary_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="live-plot-summary"
        )
        self._waveform_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="live-plot-waveform"
        )
        self._start_tk_pump()

    def shutdown(self) -> None:
        """Stop the Tk pump and the plot executors.

        Safe to call multiple times. After shutdown the manager will silently
        drop further work — useful during application teardown so threads
        don't outlive the Tk root.
        """
        self._pump_running = False
        for executor in (self._summary_executor, self._waveform_executor):
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

    def publish_waveform(
        self,
        audio_sample: Any,
        samplerate: int,
        analysis: Any | None = None,
    ) -> None:
        """Schedule a debounced background render of the captured waveform."""

        try:
            waveform = np.asarray(audio_sample, dtype=float).reshape(-1)
        except Exception:
            return
        if waveform.size == 0:
            return

        self._on_tk_thread(
            lambda: self._enqueue_waveform(waveform, int(samplerate), analysis)
        )

    def request_summary_refresh(self, config: Any, delay_ms: int = 100) -> None:
        """Debounce and redraw the current summary figure for ``config``."""

        def schedule() -> None:
            if self._summary_after_id is not None:
                try:
                    self.root.after_cancel(self._summary_after_id)
                except Exception:
                    pass
            self._summary_after_id = self.root.after(
                delay_ms,
                lambda: self._render_summary(config),
            )

        self._on_tk_thread(schedule)

    def _render_summary(self, config: Any) -> None:
        self._summary_after_id = None
        if FigureCanvasTkAgg is None:
            self._set_placeholder(
                self.summary_placeholder,
                "Matplotlib Tk backend unavailable.\nSummary plots cannot be embedded.",
            )
            return

        self._summary_generation += 1
        generation = self._summary_generation

        timer = self._start_watchdog(
            "summary",
            generation,
            SUMMARY_PLOT_TIMEOUT_S,
            lambda: self._finish_summary_refresh(generation, None, _PlotTimeout()),
            lambda: generation == self._summary_generation,
            lambda: self._invalidate_summary_generation(generation),
        )

        try:
            self._summary_executor.submit(
                self._build_summary_figure_in_background, config, generation, timer
            )
        except RuntimeError:
            timer.cancel()

    def _build_summary_figure_in_background(
        self, config: Any, generation: int, timer: threading.Timer
    ) -> None:
        try:
            figure = build_summary_plot_figure_for_config(
                config,
                figsize=LIVE_SUMMARY_FIGSIZE,
                timeout=SUMMARY_PLOT_TIMEOUT_S,
            )
        except Exception as exc:
            timer.cancel()
            captured_exc = exc
            self._on_tk_thread(
                lambda: self._finish_summary_refresh(generation, None, captured_exc)
            )
            return

        timer.cancel()
        self._on_tk_thread(
            lambda: self._finish_summary_refresh(generation, figure, None)
        )

    def _invalidate_summary_generation(self, generation: int) -> None:
        if generation == self._summary_generation:
            self._summary_generation += 1

    def _finish_summary_refresh(
        self,
        generation: int,
        figure: Figure | None,
        error: Exception | None,
    ) -> None:
        if generation != self._summary_generation:
            if figure is not None:
                figure.clear()
            return

        if error is not None:
            if isinstance(error, _PlotTimeout):
                self._set_placeholder(
                    self.summary_placeholder,
                    "Summary plot skipped (timed out).",
                )
                return
            if self.summary_canvas is not None:
                return
            self._set_placeholder(
                self.summary_placeholder,
                f"Failed to render summary plot:\n{error}",
            )
            return

        if figure is None:
            self._set_placeholder(
                self.summary_placeholder,
                "No summary data available for the selected APA/layer.",
            )
            if self.summary_canvas is not None:
                self.summary_canvas.get_tk_widget().destroy()
                self.summary_canvas = None
            return

        self._show_canvas("summary", figure)

    def _enqueue_waveform(
        self,
        waveform: np.ndarray,
        samplerate: int,
        analysis: Any | None,
    ) -> None:
        self._waveform_pending = (waveform, samplerate, analysis)
        if self._waveform_in_flight:
            return
        self._dispatch_pending_waveform()

    def _dispatch_pending_waveform(self) -> None:
        if self._waveform_in_flight:
            return
        if self._waveform_pending is None:
            return

        if FigureCanvasTkAgg is None:
            self._waveform_pending = None
            self._set_placeholder(
                self.waveform_placeholder,
                "Matplotlib Tk backend unavailable.\nWaveform plots cannot be embedded.",
            )
            return

        now = time.monotonic()
        if self._waveform_last_started_at is not None:
            elapsed = now - self._waveform_last_started_at
            if elapsed < WAVEFORM_MIN_RENDER_INTERVAL_S:
                delay_ms = int((WAVEFORM_MIN_RENDER_INTERVAL_S - elapsed) * 1000) + 1
                if self._waveform_after_id is not None:
                    try:
                        self.root.after_cancel(self._waveform_after_id)
                    except Exception:
                        pass
                try:
                    self._waveform_after_id = self.root.after(
                        delay_ms, self._dispatch_pending_waveform
                    )
                except Exception:
                    self._waveform_after_id = None
                return

        self._waveform_after_id = None
        waveform, samplerate, analysis = self._waveform_pending
        self._waveform_pending = None
        self._waveform_in_flight = True
        self._waveform_generation += 1
        generation = self._waveform_generation
        self._waveform_last_started_at = now

        timer = self._start_watchdog(
            "waveform",
            generation,
            WAVEFORM_PLOT_TIMEOUT_S,
            lambda: self._finish_waveform_refresh(generation, None, _PlotTimeout()),
            lambda: generation == self._waveform_generation,
            lambda: self._invalidate_waveform_generation(generation),
        )

        try:
            self._waveform_executor.submit(
                self._build_waveform_figure_in_background,
                waveform,
                samplerate,
                analysis,
                generation,
                timer,
            )
        except RuntimeError:
            timer.cancel()
            self._waveform_in_flight = False

    def _build_waveform_figure_in_background(
        self,
        waveform: np.ndarray,
        samplerate: int,
        analysis: Any | None,
        generation: int,
        timer: threading.Timer,
    ) -> None:
        figure: Figure | None = None
        error: Exception | None = None
        with figure_lock_or_skip(WAVEFORM_PLOT_TIMEOUT_S) as acquired:
            if not acquired:
                error = _PlotTimeout()
                LOGGER.warning(
                    "Waveform plot %d: figure lock busy (>%.1fs); skipping",
                    generation,
                    WAVEFORM_PLOT_TIMEOUT_S,
                )
            else:
                try:
                    figure = self._build_audio_diagnostics_figure(
                        waveform, samplerate, analysis
                    )
                except Exception as exc:
                    error = exc

        timer.cancel()
        self._on_tk_thread(
            lambda: self._finish_waveform_refresh(generation, figure, error)
        )

    def _invalidate_waveform_generation(self, generation: int) -> None:
        if generation == self._waveform_generation:
            self._waveform_generation += 1
        self._waveform_in_flight = False

    def _finish_waveform_refresh(
        self,
        generation: int,
        figure: Figure | None,
        error: Exception | None,
    ) -> None:
        self._waveform_in_flight = False

        if generation != self._waveform_generation:
            if figure is not None:
                figure.clear()
            self._dispatch_pending_waveform()
            return

        if error is not None:
            if isinstance(error, _PlotTimeout):
                self._set_placeholder(
                    self.waveform_placeholder,
                    "Waveform plot skipped (timed out).",
                )
            else:
                self._set_placeholder(
                    self.waveform_placeholder,
                    f"Failed to render waveform plot:\n{error}",
                )
            self._dispatch_pending_waveform()
            return

        if figure is not None:
            self._show_canvas("waveform", figure)

        self._dispatch_pending_waveform()

    def _show_canvas(self, kind: str, figure: Figure) -> None:
        parent = self.summary_parent if kind == "summary" else self.waveform_parent
        placeholder = (
            self.summary_placeholder if kind == "summary" else self.waveform_placeholder
        )
        current_canvas = (
            self.summary_canvas if kind == "summary" else self.waveform_canvas
        )

        if current_canvas is not None:
            try:
                current_canvas.get_tk_widget().destroy()
            except Exception:
                pass

        if hasattr(placeholder, "grid_remove"):
            placeholder.grid_remove()
        else:
            placeholder.grid_forget()

        canvas = FigureCanvasTkAgg(figure, master=parent)
        with figure_lock_or_skip(TK_DRAW_LOCK_TIMEOUT_S) as acquired:
            if not acquired:
                LOGGER.warning(
                    "%s canvas.draw skipped: figure lock busy (>%.1fs)",
                    kind,
                    TK_DRAW_LOCK_TIMEOUT_S,
                )
            else:
                try:
                    canvas.draw()
                except KeyboardInterrupt:
                    # GUI interrupted during drawing - safe to ignore
                    pass
                except Exception:
                    # Other drawing errors - still display the canvas
                    pass
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        if kind == "summary":
            self.summary_canvas = canvas
        else:
            self.waveform_canvas = canvas

    def _set_placeholder(self, placeholder: tk.Label, text: str) -> None:
        try:
            placeholder.configure(text=text)
            placeholder.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        except Exception:
            return

    def _on_tk_thread(self, callback: Callable[[], None]) -> None:
        if threading.current_thread() is threading.main_thread():
            try:
                callback()
            except Exception as exc:
                LOGGER.warning("Tk callback failed: %s", exc)
            return
        try:
            self._tk_queue.put_nowait(callback)
        except Exception:
            pass

    def _start_tk_pump(self) -> None:
        try:
            self.root.after(TK_PUMP_INTERVAL_MS, self._drain_tk_queue)
        except Exception:
            pass

    def _drain_tk_queue(self) -> None:
        if not self._pump_running:
            return
        for _ in range(TK_PUMP_MAX_CALLBACKS_PER_TICK):
            try:
                callback = self._tk_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as exc:
                LOGGER.warning("Tk pump callback failed: %s", exc)
        try:
            self.root.after(TK_PUMP_INTERVAL_MS, self._drain_tk_queue)
        except Exception:
            pass

    def _start_watchdog(
        self,
        kind: str,
        generation: int,
        timeout_s: float,
        on_timeout_tk: Callable[[], None],
        still_current: Callable[[], bool],
        invalidate: Callable[[], None],
    ) -> threading.Timer:
        """Start a daemon timer that marks the job aborted on timeout."""

        def fire() -> None:
            if not still_current():
                return
            LOGGER.warning(
                "%s plot generation %d timed out after %.1fs; abandoning",
                kind,
                generation,
                timeout_s,
            )
            # Surface the placeholder before invalidating: the finish
            # callback would otherwise see the bumped generation and bail
            # without updating the UI.
            self._on_tk_thread(on_timeout_tk)
            self._on_tk_thread(invalidate)

        timer = threading.Timer(timeout_s, fire)
        timer.daemon = True
        timer.start()
        return timer

    @staticmethod
    def _build_audio_diagnostics_figure(
        waveform: np.ndarray,
        samplerate: int,
        analysis: Any | None,
    ) -> Figure:
        figure = Figure(figsize=LIVE_WAVEFORM_FIGSIZE, constrained_layout=True)
        grid = figure.add_gridspec(
            2, 3, height_ratios=[2.2, 1.6], hspace=0.16, wspace=0.12
        )
        waveform_axis = figure.add_subplot(grid[0, :])
        fft_axis = figure.add_subplot(grid[1, 0])
        autocorr_axis = figure.add_subplot(grid[1, 1])
        activation_axis = figure.add_subplot(grid[1, 2])

        stride = max(1, waveform.size // 4000)
        shown = waveform[::stride]
        if samplerate > 0:
            x_axis = (np.arange(shown.size) * stride) / float(samplerate)
            x_label = "Time (s)"
        else:
            x_axis = (np.arange(shown.size) * stride).astype(np.float64)
            x_label = "Sample Index"

        waveform_axis.plot(x_axis, shown, linewidth=1.0, color="#1f77b4")
        waveform_axis.set_title("Latest Captured Waveform")
        waveform_axis.set_xlabel(x_label)
        waveform_axis.set_ylabel("Amplitude")
        waveform_axis.grid(True, linestyle=":", linewidth=0.5, color="gray")

        LivePlotManager._populate_fft_axis(fft_axis, waveform, samplerate, analysis)
        LivePlotManager._populate_autocorrelation_axis(
            autocorr_axis, waveform, samplerate, analysis
        )
        LivePlotManager._populate_pesto_axis(activation_axis, analysis)
        return figure

    @staticmethod
    def _populate_fft_axis(
        axis: Any,
        waveform: np.ndarray,
        samplerate: int,
        analysis: Any | None,
    ) -> None:
        cfg = PitchCompareConfig()
        expected_frequency = getattr(analysis, "expected_frequency", None)
        if waveform.size == 0:
            axis.text(
                0.5,
                0.5,
                "No FFT data.",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            axis.set_title("FFT")
            return

        window = np.hanning(waveform.size)
        spectrum = np.fft.rfft(waveform * window)
        freqs = np.fft.rfftfreq(waveform.size, d=1.0 / max(float(samplerate), 1.0))
        magnitudes = np.abs(spectrum)
        magnitudes_db = 20.0 * np.log10(np.maximum(magnitudes, 1e-9))

        axis.plot(freqs, magnitudes_db, color="#d95f02", linewidth=1.0)
        axis.set_title("FFT")
        axis.set_xlabel("Frequency (Hz)")
        axis.set_ylabel("Magnitude (dB)")
        axis.grid(True, linestyle=":", linewidth=0.5, color="gray")
        visible_max_frequency = LivePlotManager._expected_frequency_plot_max_frequency(
            expected_frequency,
            fallback_max=min(
                float(freqs[-1]) if freqs.size else float(cfg.max_frequency),
                float(cfg.max_frequency),
            ),
            multiplier=5.0,
        )
        if freqs.size:
            axis.set_xlim(0.0, visible_max_frequency)

        predicted_frequency = getattr(analysis, "frequency", None)
        if predicted_frequency is not None:
            try:
                predicted_frequency = float(predicted_frequency)
            except (TypeError, ValueError):
                predicted_frequency = None
        if predicted_frequency is not None and np.isfinite(predicted_frequency):
            if 0.0 <= predicted_frequency <= visible_max_frequency:
                axis.axvline(
                    predicted_frequency,
                    color="cyan",
                    linestyle="-",
                    linewidth=0.9,
                    alpha=0.85,
                )

    @staticmethod
    def _populate_pesto_axis(axis: Any, analysis: Any | None) -> None:
        cfg = PitchCompareConfig()
        activation_map = getattr(analysis, "activation_map", None)
        activation_freq_axis = getattr(analysis, "activation_freq_axis", None)
        frame_times = getattr(analysis, "frame_times", None)
        predicted_frequencies = getattr(analysis, "predicted_frequencies", None)
        expected_frequency = getattr(analysis, "expected_frequency", None)

        axis.set_title("PESTO Activations")
        axis.set_xlabel("Time (s)")
        axis.set_ylabel("Frequency (Hz)")

        if (
            activation_map is None
            or activation_freq_axis is None
            or frame_times is None
            or np.asarray(activation_map).size == 0
            or np.asarray(activation_freq_axis).size == 0
            or np.asarray(frame_times).size == 0
        ):
            axis.text(
                0.5,
                0.5,
                "PESTO activation data unavailable.",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            return

        activation_map = np.asarray(activation_map, dtype=np.float32)
        activation_freq_axis = np.asarray(activation_freq_axis, dtype=np.float32)
        frame_times = np.asarray(frame_times, dtype=np.float32)
        mask = (activation_freq_axis >= cfg.min_frequency) & (
            activation_freq_axis <= cfg.max_frequency
        )
        if not np.any(mask):
            axis.text(
                0.5,
                0.5,
                "No activation bins within frequency range.",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            axis.set_ylim(cfg.min_frequency, cfg.max_frequency)
            return

        visible_freqs = activation_freq_axis[mask]
        visible_activation = activation_map[mask, :]
        visible_max_frequency = LivePlotManager._expected_frequency_max_frequency(
            expected_frequency,
            fallback_max=float(cfg.max_frequency),
        )
        axis.pcolormesh(
            frame_times,
            visible_freqs,
            visible_activation,
            shading="nearest",
            cmap="viridis",
        )
        if predicted_frequencies is not None:
            predicted_frequencies = np.asarray(
                predicted_frequencies, dtype=np.float32
            ).reshape(-1)
            if predicted_frequencies.size == frame_times.size:
                valid = np.isfinite(predicted_frequencies) & (
                    predicted_frequencies > 0.0
                )
                valid &= predicted_frequencies >= float(cfg.min_frequency)
                valid &= predicted_frequencies <= float(cfg.max_frequency)
                if np.any(valid):
                    axis.plot(
                        frame_times[valid],
                        predicted_frequencies[valid],
                        color="cyan",
                        linewidth=1.0,
                    )
        axis.set_ylim(cfg.min_frequency, visible_max_frequency)
        axis.grid(False)

    @staticmethod
    def _populate_autocorrelation_axis(
        axis: Any,
        waveform: np.ndarray,
        samplerate: int,
        analysis: Any | None,
    ) -> None:
        cfg = PitchCompareConfig()
        axis.set_title("Autocorrelation")
        axis.set_xlabel("Frequency (Hz)")
        axis.set_ylabel("Normalized ACF")

        audio = np.asarray(waveform, dtype=np.float64).reshape(-1)
        if audio.size < 2 or samplerate <= 0:
            axis.text(
                0.5,
                0.5,
                "No autocorrelation data.",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            return

        centered = audio - float(np.mean(audio))
        energy = float(np.dot(centered, centered))
        if not np.isfinite(energy) or energy <= 0.0:
            axis.text(
                0.5,
                0.5,
                "No autocorrelation data.",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            return

        expected_frequency = getattr(analysis, "expected_frequency", None)
        visible_max_frequency = LivePlotManager._expected_frequency_plot_max_frequency(
            expected_frequency,
            fallback_max=float(cfg.max_frequency),
            multiplier=5.0,
        )

        lag_min = max(1, int(samplerate / visible_max_frequency))
        lag_max = min(int(samplerate / float(cfg.min_frequency)), audio.size - 1)
        if lag_min >= lag_max:
            axis.text(
                0.5,
                0.5,
                "Waveform too short for ACF range.",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            axis.set_xlim(float(cfg.min_frequency), visible_max_frequency)
            return

        n_fft = 1
        while n_fft < 2 * audio.size:
            n_fft <<= 1
        spectrum = np.fft.rfft(centered, n=n_fft)
        acf = np.fft.irfft(spectrum * np.conj(spectrum))[: audio.size]
        acf = acf / (energy + 1e-30)

        lags = np.arange(lag_min, lag_max + 1, dtype=np.int32)
        frequencies = float(samplerate) / lags.astype(np.float64)
        acf_band = acf[lag_min : lag_max + 1]
        order = np.argsort(frequencies)
        plot_freqs = frequencies[order]
        plot_acf = acf_band[order]

        axis.plot(plot_freqs, plot_acf, color="#7570b3", linewidth=1.0)
        axis.set_xlim(float(cfg.min_frequency), visible_max_frequency)
        axis.grid(True, linestyle=":", linewidth=0.5, color="gray")

        peak_index = int(np.argmax(acf_band))
        peak_frequency = float(frequencies[peak_index])
        peak_value = float(acf_band[peak_index])
        axis.axvline(
            peak_frequency,
            color="#7570b3",
            linestyle="--",
            linewidth=0.9,
            alpha=0.85,
        )

        predicted_frequency = getattr(analysis, "frequency", None)
        if predicted_frequency is not None:
            try:
                predicted_frequency = float(predicted_frequency)
            except (TypeError, ValueError):
                predicted_frequency = None
        if predicted_frequency is not None and np.isfinite(predicted_frequency):
            if (
                float(cfg.min_frequency)
                <= predicted_frequency
                <= float(cfg.max_frequency)
            ):
                axis.axvline(
                    predicted_frequency,
                    color="cyan",
                    linestyle="-",
                    linewidth=0.9,
                    alpha=0.85,
                )

        if expected_frequency is not None:
            try:
                expected_frequency = float(expected_frequency)
            except (TypeError, ValueError):
                expected_frequency = None
        if expected_frequency is not None and np.isfinite(expected_frequency):
            if (
                float(cfg.min_frequency)
                <= expected_frequency
                <= float(cfg.max_frequency)
            ):
                axis.axvline(
                    expected_frequency,
                    color="#666666",
                    linestyle=":",
                    linewidth=0.9,
                    alpha=0.9,
                )

        axis.text(
            0.02,
            0.98,
            f"peak {peak_frequency:.1f} Hz\nacf {peak_value:.2f}",
            ha="left",
            va="top",
            transform=axis.transAxes,
            fontsize=8,
            bbox={
                "facecolor": "white",
                "alpha": 0.75,
                "edgecolor": "none",
                "pad": 2.0,
            },
        )

    @staticmethod
    def _expected_frequency_max_frequency(
        expected_frequency: float | None,
        *,
        fallback_max: float,
    ) -> float:
        return LivePlotManager._expected_frequency_plot_max_frequency(
            expected_frequency,
            fallback_max=fallback_max,
            multiplier=2.0,
        )

    @staticmethod
    def _expected_frequency_plot_max_frequency(
        expected_frequency: float | None,
        *,
        fallback_max: float,
        multiplier: float,
    ) -> float:
        if expected_frequency is None:
            return float(fallback_max)
        try:
            limit = float(expected_frequency) * float(multiplier)
        except (TypeError, ValueError):
            return float(fallback_max)
        if not np.isfinite(limit) or limit <= 0.0:
            return float(fallback_max)
        return float(min(fallback_max, limit))


class _PlotTimeout(Exception):
    """Sentinel exception that signals a plot job was abandoned by its watchdog."""
