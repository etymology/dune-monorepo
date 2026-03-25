import unittest

from dune_winder.io.Devices.simulated_plc import SimulatedPLC


class SimulatedPlcBehaviorTests(unittest.TestCase):
  def _settle_once(self, plc: SimulatedPLC):
    plc.read(["STATE"])

  def test_startup_is_ready_and_stage_side(self):
    plc = SimulatedPLC()

    self.assertFalse(plc.isNotFunctional())
    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_READY)
    self.assertEqual(plc.get_tag("ERROR_CODE"), 0)
    self.assertEqual(plc.get_tag("HEAD_POS"), 0)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 0)
    self.assertEqual(plc.get_tag("MACHINE_SW_STAT[6]"), 1)
    self.assertEqual(plc.get_tag("MACHINE_SW_STAT[7]"), 0)

  def test_xy_seek_uses_one_cycle_settle_model(self):
    plc = SimulatedPLC()
    plc.write(("X_POSITION", 123.4))
    plc.write(("Y_POSITION", 456.7))
    plc.write(("MOVE_TYPE", SimulatedPLC.MOVE_SEEK_XY))

    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_XY_SEEK)
    self._settle_once(plc)

    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_READY)
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 123.4, places=6)
    self.assertAlmostEqual(plc.get_tag("Y_axis.ActualPosition"), 456.7, places=6)

  def test_latch_move_sets_busy_then_updates_actuator_and_head(self):
    plc = SimulatedPLC()
    plc.set_tag("HEAD_POS", 0)
    plc.set_tag("ACTUATOR_POS", 1)

    plc.write(("MOVE_TYPE", SimulatedPLC.MOVE_LATCH))
    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_LATCHING)
    self._settle_once(plc)

    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_READY)
    self.assertEqual(plc.get_tag("ACTUATOR_POS"), 2)
    self.assertEqual(plc.get_tag("HEAD_POS"), 3)

  def test_gui_latch_pulse_advances_latch_and_auto_clears(self):
    plc = SimulatedPLC()
    plc.set_tag("HEAD_POS", 0)
    plc.set_tag("ACTUATOR_POS", 1)

    plc.write(("gui_latch_pulse", 1))

    self.assertEqual(plc.get_tag("gui_latch_pulse"), 0)
    self.assertNotEqual(plc.get_tag("ACTUATOR_POS"), 1)

  def test_limit_violations_set_error_and_reset_clears(self):
    plc = SimulatedPLC()
    plc.write(("X_POSITION", 9000.0))
    plc.write(("Y_POSITION", 0.0))
    plc.write(("MOVE_TYPE", SimulatedPLC.MOVE_SEEK_XY))
    self._settle_once(plc)

    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_ERROR)
    self.assertEqual(plc.get_tag("ERROR_CODE"), 3003)

    plc.write(("MOVE_TYPE", SimulatedPLC.MOVE_RESET))
    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_READY)
    self.assertEqual(plc.get_tag("ERROR_CODE"), 0)

    plc.write(("Z_POSITION", 1000.0))
    plc.write(("MOVE_TYPE", SimulatedPLC.MOVE_SEEK_Z))
    self._settle_once(plc)
    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_ERROR)
    self.assertEqual(plc.get_tag("ERROR_CODE"), 5003)

  def test_xz_move_type_updates_x_and_z_when_y_transfer_ok(self):
    plc = SimulatedPLC()
    plc.write(("xz_position_target", [321.0, 210.5]))
    plc.write(("MOVE_TYPE", SimulatedPLC.MOVE_SEEK_XZ))

    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_XZ_SEEK)
    self._settle_once(plc)

    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_READY)
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 321.0, places=6)
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 210.5, places=6)

  def test_xz_move_type_sets_error_when_y_transfer_not_ok(self):
    plc = SimulatedPLC()
    plc.set_tag("MACHINE_SW_STAT[17]", 0, override=True)
    plc.write(("xz_position_target", [321.0, 210.5]))
    plc.write(("MOVE_TYPE", SimulatedPLC.MOVE_SEEK_XZ))

    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_ERROR)
    self.assertEqual(plc.get_tag("ERROR_CODE"), 5003)
    self.assertAlmostEqual(plc.get_tag("X_axis.ActualPosition"), 0.0, places=6)
    self.assertAlmostEqual(plc.get_tag("Z_axis.ActualPosition"), 0.0, places=6)

  def test_derived_machine_bits_support_override_precedence(self):
    plc = SimulatedPLC()
    plc.set_tag("HEAD_POS", 3)

    self.assertEqual(plc.get_tag("MACHINE_SW_STAT[7]"), 1)
    self.assertEqual(plc.get_tag("MACHINE_SW_STAT[6]"), 0)

    plc.set_tag("MACHINE_SW_STAT[7]", 0, override=True)
    self.assertEqual(plc.get_tag("MACHINE_SW_STAT[7]"), 0)

    plc.clear_override("MACHINE_SW_STAT[7]")
    self.assertEqual(plc.get_tag("MACHINE_SW_STAT[7]"), 1)

  def test_camera_fifo_stays_empty_without_explicit_writes(self):
    plc = SimulatedPLC()

    self.assertEqual(plc.get_tag("FIFO_Data[2]"), 0.0)
    self._settle_once(plc)
    self.assertEqual(plc.get_tag("FIFO_Data[2]"), 0.0)
    plc.set_tag("FIFO_Data[2]", 1.0)
    self.assertEqual(plc.get_tag("FIFO_Data[2]"), 1.0)

  def test_queue_stop_request_aborts_queue_and_stays_latched_until_cleared(self):
    plc = SimulatedPLC()
    plc.write(("IncomingSeg", {"Valid": True, "Seq": 101, "XY": [10.0, 20.0]}))
    plc.write(("IncomingSegReqID", 1))
    plc.write(("StartQueuedPath", 1))

    self.assertEqual(plc.get_tag("QueueCount"), 1)
    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_QUEUED_MOTION)

    plc.write(("QueueStopRequest", 1))

    self.assertEqual(plc.get_tag("QueueStopRequest"), 1)
    self.assertEqual(plc.get_tag("QueueCount"), 0)
    self.assertEqual(plc.get_tag("CurIssued"), 0)
    self.assertEqual(plc.get_tag("NextIssued"), 0)
    self.assertEqual(plc.get_tag("STATE"), SimulatedPLC.STATE_READY)


if __name__ == "__main__":
  unittest.main()
