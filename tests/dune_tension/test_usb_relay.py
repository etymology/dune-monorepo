import importlib
import sys
from pathlib import Path
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def _install_serial_stubs(monkeypatch, *, FakeSerial, comports):
    serial_stub = types.ModuleType("serial")
    serial_tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")

    class SerialException(Exception):
        def __init__(self, *args, errno=None):
            super().__init__(*args)
            self.errno = errno

    setattr(serial_stub, "Serial", FakeSerial)
    setattr(serial_stub, "SerialException", SerialException)
    setattr(list_ports_stub, "comports", comports)
    setattr(serial_tools_stub, "list_ports", list_ports_stub)
    monkeypatch.setitem(sys.modules, "serial", serial_stub)
    monkeypatch.setitem(sys.modules, "serial.tools", serial_tools_stub)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports_stub)
    sys.modules.pop("dune_tension.hardware.serial_discovery", None)
    sys.modules.pop("dune_tension.hardware.usb_relay", None)
    usb_relay = importlib.import_module("dune_tension.hardware.usb_relay")
    return importlib.reload(usb_relay), SerialException


def test_relay_controller_prefers_matching_name_and_vid_pid(monkeypatch):
    attempted_ports = []

    class FakePort:
        def __init__(
            self,
            device,
            description,
            *,
            vid=None,
            pid=None,
            manufacturer=None,
            product=None,
            hwid="",
        ):
            self.device = device
            self.description = description
            self.vid = vid
            self.pid = pid
            self.manufacturer = manufacturer
            self.product = product
            self.hwid = hwid

    class FakeSerial:
        def __init__(self, port, *_, **__):
            attempted_ports.append(port)
            if port != "/dev/ttyUSB1":
                raise sys.modules["serial"].SerialException(port)
            self.port = port

        def close(self):
            pass

        def write(self, _payload):
            pass

        def flush(self):
            pass

    def fake_comports():
        return [
            FakePort("COM3", "Bluetooth Link"),
            FakePort(
                "/dev/ttyUSB1",
                "USB Relay Controller",
                vid=0x1A86,
                pid=0x7523,
                manufacturer="wch.cn",
                product="USB Relay Controller",
            ),
            FakePort("/dev/ttyACM0", "Pololu Maestro Command Port"),
        ]

    usb_relay, _ = _install_serial_stubs(
        monkeypatch, FakeSerial=FakeSerial, comports=fake_comports
    )

    controller = usb_relay.RelayController()

    assert attempted_ports == ["/dev/ttyUSB1"]
    assert controller._serial.port == "/dev/ttyUSB1"
    controller.close()


def test_relay_controller_falls_back_to_all_enumerated_ports(monkeypatch):
    attempted_ports = []

    class FakePort:
        def __init__(self, device, description):
            self.device = device
            self.description = description
            self.hwid = ""

    class FakeSerial:
        def __init__(self, port, *_, **__):
            attempted_ports.append(port)
            if port != "/dev/ttyUSB9":
                raise sys.modules["serial"].SerialException(port)
            self.port = port

        def close(self):
            pass

        def write(self, _payload):
            pass

        def flush(self):
            pass

    def fake_comports():
        return [
            FakePort("/dev/ttyS0", "Onboard Serial"),
            FakePort("/dev/ttyUSB9", "Unknown USB Serial"),
        ]

    usb_relay, _ = _install_serial_stubs(
        monkeypatch, FakeSerial=FakeSerial, comports=fake_comports
    )

    controller = usb_relay.RelayController(
        config=usb_relay.RelayConfig(device_name_substrings=("definitely-not-present",))
    )

    assert attempted_ports == ["/dev/ttyS0", "/dev/ttyUSB9"]
    assert controller._serial.port == "/dev/ttyUSB9"
    controller.close()


def test_relay_controller_reports_permission_denied(monkeypatch):
    class FakePort:
        def __init__(self, device, description):
            self.device = device
            self.description = description
            self.vid = 0x1A86
            self.pid = 0x7523
            self.manufacturer = "wch.cn"
            self.product = "USB Relay Controller"
            self.hwid = ""

    class FakeSerial:
        def __init__(self, port, *_, **__):
            raise sys.modules["serial"].SerialException(
                f"could not open port {port}: Permission denied",
                errno=13,
            )

    def fake_comports():
        return [FakePort("/dev/ttyUSB0", "USB Relay Controller")]

    usb_relay, _ = _install_serial_stubs(
        monkeypatch, FakeSerial=FakeSerial, comports=fake_comports
    )

    with pytest.raises(RuntimeError, match="access was denied"):
        usb_relay.RelayController()


class _RecordingSerial:
    """In-memory fake serial port that records writes and replays a read buffer."""

    def __init__(self, port, *_, **kwargs):
        self.port = port
        self.timeout = kwargs.get("timeout", 0)
        self.payloads: list[bytes] = []
        self._read_buffer = b""

    def close(self):
        pass

    def write(self, payload):
        self.payloads.append(bytes(payload))

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def queue_read(self, data: bytes) -> None:
        self._read_buffer = data

    def read(self, size: int) -> bytes:
        chunk = self._read_buffer[:size]
        self._read_buffer = self._read_buffer[size:]
        return chunk


