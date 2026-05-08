# Plan: Refresh `docs/code_boundary_refactor.md`

## Context

The plan was created Apr 23, 2026 — two days ago. Since then, active work on UV targeting (commits Apr 19 and Apr 24) has changed the picture: some geometry has been extracted into new `machine/geometry/` modules, and all target files have grown. The plan's line counts are stale, one large file (`gcode/handler_base.py`) is missing from the analysis, `plc_ladder/codegen.py` appears in the separations section but not the analysis table, and the `uv_head_target.py` split plan needs to reflect what has already been extracted.

## Changes to Make

**File to edit:** `docs/code_boundary_refactor.md`

### 1. Update line counts in the Current State Analysis table

| File | Old count | New count |
|------|-----------|-----------|
| `uv_head_target.py` | 2,104 | 2,537 |
| `manual_calibration.py` | 2,062 | 2,370 |
| `segment_patterns.py` | 1,827 | 1,856 |
| `gcode/handler.py` | 1,546 | 1,633 |
| `plc_ladder/imperative.py` | 1,422 | 1,424 |
| `plc_ladder/runtime.py` | 1,258 | 1,459 |
| `api/commands.py` | 1,522 | 1,724 |

### 2. Add missing files to the analysis table

Add two rows:

- `gcode/handler_base.py` | 1,707 | G-code handler base classes, model, renderer, parser | Closely coupled to `handler.py`; should be refactored together
- `plc_ladder/codegen.py` | 1,446 | Python code generation from PLC ladder AST | Two distinct concerns: code generators + transpiler entry points

### 3. Update the `uv_head_target.py` split plan

Note that new modules have already been extracted into `machine/geometry/`:
- `uv_layout.py` — pin layouts, nominal positions, face ranges, endpoint pins
- `uv_tangency.py` — tangency analysis for UV winding paths
- `uv_calibration.py` — calibration normalization and absolute position calculations

Revise the 5-module split to reflect what remains in `uv_head_target.py` after these extractions, and cross-reference the UV layer rewrite plan (`docs/UVlayerRewritePlan.md`) which is driving coordinate system unification.

### 4. Merge `gcode/handler.py` and `gcode/handler_base.py` into a combined refactor section

Currently the plan only mentions `handler.py`. Since `handler_base.py` is 1,707 lines and the two files are tightly coupled, the refactor section should cover both together with a combined module breakdown.

### 5. Add a cross-reference to `docs/UVlayerRewritePlan.md`

Add a brief note in the Overview (or a new "Related Plans" section at the top) so readers know the UV layer rewrite is proceeding in parallel and the `uv_head_target.py` refactor should be coordinated with it.

## Verification

- Read the updated file after editing to confirm all line counts, table rows, and section content look correct.
- No tests to run — this is a documentation-only change.
