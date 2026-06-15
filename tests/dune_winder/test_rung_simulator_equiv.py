"""Confirm .rung round-trips behave identically under the PLC simulator.

``rung_lang`` has its own random-valuation equivalence checker; this test
is the *independent* oracle: the ``plc_ladder`` runtime (the engine behind
``LadderSimulatedPLC``) executes both the original ladder and the
.rung-round-tripped ladder over identical seeded tag stores for several
scans, and the resulting tag snapshots must match.

One-shot bookkeeping bits are excluded from the comparison: the compiler
deliberately renames them (``auto_edge_<k>_*``), and both stores start
zeroed so the k-th edge detector behaves identically on both sides.

Routines using instructions the plc_ladder runtime does not implement are
skipped (the rung_lang equivalence checker still covers them in
test_rung_roundtrip).
"""

from __future__ import annotations

import random

import pytest

from dune_winder.paths import PLC_ROOT
from dune_winder.plc_ladder import (
    JSRRegistry,
    RllParser,
    RoutineExecutor,
    RuntimeState,
    ScanContext,
    TagStore,
    load_plc_metadata,
)
from dune_winder.plc_ladder.metadata import TagDefinition
from dune_winder.plc_l5x import routine_paren_text
from dune_winder.plc_rung_transform import transform_text
from dune_winder.rung_lang import emit_rllscrap
from dune_winder.rung_lang.equiv import bool_context_names, internal_bit_names
from dune_winder.rung_lang.lower import lower_routine
from dune_winder.rung_lang.parse_rllscrap import parse_rllscrap_text
from dune_winder.rung_lang.parser import parse_rung_source
from dune_winder.rung_lang.render import render_routine
from dune_winder.rung_lang.tagmeta import load_tag_meta
from dune_winder.rung_lang.timer_args import resolve_timer_counter_args

from _plc_paste_support import l5x_path, paste_text

#: routines the plc_ladder runtime is known to execute (the simulator's
#: own scan set plus the sugar-heavy state routines)
ROUTINES = [
    ("main", "main"),
    ("tension_pid", "main"),
    ("init", "main"),
    ("state_1_ready", "main"),
    ("state_3_move_xy", "main"),
    ("state_3_move_xy", "xy_speed_regulator"),
    ("state_5_move_z", "main"),
    ("state_6_latch", "main"),
    ("state_9_unservo", "main"),
    ("state_12_move_xz", "main"),
    ("state_13_move_yz", "main"),
    ("state_14_hmi_stop", "main"),
    ("state_10_error", "main"),
    ("queued_motion", "main"),
    ("queued_motion", "CapSegSpeed"),
]

SCANS = 4


@pytest.fixture(scope="module")
def plc_metadata():
    return load_plc_metadata(PLC_ROOT)


@pytest.fixture(scope="module")
def rung_meta():
    return load_tag_meta(PLC_ROOT)


def _roundtrip_paste_text(
    program: str, routine_dir: str, rung_meta
) -> tuple[str, set[str]]:
    """Original rung text -> .rung -> rung text -> paste dialect, plus the
    base names of one-shot bookkeeping bits on both sides."""
    source = routine_paren_text(l5x_path(program, routine_dir))
    original = parse_rllscrap_text(source, program=program, routine=routine_dir)
    rendered = render_routine(
        resolve_timer_counter_args(original, rung_meta), rung_meta
    )
    compiled = lower_routine(parse_rung_source(rendered.text))
    resolved = resolve_timer_counter_args(compiled.routine, rung_meta)
    paste = transform_text(emit_rllscrap.routine_text(resolved))
    internal = internal_bit_names(original) | internal_bit_names(compiled.routine)
    internal_bases = {name.split(".")[0].split("[")[0] for name in internal}
    return paste, internal_bases


def _inject_auto_tags(plc_metadata, program: str, names: set[str]) -> None:
    tags = plc_metadata.programs[program].tags
    for name in names:
        if name.startswith("auto_edge_") and name not in tags:
            tags[name] = TagDefinition(
                name=name,
                fully_qualified_name=f"Program:{program}.{name}",
                tag_type="atomic",
                data_type_name="BOOL",
                dimensions=(0, 0, 0),
                array_dimensions=0,
                udt_name=None,
                program=program,
                value=None,
            )


