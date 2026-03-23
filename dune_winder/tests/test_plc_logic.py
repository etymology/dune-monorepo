import unittest

from dune_winder.io.controllers.plc_logic import PLC_Logic
from dune_winder.io.devices.plc import PLC
from dune_winder.io.primitives.plc_motor import PLC_Motor


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
        ("xz_position_target", [12.5, 34.5]),
        ("MOVE_TYPE", PLC_Logic.MoveTypes.SEEK_XZ),
      ],
    )

  def test_z_seek_pulses_move_type_after_updating_target(self):
    plc = _FreshReadPLC()
    zAxis = PLC_Motor("zAxis", plc, "Z")
    logic = PLC_Logic(plc, object(), zAxis)

    logic.setZ_Position(43.0, velocity=250.0)

    self.assertEqual(
      plc.write_calls,
      [
        ("Z_SPEED", 250.0),
        ("Z_DIR", 0),
        ("Z_POSITION", 43.0),
        ("MOVE_TYPE", PLC_Logic.MoveTypes.RESET),
        ("MOVE_TYPE", PLC_Logic.MoveTypes.SEEK_Z),
      ],
    )

  def test_z_jog_pulses_move_type_for_reverse_direction(self):
    plc = _FreshReadPLC()
    zAxis = PLC_Motor("zAxis", plc, "Z")
    logic = PLC_Logic(plc, object(), zAxis)

    logic.jogZ(-125.0)

    self.assertEqual(
      plc.write_calls,
      [
        ("Z_SPEED", 125.0),
        ("Z_DIR", 1),
        ("MOVE_TYPE", PLC_Logic.MoveTypes.RESET),
        ("MOVE_TYPE", PLC_Logic.MoveTypes.JOG_Z),
      ],
    )

  def test_get_state_reads_live_value_via_list_based_fresh_read(self):
    plc = _FreshReadPLC()
    logic = PLC_Logic(plc, object(), object())

    state = logic.getState()

    self.assertEqual(state, 1)
    self.assertEqual(plc.read_calls, [["STATE"]])


if __name__ == "__main__":
  unittest.main()
