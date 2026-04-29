import importlib
import sys
from pathlib import Path
import types

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def test_valve_controller_prefers_matching_name_and_vid_pid(monkeypatch):
    serial_stub = types.ModuleType("serial")
    serial_tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")
    attempted_ports = []

    class SerialException(Exception):
        pass

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
                raise SerialException(port)
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

    setattr(serial_stub, "Serial", FakeSerial)
    setattr(serial_stub, "SerialException", SerialException)
    setattr(list_ports_stub, "comports", fake_comports)
    setattr(serial_tools_stub, "list_ports", list_ports_stub)
    monkeypatch.setitem(sys.modules, "serial", serial_stub)
    monkeypatch.setitem(sys.modules, "serial.tools", serial_tools_stub)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports_stub)
    sys.modules.pop("dune_tension.hardware.serial_discovery", None)
    sys.modules.pop("dune_tension.hardware.valve_trigger", None)

    valve_trigger = importlib.import_module("dune_tension.hardware.valve_trigger")
    valve_trigger = importlib.reload(valve_trigger)

    controller = valve_trigger.ValveController()

    assert attempted_ports == ["/dev/ttyUSB1"]
    assert controller._serial.port == "/dev/ttyUSB1"
    controller.close()


def test_valve_controller_falls_back_to_all_enumerated_ports(monkeypatch):
    serial_stub = types.ModuleType("serial")
    serial_tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")
    attempted_ports = []

    class SerialException(Exception):
        pass

    class FakePort:
        def __init__(self, device, description):
            self.device = device
            self.description = description
            self.hwid = ""

    class FakeSerial:
        def __init__(self, port, *_, **__):
            attempted_ports.append(port)
            if port != "/dev/ttyUSB9":
                raise SerialException(port)
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

    setattr(serial_stub, "Serial", FakeSerial)
    setattr(serial_stub, "SerialException", SerialException)
    setattr(list_ports_stub, "comports", fake_comports)
    setattr(serial_tools_stub, "list_ports", list_ports_stub)
    monkeypatch.setitem(sys.modules, "serial", serial_stub)
    monkeypatch.setitem(sys.modules, "serial.tools", serial_tools_stub)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports_stub)
    sys.modules.pop("dune_tension.hardware.serial_discovery", None)
    sys.modules.pop("dune_tension.hardware.valve_trigger", None)

    valve_trigger = importlib.import_module("dune_tension.hardware.valve_trigger")
    valve_trigger = importlib.reload(valve_trigger)

    controller = valve_trigger.ValveController(
        config=valve_trigger.ValveConfig(device_name_substrings=("definitely-not-present",))
    )

    assert attempted_ports == ["/dev/ttyS0", "/dev/ttyUSB9"]
    assert controller._serial.port == "/dev/ttyUSB9"
    controller.close()


def test_valve_controller_reports_permission_denied(monkeypatch):
    serial_stub = types.ModuleType("serial")
    serial_tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")

    class SerialException(Exception):
        def __init__(self, *args, errno=None):
            super().__init__(*args)
            self.errno = errno

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
            raise SerialException(
                f"could not open port {port}: Permission denied",
                errno=13,
            )

    def fake_comports():
        return [FakePort("/dev/ttyUSB0", "USB Relay Controller")]

    setattr(serial_stub, "Serial", FakeSerial)
    setattr(serial_stub, "SerialException", SerialException)
    setattr(list_ports_stub, "comports", fake_comports)
    setattr(serial_tools_stub, "list_ports", list_ports_stub)
    monkeypatch.setitem(sys.modules, "serial", serial_stub)
    monkeypatch.setitem(sys.modules, "serial.tools", serial_tools_stub)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports_stub)
    sys.modules.pop("dune_tension.hardware.serial_discovery", None)
    sys.modules.pop("dune_tension.hardware.valve_trigger", None)

    valve_trigger = importlib.import_module("dune_tension.hardware.valve_trigger")
    valve_trigger = importlib.reload(valve_trigger)

    with pytest.raises(RuntimeError, match="access was denied"):
        valve_trigger.ValveController()
