import importlib
import logging
import sys
from pathlib import Path
import types


def test_controller_scans_named_ports_then_falls_back_exhaustively(monkeypatch):
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

    class FakeSerial:
        def __init__(self, port, *_, **__):
            attempted_ports.append(port)
            if port in {"COM7", "/dev/cu.usbmodem999", "/dev/ttyUSB0"}:
                raise SerialException(port)
            self.port = port

        def close(self):
            pass

        def write(self, _payload):
            pass

        def read(self):
            return b"\x00"

    def fake_comports():
        return [
            FakePort("COM7", "Bluetooth Serial"),
            FakePort("/dev/cu.usbmodem999", "Micro Maestro 6-Servo Controller"),
            FakePort("/dev/ttyUSB0", "USB Serial Device"),
            FakePort("/dev/ttyACM2", "Pololu Maestro Command Port"),
        ]

    setattr(serial_stub, "Serial", FakeSerial)
    setattr(serial_stub, "SerialException", SerialException)
    setattr(list_ports_stub, "comports", fake_comports)
    setattr(serial_tools_stub, "list_ports", list_ports_stub)
    monkeypatch.setitem(sys.modules, "serial", serial_stub)
    monkeypatch.setitem(sys.modules, "serial.tools", serial_tools_stub)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports_stub)
    sys.modules.pop("dune_tension.hardware.serial_discovery", None)
    sys.modules.pop("dune_tension.maestro", None)

    maestro = importlib.import_module("dune_tension.maestro")
    maestro = importlib.reload(maestro)

    controller = maestro.Controller()

    assert attempted_ports == ["/dev/cu.usbmodem999", "/dev/ttyACM2"]
    assert controller.faulted is False
    assert controller.usb.port == "/dev/ttyACM2"


def test_controller_logs_permission_denied_distinctly(monkeypatch, caplog):
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

    class FakeSerial:
        def __init__(self, port, *_, **__):
            raise SerialException(
                f"could not open port {port}: Permission denied",
                errno=13,
            )

    def fake_comports():
        return [FakePort("/dev/ttyUSB0", "Pololu Maestro Command Port")]

    setattr(serial_stub, "Serial", FakeSerial)
    setattr(serial_stub, "SerialException", SerialException)
    setattr(list_ports_stub, "comports", fake_comports)
    setattr(serial_tools_stub, "list_ports", list_ports_stub)
    monkeypatch.setitem(sys.modules, "serial", serial_stub)
    monkeypatch.setitem(sys.modules, "serial.tools", serial_tools_stub)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", list_ports_stub)
    sys.modules.pop("dune_tension.hardware.serial_discovery", None)
    sys.modules.pop("dune_tension.maestro", None)

    maestro = importlib.import_module("dune_tension.maestro")
    maestro = importlib.reload(maestro)

    with caplog.at_level(logging.WARNING):
        controller = maestro.Controller()

    assert controller.faulted is True
    assert "access was denied" in caplog.text
