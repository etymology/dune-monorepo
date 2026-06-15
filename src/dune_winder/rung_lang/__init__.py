"""LLM-friendly ladder language (.rung) <-> L5X.

See plans/llm-friendly-ladder-language-to-l5x.md. The package owns:

- parsing Studio's paren-dialect rung text (rllscrap) into a rung IR,
- rendering the IR as readable ``.rung`` source (the form LLMs edit),
- compiling edited ``.rung`` back to rung IR, rllscrap, and an importable
  routine L5X (donor context shell + synthesized tags for new locals),
- a semantic equivalence checker used by CI and ``rung-compile``.

Standalone from ``plc_ladder``/``transpiler`` (both retired as authoring
paths); the rllscrap parser is a fresh implementation, not an import.
"""

from .parse_rllscrap import parse_rllscrap_text
from .render import render_routine
from .rung_ir import BranchIR, Instr, RoutineIR, RungIR

__all__ = [
    "BranchIR",
    "Instr",
    "RoutineIR",
    "RungIR",
    "parse_rllscrap_text",
    "render_routine",
]
