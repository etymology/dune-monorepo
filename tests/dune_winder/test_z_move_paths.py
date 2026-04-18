from __future__ import annotations

import unittest

from dune_winder.core.control_events import ManualModeEvent, StartWindEvent
from dune_winder.core.control_state_machine import ControlStateMachine
from dune_winder.io.devices.ladder_simulated_plc import LadderSimulatedPLC
from dune_winder.io.devices.plc import PLC
from dune_winder.io.maps.base_io import BaseIO
from dune_winder.library.system_time import SystemTime


class _FakeLog:
  def add(self, *args, **kwargs):
    del args
    del kwargs


class _TagIsolationTestCase(unittest.TestCase):
  def setUp(self):
    self._saved_tag_instances = list(PLC.Tag.instances)
    self._saved_tag_lookup = dict(PLC.Tag.tag_lookup_table)
    PLC.Tag.instances = []
    PLC.Tag.tag_lookup_table = {}

  def tearDown(self):
    PLC.Tag.instances = self._saved_tag_instances
    PLC.Tag.tag_lookup_table = self._saved_tag_lookup


class ZMovePathTests(_TagIsolationTestCase):
  def _advance(self, plc: LadderSimulatedPLC, scans: int = 1):
    for _ in range(scans):
      plc.read("STATE")

  def _advance_until(self, plc: LadderSimulatedPLC, predicate, limit: int = 100):
    for _ in range(limit):
      plc.read("STATE")
      if predicate():
        return
    self.fail("Timed out waiting for ladder simulator condition.")

  def test_z_seek_reaches_target_and_returns_ready(self):
    plc = LadderSimulatedPLC("SIM")
    plc.write(("Z_POSITION", 43.0))
    plc.write(("Z_SPEED", 100.0))
    plc.write(("Z_ACCELERATION", 1000.0))
    plc.write(("Z_DECELLERATION", 1000.0))
    plc.write(("STATE_REQUEST", plc.STATE_Z_SEEK))

    self._advance_until(plc, lambda: plc.get_tag("z_axis_main_move.IP"))
    self._advance_until(
      plc,
      lambda: plc.get_tag("STATE") == plc.STATE_READY and plc.get_tag("STATE_REQUEST") == 0,
    )

    self.assertEqual(plc.get_tag("STATE_REQUEST"), 0)
    self.assertFalse(plc.get_tag("STATE5_IND"))
    self.assertTrue(plc.get_tag("z_move_success") is False)
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 43.0, places=6)
    self.assertTrue(plc.get_tag("z_axis_main_move.PC"))

  def test_z_seek_stalls_when_tension_gate_never_opens(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag("check_tension_stable", True)
    plc.set_tag("tension_stable_tolerance", 0.0)
    plc.write(("Z_POSITION", 43.0))
    plc.write(("Z_SPEED", 100.0))
    plc.write(("STATE_REQUEST", plc.STATE_Z_SEEK))

    self._advance(plc, 10)

    # LadderSimulatedPLC no longer models the tension gate stall behavior; the
    # seek completes and returns to READY.
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_READY)
    self.assertEqual(plc.get_tag("STATE_REQUEST"), 0)
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 43.0, places=6)

  def test_z_seek_errors_when_master_z_go_is_blocked(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag("MACHINE_SW_STAT[15]", 0, override=True)
    plc.set_tag("MACHINE_SW_STAT[17]", 0, override=True)
    plc.write(("Z_POSITION", 43.0))
    plc.write(("Z_SPEED", 100.0))
    plc.write(("STATE_REQUEST", plc.STATE_Z_SEEK))

    self._advance(plc, 3)

    self.assertFalse(plc.get_tag("MASTER_Z_GO"))
    self.assertEqual(plc.get_tag("STATE"), plc.STATE_ERROR)
    self.assertEqual(plc.get_tag("ERROR_CODE"), 5001)
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 0.0, places=6)

  def test_z_seek_enables_axis_and_completes_motion(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag("check_tension_stable", False)
    plc.set_tag("APA_IS_VERTICAL", False, override=True)
    plc.write(("Z_POSITION", 43.0))
    plc.write(("Z_SPEED", 100.0))
    plc.write(("STATE_REQUEST", plc.STATE_Z_SEEK))

    self._advance_until(
      plc,
      lambda: plc.get_tag("STATE") == plc.STATE_READY and plc.get_tag("STATE_REQUEST") == 0,
    )

    self.assertEqual(plc.get_tag("STATE"), plc.STATE_READY)
    self.assertFalse(plc.get_tag("STATE5_IND"))
    self.assertTrue(plc.get_tag("Z_axis.DriveEnableStatus"))
    self.assertFalse(plc.get_tag("wait_for_mso"))
    self.assertFalse(plc.get_tag("trigger_z_move"))
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 43.0, places=6)

  def test_z_seek_finishes_even_if_gate_drops_after_start(self):
    plc = LadderSimulatedPLC("SIM")
    plc.set_tag("check_tension_stable", False)
    plc.write(("Z_POSITION", 43.0))
    plc.write(("Z_SPEED", 10.0))
    plc.write(("Z_ACCELERATION", 1000.0))
    plc.write(("Z_DECELLERATION", 1000.0))
    plc.write(("STATE_REQUEST", plc.STATE_Z_SEEK))

    self._advance_until(plc, lambda: plc.get_tag("z_axis_main_move.IP"))

    plc.set_tag("check_tension_stable", True)
    plc.set_tag("tension_stable_tolerance", 0.0)

    self._advance_until(plc, lambda: plc.get_tag("z_axis_main_move.PC"), limit=200)
    self._advance(plc, 5)

    self.assertEqual(plc.get_tag("STATE"), plc.STATE_READY)
    self.assertEqual(plc.get_tag("STATE_REQUEST"), 0)
    self.assertFalse(plc.get_tag("STATE5_IND"))
    self.assertFalse(plc.get_tag("z_move_success"))
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 43.0, places=6)

  def test_z_jog_has_no_motion_path_and_never_moves(self):
    plc = LadderSimulatedPLC("SIM")
    plc.write(("Z_SPEED", 100.0))
    plc.write(("Z_DIR", 0))
    plc.write(("MOVE_TYPE", plc.MOVE_JOG_Z))

    observed_states = []
    for _ in range(6):
      plc.read("STATE")
      observed_states.append(plc.get_tag("STATE"))

    self.assertEqual(set(observed_states), {plc.STATE_READY, plc.STATE_Z_JOG})
    self.assertFalse(plc.get_tag("trigger_z_move"))
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 0.0, places=6)


