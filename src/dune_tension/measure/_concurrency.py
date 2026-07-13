from __future__ import annotations

import logging
import threading
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)


def invoke_with_timeout(
    callback: Callable[..., Any],
    *args: Any,
    timeout_s: float,
    label: str,
) -> None:
    """Run ``callback`` in a daemon thread; return after ``timeout_s`` seconds.

    The thread keeps running on its own if the callback hasn't returned; we
    just stop waiting. This guarantees the wire loop never blocks on a
    misbehaving callback (e.g. a plot dispatch that has wedged).
    """

    def _runner() -> None:
        try:
            callback(*args)
        except Exception as exc:  # noqa: BLE001 — callback is user code
            LOGGER.debug("%s raised: %s", label, exc)

    thread = threading.Thread(
        target=_runner, name=f"timeout-guard-{label}", daemon=True
    )
    thread.start()
    thread.join(timeout=timeout_s)
    if thread.is_alive():
        LOGGER.warning(
            "%s exceeded %.2fs wall-clock guard; continuing measurement",
            label,
            timeout_s,
        )


# Backwards-compatible private alias for the historical name.
_invoke_with_timeout = invoke_with_timeout
