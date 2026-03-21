from pathlib import Path
import unittest

from dune_winder.plc_ladder import PythonCodeGenerator
from dune_winder.plc_ladder import RllEmitter
from dune_winder.plc_ladder import RllParser


PLC_ROOT = Path(__file__).resolve().parents[1] / "plc"


class PlcLadderParserTests(unittest.TestCase):
  def setUp(self):
    self.parser = RllParser()
    self.emitter = RllEmitter()
    self.codegen = PythonCodeGenerator()

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

  def test_generates_python_with_rockwell_mnemonics(self):
    path = PLC_ROOT / "MoveXY_State_2_3" / "main" / "pasteable.rll"
    routine = self.parser.parse_routine_text(
      "main",
      path.read_text(encoding="utf-8"),
      program="MoveXY_State_2_3",
      source_path=path,
    )

    generated = self.codegen.generate_routine(routine)

    self.assertIn("def MoveXY_State_2_3_main", generated)
    self.assertIn("MCLM(", generated)
    self.assertIn("BRANCH(", generated)


if __name__ == "__main__":
  unittest.main()
