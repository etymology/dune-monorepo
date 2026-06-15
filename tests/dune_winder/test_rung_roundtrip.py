"""Round-trip CI over every checked-in routine (plan §6.2), both directions.

1. **Render soundness:** rllscrap -> .rung -> rllscrap is semantically
   equivalent (random-valuation scan comparison). The renderer may not
   change meaning, ever.
2. **Fixed point:** .rung -> rllscrap -> .rung reproduces the rendered
   text byte-for-byte, which is what keeps the edit-import-re-export
   cycle diff-clean.

Plus the plan §4 worked-translation fixtures as compile-direction golden
tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dune_winder.paths import PLC_ROOT
from dune_winder.rung_lang.cli import iter_tree_routines
from dune_winder.rung_lang.equiv import check_equivalence
from dune_winder.rung_lang.lower import lower_routine
from dune_winder.rung_lang.parse_rllscrap import parse_rllscrap_text
from dune_winder.rung_lang.parser import parse_rung_source
from dune_winder.rung_lang.render import render_routine
from dune_winder.rung_lang.tagmeta import load_tag_meta
from dune_winder.rung_lang.timer_args import resolve_timer_counter_args

FIXTURES = Path(__file__).parent / "fixtures" / "rung"

_META = load_tag_meta(PLC_ROOT)
ROUTINES = list(iter_tree_routines(PLC_ROOT, _META))


@pytest.fixture(scope="module")
def meta():
    return _META


@pytest.mark.parametrize(
    "program,routine,rdir,original",
    ROUTINES,
    ids=[f"{program}-{routine}" for program, routine, _, _ in ROUTINES],
)
def test_render_soundness_and_fixed_point(program, routine, rdir, original, meta):
    rendered = render_routine(original, meta)
    lowered = lower_routine(parse_rung_source(rendered.text))
    compiled = resolve_timer_counter_args(lowered.routine, meta)

    report = check_equivalence(original, compiled, trials=60)
    assert report.equivalent, (
        f"render changed meaning for {program}/{routine}: {report.summary()}"
    )

    re_rendered = render_routine(compiled, meta)
    assert re_rendered.text == rendered.text, (
        f"fixed point broken for {program}/{routine}"
    )


def test_rendered_tree_is_checked_in_and_current(meta):
    """The .rung files in the tree match what the renderer produces."""
    stale = []
    for program, routine, rdir, ir in ROUTINES:
        rung_file = rdir / f"{routine}.rung"
        assert rung_file.exists(), f"no .rung checked in for {program}/{routine}"
        expected = render_routine(ir, meta).text
        if rung_file.read_text(encoding="utf-8") != expected:
            stale.append(str(rung_file))
    assert not stale, f"stale .rung files (re-run `uv run rung-render --all`): {stale}"


def test_raw_density_does_not_regress(meta):
    """Track plan §3.6's raw-density metric; tighten as sugar improves.
    Pending-edit rungs are excluded — they are forced raw by Studio state,
    not by renderer coverage."""
    raw = total = 0
    for _, _, _, ir in ROUTINES:
        result = render_routine(ir, meta)
        raw += result.raw_rungs - result.pending_rungs
        total += result.total_rungs - result.pending_rungs
    assert total > 800
    assert raw / total < 0.02, f"raw density regressed: {raw}/{total}"


# ---------------------------------------------------------------------------
# Plan §4 fixtures: compile direction must reproduce the existing ladder
# semantically (rung packing and bookkeeping names may differ).
# ---------------------------------------------------------------------------


def _load_rllscrap(program: str, routine_dir: str):
    path = PLC_ROOT / program / routine_dir / "studio_copy.rllscrap"
    return parse_rllscrap_text(
        path.read_text(encoding="utf-8"), program=program, routine=routine_dir
    )


def test_fixture_state_9_unservo_compiles_equivalent(meta):
    source = (FIXTURES / "state_9_unservo_main.rung").read_text(encoding="utf-8")
    compiled = lower_routine(parse_rung_source(source)).routine
    original = _load_rllscrap("state_9_unservo", "main")
    report = check_equivalence(original, compiled, trials=100)
    assert report.equivalent, report.summary()


def test_fixture_state_3_entry_compiles_equivalent(meta):
    """The hard branch case (§4.2): the flattened source must match the
    bracket-packed entry rung of state_3_move_xy/main."""
    source = (FIXTURES / "state_3_entry.rung").read_text(encoding="utf-8")
    compiled = lower_routine(parse_rung_source(source)).routine

    original_full = _load_rllscrap("state_3_move_xy", "main")
    # entry rung only (rung 1 of the routine)
    from dune_winder.rung_lang.rung_ir import RoutineIR

    original = RoutineIR("state_3_move_xy", "main", (original_full.rungs[1],))
    report = check_equivalence(original, compiled, trials=200)
    assert report.equivalent, report.summary()
