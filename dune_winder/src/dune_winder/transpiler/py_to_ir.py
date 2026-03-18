"""Convert Python AST → IR.

Handles the Python subset used in cap_segments_speed_by_axis_velocity and
its call tree:
  - FunctionDef with typed annotations
  - For (enumerate/range), If, Assign, AugAssign, Return, Raise
  - BinOp, UnaryOp, BoolOp, Compare, Call (math.*, min, max, abs, float, int)
  - Attribute access on MotionSegment → SegQueue[loop_idx].Field
  - Tuple unpacking from function calls
  - replace(seg, speed=x) → SegQueue write
  - Optional/None handling → companion BOOL
"""
from __future__ import annotations

import ast
import math
from typing import Any

from .builtins import CONST_MAP, CPT_INLINE, EXPAND, SEG_ATTR_MAP, SEG_FIELD_TYPE
from .ir import (
    Assign, AndCond, BinOp, Comment, Cmp, Condition, Const, CptCall, Expr,
    Fault, If, IRNode, IsInf, IsNotInf, JSRCall, Loop, OrCond, Reg,
    RegExpr, Return, Routine, SegField, SegFieldExpr, SetBool, UnaryOp,
    XicCond, XioCond,
)
from .regalloc import RegisterAllocator
from .types import PLCType, SegField as SegFieldType, plc_type_from_annotation


# Names of MotionSegment-typed variables within a function
_SEG_TYPES = {"MotionSegment", "seg", "start", "seg1", "seg2"}

# Python comparison op → our op string
_CMP_OPS = {
    ast.Eq: "==", ast.NotEq: "!=",
    ast.Lt: "<",  ast.LtE: "<=",
    ast.Gt: ">",  ast.GtE: ">=",
}

# Python binary op → string
_BIN_OPS = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.Mod: "%", ast.Pow: "**", ast.FloorDiv: "/",
}


class _Scope:
    """Tracks variable→Reg within one function being compiled."""

    def __init__(self, alloc: RegisterAllocator) -> None:
        self.alloc = alloc
        self.vars: dict[str, Reg] = {}
        # name → bool: is this var an Optional that needs a companion BOOL
        self.optional_valid: dict[str, Reg] = {}
        # variables that hold tuple values returned from subroutines
        self.tuple_vars: dict[str, list[Reg]] = {}
        # current loop index register (for SegQueue[idx] access)
        self.loop_idx: Reg | None = None
        # name of the 'seg' variable in a for-enumerate loop
        self.seg_var: str | None = None
        # name of the 'segments' / input list variable
        self.list_var: str | None = None
        # fault bool for this routine
        self.fault_reg: Reg | None = None
        # end label for this routine
        self.end_label: str = ""
        # return output register
        self.ret_regs: list[Reg] = []

    def get_or_alloc(self, name: str, typ: PLCType) -> Reg:
        if name not in self.vars:
            self.vars[name] = self.alloc.alloc(typ, name)
        return self.vars[name]

    def ensure(self, name: str, typ: PLCType) -> Reg:
        return self.get_or_alloc(name, typ)


