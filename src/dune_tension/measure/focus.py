from __future__ import annotations

import logging
import math
from typing import Any

LOGGER = logging.getLogger(__name__)

FOCUS_MM_PER_QUARTER_US = 20.0 / 4000.0
FOCUS_X_MM_PER_QUARTER_US = FOCUS_MM_PER_QUARTER_US / math.sqrt(3.0)


class FocusController:
    """Focus positioning and focus/X coupling compensation, carved out of
    Tensiometer.

    Reads the host's live focus callables/flags (``focus_position_getter``,
    ``focus_range_getter``, ``focus_wiggle_func``, ``use_manual_focus``,
    ``manual_focus_target``, ``_has_focus_wiggle_callback``) plus the motion
    callables used for X compensation, so post-construction reassignment in
    tests is honored.
    """

    def __init__(self, host: Any) -> None:
        self._host = host

    def wiggle_x_sign(self) -> float:
        """Return focus/X coupling sign for the configured side."""

        from dune_tension.streaming.pose import focus_side_sign

        return focus_side_sign(self._host.config.side)

    def focus_to_x_delta_mm(self, delta_focus_units: float) -> float:
        """Convert a focus delta in quarter-us to the coupled X delta in mm."""

        return (
            self.wiggle_x_sign()
            * float(delta_focus_units)
            * FOCUS_X_MM_PER_QUARTER_US
        )

    def get_focus_position(self) -> int:
        """Return the latest commanded focus position in quarter-us units."""

        try:
            return int(self._host.focus_position_getter())
        except Exception:
            return 0

    def apply_focus_wiggle_with_x_compensation(
        self, delta_focus: float
    ) -> float | None:
        """Apply focus wiggle and X compensation for equivalent travel in mm."""

        host = self._host
        if not host._has_focus_wiggle_callback:
            return None

        commanded_delta = int(float(delta_focus))
        host.focus_wiggle_func(commanded_delta)
        if commanded_delta == 0:
            return None

        delta_x_mm = self.focus_to_x_delta_mm(commanded_delta)
        try:
            cur_x, cur_y = host.get_current_xy_position()
        except Exception as exc:
            LOGGER.warning("Unable to read XY for focus wiggle compensation: %s", exc)
            return None

        new_x = round(cur_x + delta_x_mm, 1)
        try:
            moved = host.goto_xy_func(new_x, cur_y)
        except Exception as exc:
            LOGGER.warning("Focus wiggle compensation move failed: %s", exc)
            return None
        if moved is False:
            LOGGER.warning(
                "Focus wiggle compensation move to %s,%s failed.",
                new_x,
                cur_y,
            )
            return None

        try:
            compensated_x, _ = host.get_current_xy_position()
            return float(compensated_x)
        except Exception:
            return new_x

    def get_focus_bounds(self) -> tuple[int, int]:
        try:
            bounds = self._host.focus_range_getter()
        except Exception:
            bounds = None
        if not bounds or len(bounds) != 2:
            return (4000, 8000)
        low, high = int(bounds[0]), int(bounds[1])
        if low > high:
            return (4000, 8000)
        return (low, high)

    def clamp_focus_position(self, focus_position: int) -> int:
        low, high = self.get_focus_bounds()
        return max(low, min(high, int(focus_position)))

    def active_focus_target(self, focus_target: int | None = None) -> int | None:
        host = self._host
        if host.use_manual_focus:
            if host.manual_focus_target is None:
                return self.clamp_focus_position(self.get_focus_position())
            return self.clamp_focus_position(host.manual_focus_target)
        if focus_target is None:
            return None
        return self.clamp_focus_position(int(focus_target))
