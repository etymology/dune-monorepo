from pathlib import Path
import unittest

from dune_winder.plc_ladder import PythonCodeGenerator
from dune_winder.plc_ladder import RllEmitter
from dune_winder.plc_ladder import RllParser
from dune_winder.plc_ladder import StructuredPythonCodeGenerator
from dune_winder.plc_ladder import load_generated_routine


PLC_ROOT = Path(__file__).resolve().parents[1] / "plc"


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

    self.assertIn("def MoveXY_State_2_3_main(ctx):", generated)
    self.assertIn("formula('STATE=2')", generated)
    self.assertIn("if not tag('main_xy_move.IP'):", generated)
    self.assertIn("MCLM(", generated)
    self.assertIn("__ladder_routine__ = ROUTINE(", generated)
    compile(generated, str(path), "exec")

    restored = load_generated_routine(generated)
    self.assertEqual(
      self.emitter.emit_routine(restored).strip().splitlines(),
      self.emitter.emit_routine(routine).strip().splitlines(),
    )

  def test_imperative_codegen_rejects_jump_label_routines(self):
    path = PLC_ROOT / "motionQueue" / "ArcSweepRad" / "pasteable.rll"
    routine = self.parser.parse_routine_path(
      path,
      routine_name=path.parent.name,
      program="motionQueue",
    )

    with self.assertRaises(NotImplementedError):
      self.codegen.generate_routine(routine)

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

    self.assertIn("if tag('trigger_z_move'):", generated)
    self.assertIn("MAM(", generated)
    compile(generated, str(path), "exec")


if __name__ == "__main__":
  unittest.main()