def _load_with_recording_serial(monkeypatch):
    def fake_comports():
        return []

    usb_relay, _ = _install_serial_stubs(
        monkeypatch, FakeSerial=_RecordingSerial, comports=fake_comports
    )
    return usb_relay


def test_pulse_writes_open_padding_and_close(monkeypatch):
    usb_relay = _load_with_recording_serial(monkeypatch)
    controller = usb_relay.RelayController(port="/dev/ttyUSB0")
    controller.pulse(0.01)

    assert len(controller._serial.payloads) == 1
    payload = controller._serial.payloads[0]
    assert payload.startswith(bytes([0xA0, 0x01, 0x01, 0xA2]))
    assert payload.endswith(bytes([0xA0, 0x01, 0x00, 0xA1]))
    controller.close()


def test_set_channel_writes_exact_bytes(monkeypatch):
    usb_relay = _load_with_recording_serial(monkeypatch)
    controller = usb_relay.RelayController(port="/dev/ttyUSB0")

    controller.set_channel(1, True)
    controller.set_channel(1, False)
    controller.set_channel(2, True)
    controller.set_channel(2, False)

    assert controller._serial.payloads == [
        bytes([0xA0, 0x01, 0x01, 0xA2]),
        bytes([0xA0, 0x01, 0x00, 0xA1]),
        bytes([0xA0, 0x02, 0x01, 0xA3]),
        bytes([0xA0, 0x02, 0x00, 0xA2]),
    ]
    controller.close()


def test_sensor_power_helpers_use_channel_two(monkeypatch):
    usb_relay = _load_with_recording_serial(monkeypatch)
    controller = usb_relay.RelayController(port="/dev/ttyUSB0")

    controller.sensor_power_on()
    assert controller.is_sensor_powered() is True
    controller.sensor_power_off()
    assert controller.is_sensor_powered() is False

    assert controller._serial.payloads == [
        bytes([0xA0, 0x02, 0x01, 0xA3]),
        bytes([0xA0, 0x02, 0x00, 0xA2]),
    ]
    controller.close()


def test_query_state_parses_mixed_spacing(monkeypatch):
    usb_relay = _load_with_recording_serial(monkeypatch)
    controller = usb_relay.RelayController(port="/dev/ttyUSB0")
    controller._serial.queue_read(b"CH1:ON \r\nCH2: OFF\r\nCH3:OFF\r\nCH4: ON\r\n")

    state = controller.query_state()

    assert state == {1: True, 2: False, 3: False, 4: True}
    assert controller._serial.payloads == [bytes([0xFF])]
    controller.close()


def test_is_sensor_powered_can_bypass_cache(monkeypatch):
    usb_relay = _load_with_recording_serial(monkeypatch)
    controller = usb_relay.RelayController(port="/dev/ttyUSB0")
    controller.sensor_power_off()  # cache says False
    controller._serial.queue_read(b"CH1:OFF\r\nCH2:ON \r\nCH3:OFF\r\nCH4:OFF\r\n")

    assert controller.is_sensor_powered() is False
    assert controller.is_sensor_powered(use_cache=False) is True
    controller.close()


def test_sensor_power_session_powers_on_and_off(monkeypatch):
    usb_relay = _load_with_recording_serial(monkeypatch)
    controller = usb_relay.RelayController(port="/dev/ttyUSB0")

    with controller.sensor_power_session():
        assert controller.is_sensor_powered() is True

    assert controller.is_sensor_powered() is False
    assert controller._serial.payloads == [
        bytes([0xA0, 0x02, 0x01, 0xA3]),
        bytes([0xA0, 0x02, 0x00, 0xA2]),
    ]
    controller.close()


def test_sensor_power_session_off_even_on_exception(monkeypatch):
    usb_relay = _load_with_recording_serial(monkeypatch)
    controller = usb_relay.RelayController(port="/dev/ttyUSB0")

    with pytest.raises(RuntimeError, match="boom"):
        with controller.sensor_power_session():
            raise RuntimeError("boom")

    assert controller.is_sensor_powered() is False
    assert controller._serial.payloads[-1] == bytes([0xA0, 0x02, 0x00, 0xA2])
    controller.close()


def test_sensor_power_session_refcount_only_flips_at_outer_boundaries(monkeypatch):
    usb_relay = _load_with_recording_serial(monkeypatch)
    controller = usb_relay.RelayController(port="/dev/ttyUSB0")

    with controller.sensor_power_session():
        with controller.sensor_power_session():
            with controller.sensor_power_session():
                assert controller.is_sensor_powered() is True
            assert controller.is_sensor_powered() is True
        assert controller.is_sensor_powered() is True
    assert controller.is_sensor_powered() is False

    assert controller._serial.payloads == [
        bytes([0xA0, 0x02, 0x01, 0xA3]),
        bytes([0xA0, 0x02, 0x00, 0xA2]),
    ]
    controller.close()
