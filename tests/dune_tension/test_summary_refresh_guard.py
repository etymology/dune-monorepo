"""Verify the summary-refresh callback can't stall the measurement loop."""

from __future__ import annotations

import threading
import time


def test_invoke_with_timeout_returns_before_callback_finishes() -> None:
    from dune_tension.tensiometer import _invoke_with_timeout

    callback_returned = threading.Event()

    def slow_callback(_config: object) -> None:
        time.sleep(2.0)
        callback_returned.set()

    start = time.monotonic()
    _invoke_with_timeout(
        slow_callback,
        object(),
        timeout_s=0.1,
        label="slow_test",
    )
    elapsed = time.monotonic() - start

    assert elapsed < 0.6, (
        f"_invoke_with_timeout must return within ~timeout_s; took {elapsed:.2f}s"
    )
    assert not callback_returned.is_set(), (
        "callback should still be running when we return"
    )


def test_invoke_with_timeout_swallows_callback_exception() -> None:
    from dune_tension.tensiometer import _invoke_with_timeout

    def raising_callback(_config: object) -> None:
        raise RuntimeError("boom")

    # No exception should propagate.
    _invoke_with_timeout(
        raising_callback,
        object(),
        timeout_s=0.5,
        label="raising_test",
    )


def test_save_plot_skips_on_lock_contention(monkeypatch, tmp_path) -> None:
    """save_plot(timeout=...) must not block forever when the lock is held."""

    from dune_tension import summaries
    from dune_tension._matplotlib_lock import get_figure_lock

    lock = get_figure_lock()
    lock.acquire()
    try:
        monkeypatch.setattr(
            summaries, "build_summary_plot_figure", lambda *_a, **_kw: None
        )

        start = time.monotonic()
        wrote = summaries.save_plot(
            [], [], "APA", "X", str(tmp_path), timeout=0.05
        )
        elapsed = time.monotonic() - start

        assert wrote is False
        assert elapsed < 0.4, (
            f"save_plot(timeout=0.05) should return quickly; took {elapsed:.2f}s"
        )
    finally:
        lock.release()