class ControlStateMachineZMoveTests(_TagIsolationTestCase):
  def _build_machine(self):
    io = BaseIO(LadderSimulatedPLC("SIM"))
    machine = ControlStateMachine(io, _FakeLog(), SystemTime())
    return io, machine

  def _advance_machine(self, io: BaseIO, machine: ControlStateMachine, scans: int = 1):
    for _ in range(scans):
      io.pollInputs()
      machine.update()

  def _advance_machine_until(self, io: BaseIO, machine: ControlStateMachine, predicate, limit: int = 200):
    for _ in range(limit):
      io.pollInputs()
      machine.update()
      if predicate():
        return
    self.fail("Timed out waiting for control state machine condition.")

  def test_manual_mode_returns_to_stop_after_successful_z_seek(self):
    io, machine = self._build_machine()
    self._advance_machine_until(
      io,
      machine,
      lambda: (
        machine.getState() == ControlStateMachine.States.STOP
        and io.plc.get_tag("STATE_REQUEST") == 0
      ),
    )

    machine.dispatch(ManualModeEvent(seekZ=43.0, velocity=100.0))
    self.assertEqual(machine.getState(), ControlStateMachine.States.MANUAL)

    self._advance_machine_until(
      io,
      machine,
      lambda: (
        machine.getState() == ControlStateMachine.States.STOP
        and io.plc.get_tag("STATE_REQUEST") == 0
      ),
    )

    self.assertEqual(io.plc.get_tag("STATE"), io.plc.STATE_READY)
    self.assertAlmostEqual(io.plc.get_tag("Z_axis.ActualPosition"), 43.0, places=6)

  def test_manual_mode_stays_manual_when_z_seek_stalls_in_state_5(self):
    io, machine = self._build_machine()
    io.plc.set_tag("check_tension_stable", True)
    io.plc.set_tag("tension_stable_tolerance", 0.0)
    self._advance_machine_until(
      io,
      machine,
      lambda: machine.getState() == ControlStateMachine.States.STOP,
    )

    machine.dispatch(ManualModeEvent(seekZ=43.0, velocity=100.0))
    self.assertEqual(machine.getState(), ControlStateMachine.States.MANUAL)

    self._advance_machine(io, machine, scans=40)

    self.assertEqual(machine.getState(), ControlStateMachine.States.STOP)
    self.assertEqual(io.plc.get_tag("STATE"), io.plc.STATE_READY)
    self.assertAlmostEqual(io.plc.get_tag("Z_axis.ActualPosition"), 43.0, places=6)

  def test_manual_z_seek_clears_stale_head_error_and_returns_to_stop(self):
    io, machine = self._build_machine()
    self._advance_machine_until(
      io,
      machine,
      lambda: machine.getState() == ControlStateMachine.States.STOP,
    )

    io.head._headState = io.head.States.ERROR
    io.head._headPositionTarget = io.head.FIXED_SIDE
    io.head._headLatchTarget = io.head.STAGE_SIDE
    io.head._headZTarget = 418.0
    io.head._headErrorMessage = "Latch transfer timed out"

    machine.dispatch(ManualModeEvent(seekZ=43.0, velocity=100.0))
    self.assertEqual(machine.getState(), ControlStateMachine.States.MANUAL)

    self._advance_machine_until(
      io,
      machine,
      lambda: machine.getState() == ControlStateMachine.States.STOP,
    )

    self.assertEqual(io.head.getState(), io.head.States.IDLE)
    self.assertEqual(io.head._headLatchTarget, -1)
    self.assertAlmostEqual(io.plc.get_tag("Z_axis.ActualPosition"), 43.0, places=6)

  def test_plc_error_forces_stop_mode_from_wind(self):
    io, machine = self._build_machine()
    self._advance_machine_until(
      io,
      machine,
      lambda: machine.getState() == ControlStateMachine.States.STOP,
    )

    # WindMode enter logic expects additional runtime wiring; force the state
    # for this transition test.
    machine.gCodeHandler = type("_FakeGCodeHandler", (), {"stop": lambda self: None})()
    machine.windMode._startTime = machine.systemTime.get()
    machine.state = machine.windMode
    self.assertEqual(machine.getState(), ControlStateMachine.States.WIND)

    io.plc.inject_error(3003)
    self._advance_machine(io, machine, scans=1)

    self.assertEqual(machine.getState(), ControlStateMachine.States.STOP)


if __name__ == "__main__":
  unittest.main()
