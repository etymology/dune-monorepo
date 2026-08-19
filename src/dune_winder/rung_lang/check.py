"""Compile-time checks: the rules that used to be a human checklist.

Every tag a routine references must be either ``uses`` (and present in
the tag JSON exports at controller or program scope), ``local`` (new -
synthesized into the import L5X), an auto-allocated edge bit, or a
module-qualified I/O path. An unresolved tag is a compile error, not a
Studio import surprise. ``rung-compile`` also refuses routines whose
source carries pending-edit markers (importing over uncommitted Studio
edits is a corruption vector) and JSR calls to unknown routines.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ast as rast
from .lower import Lowered
from .rung_ir import referenced_tag_bases
from .tagmeta import TagMeta


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: locals (declared + auto edge bits) that do not exist yet and must be
    #: synthesized into the import L5X's context shell
    new_tags: list[rast.TagDecl] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def check_routine(ast: rast.RoutineAST, lowered: Lowered, meta: TagMeta) -> CheckResult:
    result = CheckResult()
    program = ast.program

    for stmt in ast.statements:
        if isinstance(stmt, rast.RawStmt) and stmt.pending:
            result.errors.append(
                "routine contains PENDING EDIT markers; finalize or discard the"
                " pending rungs in Studio 5000 first, then re-export"
            )
            break

    declared_locals = {decl.name: decl for decl in ast.locals}
    uses_names = {decl.name for decl in ast.uses}

    for name, decl in declared_locals.items():
        if meta.scope(program, name) is not None:
            result.errors.append(
                f"local {name!r} already exists at {meta.scope(program, name)} scope;"
                " list it under 'uses' instead"
            )
        else:
            result.new_tags.append(decl)
    for name in sorted(lowered.auto_tags):
        if name in declared_locals:
            continue
        if meta.scope(program, name) is None:
            result.new_tags.append(rast.TagDecl(name, type="bool"))

    for name in sorted(uses_names):
        if ":" in name:
            continue  # module I/O; Studio validates these
        if meta.scope(program, name) is None:
            result.errors.append(
                f"uses {name!r}: not found in the tag JSON exports"
                " (controller_level_tags.json / programTags.json);"
                " declare it 'local <type> ...' if it is new"
            )

    known = uses_names | set(declared_locals) | set(lowered.auto_tags)

    # raw rungs skip the strict scope check (plan §3.6) but warn
    raw_refs: set[str] = set()
    for stmt in ast.statements:
        if isinstance(stmt, rast.RawStmt):
            from .parse_rllscrap import parse_rung_text

            for text in stmt.text.split(";"):
                if text.strip():
                    raw_refs |= referenced_tag_bases(parse_rung_text(text.strip()))

    routines = set(meta.program_routines(program))
    for rung in lowered.routine.rungs:
        for base in sorted(referenced_tag_bases(rung)):
            if ":" in base or base in known:
                continue
            if meta.scope(program, base) is not None:
                continue  # referenced directly without a uses line: tolerated
            if base in raw_refs:
                result.warnings.append(
                    f"raw rung references unknown tag {base!r}; Studio will"
                    " reject the import if it does not exist"
                )
                continue
            result.errors.append(
                f"tag {base!r} is neither 'uses' (existing) nor 'local' (new)"
            )

    from .rung_ir import all_instructions

    for rung in lowered.routine.rungs:
        for instr in all_instructions(rung):
            if instr.opcode == "JSR" and routines and instr.operands:
                target = instr.operands[0]
                if target not in routines:
                    result.errors.append(
                        f"JSR target {target!r} is not a routine of program"
                        f" {program!r} (known: {sorted(routines)})"
                    )

    # deduplicate, preserve order
    seen: set[str] = set()
    result.errors = [e for e in result.errors if not (e in seen or seen.add(e))]
    seen = set()
    result.warnings = [w for w in result.warnings if not (w in seen or seen.add(w))]
    return result
