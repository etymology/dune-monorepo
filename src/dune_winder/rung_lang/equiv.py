"""Semantic equivalence checker over the rung IR.

Two routines are equivalent when, across many seeded-random tag
valuations, one full scan produces:

- the same final store (writes to tags), excluding *internal* one-shot
  bookkeeping bits (OSR/OSF storage and edge operands, ONS storage) —
  the compiler renames those deterministically, so their names differ
  between an original routine and its round-trip; and
- the same ordered list of enabled fires of non-modelled instructions
  (motion, JSR, TON, PID, ...), with one-shot bookkeeping operand names
  canonicalised by occurrence index.

To make edge behaviour comparable, the k-th one-shot instruction (in scan
order) of both routines receives the same random initial storage value.
Valuations are biased toward the numeric literals each tag is compared
against, so CMP/EQU branches get exercised in both directions.

Approximation: JMP does not transfer control (see ``rung_ir.Evaluator``).
Both sides share the approximation, so structural re-arrangements that
this package performs are still checked faithfully.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import formula
from .formula import Bin, Num, Ref
from .rung_ir import Evaluator, Instr, RoutineIR, all_instructions

ONE_SHOT_OPCODES = {"ONS", "OSR", "OSF"}


def one_shot_instrs(routine: RoutineIR) -> list[Instr]:
    out = []
    for rung in routine.rungs:
        for instr in all_instructions(rung):
            if instr.opcode in ONE_SHOT_OPCODES:
                out.append(instr)
    return out


def internal_bit_names(routine: RoutineIR) -> set[str]:
    names: set[str] = set()
    for instr in one_shot_instrs(routine):
        names.update(op.strip() for op in instr.operands)
    return names


_BOOL_CONTEXT = {"XIC", "XIO", "OTE", "OTL", "OTU", "ONS", "OSR", "OSF"}


def bool_context_names(routine: RoutineIR) -> set[str]:
    """Operand paths used as contacts/coils; their valuations must be 0/1
    (they are BOOLs on the controller) so that e.g. an unconditional
    ``MOV(b,x)`` and ``XIC(b)OTE(x)`` — which Logix treats identically for
    BOOLs — compare equal under the type-blind evaluator."""
    names: set[str] = set()
    for rung in routine.rungs:
        for instr in all_instructions(rung):
            if instr.opcode in _BOOL_CONTEXT:
                names.update(op.strip() for op in instr.operands)
    return names


def _comparison_literals(routine: RoutineIR) -> dict[str, set[float]]:
    """tag path -> numeric literals it is compared against anywhere."""
    pools: dict[str, set[float]] = {}

    def collect(expr: formula.Expr) -> None:
        for node in formula.walk(expr):
            if isinstance(node, Bin) and node.op in formula.COMPARATORS:
                sides = (node.lhs, node.rhs)
                for a, b in (sides, sides[::-1]):
                    if isinstance(a, Ref) and isinstance(b, Num):
                        pools.setdefault(a.text, set()).add(float(b.text))

    for rung in routine.rungs:
        for instr in all_instructions(rung):
            if instr.opcode == "CMP":
                collect(formula.parse_formula(instr.operands[0]))
            elif instr.opcode == "CPT":
                collect(formula.parse_formula(instr.operands[1]))
            elif instr.opcode in formula.OPCODE_COMPARATOR:
                comparator = formula.OPCODE_COMPARATOR[instr.opcode]
                collect(
                    Bin(
                        comparator,
                        formula.parse_operand(instr.operands[0]),
                        formula.parse_operand(instr.operands[1]),
                    )
                )

    return pools


class _LazyStore(dict):
    """Valuation that invents a deterministic value on first read."""

    def __init__(self, seed: str, pools: dict[str, set[float]], bools: set[str]):
        super().__init__()
        self._seed = seed
        self._pools = pools
        self._bools = bools

    def get(self, key, default=0.0):
        if key not in self:
            self[key] = self._fresh(key)
        return self[key]

    def _fresh(self, key: str) -> float:
        rng = random.Random(f"{self._seed}:{key}")
        if key in self._bools:
            return float(rng.randint(0, 1))
        pool = sorted(self._pools.get(key, ()))
        roll = rng.random()
        if pool and roll < 0.5:
            base = rng.choice(pool)
            return rng.choice([base, base, base + 1, base - 1])
        if roll < 0.8:
            return float(rng.randint(0, 1))
        return round(rng.uniform(-10, 10), 3)


@dataclass
class EquivReport:
    equivalent: bool
    trials: int = 0
    failures: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.equivalent:
            return f"equivalent over {self.trials} random valuations"
        return f"NOT equivalent: {self.failures[0]}" + (
            f" (+{len(self.failures) - 1} more)" if len(self.failures) > 1 else ""
        )


def _canonical_fires(
    fires: list[tuple[str, tuple[str, ...]]],
    internal: set[str],
    renames: dict[str, str],
) -> list[tuple[str, tuple[str, ...]]]:
    out = []
    for opcode, operands in fires:
        out.append(
            (opcode, tuple(renames.get(op.strip(), op.strip()) for op in operands))
        )
    return out


def check_equivalence(
    a: RoutineIR, b: RoutineIR, *, trials: int = 100, seed: str = "rung-equiv"
) -> EquivReport:
    internal = internal_bit_names(a) | internal_bit_names(b)
    bools = bool_context_names(a) | bool_context_names(b)
    pools = _comparison_literals(a)
    for key, vals in _comparison_literals(b).items():
        pools.setdefault(key, set()).update(vals)

    # canonical names for one-shot bookkeeping operands, by occurrence
    renames_a: dict[str, str] = {}
    renames_b: dict[str, str] = {}
    shots_a = one_shot_instrs(a)
    shots_b = one_shot_instrs(b)
    for renames, shots in ((renames_a, shots_a), (renames_b, shots_b)):
        for k, instr in enumerate(shots):
            for j, op in enumerate(instr.operands):
                renames.setdefault(op.strip(), f"__shot_{k}_{j}")

    failures: list[str] = []
    for trial in range(trials):
        store_a = _LazyStore(f"{seed}:{trial}", pools, bools)
        store_b = _LazyStore(f"{seed}:{trial}", pools, bools)
        # seed the k-th one-shot storage of both routines identically
        rng = random.Random(f"{seed}:{trial}:shots")
        for k in range(max(len(shots_a), len(shots_b))):
            value = float(rng.randint(0, 1))
            if k < len(shots_a):
                store_a[shots_a[k].operands[0].strip()] = value
            if k < len(shots_b):
                store_b[shots_b[k].operands[0].strip()] = value

        eval_a = Evaluator(store_a)
        eval_b = Evaluator(store_b)
        eval_a.scan(a)
        eval_b.scan(b)

        fires_a = _canonical_fires(eval_a.fires, internal, renames_a)
        fires_b = _canonical_fires(eval_b.fires, internal, renames_b)
        if fires_a != fires_b:
            only_a = [f for f in fires_a if f not in fires_b]
            only_b = [f for f in fires_b if f not in fires_a]
            failures.append(
                f"trial {trial}: fires differ; only-in-a={only_a[:3]} only-in-b={only_b[:3]}"
            )
            continue

        # Compare final values for every tag either side *wrote*. A key
        # written on one side only is read lazily from the other, which
        # invents the identical initial value, so an unchanged rewrite
        # passes and a real difference fails. One-shot bookkeeping bits
        # are compared under their canonical occurrence names.
        back_a = {v: k for k, v in renames_a.items()}
        back_b = {v: k for k, v in renames_b.items()}
        keys = {renames_a.get(k, k) for k in eval_a.writes} | {
            renames_b.get(k, k) for k in eval_b.writes
        }
        diff = []
        for key in sorted(keys):
            if key in internal and not key.startswith("__shot_"):
                continue
            val_a = store_a.get(back_a.get(key, key))
            val_b = store_b.get(back_b.get(key, key))
            if val_a != val_b:
                diff.append(key)
        if diff:
            failures.append(f"trial {trial}: store differs on {diff[:5]}")

    return EquivReport(equivalent=not failures, trials=trials, failures=failures)
