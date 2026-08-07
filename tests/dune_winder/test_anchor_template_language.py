###############################################################################
# Name: test_anchor_template_language.py
# Uses: Cover the anchorToTarget template dialect and the U/V wrapping
#       invariants that the hand-rolled builders used to encode implicitly.
# Date: 2026-08-06
###############################################################################

import unittest

from dune_winder.recipes.anchor_template_language import (
    OFFSET_MODE_NATURAL,
    AnchorLayerAdapter,
    compile_anchor_script_sections,
    render_anchor_layer_lines,
)
from dune_winder.recipes.line_offset_overrides import (
    _ANCHOR_TO_TARGET_NAME,
    _extract_anchor_to_target_call,
)
from dune_winder.recipes.recipe_template_language import RecipeTemplateLanguageError
from dune_winder.recipes import u_template_gcode as U
from dune_winder.recipes import v_template_gcode as V
from dune_winder.uv_head_target_parts.constants import _ANCHOR_TO_TARGET_RE

WRAPPING = "wrapping"

# Measured on the output the hand-rolled builders produced.  They are pinned
# because nothing else in the suite constrains the total, and a dropped or
# duplicated conditional line shifts every (wrap,line) identifier -- which
# silently re-points saved jog-calibration offsets.
U_WRAPPING_LINE_COUNT = 7276
V_WRAPPING_LINE_COUNT = 7274
COMB_PULL_LINE_COUNT = 72


def _fake_adapter(**overrides):
    settings = {
        "layer": "U",
        "line_builder": lambda *parts: " ".join(str(part) for part in parts if part),
        "coord": lambda axis, value: "%s%g" % (axis, value),
        "wrap_pin": lambda value: value,
        "near_comb": lambda pin_number: False,
        "annotate_wrap_lines": lambda wrap_number, lines: [
            "(%d,%d) %s" % (wrap_number, index, line)
            for index, line in enumerate(lines, start=1)
        ],
        "offset_mode": OFFSET_MODE_NATURAL,
        "offset_ids": ("only",),
        "offset_natural_axis": {"only": "x"},
        "named_values": {},
    }
    settings.update(overrides)
    return AnchorLayerAdapter(**settings)


def _render_fake(sections, *, adapter=None, wrap_count=2, offsets=(0.0,)):
    return render_anchor_layer_lines(
        sections,
        adapter or _fake_adapter(),
        offsets=list(offsets),
        pull_ins={"X_PULL_IN": 70.0, "Y_PULL_IN": 50.0, "HEAD_ARM_LENGTH": 70.0},
        wrap_count=wrap_count,
    )


def _bodies(lines):
    """Strip the leading N<i> token so assertions can be position-independent."""
    return [str(line).split(" ", 1)[-1] for line in lines]


def _find(lines, needle):
    matches = [line for line in lines if needle in line]
    if not matches:
        raise AssertionError("no line contains " + repr(needle))
    return matches


