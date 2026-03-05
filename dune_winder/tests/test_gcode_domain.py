import unittest

from dune_winder.gcode.model import OPCODE_CATALOG, FunctionCall, Opcode
from dune_winder.gcode.parser import GCodeParseError, parse_line_text
from dune_winder.gcode.renderer import render_line
from dune_winder.gcode.runtime import (
  GCodeCallbacks,
  GCodeExecutionError,
  GCodeProgramExecutor,
  execute_program_line,
)
from dune_winder.recipes.gcode_functions import pin_center


class GCodeParserTests(unittest.TestCase):
  def test_p_parameters_bind_to_previous_word(self):
    line = parse_line_text("G103 PF800 PF799 PXY")
    function = line.items[0]

    self.assertIsInstance(function, FunctionCall)
    self.assertEqual(function.opcode, "103")
    self.assertEqual(function.parameters, ["F800", "F799", "XY"])

  def test_parse_rejects_unassigned_parameter(self):
    with self.assertRaises(GCodeParseError) as context:
      parse_line_text("PF100")

    self.assertEqual(str(context.exception), "Unassigned parameter F100")

  def test_parse_rejects_unknown_code(self):
    with self.assertRaises(GCodeParseError) as context:
      parse_line_text("Q2")

    self.assertEqual(str(context.exception), "Unknown parameter Q")

  def test_comments_are_preserved_and_rendered_normalized(self):
    line = parse_line_text("  N1   X1   ( hello )   Y2  ")
    self.assertEqual(render_line(line), "N1 X1 ( hello ) Y2")


class GCodeRuntimeTests(unittest.TestCase):
  def test_runtime_callback_order_and_payload_match_legacy_shapes(self):
    seen = []
    callbacks = {
      "X": lambda value: seen.append(("X", value)),
      "Y": lambda value: seen.append(("Y", value)),
      "F": lambda value: seen.append(("F", value)),
      "G": lambda value: seen.append(("G", value)),
      "N": lambda value: seen.append(("N", value)),
    }

    line = parse_line_text("X10 Y11 F120 G103 PF1 PF2 PXY N7")
    execute_program_line(line, callbacks.get)

    self.assertEqual(
      seen,
      [
        ("X", 10.0),
        ("Y", 11.0),
        ("F", 120.0),
        ("G", ["103", "F1", "F2", "XY"]),
        ("N", 7),
      ],
    )


class GCodeDomainTests(unittest.TestCase):
  def test_opcode_catalog_covers_all_runtime_opcodes(self):
    expected = set(range(100, 113))
    self.assertEqual(set(OPCODE_CATALOG.keys()), expected)
    self.assertEqual(int(Opcode.LATCH), 100)
    self.assertEqual(int(Opcode.TENSION_TESTING), 112)

  def test_recipe_function_helpers_build_canonical_calls(self):
    function = pin_center(["F1", "F2"], "XY")

    self.assertIsInstance(function, FunctionCall)
    self.assertEqual(function.opcode, int(Opcode.PIN_CENTER))
    self.assertEqual(function.parameters, ["F1", "F2", "XY"])

  def test_program_executor_executes_with_canonical_runtime(self):
    seen = []
    callbacks = GCodeCallbacks()
    callbacks.registerCallback("G", lambda parameter: seen.append(parameter))
    gCode = GCodeProgramExecutor([], callbacks)

    gCode.execute("G105 PX-10")

    self.assertEqual(seen, [[str(int(Opcode.OFFSET)), "X-10"]])

  def test_program_executor_maps_parse_errors_to_execution_errors(self):
    callbacks = GCodeCallbacks()
    gCode = GCodeProgramExecutor([], callbacks)

    with self.assertRaises(GCodeExecutionError) as context:
      gCode.execute("PF100")

    self.assertEqual(str(context.exception), "Unassigned parameter F100")
    self.assertEqual(context.exception.data, ["PF100", "P", "F100"])


if __name__ == "__main__":
  unittest.main()
