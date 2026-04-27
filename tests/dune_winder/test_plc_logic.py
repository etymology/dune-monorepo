import unittest

from dune_winder.io.controllers.plc_logic import PLC_Logic
from dune_winder.io.devices.plc import PLC
from dune_winder.io.primitives.multi_axis_motor import MultiAxisMotor
from dune_winder.io.primitives.plc_motor import PLC_Motor


class _FreshReadPLC(PLC):
    def __init__(self):
        self.read_calls = []
        self.write_calls = []
        self._functional = True
        self.read_values = {}

    def initialize(self):
        return True

    def isNotFunctional(self):
        return not self._functional

    def read(self, tag):
        self.read_calls.append(tag)
        if isinstance(tag, str):
            return None
        return [
            [str(tagName), self.read_values.get(str(tagName), 1)] for tagName in tag
        ]

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
                ("STATE_REQUEST", PLC_Logic.States.XZ_SEEK),
            ],
        )

    def test_z_seek_requests_state_after_updating_target(self):
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
                ("STATE_REQUEST", PLC_Logic.States.Z_SEEK),
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

    def test_move_latch_requests_state_when_both_present_bits_are_true(self):
        plc = _FreshReadPLC()
        logic = PLC_Logic(plc, object(), object())

        sent = logic.move_latch()

        self.assertTrue(sent)
        self.assertEqual(plc.read_calls, [["ENABLE_ACTUATOR"]])
        self.assertEqual(
            plc.write_calls, [("STATE_REQUEST", PLC_Logic.States.LATCHING)]
        )

    def test_move_latch_skips_pulse_when_present_interlock_is_false(self):
        plc = _FreshReadPLC()
        plc.read_values["ENABLE_ACTUATOR"] = 0
        logic = PLC_Logic(plc, object(), object())

        sent = logic.move_latch()

        self.assertFalse(sent)
        self.assertEqual(plc.read_calls, [["ENABLE_ACTUATOR"]])
        self.assertEqual(plc.write_calls, [])

    def test_get_transfer_state_now_reads_live_snapshot(self):
        plc = _FreshReadPLC()
        plc.read_values.update(
            {
                "MACHINE_SW_STAT[9]": 1,
                "MACHINE_SW_STAT[10]": 1,
                "MACHINE_SW_STAT[6]": 1,
                "MACHINE_SW_STAT[7]": 0,
                "MACHINE_SW_STAT[5]": 1,
                "ENABLE_ACTUATOR": 1,
                "ACTUATOR_POS": 1,
                "Z_axis.ActualPosition": 418.0,
            }
        )
        zAxis = PLC_Motor("zAxis", plc, "Z")
        logic = PLC_Logic(plc, object(), zAxis)

        state = logic.getTransferStateNow()

        self.assertEqual(
            plc.read_calls,
            [
                [
                    "MACHINE_SW_STAT[9]",
                    "MACHINE_SW_STAT[10]",
                    "MACHINE_SW_STAT[6]",
                    "MACHINE_SW_STAT[7]",
                    "MACHINE_SW_STAT[5]",
                    "ENABLE_ACTUATOR",
                    "ACTUATOR_POS",
                    "Z_axis.ActualPosition",
                ]
            ],
        )
        self.assertTrue(state["stagePresent"])
        self.assertTrue(state["fixedPresent"])
        self.assertTrue(state["stageLatched"])
        self.assertFalse(state["fixedLatched"])
        self.assertTrue(state["zExtended"])
        self.assertTrue(state["enableActuator"])
        self.assertEqual(state["actuatorPos"], 1)
        self.assertEqual(state["zPosition"], 418.0)

    def test_stop_seek_requests_hmi_stop_state(self):
        plc = _FreshReadPLC()
        logic = PLC_Logic(plc, object(), object())

        logic.stopSeek()

        self.assertEqual(
            plc.write_calls, [("STATE_REQUEST", PLC_Logic.States.HMI_STOP)]
        )

    def test_reset_clears_error_code_and_state_request(self):
        plc = _FreshReadPLC()
        logic = PLC_Logic(plc, object(), object())

        logic.reset()

        self.assertEqual(
            plc.write_calls,
            [
                ("ERROR_CODE", 0),
                ("STATE_REQUEST", 0),
            ],
        )

    def test_xy_seek_requests_state_request(self):
        plc = _FreshReadPLC()
        xAxis = PLC_Motor("xAxis", plc, "X")
        yAxis = PLC_Motor("yAxis", plc, "Y")
        logic = PLC_Logic(plc, MultiAxisMotor("xyAxis", [xAxis, yAxis]), object())

        logic.setXY_Position(
            10.0, 20.0, velocity=150.0, acceleration=2.0, deceleration=3.0
        )

        self.assertEqual(
            plc.write_calls,
            [
                ("XY_ACCELERATION", 2.0),
                ("XY_DECELERATION", 3.0),
                ("XY_SPEED", 150.0),
                ("X_POSITION", 10.0),
                ("Y_POSITION", 20.0),
                ("STATE_REQUEST", PLC_Logic.States.XY_SEEK),
            ],
        )

    def test_servo_disable_requests_state_request(self):
        plc = _FreshReadPLC()
        logic = PLC_Logic(plc, object(), object())

        logic.servoDisable()

        self.assertEqual(plc.write_calls, [("STATE_REQUEST", PLC_Logic.States.UNSERVO)])

    def test_eot_recover_requests_state_request(self):
        plc = _FreshReadPLC()
        logic = PLC_Logic(plc, object(), object())

        logic.recoverEOT()

        self.assertEqual(plc.write_calls, [("STATE_REQUEST", PLC_Logic.States.EOT)])

    def test_latch_home_is_not_supported_by_checked_in_plc_contract(self):
        plc = _FreshReadPLC()
        logic = PLC_Logic(plc, object(), object())

        with self.assertRaisesRegex(NotImplementedError, "not supported"):
            logic.latchHome()

    def test_latch_unlock_is_not_supported_by_checked_in_plc_contract(self):
        plc = _FreshReadPLC()
        logic = PLC_Logic(plc, object(), object())

        with self.assertRaisesRegex(NotImplementedError, "not supported"):
            logic.latchUnlock()


if __name__ == "__main__":
    unittest.main()
