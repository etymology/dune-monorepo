from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from pathlib import Path
import sys
from typing import Any

import numpy as np


from dune_tension.gui import live_plots
from dune_tension.gui.live_plots import (
    LIVE_WAVEFORM_FIGSIZE,
    WAVEFORM_MIN_RENDER_INTERVAL_S,
    LivePlotManager,
)


class _FakeRoot:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: list[tuple[str, int, Any]] = []
        self._counter = 0
        self.cancelled: list[Any] = []

    def after(self, delay_ms: int, func: Any) -> str:
        with self._lock:
            self._counter += 1
            token = f"after-{self._counter}"
            self._queue.append((token, int(delay_ms), func))
        return token

    def after_cancel(self, token: Any) -> None:
        self.cancelled.append(token)
        with self._lock:
            self._queue = [item for item in self._queue if item[0] != token]

    def drain(self, timeout: float = 1.0) -> int:
        """Run queued after callbacks until none remain or timeout elapses."""
        deadline = time.monotonic() + timeout
        ran = 0
        while time.monotonic() < deadline:
            with self._lock:
                if not self._queue:
                    break
                token, delay_ms, func = self._queue.pop(0)
            try:
                func()
            except Exception:
                pass
            ran += 1
        return ran

    def drain_until(self, predicate: Any, timeout: float = 2.0) -> bool:
        """Drain after callbacks until ``predicate()`` is true or timeout elapses."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            with self._lock:
                ready = self._queue
                self._queue = []
            for _token, _delay_ms, func in ready:
                try:
                    func()
                except Exception:
                    pass
            if not ready:
                time.sleep(0.01)
        return predicate()


def _make_manager(monkeypatch) -> LivePlotManager:
    """Build a LivePlotManager bypassing Tk widget construction."""
    monkeypatch.setattr(live_plots, "FigureCanvasTkAgg", object, raising=False)

    manager = LivePlotManager.__new__(LivePlotManager)
    manager.root = _FakeRoot()
    manager.summary_parent = None
    manager.waveform_parent = None
    manager.summary_canvas = None
    manager.waveform_canvas = None
    manager.summary_placeholder = SimpleNamespace(
        configure=lambda **_kwargs: None,
        grid=lambda **_kwargs: None,
        grid_remove=lambda: None,
        grid_forget=lambda: None,
    )
    manager.waveform_placeholder = SimpleNamespace(
        configure=lambda **_kwargs: None,
        grid=lambda **_kwargs: None,
        grid_remove=lambda: None,
        grid_forget=lambda: None,
    )
    manager._summary_after_id = None
    manager._summary_generation = 0
    manager._waveform_after_id = None
    manager._waveform_generation = 0
    manager._waveform_pending = None
    manager._waveform_in_flight = False
    manager._waveform_last_started_at = None
    manager._tk_queue = queue.Queue()
    manager._pump_running = True
    manager._summary_executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="test-summary"
    )
    manager._waveform_executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="test-waveform"
    )
    manager._start_tk_pump()
    return manager


def test_build_audio_diagnostics_figure_includes_fft_and_pesto_axes() -> None:
    waveform = np.sin(np.linspace(0.0, 8.0 * np.pi, 2048, dtype=np.float32))
    analysis = SimpleNamespace(
        activation_map=np.ones((32, 8), dtype=np.float32),
        activation_freq_axis=np.geomspace(40.0, 400.0, 32).astype(np.float32),
        frame_times=np.linspace(0.0, 0.04, 8, dtype=np.float32),
        predicted_frequencies=np.linspace(80.0, 120.0, 8, dtype=np.float32),
        expected_frequency=200.0,
    )

    figure = LivePlotManager._build_audio_diagnostics_figure(
        waveform,
        8000,
        analysis,
    )

    assert len(figure.axes) == 4
    assert [axis.get_title() for axis in figure.axes] == [
        "Latest Captured Waveform",
        "FFT",
        "Autocorrelation",
        "PESTO Activations",
    ]
    assert figure.axes[1].get_xlim()[1] <= 2000.0
    assert figure.axes[3].get_ylim() == (30.0, 400.0)


def test_pesto_axis_uses_twice_expected_frequency() -> None:
    cutoff = LivePlotManager._expected_frequency_max_frequency(
        250.0,
        fallback_max=2000.0,
    )

    assert cutoff == 500.0


def test_audio_diagnostics_figure_uses_live_panel_size() -> None:
    waveform = np.sin(np.linspace(0.0, 4.0 * np.pi, 1024, dtype=np.float32))

    figure = LivePlotManager._build_audio_diagnostics_figure(
        waveform,
        8000,
        None,
    )

    assert tuple(figure.get_size_inches()) == LIVE_WAVEFORM_FIGSIZE


def test_publish_waveform_offloads_figure_build_to_worker(monkeypatch) -> None:
    manager = _make_manager(monkeypatch)

    build_thread_holder: list[int] = []
    show_canvas_calls: list[tuple[str, Any]] = []
    done = threading.Event()

    def fake_build(waveform, samplerate, analysis):
        build_thread_holder.append(threading.get_ident())
        return SimpleNamespace(clear=lambda: None)

    def fake_show_canvas(kind, figure):
        show_canvas_calls.append((kind, figure))
        done.set()

    monkeypatch.setattr(
        LivePlotManager,
        "_build_audio_diagnostics_figure",
        staticmethod(fake_build),
    )
    monkeypatch.setattr(manager, "_show_canvas", fake_show_canvas)

    main_thread_id = threading.get_ident()
    manager.publish_waveform(np.array([0.1, -0.1, 0.2], dtype=float), 8000, None)

    completed = manager.root.drain_until(done.is_set, timeout=2.0)

    assert completed, "waveform render did not complete"
    assert build_thread_holder, "_build_audio_diagnostics_figure was never invoked"
    assert build_thread_holder[0] != main_thread_id, (
        "figure build must run off the Tk (main) thread"
    )
    assert len(show_canvas_calls) == 1
    assert show_canvas_calls[0][0] == "waveform"


def test_publish_waveform_supersedes_pending_with_latest(monkeypatch) -> None:
    manager = _make_manager(monkeypatch)
    manager._waveform_last_started_at = time.monotonic()  # force throttle path

    build_calls: list[tuple[float, ...]] = []

    def fake_build(waveform, samplerate, analysis):
        build_calls.append(tuple(waveform.tolist()))
        return SimpleNamespace(clear=lambda: None)

    monkeypatch.setattr(
        LivePlotManager,
        "_build_audio_diagnostics_figure",
        staticmethod(fake_build),
    )
    monkeypatch.setattr(manager, "_show_canvas", lambda *_a, **_kw: None)

    manager.publish_waveform(np.array([1.0, 1.0], dtype=float), 8000, None)
    manager.publish_waveform(np.array([2.0, 2.0], dtype=float), 8000, None)
    manager.publish_waveform(np.array([3.0, 3.0], dtype=float), 8000, None)

    # Throttle should park the work in an after() and not start any worker yet.
    assert build_calls == []
    assert manager._waveform_after_id is not None
    assert manager._waveform_pending is not None
    assert tuple(manager._waveform_pending[0].tolist()) == (3.0, 3.0)


def test_finish_waveform_refresh_drops_stale_generation(monkeypatch) -> None:
    manager = _make_manager(monkeypatch)
    cleared = threading.Event()

    show_canvas_calls: list[Any] = []
    monkeypatch.setattr(
        manager, "_show_canvas", lambda *_a, **_kw: show_canvas_calls.append(_a)
    )

    manager._waveform_in_flight = True
    manager._waveform_generation = 5

    stale_figure = SimpleNamespace(clear=cleared.set)
    manager._finish_waveform_refresh(generation=2, figure=stale_figure, error=None)

    assert show_canvas_calls == []
    assert cleared.is_set(), "stale figure should be cleared, not painted"
    assert manager._waveform_in_flight is False


def test_throttle_constant_is_configured() -> None:
    assert WAVEFORM_MIN_RENDER_INTERVAL_S >= 0.05


def test_on_tk_thread_does_not_block_when_called_from_worker(monkeypatch) -> None:
    """A worker thread enqueuing onto _tk_queue must not block on Tcl."""

    manager = _make_manager(monkeypatch)

    received: list[str] = []

    def callback() -> None:
        received.append("ran")

    started = threading.Event()
    finished = threading.Event()

    def caller() -> None:
        started.set()
        manager._on_tk_thread(callback)
        finished.set()

    worker = threading.Thread(target=caller, daemon=True)
    worker.start()
    assert started.wait(timeout=1.0)
    assert finished.wait(timeout=0.5), (
        "_on_tk_thread from a worker thread must not block"
    )

    # The callback is queued; the FakeRoot pump drains it on its next tick.
    assert manager.root.drain_until(lambda: bool(received), timeout=2.0)
    assert received == ["ran"]


def test_waveform_render_continues_when_figure_lock_is_held(monkeypatch) -> None:
    """A hung holder of the figure lock must not stop measurement-side dispatch."""

    manager = _make_manager(monkeypatch)

    from dune_tension._matplotlib_lock import get_figure_lock

    lock = get_figure_lock()
    lock.acquire()
    try:
        worker_unblocked = threading.Event()

        def caller() -> None:
            manager.publish_waveform(
                np.array([0.0, 0.1, 0.2], dtype=float), 8000, None
            )
            worker_unblocked.set()

        thread = threading.Thread(target=caller, daemon=True)
        thread.start()

        assert worker_unblocked.wait(timeout=0.5), (
            "publish_waveform from a worker thread must not block on the figure lock"
        )

        # The watchdog should fire and surface a "timed out" placeholder.
        placeholder_text: list[str] = []
        monkeypatch.setattr(
            manager.waveform_placeholder,
            "configure",
            lambda **kw: placeholder_text.append(kw.get("text", "")),
        )

        assert manager.root.drain_until(
            lambda: any("timed out" in t for t in placeholder_text),
            timeout=live_plots.WAVEFORM_PLOT_TIMEOUT_S + 2.0,
        ), f"watchdog should produce a 'timed out' placeholder; got {placeholder_text}"
    finally:
        lock.release()


def test_summary_refresh_does_not_block_caller(monkeypatch) -> None:
    """request_summary_refresh from a worker thread must return immediately."""

    manager = _make_manager(monkeypatch)
    config = SimpleNamespace(apa_name="APA", layer="X")

    started = threading.Event()
    finished = threading.Event()

    def caller() -> None:
        started.set()
        manager.request_summary_refresh(config)
        finished.set()

    thread = threading.Thread(target=caller, daemon=True)
    thread.start()
    assert started.wait(timeout=1.0)
    assert finished.wait(timeout=0.2), (
        "request_summary_refresh from a worker must not block"
    )
