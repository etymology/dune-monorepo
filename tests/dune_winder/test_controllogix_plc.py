import threading
import unittest

from dune_winder.io.devices.controllogix_plc import ControllogixPLC


class _Driver:
  def __init__(self):
    self.connected = True
    self.writes = []

  def write(self, tag):
    self.writes.append(tag)
    return tag


class ControllogixPLCTests(unittest.TestCase):
  def _plc(self):
    plc = ControllogixPLC.__new__(ControllogixPLC)
    plc._plcDriver = _Driver()
    plc._isFunctional = True
    plc._lock = threading.Lock()
    return plc

  def test_write_expands_real_array_tag_to_pycomm3_count_syntax(self):
    plc = self._plc()

    result = plc.write(("xz_position_target", [440.0, 0.0]), typeName="REAL[2]")

    self.assertEqual(result, ("xz_position_target{2}", [440.0, 0.0]))
    self.assertEqual(plc._plcDriver.writes, [("xz_position_target{2}", [440.0, 0.0])])

  def test_write_leaves_scalar_tag_name_unchanged(self):
    plc = self._plc()

    result = plc.write(("STATE_REQUEST", 12), typeName="DINT")

    self.assertEqual(result, ("STATE_REQUEST", 12))
    self.assertEqual(plc._plcDriver.writes, [("STATE_REQUEST", 12)])


if __name__ == "__main__":
  unittest.main()
