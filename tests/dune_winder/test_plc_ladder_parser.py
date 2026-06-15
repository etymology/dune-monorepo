from pathlib import Path
import re
import unittest
from typing import cast

from dune_winder.plc_ladder import PythonCodeGenerator
from dune_winder.plc_ladder import RllEmitter
from dune_winder.plc_ladder import RllParser
from dune_winder.plc_ladder import StructuredPythonCodeGenerator
from dune_winder.plc_ladder import load_generated_routine
from dune_winder.plc_ladder.ast import InstructionCall

from _plc_paste_support import PLC_ROOT, iter_paste_routine_dirs, paste_text


class PlcLadderParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = RllParser()
        self.emitter = RllEmitter()
        self.codegen = PythonCodeGenerator()
        self.structured_codegen = StructuredPythonCodeGenerator()

    def _parse_tree_routine(self, program: str, routine_dir: str, routine_name=None):
        return self.parser.parse_routine_text(
            routine_name or routine_dir,
            paste_text(program, routine_dir),
            program=program,
        )

    def test_round_trips_movez_main_routine(self):
        source = paste_text("state_5_move_z", "main")

        routine = self.parser.parse_routine_text(
            "main",
            source,
            program="state_5_move_z",
        )
        emitted = self.emitter.emit_routine(routine)

        self.assertEqual(emitted.strip().splitlines(), source.strip().splitlines())

    def test_parses_quoted_cmp_formula_as_unquoted_ast_operand(self):
        routine = self.parser.parse_routine_text(
            "main",
            'CMP "Z_axis.ActualPosition>415" OTE MACHINE_SW_STAT[5] \n',
            program="main",
        )

        rung = routine.rungs[0]
        node = cast(InstructionCall, rung.nodes[0])
        self.assertEqual(node.opcode, "CMP")
        self.assertEqual(node.operands, ("Z_axis.ActualPosition>415",))
        self.assertEqual(
            self.emitter.emit_routine(routine),
            'CMP "Z_axis.ActualPosition>415" OTE MACHINE_SW_STAT[5] \n',
        )

    def test_parses_all_targeted_acceptance_routines(self):
        routines = [
            ("main", "main"),
            ("state_1_ready", "main"),
            ("state_3_move_xy", "main"),
            ("state_3_move_xy", "xy_speed_regulator"),
            ("state_5_move_z", "main"),
            ("state_12_move_xz", "main"),
            ("state_10_error", "main"),
            ("queued_motion", "main"),
        ]

        for program, routine_dir in routines:
            with self.subTest(routine=f"{program}/{routine_dir}"):
                routine = self._parse_tree_routine(program, routine_dir)
                self.assertGreater(len(routine.rungs), 0)

    def test_parses_all_checked_in_routines(self):
        for routine_dir in iter_paste_routine_dirs():
            program = routine_dir.parent.name
            with self.subTest(routine=f"{program}/{routine_dir.name}"):
                source = paste_text(program, routine_dir.name)
                routine = self.parser.parse_routine_text(
                    routine_dir.name, source, program=program
                )
                if source.strip():
                    self.assertGreater(len(routine.rungs), 0)
                else:
                    self.assertEqual(len(routine.rungs), 0)

    def test_generates_python_with_rockwell_mnemonics(self):
        path = PLC_ROOT / "state_3_move_xy" / "main_Routine_RLL.L5X"
        routine = self._parse_tree_routine("state_3_move_xy", "main")

        generated = self.codegen.generate_routine(routine)

        self.assertIn("def state_3_move_xy_main(ctx: ScanContext) -> None:", generated)
        self.assertIn("api: BoundRoutineAPI = bind_scan_context(ctx)", generated)
        self.assertIn("STATE: IntTag = api.ref('STATE')", generated)
        self.assertIn("X_Y: CoordinateSystemTag = api.ref('X_Y')", generated)
        self.assertIn("X_axis: AxisTag = api.ref('X_axis')", generated)
        self.assertIn(
            "main_xy_move: MotionControlTag = api.ref('main_xy_move')", generated
        )
        self.assertIn("MCLM: MCLMCallable = api.MCLM", generated)
        self.assertIn("if STATE==2:", generated)
        # Rungs 0 and 1 are separate in the ACD-extracted ladder (the old
        # hand-copied rllscrap had accidentally merged them into one rung).
        self.assertIn(
            "if (not main_xy_move.IP) and (STATE==3)", generated
        )
        self.assertIn("MCLM(", generated)
        self.assertIn("motion_control=main_xy_move", generated)
        self.assertIn("speed_units='Units per sec'", generated)
        self.assertIn("accel_units='Units per sec2'", generated)
        self.assertIn("decel_units='Units per sec2'", generated)
        self.assertIn("jerk_units='Units per sec3'", generated)
        self.assertIn("profile='S-Curve'", generated)
        self.assertIn("merge='Disabled'", generated)
        self.assertIn("termination_type=0", generated)
        self.assertIn("lock_position=0", generated)
        self.assertIn("lock_direction='None'", generated)
        self.assertIn("event_distance=0", generated)
        self.assertIn("calculated_data=0", generated)
        self.assertIn("__ladder_routine__ = ROUTINE(", generated)
        self.assertNotIn("tag('", generated)
        self.assertNotIn("formula(", generated)
        compile(generated, str(path), "exec")

        restored = load_generated_routine(generated)
        self.assertEqual(
            self.emitter.emit_routine(restored).strip().splitlines(),
            self.emitter.emit_routine(routine).strip().splitlines(),
        )

    def test_imperative_codegen_compiles_jump_label_routines(self):
        routine = self._parse_tree_routine("queued_motion", "ArcSweepRad")

        generated = self.codegen.generate_routine(routine)

        self.assertIn("while _pc <", generated)
        self.assertRegex(generated, re.compile(r"_pc = \d+"))
        compile(generated, "<ArcSweepRad>", "exec")

    def test_imperative_codegen_reuses_boolean_branch_temps_for_ote(self):
        routine = self.parser.parse_routine_text(
            "main",
            'BST XIC Local:1:I.Pt04.Data NXB CMP "Z_axis.ActualPosition>415" BND OTE MACHINE_SW_STAT[5] OTE Z_EXTENDED\n',
            program="main",
        )

        generated = self.codegen.generate_routine(routine)

        self.assertRegex(
            generated, re.compile(r"MACHINE_SW_STAT\[5\]\.set\(_branch_\d+\)")
        )
        self.assertRegex(generated, re.compile(r"Z_EXTENDED\.set\(_branch_\d+\)"))
        self.assertNotRegex(generated, re.compile(r"\.set\(bool\(_branch_\d+\)\)"))
        compile(generated, "<branch_ote>", "exec")

    def test_imperative_codegen_sanitizes_invalid_root_names(self):
        path = PLC_ROOT / "main" / "main_Routine_RLL.L5X"
        routine = self._parse_tree_routine("main", "main")

        generated = self.codegen.generate_routine(routine)

        self.assertIn("Local_1_I: TagRef = api.ref('Local:1:I')", generated)
        self.assertIn("DUNEW2PLC2_1_I: TagRef = api.ref('DUNEW2PLC2:1:I')", generated)
        self.assertIn("Local_1_I.Pt00.Data", generated)
        self.assertIn("DUNEW2PLC2_1_I.Pt00Data", generated)
        compile(generated, str(path), "exec")

    def test_round_trips_motion_queue_helpers_through_structured_python(self):
        helpers = [
            "ArcSweepRad",
            "CapSegSpeed",
            "CircleCenterForSeg",
            "MaxAbsCosSweep",
            "MaxAbsSinSweep",
            "SegTangentBounds",
        ]

        for helper in helpers:
            with self.subTest(routine=f"queued_motion/{helper}"):
                routine = self._parse_tree_routine("queued_motion", helper)
                generated = self.structured_codegen.generate_routine(routine)
                restored = load_generated_routine(generated)

                self.assertEqual(restored.name, routine.name)
                self.assertEqual(restored.program, routine.program)
                self.assertEqual(
                    self.emitter.emit_routine(restored).strip().splitlines(),
                    self.emitter.emit_routine(routine).strip().splitlines(),
                )

    def test_imperative_codegen_compiles_for_movez_main(self):
        routine = self._parse_tree_routine("state_5_move_z", "main", "main")

        generated = self.codegen.generate_routine(routine)

        self.assertIn("def state_5_move_z_main(ctx: ScanContext) -> None:", generated)
        self.assertIn("MAM(", generated)
        self.assertIn("motion_control=z_axis_main_move", generated)
        compile(generated, "<state_5_move_z_main>", "exec")


if __name__ == "__main__":
    unittest.main()
