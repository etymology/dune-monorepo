"""Top-level transpiler: Python source → Ladder Logic text.

Usage:
    from dune_winder.transpiler import transpile

    ld_text = transpile(python_source, function_names=["cap_segments_speed_by_axis_velocity"])
    print(ld_text)

CLI:
    python -m dune_winder.transpiler <source.py> [func_name ...]
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from .ir_to_ld import LDEmitter
from .py_to_ir import PythonToIR
from .regalloc import RegisterAllocator

# Map Python function names → LD routine names
ROUTINE_NAME_MAP: dict[str, str] = {
    "cap_segments_speed_by_axis_velocity": "CapSegSpeed",
    "_segment_tangent_component_bounds":   "SegTangentBounds",
    "_max_abs_sin_over_sweep":             "MaxAbsSinSweep",
    "_max_abs_cos_over_sweep":             "MaxAbsCosSweep",
    "circle_center_for_segment":           "CircleCenterForSeg",
    "arc_sweep_rad":                       "ArcSweepRad",
}

# Topological order: callees before callers so JSR sigs are resolved
FUNCTION_ORDER = [
    "_max_abs_sin_over_sweep",
    "_max_abs_cos_over_sweep",
    "arc_sweep_rad",
    "circle_center_for_segment",
    "_segment_tangent_component_bounds",
    "cap_segments_speed_by_axis_velocity",
]


def _eval_const(node: ast.expr) -> float | None:
    """Try to evaluate a simple constant expression to a number."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _eval_const(node.operand)
        return -v if v is not None else None
    return None


def transpile(
    source: str,
    function_names: list[str] | None = None,
    seg_count_var: str = "seg_count",
) -> str:
    """Transpile Python source to Ladder Logic text.

    Args:
        source: Python source code string.
        function_names: Which functions to transpile.  Defaults to all known
            functions in FUNCTION_ORDER that appear in the source.
        seg_count_var: Name of the DINT register holding the segment count.

    Returns:
        Ladder Logic text (one rung per line).
    """
    tree = ast.parse(source)

    # Index all function defs by name
    func_defs: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_defs[node.name] = node

    # Determine which functions to compile and in what order
    if function_names is None:
        ordered = [n for n in FUNCTION_ORDER if n in func_defs]
        # Only compile known call-tree functions
    else:
        # Expand requested names to include callees
        requested = set(function_names)
        ordered = [n for n in FUNCTION_ORDER if n in requested and n in func_defs]
        for n in requested:
            if n not in ordered and n in func_defs:
                ordered.append(n)

    if not ordered:
        return "; No matching functions found\n"

    # Collect module-level integer constants (top-level only, not function bodies)
    module_consts: dict[str, float] = {}
    for node in tree.body:   # only direct children of the module
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (isinstance(t, ast.Name)
                        and isinstance(node.value, (ast.Constant, ast.UnaryOp))):
                    v = _eval_const(node.value)
                    if v is not None:
                        module_consts[t.id] = v

    alloc = RegisterAllocator()
    converter = PythonToIR(
        alloc=alloc,
        seg_count_var=seg_count_var,
        routine_name_map=ROUTINE_NAME_MAP,
        module_consts=module_consts,
    )

    routines = []
    for name in ordered:
        if name in func_defs:
            routines.append(converter.convert_function(func_defs[name]))

    emitter = LDEmitter()
    lines = emitter.emit_all(routines)
    return "\n".join(lines)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: python -m dune_winder.transpiler <source.py> [more.py ...] [func_name ...]",
              file=sys.stderr)
        sys.exit(1)

    # Collect all .py file paths first; remaining args are function names
    source_paths = []
    func_names_args = []
    for arg in args:
        p = Path(arg)
        if p.suffix == ".py":
            if not p.exists():
                print(f"File not found: {p}", file=sys.stderr)
                sys.exit(1)
            source_paths.append(p)
        else:
            func_names_args.append(arg)

    if not source_paths:
        print("No .py source files given.", file=sys.stderr)
        sys.exit(1)

    # Concatenate all sources separated by a newline
    source = "\n".join(p.read_text(encoding="utf-8") for p in source_paths)
    func_names = func_names_args if func_names_args else None

    result = transpile(source, func_names)
    print(result)


if __name__ == "__main__":
    main()
