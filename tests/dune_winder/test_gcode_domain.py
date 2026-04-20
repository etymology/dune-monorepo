import unittest

from dune_winder.gcode.model import MacroCall, OPCODE_CATALOG, FunctionCall, Opcode
from dune_winder.gcode.parser import GCodeParseError, parse_line_text
from dune_winder.gcode.renderer import render_line
from dune_winder.gcode.runtime import (
  GCodeCallbacks,
  GCodeExecutionError,
  GCodeProgramExecutor,
  execute_program_line,
)
from dune_winder.recipes.gcode_functions import (
  head_transfer,
  pin_center,
  wrap_anchor,
  wrap_b,
  wrap_b_to_a,
  wrap_goto,
  wrap_increment,
)


class GCodeParserTests(unittest.TestCase):
  def test_p_parameters_bind_to_previous_word(self):
    line = parse_line_text("G103 PA800 PA799 PXY")
    function = line.items[0]

    self.assertIsInstance(function, FunctionCall)
    self.assertEqual(function.opcode, "103")
    self.assertEqual(function.parameters, ["A800", "A799", "XY"])

  def test_parse_rejects_unassigned_parameter(self):
    with self.assertRaises(GCodeParseError) as context:
      parse_line_text("PA100")

    self.assertEqual(str(context.exception), "Unassigned parameter A100")

  def test_parse_rejects_unknown_code(self):
    with self.assertRaises(GCodeParseError) as context:
      parse_line_text("Q2")

    self.assertEqual(str(context.exception), "Unknown parameter Q")

  def test_comments_are_preserved_and_rendered_normalized(self):
    line = parse_line_text("  N1   X1   ( hello )   Y2  ")
    self.assertEqual(render_line(line), "N1 X1 ( hello ) Y2")

  def test_parser_supports_symbolic_z_extend_with_pxz_recipe_order(self):
    line = parse_line_text("G103 PA800 PA799 ZEXTEND PXZ")

    self.assertEqual(render_line(line), "G103 PA800 PA799 PXZ ZEXTEND")
    self.assertIsInstance(line.items[0], FunctionCall)
    self.assertEqual(line.items[0].parameters, ["A800", "A799", "XZ"])
    self.assertEqual(line.items[1].letter, "Z")
    self.assertEqual(line.items[1].value, "EXTEND")

  def test_parser_and_renderer_support_tilde_macro_lines(self):
    line = parse_line_text("N7 ~anchorToTarget(B1201,B2001) ( top )")

    self.assertEqual(render_line(line), "N7 ~anchorToTarget(B1201,B2001) ( top )")
    self.assertIsInstance(line.items[1], MacroCall)
    self.assertEqual(line.items[1].text, "anchorToTarget(B1201,B2001)")


class GCodeRuntimeTests(unittest.TestCase):
  def test_runtime_delivers_one_callback_per_instruction(self):
    seen = []
    callbacks = {"on_instruction": lambda line: seen.append(line)}

    line = parse_line_text("X10 Y11 F120 G103 PA1 PA2 PXY N7 ( note )")
    execute_program_line(line, callbacks.get)

    self.assertEqual(seen, [line])


