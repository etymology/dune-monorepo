"""Comms module for the NOYITO 5V 2-Channel Micro USB Relay Module.

Channel 1 fires the pneumatic air valve.  Channel 2 switches power to the
tensiometer's laser-pickup sensor (battery powering the audio readout).  The
module exposes a :class:`RelayController` for direct use, a
:func:`air_pulse` convenience function backed by a module-level singleton,
and a small CLI that fires a single valve pulse each time the user presses
the spacebar.

 Product Description


NOYITO 5V 2-Channel Micro USB Relay Module User Manual, Documentation, Schematic
https://1drv.ms/u/c/4a0865b22350d05c/EVzQUCOyZQgggEp-AAAAAAABW320WOGiHIcFPWMXibf0Cw?e=f1vXsu

Features:
1. Onboard high-performance microcontrollers chip;
2. Onboard CH340 USB control chip;
3. Onboard power LED and relay status LED;
4. Onboard 2-way 5V, 10A / 250VAC, 10A / 30VDC relays, relay life can be a continuous pull 10 million times;
5. Module with overcurrent protection and relay diode freewheeling protection;

Hardware introduction and description
Board size: 50 x 40mm
Board Interface Description:
COM1: common;
NC1: normally closed;
NO1: normally open.
COM2: common;
NC2: normally closed;
NO2: normally open.

Communication protocol description:
LC USB switch default communication baud rate: 9600BPS
Open the first USB switch: A0 01 01 A2
Turn off the first USB switch: A0 01 00 A1
Open the second USB switch: A0 02 01 A3
Turn off the second USB switch: A0 02 00 A2

USB switch communication protocol
Data (1) --- start flag (default is 0xA0)
Data (2) --- switch address codes (0x01 and 0x02 represent the first and second switches, respectively)
Data (3) --- operating data (0x00 is "off", 0x01 is "on")
Data (4) --- check code

Relay status query command:
Send "FF" as hexadecimal (hex) to query.
For example, if relays 1 and 2 are ON, and relays 3 and 4 are OFF, sending the relay query command "FF"will return:
"CH1:ON \r\nCH2:ON \r\nCH3: OFF\r\nCH4:OFF\r\n"
(Each channel relay is to return 10 byte sequence information)

Usage Description:
1. Connect the USB relay module to the computer and install the CH340 USB to serial chip driver
2. Open the STC-ISP, SSCOM32 such serial debugging software, select the baud rate of 9600, in hexadecimal (hex) form send A0 01 01 A2 and A0 02 01 A3 can be opened the first and second relay ; Send in hexadecimal (hex) A0 01 00 A1 and A0 02 00 A2 can be turned off the first and second relay, respectively.

Package Included:
1pcs NOYITO 5V2-Channel Micro USB Relay Module

"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
import termios
import threading
import tty
from dataclasses import dataclass
from math import ceil
from types import TracebackType
from typing import IO, Iterator, Sequence

import serial
from serial import Serial

from dune_tension.hardware.serial_discovery import (
    build_candidate_ports,
    is_serial_permission_error,
)

# Exact byte sequences from the vendor protocol table.  Keyed by (channel, on).
_RELAY_COMMANDS: dict[tuple[int, bool], bytes] = {
    (1, True): bytes([0xA0, 0x01, 0x01, 0xA2]),
    (1, False): bytes([0xA0, 0x01, 0x00, 0xA1]),
    (2, True): bytes([0xA0, 0x02, 0x01, 0xA3]),
    (2, False): bytes([0xA0, 0x02, 0x00, 0xA2]),
}
_QUERY_COMMAND = bytes([0xFF])
_QUERY_TIMEOUT_S = 0.2
_QUERY_RESPONSE_BYTES = 40  # 4 channels * 10 bytes per channel
_QUERY_PATTERN = re.compile(rb"CH(\d):\s*(ON|OFF)")

_SENSOR_CHANNEL = 2


class DeviceNotFoundError(RuntimeError):
    """Raised when the USB relay cannot be located."""


@dataclass(slots=True)
class RelayConfig:
    """Configuration for the USB relay serial connection."""

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


class RelayController:
    """Manage the serial connection to the 2-channel USB relay."""

    def __init__(self, *, port: str | None = None, config: RelayConfig | None = None):
        self._config = config or RelayConfig()
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
                raise DeviceNotFoundError("Unable to locate the USB relay.")
            if permission_error is not None:
                raise RuntimeError(
                    "Unable to open the USB relay serial port because access was denied. "
                    "Check OS serial-port permissions."
                ) from permission_error
            raise RuntimeError("Unable to open the USB relay serial port.") from last_error
        self._lock = threading.Lock()
        self._channel_state: dict[int, bool] = {1: False, 2: False}
        self._sensor_refcount: int = 0

    def pulse(self, duration: float, *, channel: int = 1) -> None:
        """Energize *channel* immediately and de-energize it after *duration* seconds.

        The call returns as soon as the relay has been commanded to energize;
        the de-energize command is queued into the same write so the device's
        own UART pacing produces the delay (baud-rate padding).
        """
        if duration <= 0:
            raise ValueError("Pulse duration must be positive.")

        on_cmd = _RELAY_COMMANDS[(channel, True)]
        off_cmd = _RELAY_COMMANDS[(channel, False)]
        n_pad = ceil(duration * self._config.baud_rate / 10)  # 8N1
        padding = b"\x00" * n_pad
        with self._lock:
            serial_port = self._require_serial()
            serial_port.write(on_cmd + padding + off_cmd)
            serial_port.flush()
            self._channel_state[channel] = False

    def set_channel(self, channel: int, on: bool) -> None:
        """Energize or de-energize the given channel."""
        command = _RELAY_COMMANDS[(channel, on)]
        with self._lock:
            serial_port = self._require_serial()
            serial_port.write(command)
            serial_port.flush()
            self._channel_state[channel] = on

    def sensor_power_on(self) -> None:
        """Energize the sensor-power channel (channel 2)."""
        self.set_channel(_SENSOR_CHANNEL, True)

    def sensor_power_off(self) -> None:
        """De-energize the sensor-power channel (channel 2)."""
        self.set_channel(_SENSOR_CHANNEL, False)

    def is_sensor_powered(self, *, use_cache: bool = True) -> bool:
        """Return whether sensor power (channel 2) is on.

        ``use_cache=True`` (default) returns the last commanded state.  Pass
        ``use_cache=False`` to issue a live query to the device.
        """
        if use_cache:
            return self._channel_state[_SENSOR_CHANNEL]
        return self.query_state().get(_SENSOR_CHANNEL, False)

    def query_state(self) -> dict[int, bool]:
        """Send the status query and return a map of channel -> on/off."""
        with self._lock:
            serial_port = self._require_serial()
            previous_timeout = serial_port.timeout
            try:
                serial_port.timeout = _QUERY_TIMEOUT_S
                serial_port.reset_input_buffer()
                serial_port.write(_QUERY_COMMAND)
                serial_port.flush()
                response = serial_port.read(_QUERY_RESPONSE_BYTES)
            finally:
                serial_port.timeout = previous_timeout
        result: dict[int, bool] = {}
        for channel_bytes, status_bytes in _QUERY_PATTERN.findall(response):
            result[int(channel_bytes)] = status_bytes == b"ON"
        return result

    @contextlib.contextmanager
    def sensor_power_session(self) -> Iterator[None]:
        """Context manager that powers the sensor on at enter and off at exit.

        Re-entrant via an internal refcount: nested sessions only flip the
        relay on the outermost enter and the outermost exit.  The off command
        always runs in the ``finally`` block.
        """
        with self._lock:
            self._sensor_refcount += 1
            outermost = self._sensor_refcount == 1
        if outermost:
            self.sensor_power_on()
        try:
            yield
        finally:
            with self._lock:
                self._sensor_refcount -= 1
                last = self._sensor_refcount == 0
            if last:
                self.sensor_power_off()

    def __enter__(self) -> "RelayController":
        return self

    def close(self) -> None:
        """Close the serial connection to the USB relay."""
        self._require_serial().close()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def _require_serial(self) -> Serial:
        serial_port = self._serial
        if serial_port is None:  # pragma: no cover - construction guarantees this
            raise RuntimeError("USB relay serial port is not connected.")
        return serial_port


_DEFAULT_CONTROLLER: RelayController | None = None
_DEFAULT_CONTROLLER_LOCK = threading.Lock()


def _get_default_controller() -> RelayController:
    global _DEFAULT_CONTROLLER
    with _DEFAULT_CONTROLLER_LOCK:
        if _DEFAULT_CONTROLLER is None:
            _DEFAULT_CONTROLLER = RelayController()
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
        controller = RelayController(port=port)
    except DeviceNotFoundError:
        print("Error: USB relay not found.", file=sys.stderr)
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
                    controller.pulse(duration)
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
        help="Serial port path for the USB relay. Auto-detected when omitted.",
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
