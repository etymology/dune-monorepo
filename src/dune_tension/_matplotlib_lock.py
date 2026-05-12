"""Process-wide lock that serializes matplotlib Figure construction and draw.

Matplotlib's Agg renderer and Figure machinery share enough mutable state
that running multiple Figure builds (or a build + a draw) concurrently can
hang or corrupt output. Use ``figure_lock`` as a context manager around any
code path that constructs Figures, calls ``canvas.draw()``, or writes
figures to disk via ``savefig``.

``figure_lock_or_skip(timeout)`` is the safer variant for interactive
contexts: it yields ``True`` if the lock was acquired within ``timeout``
seconds and ``False`` otherwise, so callers can abandon the plot rather
than block indefinitely behind a hung matplotlib worker.
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
import threading
from typing import Iterator

LOGGER = logging.getLogger(__name__)

_figure_lock = threading.Lock()


@contextmanager
def figure_lock() -> Iterator[None]:
    """Serialize matplotlib Figure work across threads (blocking)."""
    _figure_lock.acquire()
    try:
        yield
    finally:
        _figure_lock.release()


@contextmanager
def figure_lock_or_skip(timeout: float) -> Iterator[bool]:
    """Try to acquire the figure lock within ``timeout`` seconds.

    Yields ``True`` if acquired (and releases on exit), ``False`` if the
    lock could not be obtained — in which case the caller should abandon
    the plot operation rather than block.
    """
    acquired = _figure_lock.acquire(timeout=max(0.0, float(timeout)))
    try:
        yield acquired
    finally:
        if acquired:
            _figure_lock.release()


def get_figure_lock() -> threading.Lock:
    """Return the shared lock (for tests and rare direct-acquire callers)."""
    return _figure_lock
