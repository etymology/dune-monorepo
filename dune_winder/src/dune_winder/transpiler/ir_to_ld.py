"""IR → Rockwell Ladder Logic text.

Output format: one rung per line, space-separated instructions.
  BST ... NXB ... BND  for OR branches
  JMP lbl / LBL lbl    for control flow
  CPT dest expr        for math
  MOV src dest         for simple moves
  TRN src dest         for truncate (standalone, not inside CPT)
"""
from __future__ import annotations
from .ir import (
    Assign, BinOp, Comment, Cmp, Condition, Const, CptCall, Expr,
    Fault, If, IRNode, IsInf, IsNotInf, JSRCall, Loop, OrCond, AndCond,
    Reg, RegExpr, Return, Routine, SegField, SegFieldExpr, SetBool, UnaryOp,
    XicCond, XioCond,
)
from .types import PLCType

_PI = "3.14159265358979"
_INF = "3.4028235E+38"


class LDEmitter:
    def __init__(self) -> None:
        self._lines: list[str] = []
        self._label_counter = 0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def emit_routine(self, routine: Routine) -> list[str]:
        self._lines = []
        end_lbl = f"lbl_{routine.name}_end"

        # Header comments
        self._lines.append(f"; {'='*60}")
        self._lines.append(f"; Routine: {routine.name}")
        for c in routine.alloc_comments:
            self._lines.append(c)
        if routine.in_params:
            self._lines.append("; Inputs:  " +
                "  ".join(f"{r}={n}" for n, r in routine.in_params))
        if routine.out_params:
            self._lines.append("; Outputs: " +
                "  ".join(f"{r}={n}" for n, r in routine.out_params))
        self._lines.append(f"; {'='*60}")

        for node in routine.body:
            self._emit_node(node, end_lbl)

        self._lines.append(f"LBL {end_lbl}")

        return self._fixup_bare_labels(self._lines)

    def emit_all(self, routines: list[Routine]) -> list[str]:
        result: list[str] = []
        for r in routines:
            result.extend(self.emit_routine(r))
            result.append("")
        return result

    # ------------------------------------------------------------------
    # Node dispatch
    # ------------------------------------------------------------------

    def _emit_node(self, node: IRNode, end_lbl: str) -> None:
        if isinstance(node, Comment):
            self._lines.append(node.text)
        elif isinstance(node, Assign):
            self._emit_assign(node)
        elif isinstance(node, SetBool):
            instr = "OTL" if node.value else "OTU"
            self._lines.append(f"{instr} {node.reg}")
        elif isinstance(node, If):
            self._emit_if(node, end_lbl)
        elif isinstance(node, Loop):
            self._emit_loop(node, end_lbl)
        elif isinstance(node, JSRCall):
            self._emit_jsr(node)
        elif isinstance(node, Return):
            if node.value is not None and node.out_reg is not None:
                self._emit_assign(Assign(node.out_reg, node.value))
            self._lines.append(f"JMP {node.end_label}")
        elif isinstance(node, Fault):
            self._lines.append(f"OTL {node.fault_reg}")
            self._lines.append(f"JMP {node.end_label}")

    # ------------------------------------------------------------------
    # Assign / CPT / MOV / TRN
    # ------------------------------------------------------------------

    def _emit_assign(self, node: Assign) -> None:
        dest_s = str(node.dest)
        expr = node.expr

        # Check if this is a multi-rung expansion
        if isinstance(expr, CptCall):
            tag = expr.func
            if tag == "ATAN2":
                self._emit_atan2(expr.args[0], expr.args[1], node.dest)
                return
            if tag == "MIN":
                self._emit_min(expr.args[0], expr.args[1], node.dest)
                return
            if tag == "MAX":
                self._emit_max(expr.args[0], expr.args[1], node.dest)
                return
            if tag == "CEIL":
                self._emit_ceil(expr.args[0], node.dest)
                return
            if tag == "TRUNC":
                # Standalone TRN instruction — cannot appear inside CPT
                self._emit_trunc(expr.args[0], node.dest)
                return
            if tag == "ISINF":
                # Emit a bool result: GEQ ABS(x) INF → BOOLS[k]
                x = self._mat_str(expr.args[0])
                self._lines.append(f"CPT {dest_s} ABS({x})")
                return

        # Simple MOV if expr is a plain register or constant
        if isinstance(expr, (RegExpr, SegFieldExpr, Const)):
            self._lines.append(f"MOV {self._expr_str(expr)} {dest_s}")
            return

        # Otherwise CPT
        self._lines.append(f"CPT {dest_s} {self._expr_str(expr)}")

    # ------------------------------------------------------------------
    # Expression → string (for use inside CPT)
    # ------------------------------------------------------------------

    def _expr_str(self, expr: Expr) -> str:
        if isinstance(expr, Const):
            return str(expr)
        if isinstance(expr, RegExpr):
            return str(expr.reg)
        if isinstance(expr, SegFieldExpr):
            return str(expr.sf)
        if isinstance(expr, UnaryOp):
            if expr.op == "-":
                return f"-{self._expr_str(expr.operand)}"
            return f"NOT({self._expr_str(expr.operand)})"
        if isinstance(expr, BinOp):
            l = self._expr_str(expr.left)
            r = self._expr_str(expr.right)
            return f"{l}{expr.op}{r}"
        if isinstance(expr, CptCall):
            tag = expr.func
            if tag == "SQR_HYPOT":
                a = self._expr_str(expr.args[0])
                b = self._expr_str(expr.args[1])
                return f"SQR({a}*{a}+{b}*{b})"
            if tag == "TRUNC":
                # TRUNC cannot appear inside a CPT equation — materialise via TRN
                inner_s = self._mat_str(expr.args[0])
                tmp = Reg(PLCType.DINT, self._alloc_dint())
                self._lines.append(f"TRN {inner_s} {tmp}")
                return str(tmp)
            # Expansion tags used inline (will be materialised by caller)
            args_s = ",".join(self._expr_str(a) for a in expr.args)
            if tag in ("ATAN2", "MIN", "MAX", "CEIL", "ISINF"):
                # Can't inline — caller should have handled these
                return f"_{tag.lower()}_result"
            return f"{tag}({args_s})"
        return "0.0"

    # ------------------------------------------------------------------
    # Materialise helper: returns a simple tag string usable in non-CPT
    # instructions (GRT, LES, MOV, etc.).  Emits a CPT prereq rung if the
    # expression is complex.
    # ------------------------------------------------------------------

    def _mat_str(self, expr: Expr) -> str:
        """Return a simple tag for use in non-CPT instructions.

        If *expr* is already a register, constant, or segment field it is
        returned as-is.  Otherwise a scratch REAL is allocated, a CPT rung is
        emitted to compute the value into it, and the scratch tag is returned.
        """
        if isinstance(expr, (Const, RegExpr, SegFieldExpr)):
            return self._expr_str(expr)
        if isinstance(expr, CptCall) and expr.func == "TRUNC":
            # Handle TRUNC specially: emit TRN, return DINT scratch
            inner_s = self._mat_str(expr.args[0])
            tmp = Reg(PLCType.DINT, self._alloc_dint())
            self._lines.append(f"TRN {inner_s} {tmp}")
            return str(tmp)
        tmp = Reg(PLCType.REAL, self._alloc_real())
        self._lines.append(f"CPT {tmp} {self._expr_str(expr)}")
        return str(tmp)

    # ------------------------------------------------------------------
    # Condition → rung prefix string(s)
    # ------------------------------------------------------------------

    def _cond_str(self, cond: Condition) -> str:
        """Return a rung prefix for a simple condition (no BST/NXB needed).

        May emit CPT prereq rungs for complex sub-expressions.
        """
        if isinstance(cond, Cmp):
            l = self._mat_str(cond.left)
            r = self._mat_str(cond.right)
            return f"{cond.instr} {l} {r}"
        if isinstance(cond, XicCond):
            return f"XIC {cond.reg}"
        if isinstance(cond, XioCond):
            return f"XIO {cond.reg}"
        if isinstance(cond, IsInf):
            return f"GEQ {self._mat_str(cond.expr)} {_INF}"
        if isinstance(cond, IsNotInf):
            return f"LES {self._mat_str(cond.expr)} {_INF}"
        # AndCond: space-joined contacts
        if isinstance(cond, AndCond):
            return " ".join(self._cond_str(p) for p in cond.parts)
        return ""

    def _emit_cond_prereqs(self, cond: Condition, result_bool: Reg) -> None:
        """For OR conditions, emit BST...NXB...BND OTL result_bool."""
        if isinstance(cond, OrCond):
            parts = [self._cond_str(p) for p in cond.parts]
            bst_body = " NXB ".join(parts)
            self._lines.append(f"BST {bst_body} BND OTL {result_bool}")

    def _next_label(self, prefix: str) -> str:
        n = self._label_counter
        self._label_counter += 1
        return f"lbl_{prefix}_{n}"

    # ------------------------------------------------------------------
    # If / else
    # ------------------------------------------------------------------

    def _emit_if(self, node: If, end_lbl: str) -> None:
        lbl_else = self._next_label("else")
        lbl_end = self._next_label("end")

        # For OR conditions we need a temp BOOL
        or_bool: Reg | None = None
        if isinstance(node.cond, OrCond):
            or_bool = Reg(PLCType.BOOL, self._alloc_bool())
            self._emit_cond_prereqs(node.cond, or_bool)

        # Emit negated condition → JMP lbl_else
        neg = node.cond.negated()
        if isinstance(neg, OrCond):
            # neg of AndCond is OrCond
            b = Reg(PLCType.BOOL, self._alloc_bool())
            parts = [self._cond_str(p) for p in neg.parts]
            bst_body = " NXB ".join(parts)
            self._lines.append(f"BST {bst_body} BND OTL {b}")
            self._lines.append(f"XIC {b} JMP {lbl_else}")
        else:
            neg_str = self._cond_str(neg)
            if neg_str:
                self._lines.append(f"{neg_str} JMP {lbl_else}")
            else:
                self._lines.append(f"JMP {lbl_else}")

        # Then body
        for n2 in node.then_body:
            self._emit_node(n2, end_lbl)

        if node.else_body:
            self._lines.append(f"JMP {lbl_end}")
            self._lines.append(f"LBL {lbl_else}")
            for n2 in node.else_body:
                self._emit_node(n2, end_lbl)
            self._lines.append(f"LBL {lbl_end}")
        else:
            self._lines.append(f"LBL {lbl_else}")

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    def _emit_loop(self, node: Loop, end_lbl: str) -> None:
        lbl_top = self._next_label("loop")
        lbl_end = self._next_label("loop_end")

        # Initialise counter
        self._lines.append(f"MOV 0 {node.counter}")
        self._lines.append(f"LBL {lbl_top}")

        # Exit condition: GEQ counter limit
        limit_s = str(node.limit) if isinstance(node.limit, Reg) else self._expr_str(node.limit)
        self._lines.append(f"GEQ {node.counter} {limit_s} JMP {lbl_end}")

        # Body
        for n2 in node.body:
            self._emit_node(n2, end_lbl)

        # Increment and loop back
        self._lines.append(f"ADD {node.counter} 1 {node.counter}")
        self._lines.append(f"JMP {lbl_top}")
        self._lines.append(f"LBL {lbl_end}")

    # ------------------------------------------------------------------
    # JSR
    # ------------------------------------------------------------------

    def _emit_jsr(self, node: JSRCall) -> None:
        # Pre-load input args
        for dest_reg, val_expr in node.in_args:
            val_s = self._mat_str(val_expr)
            self._lines.append(f"MOV {val_s} {dest_reg}")
        self._lines.append(f"JSR {node.routine}")
        # Read output args
        for src_reg, dest_reg in node.out_args:
            if src_reg.index >= 9000:
                # Placeholder: callee ret reg not yet resolved — emit comment
                self._lines.append(
                    f"; TODO: MOV {node.routine}_ret_{src_reg.index - 9000} {dest_reg}")
            else:
                self._lines.append(f"MOV {src_reg} {dest_reg}")

    # ------------------------------------------------------------------
    # Multi-rung expansions
    # ------------------------------------------------------------------

    def _emit_atan2(self, y: Expr, x: Expr, dest: Reg | SegField) -> None:
        dest_s = str(dest)
        y_s = self._mat_str(y)
        x_s = self._mat_str(x)
        lbl_done = self._next_label("atan2_done")
        # case x > 0
        self._lines.append(
            f"GRT {x_s} 0.0 CPT {dest_s} ATN({y_s}/{x_s}) JMP {lbl_done}")
        # case x < 0, y >= 0
        self._lines.append(
            f"LES {x_s} 0.0 GEQ {y_s} 0.0 CPT {dest_s} ATN({y_s}/{x_s})+{_PI} JMP {lbl_done}")
        # case x < 0, y < 0
        self._lines.append(
            f"LES {x_s} 0.0 LES {y_s} 0.0 CPT {dest_s} ATN({y_s}/{x_s})-{_PI} JMP {lbl_done}")
        # x = 0, y > 0
        self._lines.append(
            f"EQU {x_s} 0.0 GRT {y_s} 0.0 MOV 1.5707963267949 {dest_s} JMP {lbl_done}")
        # x = 0, y < 0
        self._lines.append(
            f"EQU {x_s} 0.0 LES {y_s} 0.0 MOV -1.5707963267949 {dest_s} JMP {lbl_done}")
        # x = 0, y = 0
        self._lines.append(f"MOV 0.0 {dest_s}")
        self._lines.append(f"LBL {lbl_done}")

    def _emit_min(self, a: Expr, b: Expr, dest: Reg | SegField) -> None:
        dest_s = str(dest)
        a_s = self._mat_str(a)
        b_s = self._mat_str(b)
        lbl_a = self._next_label("min_a")
        lbl_end = self._next_label("min_end")
        self._lines.append(f"LES {a_s} {b_s} JMP {lbl_a}")
        self._lines.append(f"MOV {b_s} {dest_s} JMP {lbl_end}")
        self._lines.append(f"LBL {lbl_a} MOV {a_s} {dest_s}")
        self._lines.append(f"LBL {lbl_end}")

    def _emit_max(self, a: Expr, b: Expr, dest: Reg | SegField) -> None:
        dest_s = str(dest)
        a_s = self._mat_str(a)
        b_s = self._mat_str(b)
        lbl_a = self._next_label("max_a")
        lbl_end = self._next_label("max_end")
        self._lines.append(f"GRT {a_s} {b_s} JMP {lbl_a}")
        self._lines.append(f"MOV {b_s} {dest_s} JMP {lbl_end}")
        self._lines.append(f"LBL {lbl_a} MOV {a_s} {dest_s}")
        self._lines.append(f"LBL {lbl_end}")

    def _emit_ceil(self, x: Expr, dest: Reg | SegField) -> None:
        """math.ceil(x) → integer dest.

        TRN truncates toward zero (= floor for positive, ceiling for negative).
        If float(TRN(x)) < x the value was positive-fractional: add 1.
        """
        dest_s = str(dest)
        lbl_done = self._next_label("ceil_done")
        x_s = self._mat_str(x)                              # simple REAL tag
        tmp_int = Reg(PLCType.DINT, self._alloc_dint())     # TRN result
        tmp_float = Reg(PLCType.REAL, self._alloc_real())   # back-converted for cmp
        self._lines.append(f"TRN {x_s} {tmp_int}")         # tmp_int = trunc(x)
        self._lines.append(f"MOV {tmp_int} {tmp_float}")    # tmp_float = float(trunc)
        # If float(trunc) >= x: exact integer or negative — already the ceiling
        self._lines.append(f"GEQ {tmp_float} {x_s} JMP {lbl_done}")
        # Positive fractional: add 1
        self._lines.append(f"ADD {tmp_int} 1 {tmp_int}")
        # Store result (label is merged with this MOV by _fixup_bare_labels)
        self._lines.append(f"LBL {lbl_done}")
        self._lines.append(f"MOV {tmp_int} {dest_s}")

    def _emit_trunc(self, x: Expr, dest: Reg | SegField) -> None:
        """math.floor / int(x) → TRN (standalone, not inside CPT)."""
        x_s = self._mat_str(x)
        self._lines.append(f"TRN {x_s} {dest}")

    # ------------------------------------------------------------------
    # Post-processing: fix bare LBL rungs
    # ------------------------------------------------------------------

    @staticmethod
    def _fixup_bare_labels(lines: list[str]) -> list[str]:
        """Merge bare 'LBL name' rungs with the following instruction rung.

        A rung is bare when it contains only 'LBL name' with no output
        instruction.  Rockwell requires every rung to carry at least one
        output.  We fix this by prepending the label to the next rung.
        If a bare label is the very last line (routine end), append NOP.
        """
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # Bare label: "LBL name" — label name itself contains no spaces
            if line.startswith("LBL ") and " " not in line[4:].strip():
                # Skip over any intervening blank/comment lines, collecting them
                j = i + 1
                passed: list[str] = []
                while j < len(lines) and (
                        not lines[j].strip() or lines[j].lstrip().startswith(";")):
                    passed.append(lines[j])
                    j += 1
                if j < len(lines):
                    next_line = lines[j]
                    if next_line.startswith("LBL ") and " " not in next_line[4:].strip():
                        # Next is also a bare label — emit current with NOP
                        result.append(line + " NOP")
                        result.extend(passed)
                    else:
                        # Merge: prepend label to next instruction
                        result.extend(passed)
                        result.append(line + " " + next_line)
                        i = j + 1
                        continue
                else:
                    # Trailing bare label (routine end) — append NOP
                    result.extend(passed)
                    result.append(line + " NOP")
            else:
                result.append(line)
            i += 1
        return result

    # ------------------------------------------------------------------
    # Scratch register helpers (allocate from high indices to avoid conflicts)
    # ------------------------------------------------------------------

    _scratch_real = 900
    _scratch_bool = 900
    _scratch_dint = 900

    def _alloc_real(self) -> int:
        idx = LDEmitter._scratch_real
        LDEmitter._scratch_real += 1
        return idx

    def _alloc_bool(self) -> int:
        idx = LDEmitter._scratch_bool
        LDEmitter._scratch_bool += 1
        return idx

    def _alloc_dint(self) -> int:
        idx = LDEmitter._scratch_dint
        LDEmitter._scratch_dint += 1
        return idx
