from pathlib import Path
import re
import unittest

from dune_winder.plc_ladder import PythonCodeGenerator
from dune_winder.plc_ladder import RllEmitter
from dune_winder.plc_ladder import RllParser
from dune_winder.plc_ladder import StructuredPythonCodeGenerator
from dune_winder.plc_ladder import load_generated_routine


PLC_ROOT = Path(__file__).resolve().parents[2] / "dune_winder" / "plc"


class PlcLadderParserTests(unittest.TestCase):
  def setUp(self):
    self.parser = RllParser()
    self.emitter = RllEmitter()
    self.codegen = PythonCodeGenerator()
    self.structured_codegen = StructuredPythonCodeGenerator()

  def test_round_trips_movez_main_routine(self):
    path = PLC_ROOT / "MoveZ_State_4_5" / "main" / "pasteable.rll"
    source = path.read_text(encoding="utf-8")

    routine = self.parser.parse_routine_text(
      "main",
      source,
      program="MoveZ_State_4_5",
      source_path=path,
    )
    emitted = self.emitter.emit_routine(routine)

    self.assertEqual(emitted.strip().splitlines(), source.strip().splitlines())

  def test_parses_quoted_cmp_formula_as_unquoted_ast_operand(self):
    routine = self.parser.parse_routine_text(
      "main",
      'CMP "Z_axis.ActualPosition>415" OTE MACHINE_SW_STAT[5] \n',
      program="MainProgram",
    )

    rung = routine.rungs[0]
    self.assertEqual(rung.nodes[0].opcode, "CMP")
    self.assertEqual(rung.nodes[0].operands, ("Z_axis.ActualPosition>415",))
    self.assertEqual(
      self.emitter.emit_routine(routine),
      'CMP "Z_axis.ActualPosition>415" OTE MACHINE_SW_STAT[5] \n',
    )

  def test_parses_all_targeted_acceptance_routines(self):
    routine_paths = [
      PLC_ROOT / "MainProgram" / "main" / "pasteable.rll",
      PLC_ROOT / "Ready_State_1" / "main" / "pasteable.rll",
      PLC_ROOT / "MoveXY_State_2_3" / "main" / "pasteable.rll",
      PLC_ROOT / "MoveXY_State_2_3" / "xy_speed_regulator" / "pasteable.rll",
      PLC_ROOT / "MoveZ_State_4_5" / "main" / "pasteable.rll",
      PLC_ROOT / "xz_move" / "main" / "pasteable.rll",
      PLC_ROOT / "Error_State_10" / "main" / "pasteable.rll",
      PLC_ROOT / "Initialize" / "main" / "pasteable.rll",
      PLC_ROOT / "motionQueue" / "main" / "pasteable.rll",
    ]

    for path in routine_paths:
      with self.subTest(path=path):
        routine = self.parser.parse_routine_path(path, routine_name=path.parent.name)
        self.assertGreater(len(routine.rungs), 0)

  def test_parses_all_checked_in_pasteable_routines(self):
    for path in sorted(PLC_ROOT.rglob("pasteable.rll")):
      with self.subTest(path=path):
        routine = self.parser.parse_routine_path(path, routine_name=path.parent.name)
        source = path.read_text(encoding="utf-8").strip()
        if source:
          self.assertGreater(len(routine.rungs), 0)
        else:
          self.assertEqual(len(routine.rungs), 0)

  def test_generates_python_with_rockwell_mnemonics(self):
    path = PLC_ROOT / "MoveXY_State_2_3" / "main" / "pasteable.rll"
    routine = self.parser.parse_routine_text(
      "main",
      path.read_text(encoding="utf-8"),
      program="MoveXY_State_2_3",
      source_path=path,
    )

    generated = self.codegen.generate_routine(routine)

    self.assertIn("def MoveXY_State_2_3_main(ctx: ScanContext) -> None:", generated)
    self.assertIn("api: BoundRoutineAPI = bind_scan_context(ctx)", generated)
    self.assertIn("STATE: IntTag = api.ref('STATE')", generated)
    self.assertIn("X_Y: CoordinateSystemTag = api.ref('X_Y')", generated)
    self.assertIn("X_axis: AxisTag = api.ref('X_axis')", generated)
    self.assertIn("main_xy_move: MotionControlTag = api.ref('main_xy_move')", generated)
    self.assertIn("MCLM: MCLMCallable = api.MCLM", generated)
    self.assertIn("if STATE==2:", generated)
    self.assertIn("if (not XY_AXIS_STAT[4].IP) and (STATE==3)", generated)
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
    path = PLC_ROOT / "motionQueue" / "ArcSweepRad" / "pasteable.rll"
    routine = self.parser.parse_routine_path(
      path,
      routine_name=path.parent.name,
      program="motionQueue",
    )

    generated = self.codegen.generate_routine(routine)

    self.assertIn("while _pc <", generated)
    self.assertRegex(generated, re.compile(r"_pc = \d+"))
    compile(generated, str(path), "exec")

  def test_imperative_codegen_reuses_boolean_branch_temps_for_ote(self):
    routine = self.parser.parse_routine_text(
      "main",
      'BST XIC Local:1:I.Pt04.Data NXB CMP "Z_axis.ActualPosition>415" BND OTE MACHINE_SW_STAT[5] OTE Z_EXTENDED\n',
      program="MainProgram",
    )

    generated = self.codegen.generate_routine(routine)

    self.assertRegex(generated, re.compile(r"MACHINE_SW_STAT\[5\]\.set\(_branch_\d+\)"))
    self.assertRegex(generated, re.compile(r"Z_EXTENDED\.set\(_branch_\d+\)"))
    self.assertNotRegex(generated, re.compile(r"\.set\(bool\(_branch_\d+\)\)"))
    compile(generated, "<branch_ote>", "exec")

  def test_imperative_codegen_sanitizes_invalid_root_names(self):
    path = PLC_ROOT / "MainProgram" / "main" / "pasteable.rll"
    routine = self.parser.parse_routine_path(
      path,
      routine_name="main",
      program="MainProgram",
    )

    generated = self.codegen.generate_routine(routine)

    self.assertIn("Local_1_I: TagRef = api.ref('Local:1:I')", generated)
    self.assertIn("DUNEW2PLC2_1_I: TagRef = api.ref('DUNEW2PLC2:1:I')", generated)
    self.assertIn("Local_1_I.Pt00.Data", generated)
    self.assertIn("DUNEW2PLC2_1_I.Pt00Data", generated)
    compile(generated, str(path), "exec")

  def test_round_trips_motion_queue_helpers_through_structured_python(self):
    helper_paths = [
      PLC_ROOT / "motionQueue" / "ArcSweepRad" / "pasteable.rll",
      PLC_ROOT / "motionQueue" / "CapSegSpeed" / "pasteable.rll",
      PLC_ROOT / "motionQueue" / "CircleCenterForSeg" / "pasteable.rll",
      PLC_ROOT / "motionQueue" / "MaxAbsCosSweep" / "pasteable.rll",
      PLC_ROOT / "motionQueue" / "MaxAbsSinSweep" / "pasteable.rll",
      PLC_ROOT / "motionQueue" / "SegTangentBounds" / "pasteable.rll",
    ]

    for path in helper_paths:
      with self.subTest(path=path):
        routine = self.parser.parse_routine_path(
          path,
          routine_name=path.parent.name,
          program="motionQueue",
        )
        generated = self.structured_codegen.generate_routine(routine)
        restored = load_generated_routine(generated)

        self.assertEqual(restored.name, routine.name)
        self.assertEqual(restored.program, routine.program)
        self.assertEqual(
          self.emitter.emit_routine(restored).strip().splitlines(),
          self.emitter.emit_routine(routine).strip().splitlines(),
        )

  def test_imperative_codegen_compiles_for_movez_main(self):
    path = PLC_ROOT / "MoveZ_State_4_5" / "main" / "pasteable.rll"
    routine = self.parser.parse_routine_path(
      path,
      routine_name="main",
      program="MoveZ_State_4_5",
    )

    generated = self.codegen.generate_routine(routine)

    self.assertIn("def MoveZ_State_4_5_main(ctx: ScanContext) -> None:", generated)
    self.assertIn("MAM(", generated)
    self.assertIn("motion_control=z_axis_main_move", generated)
    compile(generated, str(path), "exec")


if __name__ == "__main__":
  unittest.main()