class PythonToIR(ast.NodeVisitor):
    """Converts a Python module's function definitions to a list of Routine IR nodes."""

    def __init__(
        self,
        alloc: RegisterAllocator,
        seg_count_var: str = "seg_count",
        routine_name_map: dict[str, str] | None = None,
        module_consts: dict[str, float] | None = None,
    ) -> None:
        self.alloc = alloc
        self.seg_count_var = seg_count_var
        self.routine_name_map = routine_name_map or {}
        self.module_consts: dict[str, float] = module_consts or {}
        self.routines: list[Routine] = []
        # After first pass: function name → (in_regs, out_regs) for JSR generation
        self._routine_sigs: dict[str, tuple[list[Reg], list[Reg]]] = {}

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------

    def convert_function(self, func_def: ast.FunctionDef) -> Routine:
        ld_name = self.routine_name_map.get(func_def.name, func_def.name)
        scope = _Scope(self.alloc)
        scope.end_label = f"lbl_{ld_name}_end"

        # --- Allocate parameters ---
        in_params: list[tuple[str, Reg]] = []
        for arg in func_def.args.args:
            ann = self._annotation_str(arg.annotation)
            # MotionSegment parameter → allocate a DINT as segment index
            if ann in ("MotionSegment",) or "MotionSegment" == ann:
                reg = self.alloc.alloc(PLCType.IDX, f"{arg.arg}_idx")
                scope.vars[arg.arg] = reg
                # Use as the loop index for SegQueue access in this function
                if scope.loop_idx is None:
                    scope.loop_idx = reg
                in_params.append((f"{arg.arg}_idx", reg))
                continue
            typ = self._param_type(ann, arg.arg)
            if typ is None:
                continue  # skip 'self', 'segments' list param (handled separately)
            reg = self.alloc.alloc(typ, arg.arg)
            scope.vars[arg.arg] = reg
            in_params.append((arg.arg, reg))

        # Special: 'segments' list parameter → seg_count DINT + optional start_xy BOOLs
        self._handle_list_param(func_def, scope, in_params)

        # Fault register
        scope.fault_reg = self.alloc.alloc(PLCType.BOOL, f"{func_def.name}_fault")

        # Return register(s) — determined by return annotation
        out_params = self._alloc_return_regs(func_def, scope)

        # --- Convert body ---
        body: list[IRNode] = []
        for stmt in func_def.body:
            body.extend(self._convert_stmt(stmt, scope))

        routine = Routine(
            name=ld_name,
            in_params=in_params,
            out_params=out_params,
            body=body,
            alloc_comments=self.alloc.summary_comments(),
        )
        self._routine_sigs[func_def.name] = (
            [r for _, r in in_params],
            [r for _, r in out_params],
        )
        self.routines.append(routine)
        return routine

    # ------------------------------------------------------------------
    # Parameter helpers
    # ------------------------------------------------------------------

    def _annotation_str(self, ann: ast.expr | None) -> str:
        if ann is None:
            return ""
        if isinstance(ann, ast.Name):
            return ann.id
        if isinstance(ann, ast.Constant):
            return str(ann.value)
        if isinstance(ann, ast.Subscript):
            # e.g. list[MotionSegment], Optional[tuple[...]]
            return ast.unparse(ann)
        return ast.unparse(ann)

    def _param_type(self, ann: str, name: str) -> PLCType | None:
        if ann.startswith("list[") or ann.startswith("List["):
            return None  # handled as seg_count
        if "MotionSegment" in ann:
            return None
        if ann.startswith("Optional[tuple"):
            return None  # handled as start_x/start_y + valid flag
        if ann == "float":
            return PLCType.REAL
        if ann == "int":
            return PLCType.DINT
        if ann == "bool":
            return PLCType.BOOL
        # fallback
        return PLCType.REAL

    def _handle_list_param(
        self, func_def: ast.FunctionDef, scope: _Scope,
        in_params: list[tuple[str, Reg]]
    ) -> None:
        """Allocate seg_count and start_xy regs for functions that take a list."""
        for arg in func_def.args.args:
            ann = self._annotation_str(arg.annotation)
            if ann.startswith("list[") or ann.startswith("List["):
                scope.list_var = arg.arg
                reg = self.alloc.alloc(PLCType.DINT, self.seg_count_var)
                scope.vars[self.seg_count_var] = reg
                in_params.insert(0, (self.seg_count_var, reg))
            elif ann.startswith("Optional[tuple"):
                # start_xy: allocate start_x, start_y, start_xy_valid
                rx = self.alloc.alloc(PLCType.REAL, f"{arg.arg}_x")
                ry = self.alloc.alloc(PLCType.REAL, f"{arg.arg}_y")
                rv = self.alloc.alloc(PLCType.BOOL, f"{arg.arg}_valid")
                scope.vars[f"{arg.arg}_x"] = rx
                scope.vars[f"{arg.arg}_y"] = ry
                scope.vars[f"{arg.arg}"] = rv   # None check → XIO rv
                scope.optional_valid[arg.arg] = rv
                in_params.extend([(f"{arg.arg}_x", rx), (f"{arg.arg}_y", ry),
                                   (f"{arg.arg}_valid", rv)])

    def _alloc_return_regs(
        self, func_def: ast.FunctionDef, scope: _Scope
    ) -> list[tuple[str, Reg]]:
        ann = self._annotation_str(func_def.returns)
        if not ann or ann in ("None", "list[MotionSegment]", "List[MotionSegment]"):
            return []
        if ann == "float":
            r = self.alloc.alloc(PLCType.REAL, f"{func_def.name}_ret")
            scope.ret_regs = [r]
            return [("return", r)]
        if ann.startswith("tuple[float"):
            # e.g. tuple[float, float]
            parts = ann.count("float")
            regs = [self.alloc.alloc(PLCType.REAL, f"{func_def.name}_ret_{i}")
                    for i in range(parts)]
            scope.ret_regs = regs
            return [(f"return_{i}", r) for i, r in enumerate(regs)]
        if ann.startswith("Optional[float"):
            r = self.alloc.alloc(PLCType.REAL, f"{func_def.name}_ret")
            rv = self.alloc.alloc(PLCType.BOOL, f"{func_def.name}_ret_valid")
            scope.ret_regs = [r]
            scope.optional_valid["_return"] = rv
            return [("return", r), ("return_valid", rv)]
        return []

    # ------------------------------------------------------------------
    # Statement conversion
    # ------------------------------------------------------------------

    def _convert_stmt(self, stmt: ast.stmt, scope: _Scope) -> list[IRNode]:
        if isinstance(stmt, ast.Return):
            return self._conv_return(stmt, scope)
        if isinstance(stmt, ast.Raise):
            return self._conv_raise(stmt, scope)
        if isinstance(stmt, ast.Assign):
            return self._conv_assign(stmt, scope)
        if isinstance(stmt, ast.AnnAssign):
            return self._conv_ann_assign(stmt, scope)
        if isinstance(stmt, ast.AugAssign):
            return self._conv_aug_assign(stmt, scope)
        if isinstance(stmt, ast.If):
            return self._conv_if(stmt, scope)
        if isinstance(stmt, ast.For):
            return self._conv_for(stmt, scope)
        if isinstance(stmt, ast.Expr):
            if isinstance(stmt.value, ast.Constant):
                return []  # docstring or bare string
            # Handle out.append(replace(seg, speed=x)) → SegQueue write
            if isinstance(stmt.value, ast.Call):
                return self._conv_expr_stmt(stmt.value, scope)
        return [Comment(f"; unsupported: {ast.unparse(stmt)}")]

    def _conv_expr_stmt(self, call: ast.Call, scope: _Scope) -> list[IRNode]:
        """Handle expression statements that are calls: out.append(replace(...))."""
        # out.append(replace(seg, field=val, ...))
        if (isinstance(call.func, ast.Attribute)
                and call.func.attr == "append"
                and call.args):
            inner = call.args[0]
            if isinstance(inner, ast.Call):
                inner_name = (inner.func.id if isinstance(inner.func, ast.Name)
                              else "")
                if inner_name == "replace":
                    return self._conv_replace(inner, scope)
        # replace(seg, ...) as bare statement
        if isinstance(call.func, ast.Name) and call.func.id == "replace":
            return self._conv_replace(call, scope)
        return [Comment(f"; unsupported call: {ast.unparse(call)}")]

    def _conv_return(self, node: ast.Return, scope: _Scope) -> list[IRNode]:
        if node.value is None:
            return [Return(None, None, scope.end_label)]

        # return segments / return out — in-place modification, no value to write
        if isinstance(node.value, ast.Name):
            name = node.value.id
            if name in (scope.list_var, "out"):
                return [Return(None, None, scope.end_label)]

        # return (a, b) tuple → write to ret_regs
        if isinstance(node.value, ast.Tuple):
            nodes: list[IRNode] = []
            for i, elt in enumerate(node.value.elts):
                expr = self._conv_expr(elt, scope)
                if i < len(scope.ret_regs):
                    nodes.append(Assign(scope.ret_regs[i], expr))
            nodes.append(Return(None, None, scope.end_label))
            return nodes

        # return None → mark optional as invalid
        if isinstance(node.value, ast.Constant) and node.value.value is None:
            nodes = []
            if "_return" in scope.optional_valid:
                nodes.append(SetBool(scope.optional_valid["_return"], False))
            nodes.append(Return(None, None, scope.end_label))
            return nodes

        expr = self._conv_expr(node.value, scope)
        out_reg = scope.ret_regs[0] if scope.ret_regs else None
        if out_reg is not None:
            return [Assign(out_reg, expr), Return(None, None, scope.end_label)]
        return [Return(expr, out_reg, scope.end_label)]

    def _conv_raise(self, node: ast.Raise, scope: _Scope) -> list[IRNode]:
        fault_reg = scope.fault_reg or self.alloc.alloc(PLCType.BOOL, "fault")
        return [Fault(fault_reg, scope.end_label)]

    def _conv_assign(self, node: ast.Assign, scope: _Scope) -> list[IRNode]:
        # Tuple unpacking: a, b = func(...)
        if (len(node.targets) == 1
                and isinstance(node.targets[0], ast.Tuple)
                and isinstance(node.value, ast.Call)):
            return self._conv_tuple_unpack(node.targets[0], node.value, scope)

        # Tuple unpacking from a previously-returned tuple var: cx, cy = center
        if (len(node.targets) == 1
                and isinstance(node.targets[0], ast.Tuple)
                and isinstance(node.value, ast.Name)):
            name = node.value.id
            if name in scope.tuple_vars:
                src_regs = scope.tuple_vars[name]
                nodes: list[IRNode] = []
                for i, elt in enumerate(node.targets[0].elts):
                    if isinstance(elt, ast.Name) and i < len(src_regs):
                        dest = scope.get_or_alloc(elt.id, src_regs[i].typ)
                        nodes.append(Assign(dest, RegExpr(src_regs[i])))
                return nodes

        # replace(seg, speed=x) special case
        if isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == "replace":
                return self._conv_replace(call, scope)

        # Single-return subroutine call: x = known_func(...)
        if (len(node.targets) == 1
                and isinstance(node.value, ast.Call)):
            func_name = self._call_name(node.value)
            if func_name in self.routine_name_map:
                return self._conv_single_jsr(node.targets[0], node.value, scope)

        nodes: list[IRNode] = []

        # Ternary RHS: x = a if cond else b → If IR node
        if isinstance(node.value, ast.IfExp) and len(node.targets) == 1:
            return self._conv_ternary_assign(node.targets[0], node.value, scope)

        expr = self._conv_expr(node.value, scope)
        for target in node.targets:
            dest = self._conv_lvalue(target, scope, expr)
            if dest is not None:
                nodes.append(Assign(dest, expr))
        return nodes

    def _conv_ternary_assign(
        self, target: ast.expr, ternary: ast.IfExp, scope: _Scope
    ) -> list[IRNode]:
        """x = body if test else orelse → If(test, [x=body], [x=orelse])"""
        # Ensure dest is allocated before we process either branch
        placeholder_expr = self._conv_expr(ternary.body, scope)
        dest = self._conv_lvalue(target, scope, placeholder_expr)
        if dest is None:
            return []
        cond = self._conv_test(ternary.test, scope)
        then_expr = self._conv_expr(ternary.body, scope)
        else_expr = self._conv_expr(ternary.orelse, scope)
        return [If(cond, [Assign(dest, then_expr)], [Assign(dest, else_expr)])]

    def _conv_ann_assign(self, node: ast.AnnAssign, scope: _Scope) -> list[IRNode]:
        if node.value is None:
            return []
        ann = self._annotation_str(node.annotation)
        typ = plc_type_from_annotation(ann)
        if isinstance(node.target, ast.Name):
            name = node.target.id
            # Skip list/out declarations
            if ann.startswith("list["):
                return []
            reg = scope.get_or_alloc(name, typ)
            expr = self._conv_expr(node.value, scope)
            return [Assign(reg, expr)]
        return []

    def _conv_aug_assign(self, node: ast.AugAssign, scope: _Scope) -> list[IRNode]:
        dest = self._conv_lvalue(node.target, scope, None)
        if dest is None:
            return []
        left = RegExpr(dest) if isinstance(dest, Reg) else SegFieldExpr(dest)
        right = self._conv_expr(node.value, scope)
        op = _BIN_OPS.get(type(node.op), "+")
        expr: Expr = BinOp(left, op, right)
        return [Assign(dest, expr)]

    def _conv_if(self, node: ast.If, scope: _Scope) -> list[IRNode]:
        # if not segments: → check seg_count == 0
        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
            if isinstance(node.test.operand, ast.Name):
                name = node.test.operand.id
                if name == scope.list_var:
                    cond: Condition = Cmp("==", RegExpr(
                        scope.vars[self.seg_count_var]), Const(0, PLCType.DINT))
                    then = []
                    for s in node.body:
                        then.extend(self._convert_stmt(s, scope))
                    else_ = []
                    for s in node.orelse:
                        else_.extend(self._convert_stmt(s, scope))
                    return [If(cond, then, else_)]

        cond = self._conv_test(node.test, scope)
        then_body: list[IRNode] = []
        for s in node.body:
            then_body.extend(self._convert_stmt(s, scope))
        else_body: list[IRNode] = []
        for s in node.orelse:
            else_body.extend(self._convert_stmt(s, scope))
        return [If(cond, then_body, else_body)]

    def _conv_for(self, node: ast.For, scope: _Scope) -> list[IRNode]:
        """for idx, seg in enumerate(segments): ..."""
        body_nodes: list[IRNode] = []

        # Detect enumerate pattern
        if (isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Name)
                and node.iter.func.id == "enumerate"):
            idx_name, seg_name = None, None
            if isinstance(node.target, ast.Tuple) and len(node.target.elts) == 2:
                t0, t1 = node.target.elts
                if isinstance(t0, ast.Name):
                    idx_name = t0.id
                if isinstance(t1, ast.Name):
                    seg_name = t1.id

            counter = self.alloc.alloc(PLCType.IDX, idx_name or "_loop_i")
            if idx_name:
                scope.vars[idx_name] = counter
            scope.loop_idx = counter
            scope.seg_var = seg_name

            limit = scope.vars.get(self.seg_count_var,
                                   self.alloc.alloc(PLCType.DINT, self.seg_count_var))

            for s in node.body:
                body_nodes.extend(self._convert_stmt(s, scope))

            scope.loop_idx = None
            scope.seg_var = None
            return [Loop(counter, limit, body_nodes)]

        # range() loop
        if (isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Name)
                and node.iter.func.id == "range"):
            var_name = node.target.id if isinstance(node.target, ast.Name) else "_i"
            counter = self.alloc.alloc(PLCType.IDX, var_name)
            scope.vars[var_name] = counter
            args = node.iter.args
            start_expr: Expr = Const(0, PLCType.DINT)
            stop_expr: Expr
            if len(args) == 1:
                stop_expr = self._conv_expr(args[0], scope)
            else:
                start_expr = self._conv_expr(args[0], scope)
                stop_expr = self._conv_expr(args[1], scope)
            # Emit: counter = start; loop body; counter++
            nodes: list[IRNode] = []
            if not (isinstance(start_expr, Const) and start_expr.value == 0):
                tmp = self.alloc.alloc(PLCType.DINT, f"{var_name}_start")
                nodes.append(Assign(tmp, start_expr))
                counter_init: Expr = RegExpr(tmp)
            else:
                counter_init = Const(0, PLCType.DINT)
            for s in node.body:
                body_nodes.extend(self._convert_stmt(s, scope))
            limit_reg: Expr
            if isinstance(stop_expr, RegExpr):
                limit_reg = stop_expr
            else:
                tmp2 = self.alloc.alloc(PLCType.DINT, f"{var_name}_stop")
                nodes.append(Assign(tmp2, stop_expr))
                limit_reg = RegExpr(tmp2)
            actual_limit = limit_reg.reg if isinstance(limit_reg, RegExpr) else None
            if actual_limit is None:
                actual_limit = self.alloc.alloc(PLCType.DINT, "_loop_stop")
                nodes.append(Assign(actual_limit, stop_expr))
            nodes.append(Loop(counter, actual_limit, body_nodes))
            return nodes

        return [Comment(f"; unsupported for: {ast.unparse(node)}")]

    def _conv_tuple_unpack(
        self, targets: ast.Tuple, call: ast.Call, scope: _Scope
    ) -> list[IRNode]:
        """a, b = some_function(args) → JSR + read ret regs."""
        func_name = self._call_name(call)
        ld_name = self.routine_name_map.get(func_name, func_name)

        in_args = self._build_jsr_in_args(func_name, call, scope)
        # Return registers: we need to know the callee's ret regs
        # Approximate: allocate fresh regs for the tuple elements
        out_regs: list[Reg] = []
        for elt in targets.elts:
            if isinstance(elt, ast.Name):
                typ = PLCType.REAL  # assume float for now
                reg = scope.get_or_alloc(elt.id, typ)
                out_regs.append(reg)

        # Look up callee's actual output registers (compiled before caller)
        _, callee_out_regs = self._routine_sigs.get(func_name, ([], []))

        out_args: list[tuple[Reg, Reg]] = []
        for i, dest_reg in enumerate(out_regs):
            if i < len(callee_out_regs):
                src_reg = callee_out_regs[i]
            else:
                src_reg = Reg(PLCType.REAL, 9000 + i)  # sentinel placeholder
            out_args.append((src_reg, dest_reg))

        jsr = JSRCall(routine=ld_name, in_args=in_args, out_args=out_args)
        return [jsr]

    def _conv_single_jsr(
        self, target: ast.expr, call: ast.Call, scope: _Scope
    ) -> list[IRNode]:
        """x = known_func(args) → JSR + copy callee ret reg(s) to dest."""
        func_name = self._call_name(call)
        ld_name = self.routine_name_map.get(func_name, func_name)
        in_args = self._build_jsr_in_args(func_name, call, scope)
        _, callee_out_regs = self._routine_sigs.get(func_name, ([], []))

        out_args: list[tuple[Reg, Reg]] = []

        if not isinstance(target, ast.Name):
            jsr = JSRCall(routine=ld_name, in_args=in_args, out_args=[])
            return [jsr]

        name = target.id

        if not callee_out_regs:
            jsr = JSRCall(routine=ld_name, in_args=in_args, out_args=[])
            return [jsr]

        # Separate value regs from any trailing valid BOOL
        value_regs = [r for r in callee_out_regs if r.typ != PLCType.BOOL]
        valid_regs = [r for r in callee_out_regs if r.typ == PLCType.BOOL]

        if len(value_regs) == 1:
            # Simple scalar return (float/int)
            dest = scope.get_or_alloc(name, value_regs[0].typ)
            out_args.append((value_regs[0], dest))
        elif len(value_regs) >= 2:
            # Tuple return — store each component under its own reg,
            # record tuple_vars so cx, cy = name unpacking works later
            comp_regs: list[Reg] = []
            for i, vr in enumerate(value_regs):
                comp = scope.get_or_alloc(f"{name}_{i}", vr.typ)
                comp_regs.append(comp)
                out_args.append((vr, comp))
            scope.tuple_vars[name] = comp_regs

        # Optional valid BOOL
        if valid_regs:
            valid_dest = scope.alloc.alloc(PLCType.BOOL, f"{name}_valid")
            scope.optional_valid[name] = valid_dest
            out_args.append((valid_regs[0], valid_dest))

        jsr = JSRCall(routine=ld_name, in_args=in_args, out_args=out_args)
        return [jsr]

    def _conv_replace(self, call: ast.Call, scope: _Scope) -> list[IRNode]:
        """replace(seg, speed=x) → MOV x SegQueue[loop_idx].Speed"""
        nodes: list[IRNode] = []
        for kw in call.keywords:
            field_name = kw.arg
            plc_field = {
                "speed": "Speed", "accel": "Accel", "decel": "Decel",
                "jerk_accel": "JerkAccel", "jerk_decel": "JerkDecel",
                "term_type": "TermType",
            }.get(field_name or "")
            if plc_field and scope.loop_idx is not None:
                sf = SegField(scope.loop_idx, plc_field)
                expr = self._conv_expr(kw.value, scope)
                nodes.append(Assign(sf, expr))
        return nodes

    # Variables with these names are lists/objects — don't allocate registers
    _SKIP_VARS = frozenset({"out", "start", "center"})

    def _conv_lvalue(
        self, target: ast.expr, scope: _Scope, rhs: Any
    ) -> Reg | SegField | None:
        if isinstance(target, ast.Name):
            name = target.id
            if name in self._SKIP_VARS:
                return None
            # Skip list-typed variables
            if name == scope.list_var:
                return None
            # Skip MotionSegment-typed vars (loop seg variable)
            if name == scope.seg_var:
                return None
            typ = self._infer_type(rhs)
            return scope.get_or_alloc(name, typ)
        if isinstance(target, ast.Attribute):
            sf = self._conv_seg_attr(target, scope)
            return sf
        if isinstance(target, ast.Subscript):
            # Handles indexed writes if needed
            return None
        return None

    # ------------------------------------------------------------------
    # Expression conversion
    # ------------------------------------------------------------------

    def _conv_expr(self, node: ast.expr, scope: _Scope) -> Expr:
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                return Const(v, PLCType.BOOL)
            if isinstance(v, int):
                return Const(v, PLCType.DINT)
            if isinstance(v, float):
                return Const(v, PLCType.REAL)
            if v is None:
                return Const(0, PLCType.BOOL)
            return Const(float(v), PLCType.REAL)

        if isinstance(node, ast.Name):
            name = node.id
            if name in CONST_MAP:
                v = CONST_MAP[name]
                return Const(v, PLCType.REAL)
            # Module-level integer constants (SEG_TYPE_LINE, MCCM_DIR_*, etc.)
            if name in self.module_consts:
                v = self.module_consts[name]
                typ = PLCType.DINT if v == int(v) else PLCType.REAL
                return Const(int(v) if typ == PLCType.DINT else v, typ)
            # MotionSegment variable used as expression — return loop index
            if name == scope.seg_var and scope.loop_idx is not None:
                return RegExpr(scope.loop_idx)
            # list variable — return seg_count
            if name == scope.list_var:
                return RegExpr(scope.vars.get(self.seg_count_var,
                                              Reg(PLCType.DINT, 0)))
            if name in scope.vars:
                return RegExpr(scope.vars[name])
            if name in scope.optional_valid:
                return RegExpr(scope.optional_valid[name])
            # Unknown — allocate as REAL
            reg = scope.get_or_alloc(name, PLCType.REAL)
            return RegExpr(reg)

        if isinstance(node, ast.Attribute):
            # math.pi, math.inf etc.
            qualified = f"{ast.unparse(node.value)}.{node.attr}"
            if qualified in CONST_MAP:
                return Const(CONST_MAP[qualified], PLCType.REAL)
            # seg.x, seg.speed etc.
            sf = self._conv_seg_attr(node, scope)
            if sf is not None:
                field_type = SEG_FIELD_TYPE.get(sf.field, PLCType.REAL)
                return SegFieldExpr(sf, field_type)
            return Const(0.0, PLCType.REAL)

        if isinstance(node, ast.BinOp):
            left = self._conv_expr(node.left, scope)
            right = self._conv_expr(node.right, scope)
            op = _BIN_OPS.get(type(node.op), "+")
            typ = PLCType.REAL
            if (getattr(left, "typ", PLCType.REAL) == PLCType.DINT
                    and getattr(right, "typ", PLCType.REAL) == PLCType.DINT
                    and op in ("+", "-", "*")):
                typ = PLCType.DINT
            return BinOp(left, op, right, typ)

        if isinstance(node, ast.UnaryOp):
            operand = self._conv_expr(node.operand, scope)
            if isinstance(node.op, ast.USub):
                return UnaryOp("-", operand, getattr(operand, "typ", PLCType.REAL))
            if isinstance(node.op, ast.Not):
                return UnaryOp("not", operand, PLCType.BOOL)
            return operand

        if isinstance(node, ast.Call):
            return self._conv_call_expr(node, scope)

        if isinstance(node, ast.IfExp):
            # a if cond else b — caller (_conv_assign) should handle this;
            # as a sub-expression fallback return the 'body' value
            return self._conv_expr(node.body, scope)

        if isinstance(node, ast.Subscript):
            # Handle optional_tuple[0] → opt_x reg, optional_tuple[1] → opt_y reg
            if isinstance(node.value, ast.Name):
                name = node.value.id
                if name in scope.optional_valid:
                    idx_val = 0
                    if isinstance(node.slice, ast.Constant):
                        idx_val = int(node.slice.value)
                    suffix = "_x" if idx_val == 0 else "_y"
                    key = f"{name}{suffix}"
                    if key in scope.vars:
                        return RegExpr(scope.vars[key])
                # segments[0].x handled via Attribute (not here)
            return Const(0.0, PLCType.REAL)

        if isinstance(node, ast.Tuple):
            # (a, b) tuple literal — return first element as fallback
            if node.elts:
                return self._conv_expr(node.elts[0], scope)

        return Const(0.0, PLCType.REAL)

    def _conv_call_expr(self, node: ast.Call, scope: _Scope) -> Expr:
        func_name = self._call_name(node)

        # float("inf") — must check before generic CPT_INLINE float handling
        if func_name == "float" and node.args:
            if isinstance(node.args[0], ast.Constant):
                return Const(float(node.args[0].value), PLCType.REAL)
            # float(seg.x) → just pass through the seg field expression
            return self._conv_expr(node.args[0], scope)

        # Inline CPT functions
        if func_name in CPT_INLINE:
            cpt_func, ret_type = CPT_INLINE[func_name]
            if cpt_func == "PASSTHRU":
                return self._conv_expr(node.args[0], scope)
            args = [self._conv_expr(a, scope) for a in node.args]
            return CptCall(cpt_func, args, ret_type)

        # Constants
        if func_name in CONST_MAP:
            return Const(CONST_MAP[func_name], PLCType.REAL)

        # Expansion markers (atan2, ceil, isinf, min, max)
        if func_name in EXPAND:
            tag = EXPAND[func_name]
            args = [self._conv_expr(a, scope) for a in node.args]
            ret_typ = PLCType.DINT if tag == "CEIL" else PLCType.REAL
            return CptCall(tag, args, ret_typ)

        # Other calls (subroutines) — these need to be lifted to statements
        # Return a placeholder register
        tmp = self.alloc.alloc(PLCType.REAL, f"_{func_name}_ret")
        return RegExpr(tmp)

    def _conv_seg_attr(self, node: ast.expr, scope: _Scope) -> SegField | None:
        """Convert seg.attr or seg.via_center_x to SegField."""
        if not isinstance(node, ast.Attribute):
            return None
        attr = node.attr
        if attr not in SEG_ATTR_MAP:
            return None
        plc_field = SEG_ATTR_MAP[attr]
        # Use current loop index if available
        idx = scope.loop_idx if scope.loop_idx is not None else Reg(PLCType.DINT, 0)
        # Check if node.value is a subscript like segments[0]
        if isinstance(node.value, ast.Subscript):
            sub = node.value
            if isinstance(sub.slice, ast.Constant):
                return SegField(int(sub.slice.value), plc_field)
            if isinstance(sub.slice, ast.Name) and sub.slice.id in scope.vars:
                return SegField(scope.vars[sub.slice.id], plc_field)
        return SegField(idx, plc_field)

    # ------------------------------------------------------------------
    # Condition conversion
    # ------------------------------------------------------------------

    def _conv_test(self, node: ast.expr, scope: _Scope) -> Condition:
        if isinstance(node, ast.Compare):
            return self._conv_compare(node, scope)

        if isinstance(node, ast.BoolOp):
            parts = [self._conv_test(v, scope) for v in node.values]
            if isinstance(node.op, ast.And):
                return AndCond(parts)
            return OrCond(parts)

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self._conv_test(node.operand, scope)
            return inner.negated()

        if isinstance(node, ast.Name):
            name = node.id
            if name in scope.vars:
                return XicCond(scope.vars[name])
            if name in scope.optional_valid:
                return XicCond(scope.optional_valid[name])

        if isinstance(node, ast.Call):
            func_name = self._call_name(node)
            if func_name == "math.isinf":
                expr = self._conv_expr(node.args[0], scope)
                return IsInf(expr)

        if isinstance(node, ast.Attribute):
            # e.g. seg.valid
            sf = self._conv_seg_attr(node, scope)
            if sf is not None:
                return XicCond(sf)

        # Fallback: treat as truthy check
        expr = self._conv_expr(node, scope)
        return Cmp("!=", expr, Const(0, PLCType.DINT))

    def _conv_compare(self, node: ast.Compare, scope: _Scope) -> Condition:
        # Handle 'x is None' / 'x is not None'
        if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot))
                and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value is None):
            name = ast.unparse(node.left)
            valid_reg = scope.optional_valid.get(name)
            if valid_reg is not None:
                if isinstance(node.ops[0], ast.Is):
                    return XioCond(valid_reg)   # is None → XIO valid
                return XicCond(valid_reg)        # is not None → XIC valid

        left = self._conv_expr(node.left, scope)
        parts: list[Condition] = []
        prev = left
        for op, comp in zip(node.ops, node.comparators):
            right = self._conv_expr(comp, scope)
            op_str = _CMP_OPS.get(type(op), "==")
            parts.append(Cmp(op_str, prev, right))
            prev = right
        if len(parts) == 1:
            return parts[0]
        return AndCond(parts)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return f"{ast.unparse(node.func.value)}.{node.func.attr}"
        return ast.unparse(node.func)

    def _build_jsr_in_args(
        self, func_name: str, call: ast.Call, scope: _Scope
    ) -> list[tuple[Reg, Expr]]:
        """Build (callee_reg, value_expr) pairs for JSR input args.
        Uses previously recorded _routine_sigs if available.
        MotionSegment args are passed as the loop-index DINT."""
        in_regs, _ = self._routine_sigs.get(func_name, ([], []))
        result = []
        for i, arg_node in enumerate(call.args):
            # Detect MotionSegment-typed arg → pass loop index
            is_seg = (isinstance(arg_node, ast.Name)
                      and (arg_node.id == scope.seg_var
                           or arg_node.id in _SEG_TYPES))
            if is_seg and scope.loop_idx is not None:
                expr: Expr = RegExpr(scope.loop_idx)
            else:
                expr = self._conv_expr(arg_node, scope)
            dest_reg = in_regs[i] if i < len(in_regs) else self.alloc.alloc(
                PLCType.REAL, f"_jsr_arg_{i}")
            result.append((dest_reg, expr))
        return result

    def _infer_type(self, expr: Any) -> PLCType:
        if expr is None:
            return PLCType.REAL
        if isinstance(expr, Const):
            return expr.typ
        if isinstance(expr, (RegExpr, SegFieldExpr, BinOp, UnaryOp, CptCall)):
            return getattr(expr, "typ", PLCType.REAL)
        return PLCType.REAL
