"""Process-wide lock that serializes matplotlib Figure construction and draw.

Matplotlib's Agg renderer and Figure machinery share enough mutable state
that running multiple Figure builds (or a build + a draw) concurrently can
hang or corrupt output. Use ``figure_lock`` as a context manager around any
code path that constructs Figures, calls ``canvas.draw()``, or writes
figures to disk via ``savefig``.
"""

from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Iterator

_figure_lock = threading.RLock()


@contextmanager
def figure_lock() -> Iterator[None]:
    """Serialize matplotlib Figure work across threads."""
    with _figure_lock:
        yield


def get_figure_lock() -> threading.RLock:
    """Return the shared lock (for tests and rare direct-acquire callers)."""
    return _figure_lock