class AnchorScriptSectionsTests(unittest.TestCase):
    def test_omitted_sections_stay_none_rather_than_defaulting(self):
        sections = compile_anchor_script_sections(wrap=("emit A",))
        self.assertEqual(sections.preamble, ())
        self.assertEqual(sections.postscript, ())
        self.assertIsNone(sections.wrap_tail)
        self.assertIsNone(sections.final_wrap_tail)

    def test_final_wrap_tail_replaces_wrap_tail_only_on_the_last_wrap(self):
        sections = compile_anchor_script_sections(
            wrap=("emit BODY${wrap}",),
            wrap_tail=("emit TAIL${wrap}",),
            final_wrap_tail=("emit LAST${wrap}",),
        )
        self.assertEqual(
            _render_fake(sections, wrap_count=3),
            [
                "(1,1) BODY1",
                "(1,2) TAIL1",
                "(2,1) BODY2",
                "(2,2) TAIL2",
                "(3,1) BODY3",
                "(3,2) LAST3",
            ],
        )

    def test_missing_wrap_tail_is_skipped_not_substituted(self):
        sections = compile_anchor_script_sections(
            wrap=("emit BODY${wrap}",),
            final_wrap_tail=("emit LAST${wrap}",),
        )
        self.assertEqual(
            _render_fake(sections, wrap_count=2),
            ["(1,1) BODY1", "(2,1) BODY2", "(2,2) LAST2"],
        )

    def test_preamble_and_postscript_are_not_wrap_annotated(self):
        sections = compile_anchor_script_sections(
            preamble=("emit HEAD",),
            wrap=("emit BODY",),
            postscript=("emit FOOT",),
        )
        self.assertEqual(
            _render_fake(sections, wrap_count=1),
            ["HEAD", "(1,1) BODY", "FOOT"],
        )

    def test_preamble_referencing_the_wrap_number_fails_loudly(self):
        # Rendering it as "" instead would shift every downstream identifier.
        sections = compile_anchor_script_sections(preamble=("emit HEAD ${wrap}",))
        with self.assertRaises(RecipeTemplateLanguageError):
            _render_fake(sections, wrap_count=1)

    def test_statement_rendering_to_nothing_is_rejected(self):
        sections = compile_anchor_script_sections(wrap=("emit ${nothing}",))
        adapter = _fake_adapter(named_values={"nothing": None})
        with self.assertRaises(RecipeTemplateLanguageError):
            _render_fake(sections, adapter=adapter, wrap_count=1)

    def test_conditional_statement_is_omitted_when_the_condition_is_false(self):
        sections = compile_anchor_script_sections(
            wrap=("emit BODY", "if near_comb(1): emit COMB")
        )
        self.assertEqual(_render_fake(sections, wrap_count=1), ["(1,1) BODY"])
        self.assertEqual(
            _render_fake(
                sections,
                adapter=_fake_adapter(near_comb=lambda pin_number: True),
                wrap_count=1,
            ),
            ["(1,1) BODY", "(1,2) COMB"],
        )

    def test_transfer_statements_are_rejected_in_anchor_scripts(self):
        sections = compile_anchor_script_sections(wrap=("transfer b_to_a_transfer",))
        with self.assertRaises(RecipeTemplateLanguageError):
            _render_fake(sections, wrap_count=1)


class AnchorCallShapeTests(unittest.TestCase):
    """The emitted call text is parsed by four separate consumers."""

    def _render_call(self, expression, **kwargs):
        sections = compile_anchor_script_sections(wrap=("emit ${%s}" % expression,))
        return _render_fake(sections, wrap_count=1, **kwargs)[0]

    def test_zero_offset_is_omitted_entirely(self):
        self.assertEqual(
            self._render_call("anchor('A1', 'B2', offset=(0.0, 0.0))"),
            "(1,1) ~anchorToTarget(A1,B2)",
        )

    def test_offset_precedes_hover_and_in_two_moves(self):
        # offset_axis_policy anchors its regex on offset= sitting immediately
        # after the two pins, and stops clamping the off-axis component if
        # anything is inserted before it.
        self.assertEqual(
            self._render_call(
                "anchor('A1', 'B2', offset=(1.5, -2), hover=True, in_two_moves=True)"
            ),
            "(1,1) ~anchorToTarget(A1,B2,offset=(1.5,-2),hover=True,inTwoMoves=True)",
        )

    def test_call_text_carries_no_whitespace(self):
        rendered = self._render_call("anchor('A1', 'B2', offset=(1.5, -2))")
        self.assertNotIn(", ", rendered)

    def test_increment_and_goto_emit_both_components(self):
        self.assertEqual(
            self._render_call("increment(-70, 0)"), "(1,1) ~increment(-70,0)"
        )
        self.assertEqual(self._render_call("goto(440, 0)"), "(1,1) ~goto(440,0)")


class WrappingLineCountTests(unittest.TestCase):
    def test_total_line_counts(self):
        self.assertEqual(
            len(U.render_u_template_lines(script_variant=WRAPPING)),
            U_WRAPPING_LINE_COUNT,
        )
        self.assertEqual(
            len(V.render_v_template_lines(script_variant=WRAPPING)),
            V_WRAPPING_LINE_COUNT,
        )

    def test_u_postscript_is_not_wrap_annotated(self):
        lines = U.render_u_template_lines(script_variant=WRAPPING)
        self.assertEqual(
            _bodies(lines[-2:]),
            ["~anchorToTarget(A1201,B1601)", "~increment(70,0)"],
        )

    def test_v_final_wrap_tail_is_wrap_annotated(self):
        # Unlike U's postscript, V's tail renders as part of wrap 400 and so
        # stays addressable by line_offset_overrides.
        lines = V.render_v_template_lines(script_variant=WRAPPING)
        self.assertIn("(400,17)", lines[-1])


