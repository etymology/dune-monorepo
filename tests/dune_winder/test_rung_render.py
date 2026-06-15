"""Renderer unit tests: sugar recognition, raw fallback, determinism."""

from __future__ import annotations

from dune_winder.rung_lang.parse_rllscrap import parse_rllscrap_text
from dune_winder.rung_lang.render import render_routine
from dune_winder.rung_lang.tagmeta import TagMeta


def render(rllscrap: str, meta: TagMeta | None = None) -> str:
    ir = parse_rllscrap_text(rllscrap, program="prog", routine="main")
    return render_routine(ir, meta or TagMeta()).text


def body(rllscrap: str, meta: TagMeta | None = None) -> str:
    """Rendered text minus header/uses/blank scaffolding."""
    lines = render(rllscrap, meta).splitlines()
    return "\n".join(
        line for line in lines if line and not line.startswith(("routine ", "uses "))
    )


class TestRecognition:
    def test_ote_renders_as_assignment(self):
        assert body("XIC(a)CMP(STATE=9)OTE(x);") == "x = a and STATE == 9"

    def test_guarded_single_action(self):
        assert body("CMP(STATE=2)CPT(NEXTSTATE,1);") == "NEXTSTATE = 1 when STATE == 2"

    def test_series_outputs_group_into_when_block(self):
        assert body("XIC(a)CPT(x,0)MOV(0,y)CPT(z,1);").splitlines() == [
            "when a:",
            "    x = 0",
            "    y = 0",
            "    z = 1",
        ]

    def test_unconditional_multi_output_is_always_block(self):
        assert body("CPT(x,a+1)CPT(y,b+2);").splitlines() == [
            "always:",
            "    x = a + 1",
            "    y = b + 2",
        ]

    def test_branch_tautology_simplifies(self):
        # [XIC(p),XIO(p) ...outputs...] contributes no condition
        text = body("XIC(g)[XIC(p),XIO(p)CPT(e,1)]OTE(ind);")
        assert "ind = g" in text
        assert "e = 1 when g and not p" in text

    def test_output_branch_distributes(self):
        text = body("XIC(t)[MSO(X,cx),MSO(Y,cy)];")
        assert text.splitlines() == [
            "when t:",
            "    servo_on X using cx",
            "    servo_on Y using cy",
        ]

    def test_on_rising_idiom_spells_out_hand_named_bits(self):
        # sb/ob are neither the derived names nor the auto_edge fallback,
        # so the renderer preserves them with an explicit `using` clause
        text = body("XIC(a.DN)OSR(sb,ob);   XIC(ob)MAFR(X,f);")
        assert text.splitlines() == [
            "on rising a.DN using sb, ob:",
            "    fault_reset X using f",
        ]

    def test_on_rising_idiom_omits_derived_bits(self):
        # bits that match what lowering would invent stay implicit
        text = body("XIC(a.DN)OSR(a_dn_osr_sb,a_dn_rising);   XIC(a_dn_rising)MAFR(X,f);")
        assert text.splitlines() == [
            "on rising a.DN:",
            "    fault_reset X using f",
        ]

    def test_on_rising_idiom_omits_auto_edge_fallback(self):
        text = body("XIC(a.DN)OSR(auto_edge_0_sb,auto_edge_0_ob);   XIC(auto_edge_0_ob)MAFR(X,f);")
        assert text.splitlines() == [
            "on rising a.DN:",
            "    fault_reset X using f",
        ]

    def test_on_entry_idiom(self):
        text = body(
            "XIC(act)OSR(act_osr_sb,act_rising);   "
            "XIC(act)XIC(act_rising)MSF(X,c);   XIC(act)XIC(act_rising)MSF(Y,d);"
        )
        assert text.splitlines() == [
            "on entry of act:",
            "    servo_off X using c",
            "    servo_off Y using d",
        ]

    def test_idiom_rejected_when_edge_used_elsewhere(self):
        text = body("XIC(a)OSR(sb,ob);   XIC(ob)MAFR(X,f);   XIC(ob)XIC(z)CPT(q,1);")
        assert "on rising" not in text
        assert "OSR(sb, ob) when a" in text

    def test_label_prefix_splits(self):
        text = body("LBL(lbl_end)NOP();   LBL(top)NEQ(a,1)JMP(lbl_end);")
        assert text.splitlines() == [
            "label lbl_end",
            "label top",
            "JMP(lbl_end) when a != 1",
        ]

    def test_pending_rung_is_marked_raw(self):
        ir = parse_rllscrap_text(
            "XIC(a)OTE(b);",
            program="prog",
            routine="main",
            pending_rungs=frozenset({0}),
        )
        text = render_routine(ir, TagMeta()).text
        assert "# PENDING EDIT in Studio" in text
        assert "raw `XIC(a)OTE(b)`" in text


class TestRawFallback:
    def test_write_then_read_condition_goes_raw(self):
        result_text = body("XIC(req)XIC(t.DN)OTU(req)OTU(trip);")
        assert result_text.startswith("raw `")

    def test_no_output_rung_goes_raw(self):
        assert body("XIC(a)XIC(b);").startswith("raw `")

    def test_never_fails(self):
        # arbitrary deep nesting with mixed outputs still renders something
        ir = parse_rllscrap_text(
            "[[XIO(a),GEQ(p,q)]CPT(e,1),XIC(a)[XIC(b),XIO(b)CPT(e,2)]OTE(i)];",
            program="prog",
            routine="main",
        )
        result = render_routine(ir, TagMeta())
        assert result.text


class TestDeterminism:
    def test_rendering_is_pure(self):
        src = (
            "XIC(a)CMP(STATE=9)OTE(x);   XIC(x)OSR(s,e);   XIC(e)MAFR(X,f);   "
            "XIC(x)CPT(NEXTSTATE,1)MOV(0,REQ);"
        )
        assert render(src) == render(src)
