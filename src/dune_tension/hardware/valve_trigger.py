"""Utilities for triggering the pneumatic valve over the serial relay.

This module provides a high-level :func:`air_pulse` function that opens the
valve for a requested duration without blocking the caller.  It also exposes a
simple command-line interface that fires a pulse each time the user presses the
spacebar.
"""

from __future__ import annotations

import argparse
import sys
import termios
import threading
import time
from math import ceil
import tty
from dataclasses import dataclass
from types import TracebackType
from typing import IO, Sequence

import serial
from serial import Serial

from dune_tension.hardware.serial_discovery import (
    build_candidate_ports,
    is_serial_permission_error,
)

_OPEN_COMMAND = bytes([0xA0, 0x01, 0x01, 0xA2])
_CLOSE_COMMAND = bytes([0xA0, 0x01, 0x00, 0xA1])


class DeviceNotFoundError(RuntimeError):
    """Raised when the USB relay controlling the valve cannot be located."""


@dataclass(slots=True)
class ValveConfig:
    """Configuration for the valve relay connection."""

    vendor_id: str = "1A86"
    product_id: str = "7523"
    device_name_substrings: tuple[str, ...] = (
        "valve",
        "relay",
        "usb relay",
        "serial relay",
        "usb-serial ch340",
        "usb2.0-serial",
        "wchusbserial",
        "wch.cn",
    )
    baud_rate: int = 9600
    serial_timeout: float = 0


class ValveController:
    """Manage the serial connection to the valve relay."""

    def __init__(self, *, port: str | None = None, config: ValveConfig | None = None):
        self._config = config or ValveConfig()
        self._serial: Serial | None = None
        candidate_ports = build_candidate_ports(
            preferred_port=port,
            name_substrings=self._config.device_name_substrings,
            vendor_id=self._config.vendor_id,
            product_id=self._config.product_id,
        )
        last_error = None
        permission_error = None
        for candidate_port in candidate_ports:
            try:
                self._serial = Serial(
                    candidate_port,
                    self._config.baud_rate,
                    timeout=self._config.serial_timeout,
                    write_timeout=self._config.serial_timeout,
                )
                break
            except serial.SerialException as exc:
                last_error = exc
                if is_serial_permission_error(exc):
                    permission_error = exc

        if self._serial is None:
            if not candidate_ports:
                raise DeviceNotFoundError(
                    "Unable to locate the USB relay controlling the air valve."
                )
            if permission_error is not None:
                raise RuntimeError(
                    "Unable to open the valve relay serial port because access was denied. "
                    "Check OS serial-port permissions."
                ) from permission_error
            raise RuntimeError("Unable to open the valve relay serial port.") from last_error
        self._lock = threading.Lock()
        self._strum_stop_event: threading.Event | None = None
        self._strum_thread: threading.Thread | None = None

    def pulse(self, duration: float) -> None:
        """Open the valve immediately and close it after *duration* seconds.

        The call returns as soon as the valve has been commanded to open; the
        closing action is handled by a dedicated background thread.
        """
        if duration <= 0:
            raise ValueError("Pulse duration must be positive.")

        n_pad = ceil(duration * self._config.baud_rate / 10)  # 8N1
        padding = b"\x00" * n_pad  # choose a byte the device ignores
        serial_port = self._require_serial()
        serial_port.write(_OPEN_COMMAND + padding + _CLOSE_COMMAND)
        serial_port.flush()

    def start_strum(self) -> None:
        """Begin emitting 10 ms air pulses every second on a background thread."""

        with self._lock:
            if self._strum_thread is not None and self._strum_thread.is_alive():
                return

            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._strum_loop,
                args=(stop_event,),
                daemon=True,
                name="valve-strum",
            )
            self._strum_stop_event = stop_event
            self._strum_thread = thread
            thread.start()

    def stop_strum(self) -> None:
        """Stop the background strumming loop if it is running."""

        with self._lock:
            stop_event = self._strum_stop_event
            thread = self._strum_thread
            self._strum_stop_event = None
            self._strum_thread = None

        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=0.1)

    def __enter__(self) -> "ValveController":
        return self

    def close(self) -> None:
        """Close the serial connection to the valve relay."""
        self.stop_strum()
        self._require_serial().close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def _write(self, payload: bytes) -> None:
        serial_port = self._require_serial()
        serial_port.write(payload)
        serial_port.flush()

    def _require_serial(self) -> Serial:
        serial_port = self._serial
        if serial_port is None:  # pragma: no cover - construction guarantees this
            raise RuntimeError("Valve relay serial port is not connected.")
        return serial_port

    def _strum_loop(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            self.pulse(0.01)
            if stop_event.wait(1):
                break


_DEFAULT_CONTROLLER: ValveController | None = None
_DEFAULT_CONTROLLER_LOCK = threading.Lock()


def _get_default_controller() -> ValveController:
    global _DEFAULT_CONTROLLER
    with _DEFAULT_CONTROLLER_LOCK:
        if _DEFAULT_CONTROLLER is None:
            _DEFAULT_CONTROLLER = ValveController()
    return _DEFAULT_CONTROLLER


def air_pulse(t_seconds: float) -> None:
    controller = _get_default_controller()
    controller.pulse(t_seconds)


def _ensure_tty(stream: IO[str]) -> None:
    if not stream.isatty():
        raise RuntimeError("The CLI requires an interactive terminal.")


def _cli(duration: float, port: str | None = None) -> int:
    try:
        _ensure_tty(sys.stdin)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        controller = ValveController(port=port)
    except DeviceNotFoundError:
        print("Error: Air valve controller not found.", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(
        "Press SPACE to trigger the valve pulse, or 'q' to quit."
        f" Pulse duration: {duration:.3f} s"
    )

    fd = sys.stdin.fileno()
    tcgetattr = getattr(termios, "tcgetattr")
    tcsetattr = getattr(termios, "tcsetattr")
    tcsadrain = getattr(termios, "TCSADRAIN")
    setcbreak = getattr(tty, "setcbreak")

    old_settings = tcgetattr(fd)
    try:
        setcbreak(fd)
        while True:
            char = sys.stdin.read(1)
            if char == " ":
                try:
                    # controller.pulse(duration)
                    controller.start_strum()
                    print(f"Pulsed valve for {duration:.3f} seconds.")
                except Exception as exc:  # pragma: no cover - defensive
                    print(f"Error while pulsing valve: {exc}", file=sys.stderr)
                    return 1
            elif char in {"q", "Q", "\x04"}:  # Ctrl+D
                break
    except KeyboardInterrupt:
        pass
    finally:
        tcsetattr(fd, tcsadrain, old_settings)
        controller.close()

    print("Exiting.")
    return 0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pulse the air valve whenever the spacebar is pressed.",
    )
    parser.add_argument(
        "duration",
        type=float,
        help="Length of the valve pulse in seconds.",
    )
    parser.add_argument(
        "--port",
        help="Serial port path for the valve relay. Auto-detected when omitted.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.duration <= 0:
        print("Error: duration must be a positive number.", file=sys.stderr)
        return 2
    return _cli(args.duration, port=args.port)


if __name__ == "__main__":
    raise SystemExit(main())
