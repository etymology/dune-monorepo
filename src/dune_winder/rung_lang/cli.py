"""Console entry points: ``rung-compile`` and ``rung-render``.

rung-compile <file.rung> [--emit l5x|rllscrap] [--check-only]
    Parse + check + lower an edited .rung; write the routine import L5X
    (donor context + synthesized tags + new rungs) next to the source as
    ``<routine>_import.L5X`` and print an equivalence report against the
    routine's current exported L5X.

rung-render <program>/<routine> | --all
    Re-render .rung from the routine's exported L5X (also runs inside
    ``plc-acd-export`` for every routine; this standalone form is for
    development and spot-rendering).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dune_winder.paths import PLC_ROOT
from dune_winder.plc_l5x import read_l5x_rungs

from .check import check_routine
from .context import build_import_l5x, write_import_l5x
from .emit_rllscrap import routine_text, rung_text
from .equiv import check_equivalence
from .lower import Lowered, lower_routine
from .parse_rllscrap import parse_rllscrap_text
from .parser import parse_rung_source
from .render import render_routine
from .rung_ir import RoutineIR
from .tagmeta import load_tag_meta
from .timer_args import resolve_timer_counter_args


def routine_dir_name(plc_root: Path, program: str, routine: str) -> str:
    """The historical layout keeps the main routine in a ``main/`` dir."""
    if (plc_root / program / routine).is_dir():
        return routine
    return "main"


def load_routine_ir(plc_root: Path, program: str, routine: str) -> RoutineIR:
    l5x_path = plc_root / program / f"{routine}_Routine_RLL.L5X"
    if not l5x_path.exists():
        raise FileNotFoundError(l5x_path)
    rungs = read_l5x_rungs(l5x_path)
    # The L5X CDATA carries each rung's text and its Type ("e" = pending
    # edit) directly, so the source-of-truth join matches the old
    # studio_copy.rllscrap content exactly.
    text = "   ".join(rung.text for rung in rungs)
    pending = frozenset(i for i, rung in enumerate(rungs) if rung.rung_type == "e")
    return parse_rllscrap_text(
        text, program=program, routine=routine, pending_rungs=pending
    )


def iter_tree_routines(plc_root: Path, meta=None):
    """Yield (program, routine_name, routine_dir, resolved IR) for every
    routine under the tree — the single loading path shared by the export,
    the CLIs, and CI, so they all agree on routine naming (a ``main/``
    directory may hold a routine with a different real name) and on
    pending-edit marking."""
    if meta is None:
        meta = load_tag_meta(plc_root)
    for l5x_path in sorted(plc_root.glob("*/*_Routine_RLL.L5X")):
        program = l5x_path.parent.name
        routine = l5x_path.name[: -len("_Routine_RLL.L5X")]
        rdir = plc_root / program / (
            "main" if routine == meta.main_routine.get(program) else routine
        )
        ir = load_routine_ir(plc_root, program, routine)
        ir = resolve_timer_counter_args(ir, meta)
        yield program, routine, rdir, ir


def render_tree(plc_root: Path) -> tuple[list[Path], list[str]]:
    """Render <routine>.rung for every routine (plc-acd-export output #7)."""
    meta = load_tag_meta(plc_root)
    written: list[Path] = []
    warnings: list[str] = []
    for program, routine, rdir, ir in iter_tree_routines(plc_root, meta):
        result = render_routine(ir, meta)
        rdir.mkdir(parents=True, exist_ok=True)
        out = rdir / f"{routine}.rung"
        out.write_text(result.text, encoding="utf-8", newline="\n")
        written.append(out)
        warnings += [f"{program}/{routine}: {w}" for w in result.warnings]
    return written, warnings


# ---------------------------------------------------------------------------


def _equivalence_report(current: RoutineIR, compiled: RoutineIR) -> str:
    old = [rung_text(r) for r in current.rungs]
    new = [rung_text(r) for r in compiled.rungs]
    removed = [t for t in old if t not in new]
    added = [t for t in new if t not in old]
    lines = [
        f"rungs: {len(old)} in ACD export, {len(new)} compiled;"
        f" {len(old) - len(removed)} textually unchanged",
    ]
    for t in removed:
        lines.append(f"  - {t}")
    for t in added:
        lines.append(f"  + {t}")
    report = check_equivalence(current, compiled)
    lines.append(f"semantic check vs current export: {report.summary()}")
    if not report.equivalent:
        lines.append(
            "  (expected when your edit changes behaviour - review the +/- rungs)"
        )
    return "\n".join(lines)


def main_compile(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rung-compile", description=(__doc__ or "").splitlines()[0]
    )
    parser.add_argument("source", type=Path, help=".rung source file")
    parser.add_argument("--emit", choices=("l5x", "rllscrap"), default="l5x")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--plc-root", type=Path, default=PLC_ROOT)
    args = parser.parse_args(argv)

    source_text = args.source.read_text(encoding="utf-8")
    ast = parse_rung_source(source_text)
    meta = load_tag_meta(args.plc_root)
    lowered = lower_routine(ast, meta)
    lowered = Lowered(
        resolve_timer_counter_args(lowered.routine, meta),
        lowered.auto_tags,
    )
    result = check_routine(ast, lowered, meta)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if not result.ok:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    if result.new_tags:
        print("new program-scope tags (will be created by the import):")
        for decl in result.new_tags:
            dims = f"[{decl.dims}]" if decl.dims else ""
            preset = f" preset {decl.preset_ms}ms" if decl.preset_ms else ""
            print(f"  {decl.name}{dims}: {decl.type}{preset}")

    try:
        current = load_routine_ir(args.plc_root, ast.program, ast.routine)
        current = resolve_timer_counter_args(current, meta)
        print(_equivalence_report(current, lowered.routine))
    except FileNotFoundError:
        print("no current exported L5X to compare against (new routine?)")

    if args.check_only:
        print("check-only: OK")
        return 0

    if args.emit == "rllscrap":
        out = args.source.with_suffix(".rllscrap.out")
        out.write_text(routine_text(lowered.routine), encoding="utf-8")
        print(f"wrote {out}")
        return 0

    texts = [rung_text(r) for r in lowered.routine.rungs]
    l5x = build_import_l5x(
        args.plc_root, ast.program, ast.routine, texts, result.new_tags
    )
    out = args.source.parent / f"{ast.routine}_import.L5X"
    write_import_l5x(out, l5x)
    print(f"wrote {out}")
    print(
        "next: Studio 5000 -> right-click the routine -> Import Routine...,"
        " review the Import Configuration dialog (new tags appear there),"
        " save the ACD, then run `uv run plc-acd-export` and check `git diff`"
        " on the .rung file - an empty diff confirms the change landed."
    )
    return 0


def main_render(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rung-render", description="render .rung from the routine's exported L5X"
    )
    parser.add_argument(
        "routine", nargs="?", help="<program>/<routine> (e.g. state_9_unservo/main)"
    )
    parser.add_argument("--all", action="store_true", help="render the whole tree")
    parser.add_argument("--plc-root", type=Path, default=PLC_ROOT)
    args = parser.parse_args(argv)

    if args.all:
        written, warnings = render_tree(args.plc_root)
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        print(f"rendered {len(written)} .rung files under {args.plc_root}")
        return 0

    if not args.routine or "/" not in args.routine:
        parser.error("give <program>/<routine> or --all")
    program, routine = args.routine.split("/", 1)
    meta = load_tag_meta(args.plc_root)
    ir = load_routine_ir(args.plc_root, program, routine)
    ir = resolve_timer_counter_args(ir, meta)
    result = render_routine(ir, meta)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    rdir = args.plc_root / program / routine_dir_name(args.plc_root, program, routine)
    out = rdir / f"{routine}.rung"
    out.write_text(result.text, encoding="utf-8", newline="\n")
    print(
        f"wrote {out} ({result.total_rungs} rungs,"
        f" {result.raw_rungs} raw, density {result.raw_density:.1%})"
    )
    return 0
