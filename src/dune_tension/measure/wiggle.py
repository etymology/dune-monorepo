from __future__ import annotations

import logging
import threading
import time
from typing import Any

from dune_tension.config import MEASUREMENT_WIGGLE_CONFIG
from dune_tension.tensiometer_functions import check_stop_event

LOGGER = logging.getLogger(__name__)


class WiggleController:
    """Background and sweeping winder-wiggle threads, carved out of Tensiometer.

    Owns the thread/event handles. Reads the host's live motion callables and
    delegates the actual moves back to the host's reset-recovery and
    measurement-pose helpers, so behavior is identical to the inline version.
    """

    def __init__(self, host: Any) -> None:
        self._host = host
        self._wiggle_event: threading.Event | None = None
        self._wiggle_thread: threading.Thread | None = None
        self._sweeping_wiggle_event: threading.Event | None = None
        self._sweeping_wiggle_thread: threading.Thread | None = None

    def start(self) -> None:
        """Begin wiggling the winder in a background thread."""
        host = self._host
        if self._wiggle_event and self._wiggle_event.is_set():
            return

        self._wiggle_event = threading.Event()
        self._wiggle_event.set()

        start_x, start_y = host.get_current_xy_position()
        # Wiggle by roughly half the wire pitch to avoid hitting adjacent wires
        wiggle_width = MEASUREMENT_WIGGLE_CONFIG.background_y_sigma_mm

        def _run() -> None:
            while self._wiggle_event and self._wiggle_event.is_set():
                host.goto_xy_func(
                    start_x,
                    host._gauss(start_y, wiggle_width),
                    speed=MEASUREMENT_WIGGLE_CONFIG.background_speed,
                )
                if self._wiggle_event is not None and not self._wiggle_event.is_set():
                    break
                time.sleep(MEASUREMENT_WIGGLE_CONFIG.background_interval_seconds)

        self._wiggle_thread = threading.Thread(target=_run, daemon=True)
        self._wiggle_thread.start()

    def stop(self) -> None:
        """Stop the background winder wiggle thread."""
        host = self._host
        if not self._wiggle_event:
            return
        host.motion.set_speed()
        self._wiggle_event.clear()
        if self._wiggle_thread:
            self._wiggle_thread.join(timeout=0.1)
        self._wiggle_event = None
        self._wiggle_thread = None
        host.motion.reset_plc()

    def start_sweeping(
        self,
        *,
        center_x: float,
        center_y: float,
        focus_target: int | None,
    ) -> None:
        host = self._host
        if not host.sweeping_wiggle or host.sweeping_wiggle_span_mm <= 0.0:
            return
        self.stop_sweeping(return_to_center=False)

        stop_event = threading.Event()
        stop_event.set()
        self._sweeping_wiggle_event = stop_event

        low_y = float(center_y - host.sweeping_wiggle_span_mm)
        high_y = float(center_y + host.sweeping_wiggle_span_mm)
        record_duration = max(float(host.config.record_duration), 1e-6)
        sweep_speed_mm_s = max(
            (float(host.sweeping_wiggle_span_mm) / record_duration) * 2.0,
            1e-3,
        )

        def _run() -> None:
            target_y = high_y
            while stop_event.is_set():
                if check_stop_event(
                    host.stop_event, "tension measurement interrupted!"
                ):
                    break
                if not host._goto_xy_with_reset_recovery(
                    center_x,
                    target_y,
                    context="Sweeping wiggle",
                    speed=sweep_speed_mm_s,
                ):
                    break
                target_y = low_y if abs(target_y - high_y) < 1e-9 else high_y

        self._sweeping_wiggle_thread = threading.Thread(target=_run, daemon=True)
        self._sweeping_wiggle_thread.start()

    def stop_sweeping(
        self,
        *,
        return_to_center: bool,
        center_x: float | None = None,
        center_y: float | None = None,
        focus_target: int | None = None,
    ) -> None:
        host = self._host
        stop_event = self._sweeping_wiggle_event
        if stop_event is not None:
            stop_event.clear()
        if self._sweeping_wiggle_thread is not None:
            self._sweeping_wiggle_thread.join(timeout=1.0)
        self._sweeping_wiggle_event = None
        self._sweeping_wiggle_thread = None
        host.motion.set_speed()
        if return_to_center and center_x is not None and center_y is not None:
            host._move_to_measurement_pose(center_x, center_y, focus_target)
