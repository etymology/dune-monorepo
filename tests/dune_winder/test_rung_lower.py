"""Boolean -> ladder lowering and sugar expansion unit tests."""

from __future__ import annotations

import pytest

from dune_winder.rung_lang.emit_rllscrap import routine_text, rung_text
from dune_winder.rung_lang.formula import parse_surface_expr
from dune_winder.rung_lang.lower import LowerError, guard_nodes, lower_routine, nnf
from dune_winder.rung_lang.parser import parse_rung_source
from dune_winder.rung_lang.rung_ir import BranchIR, Instr
from dune_winder.rung_lang.tagmeta import TagMeta


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

    def test_bool_target_bare_tag_is_ote_not_mov(self):
        # `coil = tag` with a BOOL destination drives a coil. MOV accepts
        # only SINT/INT/DINT/REAL, so MOV(tag, coil) is an illegal rung;
        # this is also the inverse of how the renderer prints an OTE.
        meta = TagMeta(
            controller={
                "AbortQueue": {"data_type_name": "BOOL"},
                "STATE11_IND": {"data_type_name": "BOOL"},
            }
        )
        lowered = lower_routine(
            parse_rung_source("routine prog/main\n\nAbortQueue = STATE11_IND\n"), meta
        )
        assert rung_text(lowered.routine.rungs[0]) == "XIC(STATE11_IND)OTE(AbortQueue);"

    def test_numeric_target_bare_tag_stays_mov(self):
        meta = TagMeta(
            controller={
                "dest": {"data_type_name": "DINT"},
                "src": {"data_type_name": "DINT"},
            }
        )
        lowered = lower_routine(
            parse_rung_source("routine prog/main\n\ndest = src\n"), meta
        )
        assert rung_text(lowered.routine.rungs[0]) == "MOV(src,dest);"

    def test_bool_coil_in_when_block_gets_its_own_rung(self):
        # a coil's RHS contacts must not gate the outputs that follow it,
        # so it splits out of the packed gated rung.
        meta = TagMeta(controller={"flag": {"data_type_name": "BOOL"}})
        lowered = lower_routine(
            parse_rung_source(
                "routine prog/main\n\nwhen a:\n    x = 0\n    flag = b\n    y = 1\n"
            ),
            meta,
        )
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(a)MOV(0,x);",
            "XIC(a)XIC(b)OTE(flag);",
            "XIC(a)MOV(1,y);",
        ]

    def test_on_rising_derives_informative_bits(self):
        # a single-tag trigger yields readable storage/edge bit names
        lowered = lower("on rising a.DN:\n    fault_reset X using f\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(a.DN)OSR(a_dn_osr_sb,a_dn_rising);",
            "XIC(a_dn_rising)MAFR(X,f);",
        ]
        assert lowered.auto_tags == ("a_dn_osr_sb", "a_dn_rising")

    def test_on_falling_derives_informative_bits(self):
        lowered = lower("on falling door_closed:\n    latch alarm\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(door_closed)OSF(door_closed_osf_sb,door_closed_falling);",
            "XIC(door_closed_falling)OTL(alarm);",
        ]

    def test_on_rising_explicit_using_clause_is_honoured(self):
        # an explicit clause pins the bits and does not synthesize new tags
        lowered = lower(
            "on rising a.DN using ons_store[1], a_dn_edge:\n"
            "    fault_reset X using f\n"
        )
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(a.DN)OSR(ons_store[1],a_dn_edge);",
            "XIC(a_dn_edge)MAFR(X,f);",
        ]
        assert lowered.auto_tags == ()

    def test_on_rising_compound_trigger_falls_back_to_auto_edge(self):
        # a multi-term trigger has no slug, so the opaque fallback is used
        lowered = lower("on rising a.DN and b:\n    fault_reset X using f\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(a.DN)XIC(b)OSR(auto_edge_0_sb,auto_edge_0_ob);",
            "XIC(auto_edge_0_ob)MAFR(X,f);",
        ]
        assert lowered.auto_tags == ("auto_edge_0_sb", "auto_edge_0_ob")

    def test_on_block_packs_same_opcode_actions_into_one_rung(self):
        # consecutive actions of one opcode behind the same edge collapse
        # into a single gated rung (series outputs), not one rung per action
        lowered = lower(
            "on rising trip:\n"
            "    reset t1\n"
            "    reset t2\n"
            "    reset t3\n"
        )
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(trip)OSR(trip_osr_sb,trip_rising);",
            "XIC(trip_rising)RES(t1)RES(t2)RES(t3);",
        ]

    def test_on_block_splits_rungs_at_opcode_change(self):
        # only same-opcode runs combine: MOV MOV, then RES, then OTU each
        # land on their own gated rung
        lowered = lower(
            "on rising trip:\n"
            "    a = 0\n"
            "    b = 0\n"
            "    reset t1\n"
            "    reset t2\n"
            "    unlatch f\n"
        )
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(trip)OSR(trip_osr_sb,trip_rising);",
            "XIC(trip_rising)MOV(0,a)MOV(0,b);",
            "XIC(trip_rising)RES(t1)RES(t2);",
            "XIC(trip_rising)OTU(f);",
        ]

    def test_on_entry_packs_actions_behind_shared_gate(self):
        lowered = lower(
            "on entry of act:\n    servo_off X using c\n    servo_off Y using d\n"
        )
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(act)OSR(act_osr_sb,act_rising);",
            "XIC(act)XIC(act_rising)MSF(X,c)MSF(Y,d);",
        ]

    def test_on_entry_regates_actions(self):
        lowered = lower("on entry of act:\n    servo_off X using c\n")
        texts = [rung_text(r) for r in lowered.routine.rungs]
        assert texts == [
            "XIC(act)OSR(act_osr_sb,act_rising);",
            "XIC(act)XIC(act_rising)MSF(X,c);",
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