class CombPullTests(unittest.TestCase):
    """Comb clearance moves: 72 per layer, and only U labels them."""

    def test_u_comb_pulls_are_labelled(self):
        lines = U.render_u_template_lines(script_variant=WRAPPING)
        labelled = [line for line in lines if "(comb pull)" in line]
        self.assertEqual(len(labelled), COMB_PULL_LINE_COUNT)
        self.assertIn("(49,15) ~increment(153.478261,0) (comb pull)", " ".join(lines))

    def test_v_comb_pulls_are_unlabelled(self):
        lines = V.render_v_template_lines(script_variant=WRAPPING)
        self.assertEqual([line for line in lines if "comb pull" in line], [])
        comb = [line for line in lines if line.rstrip().endswith("139.565217,0)")]
        self.assertEqual(len(comb), COMB_PULL_LINE_COUNT)
        self.assertTrue(any("(51,15) ~increment(-139.565217,0)" in x for x in lines))

    def test_u_comb_pull_uses_the_wrapped_pin_near_the_head_end(self):
        # The head-end site's pin expression goes negative for wraps 1..399.
        # Testing it unwrapped never matches a comb and silently deletes 18
        # wraps' worth of clearance moves.
        lines = U.render_u_template_lines(script_variant=WRAPPING)
        wraps = {
            line.split("(")[1].split(",")[0] for line in lines if "(comb pull)" in line
        }
        self.assertTrue({"49", "57", "197", "205"}.issubset(wraps))


class FootPauseTests(unittest.TestCase):
    def test_u_wrapping_ignores_add_foot_pauses(self):
        # U routes wrapping output through the G103-based pass, which matches
        # nothing here.  V uses the anchorToTarget-aware pass instead.
        base = U.render_u_template_lines(script_variant=WRAPPING)
        paused = U.render_u_template_lines(
            script_variant=WRAPPING, add_foot_pauses=True
        )
        self.assertEqual(base, paused)

    def test_v_wrapping_honours_add_foot_pauses(self):
        base = V.render_v_template_lines(script_variant=WRAPPING)
        paused = V.render_v_template_lines(
            script_variant=WRAPPING, add_foot_pauses=True
        )
        self.assertNotEqual(base, paused)
        self.assertEqual(len([x for x in paused if "board gap" in x]), 24)


class WrappingAnchorChainTests(unittest.TestCase):
    """The wire is one continuous strand: every move starts where the last ended.

    A break means the recipe claims to anchor on a pin the wire was never
    routed to.  This is the invariant the old `1 - 399 + n` head-end anchor
    violated -- it started one pin past the preceding move's target.
    """

    def _assert_chain_is_continuous(self, layer, lines):
        pins = []
        for line in lines:
            if _ANCHOR_TO_TARGET_NAME not in line:
                continue
            _, call, _ = _extract_anchor_to_target_call(line)
            match = _ANCHOR_TO_TARGET_RE.fullmatch(call)
            if match is None:
                raise AssertionError("%s: unparseable call %r" % (layer, call))
            pins.append((line, match.group(1), match.group(2)))

        self.assertGreater(len(pins), 4000)
        breaks = [
            (previous_line, previous_target, line, anchor)
            for (previous_line, _, previous_target), (line, anchor, _) in zip(
                pins, pins[1:]
            )
            if previous_target != anchor
        ]
        self.assertEqual(
            breaks,
            [],
            "%s: %d anchor(s) do not start where the previous move ended"
            % (layer, len(breaks)),
        )

    def test_u_anchor_chain_is_continuous(self):
        self._assert_chain_is_continuous(
            "U", U.render_u_template_lines(script_variant=WRAPPING)
        )

    def test_v_anchor_chain_is_continuous(self):
        self._assert_chain_is_continuous(
            "V", V.render_v_template_lines(script_variant=WRAPPING)
        )

    def test_u_head_end_to_foot_end_handoff_stays_on_one_pin(self):
        # The specific link the off-by-one broke, pinned at both ends of the
        # wrap range so a regression cannot hide in the modular pin arithmetic.
        bodies = _bodies(U.render_u_template_lines(script_variant=WRAPPING))
        self.assertIn(
            "(1,13) ~anchorToTarget(A800,B2002,hover=True) (Top B corner - head end)",
            bodies,
        )
        self.assertIn(
            "(1,15) ~anchorToTarget(B2002,B1200) (Bottom B corner - foot end)",
            bodies,
        )
        self.assertIn(
            "(400,15) ~anchorToTarget(B2401,B801) (Bottom B corner - foot end)",
            bodies,
        )


