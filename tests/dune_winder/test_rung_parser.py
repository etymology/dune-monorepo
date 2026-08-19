"""Unit tests for the .rung surface parser and the rllscrap parser."""

from __future__ import annotations

import pytest

from dune_winder.rung_lang import ast as rast
from dune_winder.rung_lang import formula
from dune_winder.rung_lang.parse_rllscrap import (
    RllscrapError,
    parse_rllscrap_text,
    parse_rung_text,
)
from dune_winder.rung_lang.parser import RungSyntaxError, parse_rung_source
from dune_winder.rung_lang.rung_ir import BranchIR, Instr


def parse(body: str) -> rast.RoutineAST:
    return parse_rung_source("routine prog/main\n\n" + body)


class TestRllscrapParser:
    def test_simple_rung(self):
        rung = parse_rung_text("XIC(INIT_DONE)CMP(STATE=9)OTE(active)")
        assert rung.nodes == (
            Instr("XIC", ("INIT_DONE",)),
            Instr("CMP", ("STATE=9",)),
            Instr("OTE", ("active",)),
        )

    def test_branch_with_whitespace_and_nesting(self):
        rung = parse_rung_text("[XIC(A) ,XIO(B) [XIC(C),XIC(D)] ]OTE(OUT)")
        branch = rung.nodes[0]
        assert isinstance(branch, BranchIR)
        assert branch.legs[0] == (Instr("XIC", ("A",)),)
        inner = branch.legs[1][1]
        assert isinstance(inner, BranchIR)

    def test_formula_commas_do_not_split_operands(self):
        rung = parse_rung_text("CPT(dx,ABS(MIN(a,b)-c))")
        assert rung.nodes[0] == Instr("CPT", ("dx", "ABS(MIN(a,b)-c)"))

    def test_spaced_string_operands_survive(self):
        rung = parse_rung_text("MAM(Z,ctl,0,0,1000,Units per sec,1,Units per sec2)")
        instr = rung.nodes[0]
        assert isinstance(instr, Instr)
        assert instr.operands[5] == "Units per sec"

    def test_rejects_garbage(self):
        with pytest.raises(RllscrapError):
            parse_rung_text("XIC(a")

    def test_pending_rung_marking(self):
        routine = parse_rllscrap_text(
            "XIC(a)OTE(b);   XIC(c)OTE(d);",
            program="p",
            routine="r",
            pending_rungs=frozenset({1}),
        )
        assert [r.rung_type for r in routine.rungs] == ["N", "e"]


class TestSurfaceParser:
    def test_header_required(self):
        with pytest.raises(RungSyntaxError):
            parse_rung_source("when a:\n    b = 1\n")

    def test_uses_and_locals(self):
        ast = parse(
            "uses STATE, Local:1:I\n"
            "local bool flag, bits[8]\n"
            "local timer t preset 250ms\n"
            "flag = STATE == 1\n"
        )
        assert [d.name for d in ast.uses] == ["STATE", "Local:1:I"]
        assert ast.locals[1].dims == 8
        assert ast.locals[2].preset_ms == 250

    def test_when_block_and_guarded_action(self):
        ast = parse("when a and not b:\n    x = 1\n    call sub\n\nreset t when c\n")
        block = ast.statements[0]
        assert isinstance(block, rast.WhenBlock)
        assert isinstance(block.actions[0], rast.AssignAction)
        assert isinstance(block.actions[1], rast.CallAction)
        guarded = ast.statements[1]
        assert isinstance(guarded, rast.GuardedStmt)
        assert guarded.guard is not None

    def test_bool_assign_vs_value_assign(self):
        ast = parse("x = a and b\n\ny = 5\n\nz = 5 when a\n")
        assert isinstance(ast.statements[0], rast.BoolAssignStmt)
        assert isinstance(ast.statements[1], rast.GuardedStmt)
        assert isinstance(ast.statements[2], rast.GuardedStmt)

    def test_let_substitution(self):
        ast = parse("let ok = a and b\n\nx = ok and c\n")
        stmt = ast.statements[0]
        assert isinstance(stmt, rast.BoolAssignStmt)
        assert formula.print_surface(stmt.expr) == "a and b and c"

    def test_multiline_continuation(self):
        ast = parse(
            "let ok = not m.IP and STATE == 3\n         and (t.DN or not c)\n\nx = ok\n"
        )
        stmt = ast.statements[0]
        assert isinstance(stmt, rast.BoolAssignStmt)
        assert "STATE == 3" in formula.print_surface(stmt.expr)

    def test_on_blocks(self):
        ast = parse(
            "on entry of active:\n    servo_off X using c\n\n"
            "on rising a.DN and b:\n    fault_reset X using f\n"
        )
        entry, rising = ast.statements
        assert isinstance(entry, rast.OnBlock) and entry.kind == "entry"
        assert isinstance(rising, rast.OnBlock) and rising.kind == "rising"

    def test_motion_block(self):
        ast = parse(
            "when go:\n"
            "    move_axis Z_axis using ctl:\n"
            "        type     = absolute\n"
            "        position = 0\n"
            "        speed    = 1000 units/s\n"
            "        accel    = 10000 units/s2\n"
            "        decel    = 10000 units/s2\n"
            "        profile  = s-curve\n"
            "        jerk     = 10000\n"
        )
        block = ast.statements[0]
        assert isinstance(block, rast.WhenBlock)
        motion = block.actions[0]
        assert isinstance(motion, rast.MotionAction)
        assert dict(motion.pairs)["speed"] == "1000 units/s"

    def test_raw_and_pending(self):
        ast = parse("# PENDING EDIT in Studio\nraw `XIC(a)OTE(b)`\n")
        stmt = ast.statements[0]
        assert isinstance(stmt, rast.RawStmt)
        assert stmt.pending

    def test_generic_action_quoted_operands(self):
        ast = parse('MCS(X_Y, ctl, All, Yes, 10000, "Units per sec2") when stop\n')
        stmt = ast.statements[0]
        assert isinstance(stmt, rast.GuardedStmt)
        action = stmt.action
        assert isinstance(action, rast.GenericAction)
        assert action.operands[5] == "Units per sec2"

    def test_comments_stripped(self):
        ast = parse("x = 1  # set it\n")
        assert isinstance(ast.statements[0], rast.GuardedStmt)
