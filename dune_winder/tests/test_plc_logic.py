import unittest

from dune_winder.io.controllers.plc_logic import PLC_Logic
from dune_winder.io.devices.plc import PLC


class _FreshReadPLC(PLC):
  def __init__(self):
    self.read_calls = []
    self.write_calls = []
    self._functional = True

  def initialize(self):
    return True

  def isNotFunctional(self):
    return not self._functional

  def read(self, tag):
    self.read_calls.append(tag)
    if isinstance(tag, str):
      return None
    return [[str(tag[0]), 1]]

  def write(self, tag, data=None, typeName=None):
    del data
    del typeName
    self.write_calls.append(tag)
    return tag


class PLCLogicTests(unittest.TestCase):
  def setUp(self):
    self._saved_tag_instances = list(PLC.Tag.instances)
    self._saved_tag_lookup = dict(PLC.Tag.tag_lookup_table)
    PLC.Tag.instances = []
    PLC.Tag.tag_lookup_table = {}

  def tearDown(self):
    PLC.Tag.instances = self._saved_tag_instances
    PLC.Tag.tag_lookup_table = self._saved_tag_lookup

  def test_xz_move_reads_y_transfer_ok_via_list_based_fresh_read(self):
    plc = _FreshReadPLC()
    logic = PLC_Logic(plc, object(), object())

    logic.setXZ_Position(12.5, 34.5)

    self.assertEqual(plc.read_calls, [["Y_XFER_OK"]])
    self.assertEqual(
      plc.write_calls,
      [
        ("xz_position_target[0]", 12.5),
        ("xz_position_target[1]", 34.5),
        ("xz_trigger_move", True),
      ],
    )


if __name__ == "__main__":
  unittest.main()