def _seed_inputs(
    ctx: ScanContext, program: str, ir, trial: int, internal: set[str]
) -> None:
    """Deterministically randomize the contact-context tags both versions
    read, so several scans exercise edges and branches. One-shot
    bookkeeping bits must evolve naturally (and are renamed between the
    two versions), so they are never seeded."""
    for name in sorted(bool_context_names(ir) - internal):
        if name.split(".")[0].split("[")[0] in internal:
            continue
        rng = random.Random(f"{trial}:{name}")
        try:
            ctx.set_value(name, bool(rng.randint(0, 1)), program=program)
        except (KeyError, ValueError, TypeError, IndexError):
            pass
    for state_tag, pool in (("STATE", (1, 2, 3, 5, 9)), ("STATE_REQUEST", (0, 14))):
        rng = random.Random(f"{trial}:{state_tag}")
        try:
            ctx.set_value(state_tag, rng.choice(pool), program=program)
        except (KeyError, ValueError, TypeError, IndexError):
            pass


def _run(
    paste: str,
    program: str,
    routine_name: str,
    plc_metadata,
    ir,
    trial: int,
    internal: set[str],
):
    parser = RllParser()
    routine = parser.parse_routine_text(routine_name, paste, program=program)

    registry = JSRRegistry()
    program_meta = plc_metadata.programs[program]
    for sibling in program_meta.routines:
        if sibling == routine_name:
            continue
        sibling_dir = PLC_ROOT / program / sibling
        if not sibling_dir.is_dir():
            continue
        registry.register(
            sibling,
            parser.parse_routine_text(
                sibling, paste_text(program, sibling), program=program
            ),
        )

    store = TagStore(plc_metadata, use_exported_values=False)
    ctx = ScanContext(
        tag_store=store,
        jsr_registry=registry,
        runtime_state=RuntimeState(scan_time_ms=100),
    )
    executor = RoutineExecutor()
    snapshots = []
    for scan in range(SCANS):
        _seed_inputs(ctx, program, ir, trial * 100 + scan, internal)
        executor.execute_routine(routine, ctx)
        snapshots.append(store.snapshot(program))
    return snapshots


def _strip_internal(snapshot: dict, internal_bases: set[str]) -> dict:
    return {k: v for k, v in snapshot.items() if k not in internal_bases}


def _values_equal(a, b) -> bool:
    """Recursive equality that treats NaN == NaN (an uninitialized divisor
    makes both versions compute the same NaN, e.g. the d-term filter)."""
    if isinstance(a, float) and isinstance(b, float):
        return a == b or (a != a and b != b)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_values_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_values_equal(x, y) for x, y in zip(a, b))
    return a == b


@pytest.mark.parametrize("program,routine_dir", ROUTINES, ids=lambda v: str(v))
def test_roundtrip_behaves_identically_under_simulator(
    program, routine_dir, plc_metadata, rung_meta
):
    original_paste = paste_text(program, routine_dir)
    roundtrip_paste, internal_bases = _roundtrip_paste_text(
        program, routine_dir, rung_meta
    )

    routine_name = (
        plc_metadata.programs[program].main_routine_name or routine_dir
        if routine_dir == "main"
        else routine_dir
    )
    ir = parse_rllscrap_text(
        routine_paren_text(l5x_path(program, routine_dir)),
        program=program,
        routine=routine_dir,
    )
    _inject_auto_tags(plc_metadata, program, internal_bases)

    for trial in range(3):
        try:
            snaps_a = _run(
                original_paste,
                program,
                routine_name,
                plc_metadata,
                ir,
                trial,
                internal_bases,
            )
        except Exception as exc:  # runtime lacks an instruction: not our bug
            pytest.skip(f"plc_ladder runtime cannot execute original: {exc}")
        snaps_b = _run(
            roundtrip_paste,
            program,
            routine_name,
            plc_metadata,
            ir,
            trial,
            internal_bases,
        )
        for scan, (snap_a, snap_b) in enumerate(zip(snaps_a, snaps_b)):
            clean_a = _strip_internal(snap_a, internal_bases)
            clean_b = _strip_internal(snap_b, internal_bases)
            if not _values_equal(clean_a, clean_b):
                diff = {
                    k
                    for k in set(clean_a) | set(clean_b)
                    if not _values_equal(clean_a.get(k), clean_b.get(k))
                }
                raise AssertionError(
                    f"{program}/{routine_dir} trial {trial} scan {scan}:"
                    f" stores differ on {sorted(diff)[:8]}"
                )
