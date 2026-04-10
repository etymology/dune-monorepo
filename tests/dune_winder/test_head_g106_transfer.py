"""Integration tests for G206 head transfers through the full PLC stack."""

from __future__ import annotations

import time
import unittest

from dune_winder.io.controllers.head import Head
from dune_winder.io.controllers.plc_logic import PLC_Logic
from dune_winder.io.devices.plc import PLC
from dune_winder.io.devices.simulated_plc import SimulatedPLC
from dune_winder.io.primitives.multi_axis_motor import MultiAxisMotor
from dune_winder.io.primitives.plc_motor import PLC_Motor

try:
  from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC

  _HAS_LADDER = True
except ImportError:
  _HAS_LADDER = False


_MACHINE_SW_BITS_USED_BY_HEAD = [
  "MACHINE_SW_STAT[5]",
  "MACHINE_SW_STAT[6]",
  "MACHINE_SW_STAT[7]",
  "MACHINE_SW_STAT[9]",
  "MACHINE_SW_STAT[10]",
  "ENABLE_ACTUATOR",
]


def _build_full_stack(plc):
  polled = PLC.Tag.Attributes()
  polled.canWrite = False
  polled.isPolled = True
  polled.defaultValue = 0
  for bitName in _MACHINE_SW_BITS_USED_BY_HEAD:
    PLC.Tag(plc, bitName, polled)

  xAxis = PLC_Motor("xAxis", plc, "X")
  yAxis = PLC_Motor("yAxis", plc, "Y")
  zAxis = PLC_Motor("zAxis", plc, "Z")
  xyAxis = MultiAxisMotor("xyAxis", [xAxis, yAxis])
  logic = PLC_Logic(plc, xyAxis, zAxis)
  head = Head(logic)
  logic.poll()
  return logic, head


def _poll(plc):
  PLC.Tag.pollAll(plc)


def _drive_transfer(plc, head, timeout=6.0):
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    _poll(plc)
    head.update()
    if head._headState in (Head.States.IDLE, Head.States.ERROR):
      return
    time.sleep(0.12)


def _snapshot(plc):
  return {
    "ACTUATOR_POS": plc.get_tag("ACTUATOR_POS"),
    "HEAD_POS": plc.get_tag("HEAD_POS"),
    "Z_actual": plc.get_tag("Z_axis.ActualPosition"),
    "Z_EXTENDED": plc.get_tag("MACHINE_SW_STAT[5]"),
    "Z_STAGE_LATCHED": plc.get_tag("MACHINE_SW_STAT[6]"),
    "Z_FIXED_LATCHED": plc.get_tag("MACHINE_SW_STAT[7]"),
    "ENABLE_ACTUATOR": plc.get_tag("ENABLE_ACTUATOR"),
  }


class _TagStateSaver:
  def save(self):
    self._saved_instances = list(PLC.Tag.instances)
    self._saved_lookup = dict(PLC.Tag.tag_lookup_table)

  def restore(self):
    PLC.Tag.instances = self._saved_instances
    PLC.Tag.tag_lookup_table = self._saved_lookup


class G206TransferSimulatedTests(unittest.TestCase):
  def setUp(self):
    self._saver = _TagStateSaver()
    self._saver.save()
    PLC.Tag.instances = []
    PLC.Tag.tag_lookup_table = {}

  def tearDown(self):
    self._saver.restore()

  def _make_plc(self, head_pos=0, actuator_pos=1):
    plc = SimulatedPLC()
    plc.set_tag("HEAD_POS", head_pos)
    plc.set_tag("ACTUATOR_POS", actuator_pos)
    return plc

  def test_stage_to_fixed_transfer_completes(self):
    plc = self._make_plc(head_pos=0, actuator_pos=1)
    _logic, head = _build_full_stack(plc)

    self.assertIsNone(head.setTransferPosition(Head.FIXED_SIDE, 300))
    _drive_transfer(plc, head)

    snap = _snapshot(plc)
    self.assertEqual(head._headState, Head.States.IDLE, snap)
    self.assertEqual(int(snap["ACTUATOR_POS"]), 2, snap)
    self.assertTrue(bool(snap["Z_FIXED_LATCHED"]), snap)
    self.assertFalse(bool(snap["Z_STAGE_LATCHED"]), snap)
    self.assertAlmostEqual(float(snap["Z_actual"]), 0.0, places=3)

  def test_fixed_to_stage_transfer_completes(self):
    plc = self._make_plc(head_pos=3, actuator_pos=2)
    _logic, head = _build_full_stack(plc)

    self.assertIsNone(head.setTransferPosition(Head.LEVEL_A_SIDE, 300))
    _drive_transfer(plc, head)

    snap = _snapshot(plc)
    self.assertEqual(head._headState, Head.States.IDLE, snap)
    self.assertEqual(int(snap["ACTUATOR_POS"]), 1, snap)
    self.assertTrue(bool(snap["Z_STAGE_LATCHED"]), snap)
    self.assertFalse(bool(snap["Z_FIXED_LATCHED"]), snap)
    self.assertAlmostEqual(float(snap["Z_actual"]), 150.0, places=3)

  def test_same_side_stage_move_skips_latching(self):
    plc = self._make_plc(head_pos=0, actuator_pos=1)
    _logic, head = _build_full_stack(plc)

    self.assertIsNone(head.setTransferPosition(Head.LEVEL_B_SIDE, 300))
    _drive_transfer(plc, head, timeout=2.0)

    snap = _snapshot(plc)
    self.assertEqual(head._headState, Head.States.IDLE, snap)
    self.assertEqual(int(snap["ACTUATOR_POS"]), 1, snap)
    self.assertTrue(bool(snap["Z_STAGE_LATCHED"]), snap)
    self.assertAlmostEqual(float(snap["Z_actual"]), 250.0, places=3)


@unittest.skipUnless(_HAS_LADDER, "LadderSimulatedPLC not available")
class G206TransferLadderTests(G206TransferSimulatedTests):
  def _make_plc(self, head_pos=0, actuator_pos=1):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag("HEAD_POS", head_pos)
    plc.set_tag("ACTUATOR_POS", actuator_pos)
    _poll(plc)
    return plc


if __name__ == "__main__":
  unittest.main()
