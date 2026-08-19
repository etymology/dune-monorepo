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


def test_controller_prefers_command_port_over_ttl_port(monkeypatch):
    serial_stub = types.ModuleType("serial")
    serial_tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")
    attempted_ports = []

    class SerialException(Exception):
        pass

    class FakePort:
        def __init__(self, device, description, location):
            self.device = device
            self.description = description
            self.location = location
            self.hwid = f"USB VID:PID=1FFB:0089 LOCATION={location}"

    class FakeSerial:
        def __init__(self, port, *_, **__):
            attempted_ports.append(port)
            self.port = port

        def close(self):
            pass

        def write(self, _payload):
            pass

        def read(self):
            return b"\x00"

    def fake_comports():
        # Mirror the real-world enumeration where the TTL port (interface 2)
        # is returned before the command port (interface 0).
        return [
            FakePort(
                "/dev/ttyACM1",
                "Pololu Micro Maestro 6-Servo Controller",
                "3-7.4:1.2",
            ),
            FakePort(
                "/dev/ttyACM0",
                "Pololu Micro Maestro 6-Servo Controller",
                "3-7.4:1.0",
            ),
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

    assert attempted_ports[0] == "/dev/ttyACM0"
    assert controller.usb.port == "/dev/ttyACM0"


def test_controller_selects_command_port_on_windows(monkeypatch):
    """Reproduce the real Windows enumeration of the Micro Maestro.

    The usbser.sys driver names both CDC interfaces "USB Serial Device" (so
    description matching fails) and pyserial reports the location as
    ``1-7.4:x.0`` -- the field before the dot is masked as ``x`` rather than a
    digit. The device must still be found by VID/PID, and the interface-0
    command port (COMM) must win over both the interface-2 TTL port and an
    unrelated motherboard COM1 that opens successfully.
    """
    serial_stub = types.ModuleType("serial")
    serial_tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")
    attempted_ports = []

    class SerialException(Exception):
        pass

    class FakePort:
        def __init__(self, device, description, vid=None, pid=None, location=None):
            self.device = device
            self.description = description
            self.manufacturer = "Microsoft"
            self.vid = vid
            self.pid = pid
            self.location = location
            self.hwid = (
                f"USB VID:PID={vid:04X}:{pid:04X} LOCATION={location}"
                if vid is not None
                else device
            )

    class FakeSerial:
        def __init__(self, port, *_, **__):
            attempted_ports.append(port)
            self.port = port

        def close(self):
            pass

        def write(self, _payload):
            pass

        def read(self):
            return b"\x00"

    def fake_comports():
        # comports() returns ports in ascending COM order, so the TTL port
        # (COM3, interface 2) and the dead motherboard port (COM1) precede the
        # command port (COM4, interface 0).
        return [
            FakePort("COM1", "Communications Port (COM1)"),
            FakePort("COM3", "USB Serial Device", 0x1FFB, 0x0089, "1-7.4:x.2"),
            FakePort("COM4", "USB Serial Device", 0x1FFB, 0x0089, "1-7.4:x.0"),
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

    assert attempted_ports[0] == "COM4"
    assert controller.usb.port == "COM4"


def test_controller_reconnects_after_write_failure(monkeypatch):
    """A stale-handle write failure should close, reopen, and retry once.

    Mirrors a USB disconnect/suspend on Windows, where the open handle becomes
    invalid and ``write`` raises ``PermissionError(13, 'Access is denied')``.
    """
    serial_stub = types.ModuleType("serial")
    serial_tools_stub = types.ModuleType("serial.tools")
    list_ports_stub = types.ModuleType("serial.tools.list_ports")
    opened = []

    class SerialException(Exception):
        pass

    class FakePort:
        def __init__(self, device, description, vid, pid, location):
            self.device = device
            self.description = description
            self.manufacturer = "Microsoft"
            self.vid = vid
            self.pid = pid
            self.location = location
            self.hwid = f"USB VID:PID={vid:04X}:{pid:04X} LOCATION={location}"

    class FakeSerial:
        def __init__(self, port, *_, **__):
            opened.append(self)
            self.port = port
            self.closed = False
            self.writes = []
            # Only the first handle ever opened simulates a stale write.
            self._fail_next_write = len(opened) == 1

        def write(self, payload):
            if self._fail_next_write:
                self._fail_next_write = False
                raise SerialException(
                    "WriteFile failed (PermissionError(13, 'Access is denied', None, 5))"
                )
            self.writes.append(payload)

        def read(self):
            return b"\x00"

        def close(self):
            self.closed = True

    def fake_comports():
        return [FakePort("COM4", "USB Serial Device", 0x1FFB, 0x0089, "1-7.4:x.0")]

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
    controller.setTarget(1, 6000)  # write fails, reconnects, retries

    assert len(opened) == 2  # initial open + one reconnect
    assert opened[0].closed is True  # stale handle was closed
    assert controller.usb is opened[1]
    assert controller.usb.port == "COM4"
    assert controller.faulted is False
    assert opened[1].writes  # the retried write landed on the fresh handle


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
