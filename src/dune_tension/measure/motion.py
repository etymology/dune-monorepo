from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)


class Mover:
    """XY motion with single-retry PLC-reset recovery, carved out of Tensiometer.

    Reads the host's live ``goto_xy_func`` and ``motion`` so that tests which
    reassign those attributes after construction are honored.
    """

    def __init__(self, host: Any) -> None:
        self._host = host

    def goto_with_reset_recovery(
        self,
        x_target: float,
        y_target: float,
        *,
        context: str,
        **move_kwargs: Any,
    ) -> bool:
        """Attempt an XY move, resetting the PLC and retrying once on failure."""

        host = self._host
        try:
            moved = host.goto_xy_func(x_target, y_target, **move_kwargs)
        except Exception as exc:
            LOGGER.warning(
                "%s move to %s,%s raised %s", context, x_target, y_target, exc
            )
            moved = False

        if moved is not False:
            return True

        LOGGER.warning(
            "%s move to %s,%s failed. Resetting PLC and retrying once.",
            context,
            x_target,
            y_target,
        )
        try:
            host.motion.reset_plc()
        except Exception as exc:
            LOGGER.warning("PLC reset after failed move raised %s", exc)

        try:
            retry = host.goto_xy_func(x_target, y_target, **move_kwargs)
        except Exception as exc:
            LOGGER.warning(
                "%s retry after PLC reset raised %s for move to %s,%s",
                context,
                exc,
                x_target,
                y_target,
            )
            return False

        if retry is False:
            LOGGER.warning(
                "%s retry after PLC reset still failed for move to %s,%s.",
                context,
                x_target,
                y_target,
            )
            return False
        return True