class GeneratedTextHygieneTests(unittest.TestCase):
    def test_no_template_braces_survive_into_the_output(self):
        # A mismatched ${...} leaves a literal brace glued to the macro call.
        # The paren-balanced extractor puts it in the trailing comment, so the
        # parser check above cannot see it -- assert on the raw text instead.
        for layer, render in (
            ("U", U.render_u_template_lines),
            ("V", V.render_v_template_lines),
        ):
            lines = render(script_variant=WRAPPING)
            offenders = [line for line in lines if "{" in line or "}" in line]
            with self.subTest(layer=layer):
                self.assertEqual(offenders[:5], [])

    def test_every_macro_call_is_accepted_by_the_runtime_parser(self):
        for layer, render in (
            ("U", U.render_u_template_lines),
            ("V", V.render_v_template_lines),
        ):
            for line in render(script_variant=WRAPPING, offsets=[1.3] * 12):
                if _ANCHOR_TO_TARGET_NAME not in line:
                    continue
                _, call, _ = _extract_anchor_to_target_call(line)
                with self.subTest(layer=layer, call=call):
                    self.assertIsNotNone(_ANCHOR_TO_TARGET_RE.fullmatch(call))


class WrappingOffsetTests(unittest.TestCase):
    """Every corner offset must reach its labelled line, on its natural axis."""

    def _check_layer(self, module, render):
        label_for = {
            offset_id: label for label, offset_id in module.LABEL_TO_OFFSET_ID.items()
        }
        for index, offset_id in enumerate(module.OFFSET_IDS):
            axis = module.OFFSET_NATURAL_AXIS[offset_id]
            expected = "offset=(1.3,0)" if axis == "x" else "offset=(0,1.3)"
            offsets = [0.0] * 12
            offsets[index] = {"x": 1.3, "y": 1.3}
            lines = render(script_variant=WRAPPING, offsets=offsets)
            label = "(" + label_for[offset_id] + ")"
            matches = _find(lines, label)
            with self.subTest(layer=module.__name__, offset_id=offset_id):
                # The off-axis component must be clamped away, not emitted.
                self.assertTrue(
                    any(expected in line for line in matches),
                    "%s: expected %s on a %s line" % (offset_id, expected, label),
                )

    def test_u_offsets_land_on_their_natural_axis(self):
        self._check_layer(U, U.render_u_template_lines)

    def test_v_offsets_land_on_their_natural_axis(self):
        self._check_layer(V, V.render_v_template_lines)

    def test_scalar_and_natural_axis_dict_offsets_agree(self):
        for module, render in (
            (U, U.render_u_template_lines),
            (V, V.render_v_template_lines),
        ):
            scalars = [0.0] * 12
            dicts = [0.0] * 12
            for index, offset_id in enumerate(module.OFFSET_IDS):
                axis = module.OFFSET_NATURAL_AXIS[offset_id]
                scalars[index] = 1.3 if axis == "x" else 0.0
                dicts[index] = {axis: 1.3 if axis == "x" else 0.0}
            with self.subTest(layer=module.__name__):
                self.assertEqual(
                    render(script_variant=WRAPPING, offsets=scalars),
                    render(script_variant=WRAPPING, offsets=dicts),
                )


class WrappingPullInTests(unittest.TestCase):
    def test_u_pull_in_overrides_reach_the_wrapping_output(self):
        lines = U.render_u_template_lines(
            script_variant=WRAPPING,
            named_inputs={"Y_PULL_IN": 33.0, "X_PULL_IN": 100.0},
        )
        self.assertTrue(any("~increment(-100,0)" in line for line in lines))
        self.assertTrue(any("~increment(0,33)" in line for line in lines))
        self.assertFalse(any("~increment(0,60)" in line for line in lines))

    def test_head_arm_length_only_moves_the_comb_pulls(self):
        base = U.render_u_template_lines(script_variant=WRAPPING)
        changed = U.render_u_template_lines(
            script_variant=WRAPPING, named_inputs={"HEAD_ARM_LENGTH": 51.75}
        )
        differing = [a for a, b in zip(base, changed) if a != b]
        self.assertEqual(len(differing), COMB_PULL_LINE_COUNT)
        self.assertTrue(all("comb pull" in line for line in differing))


if __name__ == "__main__":
    unittest.main()
