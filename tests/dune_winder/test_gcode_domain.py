import unittest
from typing import cast

from hypothesis import assume, given, strategies as st

from dune_winder.gcode.model import (
    CommandWord,
    FunctionCall,
    MacroCall,
    OPCODE_CATALOG,
    Opcode,
    ProgramLine,
)
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


# Strategies for synthesizing canonical g-code lines.
_param_token = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_+."
    ),
    min_size=1,
    max_size=8,
)
_int_token = st.integers(min_value=-9999, max_value=9999).map(str)
_float_token = st.decimals(
    min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False, places=2
).map(str)
_macro_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="_",
    ),
    min_size=1,
    max_size=12,
)
_comment_text = st.text(
    alphabet=st.characters(
        blacklist_characters="()~", blacklist_categories=("Cs", "Cc")
    ),
    max_size=20,
)


def _command_word(letter: str, value_strategy):
    return st.builds(
        CommandWord,
        letter=st.just(letter),
        value=value_strategy,
        parameters=st.lists(_param_token, max_size=2),
    )


_function_call = st.builds(
    FunctionCall,
    opcode=st.sampled_from([int(o) for o in Opcode]).map(str),
    parameters=st.lists(_param_token, max_size=3),
)


def _line_item():
    return st.one_of(
        _function_call,
        _command_word("F", _float_token),
        _command_word("X", _float_token),
        _command_word("Y", _float_token),
        _command_word("M", _int_token),
        _command_word("N", _int_token),
        _command_word("Z", st.one_of(_float_token, st.just("EXTEND"))),
        _command_word("O", _param_token),
        st.builds(MacroCall, text=_macro_text),
    )


@st.composite
def _program_line(draw):
    items = draw(st.lists(_line_item(), min_size=1, max_size=5))
    line = ProgramLine(items=items)
    # The PXZ recipe rebinds a "P" with value "XZ" attached to a Z command word
    # back to the previous FunctionCall. That edge case is covered by an
    # explicit example below; exclude it from random generation.
    rendered = render_line(line)
    assume(" PXZ" not in rendered.upper())
    return line


class GCodeRoundTripProperties(unittest.TestCase):
    @given(line=_program_line())
    def test_render_parse_render_is_idempotent(self, line):
        first = render_line(line)
        reparsed = parse_line_text(first)
        second = render_line(reparsed)
        self.assertEqual(first, second)

    @given(
        letter=st.text(min_size=1, max_size=1).filter(lambda c: c not in "FGMNOPXYZ ")
    )
    def test_parse_rejects_unknown_command_letter(self, letter):
        assume(not letter.isspace())
        assume(letter not in "(~")
        with self.assertRaises(GCodeParseError):
            parse_line_text(letter + "1")

    @given(parameter=_param_token)
    def test_parse_rejects_unassigned_p_parameter(self, parameter):
        with self.assertRaises(GCodeParseError):
            parse_line_text("P" + parameter)


class GCodeRecipeExamples(unittest.TestCase):
    """Curated examples for parser recipes that the property test excludes."""

    def test_p_parameters_bind_to_previous_word(self):
        line = parse_line_text("G103 PA800 PA799 PXY")
        function = cast(FunctionCall, line.items[0])
        self.assertEqual(function.opcode, "103")
        self.assertEqual(function.parameters, ["A800", "A799", "XY"])

    def test_pxz_rebinds_to_previous_function_call(self):
        line = parse_line_text("G103 PA800 PA799 ZEXTEND PXZ")
        self.assertEqual(render_line(line), "G103 PA800 PA799 PXZ ZEXTEND")
        function = cast(FunctionCall, line.items[0])
        z_word = cast(CommandWord, line.items[1])
        self.assertEqual(function.parameters, ["A800", "A799", "XZ"])
        self.assertEqual(z_word.letter, "Z")
        self.assertEqual(z_word.value, "EXTEND")

    def test_comments_normalize_whitespace(self):
        line = parse_line_text("  N1   X1   ( hello )   Y2  ")
        self.assertEqual(render_line(line), "N1 X1 ( hello ) Y2")

    def test_tilde_macro_with_keyword_arguments(self):
        for text in (
            "anchorToTarget(B1201,B2001)",
            "anchorToTarget(B1201,B2001,offset=(1.25,-2.5))",
            "anchorToTarget(B1201,B2001,hover=True)",
        ):
            line = parse_line_text(f"N7 ~{text} ( top )")
            self.assertEqual(render_line(line), f"N7 ~{text} ( top )")
            macro = cast(MacroCall, line.items[1])
            self.assertEqual(macro.text, text)


class GCodeRuntimeTests(unittest.TestCase):
    def test_runtime_delivers_one_callback_per_instruction(self):
        seen = []
        callbacks = {"on_instruction": lambda line: seen.append(line)}

        line = parse_line_text("X10 Y11 F120 G103 PA1 PA2 PXY N7 ( note )")
        execute_program_line(line, callbacks.get)

        self.assertEqual(seen, [line])

    def test_program_executor_executes_with_canonical_runtime(self):
        seen = []
        callbacks = GCodeCallbacks()
        callbacks.registerCallback("on_instruction", lambda line: seen.append(line))
        gCode = GCodeProgramExecutor([], callbacks)

        gCode.execute("G105 PX-10")

        self.assertEqual(len(seen), 1)
        self.assertIsInstance(seen[0].items[0], FunctionCall)
        self.assertEqual(
            seen[0].items[0].as_legacy_parameter_list(),
            [str(int(Opcode.OFFSET)), "X-10"],
        )

    def test_program_executor_maps_parse_errors_to_execution_errors(self):
        callbacks = GCodeCallbacks()
        gCode = GCodeProgramExecutor([], callbacks)

        with self.assertRaises(GCodeExecutionError) as context:
            gCode.execute("PA100")

        self.assertEqual(str(context.exception), "Unassigned parameter A100")
        self.assertEqual(context.exception.data, ["PA100", "P", "A100"])


class GCodeDomainTests(unittest.TestCase):
    def test_opcode_catalog_matches_opcode_enum(self):
        self.assertEqual(set(OPCODE_CATALOG.keys()), {int(o) for o in Opcode})

    def test_recipe_function_helpers_build_canonical_calls(self):
        cases = [
            (pin_center(["A1", "A2"], "XY"), Opcode.PIN_CENTER, ["A1", "A2", "XY"]),
            (head_transfer(3), Opcode.HEAD_TRANSFER, [3]),
            (wrap_goto(x=7174, y=0), Opcode.WRAP_GOTO, ["X7174", "Y0"]),
            (wrap_increment(x=-70, y=50), Opcode.WRAP_INCREMENT, ["X-70", "Y50"]),
            (wrap_anchor("PA1601"), Opcode.WRAP_ANCHOR, ["PA1601"]),
            (wrap_b("PB2001"), Opcode.WRAP_B, ["PB2001"]),
            (wrap_b_to_a("PB2001"), Opcode.WRAP_B_TO_A, ["PB2001"]),
        ]
        for call, opcode, parameters in cases:
            self.assertIsInstance(call, FunctionCall)
            self.assertEqual(call.opcode, int(opcode))
            self.assertEqual(call.parameters, parameters)

    def test_parser_renders_function_call_opcodes(self):
        for text in ("G206 P3", "G106 P0", "G114 PX7174 PY0", "G118 PB2001"):
            self.assertEqual(render_line(parse_line_text(text)), text)


if __name__ == "__main__":
    unittest.main()
