"""Verify the shared matplotlib figure_lock is used by every plot path."""

from __future__ import annotations

import threading
import time
from pathlib import Path
import sys


from dune_tension._matplotlib_lock import figure_lock, get_figure_lock


def test_figure_lock_is_a_reentrant_lock() -> None:
    lock = get_figure_lock()
    # RLock supports re-entry from the same thread; a regular Lock would deadlock.
    with lock:
        with lock:
            assert True


def test_figure_lock_serializes_concurrent_acquirers() -> None:
    lock = get_figure_lock()

    inside = threading.Event()
    proceed = threading.Event()
    other_blocked = threading.Event()

    def holder() -> None:
        with figure_lock():
            inside.set()
            proceed.wait(timeout=2.0)

    def waiter() -> None:
        # Deliberately probe lock contention with a short non-blocking acquire.
        if not lock.acquire(blocking=False):
            other_blocked.set()
            with figure_lock():
                pass

    holder_thread = threading.Thread(target=holder, daemon=True)
    holder_thread.start()
    assert inside.wait(timeout=1.0)

    waiter_thread = threading.Thread(target=waiter, daemon=True)
    waiter_thread.start()

    # The holder is still inside the lock; the waiter must observe contention.
    assert other_blocked.wait(timeout=1.0), (
        "second acquirer should be blocked while the first holds the lock"
    )

    proceed.set()
    holder_thread.join(timeout=2.0)
    waiter_thread.join(timeout=2.0)
    assert not holder_thread.is_alive()
    assert not waiter_thread.is_alive()


def test_summaries_save_plot_acquires_figure_lock(monkeypatch, tmp_path) -> None:
    from dune_tension import summaries

    holder = threading.Event()
    released = threading.Event()
    save_started = threading.Event()
    save_completed = threading.Event()

    def holding_thread() -> None:
        with figure_lock():
            holder.set()
            released.wait(timeout=2.0)

    other = threading.Thread(target=holding_thread, daemon=True)
    other.start()
    assert holder.wait(timeout=1.0)

    # Patch the figure builder so we don't actually do matplotlib work.
    monkeypatch.setattr(summaries, "build_summary_plot_figure", lambda *_a, **_kw: None)

    def call_save_plot() -> None:
        save_started.set()
        summaries.save_plot([], [], "APA", "X", str(tmp_path))
        save_completed.set()

    saver = threading.Thread(target=call_save_plot, daemon=True)
    saver.start()

    # save_plot should be blocked on the lock while `other` still holds it.
    assert save_started.wait(timeout=1.0)
    time.sleep(0.05)
    assert not save_completed.is_set(), (
        "save_plot must block on the figure lock while another thread holds it"
    )

    released.set()
    saver.join(timeout=2.0)
    other.join(timeout=2.0)
    assert save_completed.is_set()


def test_build_summary_plot_figure_for_config_acquires_lock(monkeypatch) -> None:
    from dune_tension import summaries

    holder_in = threading.Event()
    release_holder = threading.Event()

    def holding_thread() -> None:
        with figure_lock():
            holder_in.set()
            release_holder.wait(timeout=2.0)

    other = threading.Thread(target=holding_thread, daemon=True)
    other.start()
    assert holder_in.wait(timeout=1.0)

    monkeypatch.setattr(summaries, "_load_summary_measurements", lambda _cfg: object())
    monkeypatch.setattr(
        summaries, "_compute_tensions", lambda *_a, **_kw: ({}, [], [], {})
    )
    monkeypatch.setattr(summaries, "build_summary_plot_figure", lambda *_a, **_kw: None)

    config = type("Cfg", (), {"apa_name": "APA", "layer": "X"})()

    started = threading.Event()
    finished = threading.Event()

    def caller() -> None:
        started.set()
        summaries.build_summary_plot_figure_for_config(config)
        finished.set()

    runner = threading.Thread(target=caller, daemon=True)
    runner.start()

    assert started.wait(timeout=1.0)
    time.sleep(0.05)
    assert not finished.is_set(), (
        "build_summary_plot_figure_for_config must block on the figure lock"
    )

    release_holder.set()
    runner.join(timeout=2.0)
    other.join(timeout=2.0)
    assert finished.is_set()