class GCodeDomainTests(unittest.TestCase):
  def test_opcode_catalog_covers_all_runtime_opcodes(self):
    expected = set(range(100, 119))
    expected.add(206)
    self.assertEqual(set(OPCODE_CATALOG.keys()), expected)
    self.assertEqual(int(Opcode.LATCH), 100)
    self.assertEqual(int(Opcode.TENSION_TESTING), 112)
    self.assertEqual(int(Opcode.QUEUE_MERGE), 113)
    self.assertEqual(int(Opcode.WRAP_GOTO), 114)
    self.assertEqual(int(Opcode.WRAP_INCREMENT), 115)
    self.assertEqual(int(Opcode.WRAP_ANCHOR), 116)
    self.assertEqual(int(Opcode.WRAP_B), 117)
    self.assertEqual(int(Opcode.WRAP_B_TO_A), 118)
    self.assertEqual(int(Opcode.HEAD_TRANSFER), 206)

  def test_recipe_function_helpers_build_canonical_calls(self):
    function = pin_center(["A1", "A2"], "XY")

    self.assertIsInstance(function, FunctionCall)
    self.assertEqual(function.opcode, int(Opcode.PIN_CENTER))
    self.assertEqual(function.parameters, ["A1", "A2", "XY"])

    transfer = head_transfer(3)
    self.assertIsInstance(transfer, FunctionCall)
    self.assertEqual(transfer.opcode, int(Opcode.HEAD_TRANSFER))
    self.assertEqual(transfer.parameters, [3])

    goto_xy = wrap_goto(x=7174, y=0)
    self.assertEqual(goto_xy.opcode, int(Opcode.WRAP_GOTO))
    self.assertEqual(goto_xy.parameters, ["X7174", "Y0"])

    increment_xy = wrap_increment(x=-70, y=50)
    self.assertEqual(increment_xy.opcode, int(Opcode.WRAP_INCREMENT))
    self.assertEqual(increment_xy.parameters, ["X-70", "Y50"])

    anchor = wrap_anchor("PA1601")
    self.assertEqual(anchor.opcode, int(Opcode.WRAP_ANCHOR))
    self.assertEqual(anchor.parameters, ["PA1601"])

    wrap_b_pin = wrap_b("PB2001")
    self.assertEqual(wrap_b_pin.opcode, int(Opcode.WRAP_B))
    self.assertEqual(wrap_b_pin.parameters, ["PB2001"])

    wrap_b_to_a_pin = wrap_b_to_a("PB2001")
    self.assertEqual(wrap_b_to_a_pin.opcode, int(Opcode.WRAP_B_TO_A))
    self.assertEqual(wrap_b_to_a_pin.parameters, ["PB2001"])

  def test_parser_and_renderer_support_g206_transfer(self):
    line = parse_line_text("G206 P3")

    self.assertEqual(render_line(line), "G206 P3")
    self.assertIsInstance(line.items[0], FunctionCall)
    self.assertEqual(line.items[0].opcode, "206")
    self.assertEqual(line.items[0].parameters, ["3"])

  def test_parser_still_supports_legacy_g106(self):
    line = parse_line_text("G106 P0")

    self.assertEqual(render_line(line), "G106 P0")

  def test_parser_and_renderer_support_wrap_commands(self):
    line = parse_line_text("G114 PX7174 PY0")
    self.assertEqual(render_line(line), "G114 PX7174 PY0")
    self.assertEqual(line.items[0].parameters, ["X7174", "Y0"])

    line = parse_line_text("G118 PB2001")
    self.assertEqual(render_line(line), "G118 PB2001")
    self.assertEqual(line.items[0].parameters, ["B2001"])

  def test_program_executor_executes_with_canonical_runtime(self):
    seen = []
    callbacks = GCodeCallbacks()
    callbacks.registerCallback("on_instruction", lambda line: seen.append(line))
    gCode = GCodeProgramExecutor([], callbacks)

    gCode.execute("G105 PX-10")

    self.assertEqual(len(seen), 1)
    self.assertIsInstance(seen[0].items[0], FunctionCall)
    self.assertEqual(seen[0].items[0].as_legacy_parameter_list(), [str(int(Opcode.OFFSET)), "X-10"])

  def test_program_executor_maps_parse_errors_to_execution_errors(self):
    callbacks = GCodeCallbacks()
    gCode = GCodeProgramExecutor([], callbacks)

    with self.assertRaises(GCodeExecutionError) as context:
      gCode.execute("PA100")

    self.assertEqual(str(context.exception), "Unassigned parameter A100")
    self.assertEqual(context.exception.data, ["PA100", "P", "A100"])


if __name__ == "__main__":
  unittest.main()
