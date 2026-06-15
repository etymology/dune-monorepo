"""Boolean -> ladder lowering and sugar expansion unit tests."""

from __future__ import annotations

import pytest

from dune_winder.rung_lang.emit_rllscrap import routine_text, rung_text
from dune_winder.rung_lang.formula import parse_surface_expr
from dune_winder.rung_lang.lower import LowerError, guard_nodes, lower_routine, nnf
from dune_winder.rung_lang.parser import parse_rung_source
from dune_winder.rung_lang.rung_ir import BranchIR, Instr


def lower(body: str):
    return lower_routine(parse_rung_source("routine prog/main\n\n" + body))


def guard(text: str):
    return guard_nodes(parse_surface_expr(text))


class TestBooleanLowering:
    def test_and_series(self):
        assert guard("a and b") == [Instr("XIC", ("a",)), Instr("XIC", ("b",))]

    def test_or_branch(self):
        nodes = guard("a or not b")
        assert nodes == [BranchIR(((Instr("XIC", ("a",)),), (Instr("XIO", ("b",)),)))]

    def test_nested_and_inside_or(self):
        nodes = guard("(a and b) or c")
        branch = nodes[0]
        assert isinstance(branch, BranchIR)
        assert branch.legs[0] == (Instr("XIC", ("a",)), Instr("XIC", ("b",)))

    def test_de_morgan(self):
        # not (a or b) -> XIO(a) XIO(b)
        assert guard("not (a or b)") == [Instr("XIO", ("a",)), Instr("XIO", ("b",))]

    def test_comparator_negation_dual(self):
        assert guard("not (x >= 5)") == [Instr("LES", ("x", "5"))]

    def test_plain_comparison_uses_contact(self):
        assert guard("STATE == 9") == [Instr("EQU", ("STATE", "9"))]

    def test_arithmetic_comparison_uses_cmp(self):
        assert guard("a - b < 0.1") == [Instr("CMP", ("a-b<0.1",))]

    def test_cannot_negate_opaque(self):
        with pytest.raises(LowerError):
            guard("not LIM(a, b, c)")


class TestStatementLowering:
    def test_assignment_mov_vs_cpt(self):
        lowered = lower("x = 1\n\ny = a + 1\n\nz = b\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == ["MOV(1,x);", "CPT(y,a+1);", "MOV(b,z);"]

    def test_bool_assign_is_ote(self):
        lowered = lower("x = a and STATE == 9\n")
        assert rung_text(lowered.routine.rungs[0]) == "XIC(a)EQU(STATE,9)OTE(x);"

    def test_when_block_series_outputs(self):
        lowered = lower("when a:\n    x = 0\n    latch y\n")
        assert rung_text(lowered.routine.rungs[0]) == "XIC(a)MOV(0,x)OTL(y);"

    def test_on_rising_allocates_storage(self):
        lowered = lower("on rising a.DN:\n    fault_reset X using f\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(a.DN)OSR(auto_edge_0_sb,auto_edge_0_ob);",
            "XIC(auto_edge_0_ob)MAFR(X,f);",
        ]
        assert lowered.auto_tags == ("auto_edge_0_sb", "auto_edge_0_ob")

    def test_on_entry_regates_actions(self):
        lowered = lower("on entry of act:\n    servo_off X using c\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(act)OSR(auto_edge_0_sb,auto_edge_0_ob);",
            "XIC(act)XIC(auto_edge_0_ob)MSF(X,c);",
        ]

    def test_label_and_jump(self):
        lowered = lower("label done\n\nJMP(done) when a != 1\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == ["LBL(done)NOP();", "NEQ(a,1)JMP(done);"]

    def test_timer_call_reset(self):
        lowered = lower("start_timer t when a\n\nreset t\n\ncall sub\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == ["XIC(a)TON(t,?,?);", "RES(t);", "JSR(sub,0);"]

    def test_motion_block_expansion(self):
        lowered = lower(
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
        text = routine_text(lowered.routine)
        assert (
            "MAM(Z_axis,ctl,0,0,1000,Units per sec,10000,Units per sec2,"
            "10000,Units per sec2,S-Curve,10000,10000,Units per sec3,0,0,0,0,0,0)"
            in text
        )

    def test_raw_passthrough(self):
        lowered = lower("raw `XIC(weird)SOMENEWINSTR(a,b,c)`\n")
        assert rung_text(lowered.routine.rungs[0]) == "XIC(weird)SOMENEWINSTR(a,b,c);"

    def test_nnf_is_identity_on_nnf_input(self):
        expr = parse_surface_expr("not a and (b or STATE != 2)")
        assert nnf(expr) == expr
