# Code Boundary Refactor Plan

## Related Plans

- **`docs/UVlayerRewritePlan.md`** — Coordinate system unification and UV calibration workflow redesign. The `uv_head_target.py` refactor must be coordinated with this work; some extractions are already underway via new modules in `machine/geometry/`.

## Overview
This document outlines a planned refactor of the `src/dune_winder` codebase to address large, multi-concern files and improve module organization. The goal is to separate concerns, reduce file sizes, and improve maintainability.

## Current State Analysis

### Large Files (>1,500 lines) with Multiple Concerns

| File | Lines | Primary Concerns | Issues |
|------|-------|-----------------|--------|
| `uv_head_target.py` | 2,537 | Data models, geometric calculations, coordinate transforms, wire pin resolution | 14 data classes + 73 functions; all in one file |
| `manual_calibration.py` | 2,370 | Calibration workflow, geometric transforms, session management, file I/O | `ManualCalibration` god class (67 methods) |
| `segment_patterns.py` | 1,856 | Path planning, geometric algorithms, motion profiling | 52 functions, no class organization |
| `gcode/handler_base.py` | 1,707 | G-code handler base classes, model, renderer, parser | Closely coupled to `handler.py`; should be refactored together |
| `gcode/handler.py` | 1,633 | G-code generation, state management, hardware interfacing | `GCodeHandler` mixes state, execution, hardware |
| `api/commands.py` | 1,724 | Command registry, utility functions | Well-organized but could be domain-split |
| `plc_ladder/runtime.py` | 1,459 | Runtime execution, state management, expression evaluation | Mixed responsibilities across 8 classes + 66 functions |
| `plc_ladder/codegen.py` | 1,446 | Python code generation from PLC ladder AST | Two distinct concerns: code generators + transpiler entry points |
| `plc_ladder/imperative.py` | 1,424 | PLC ladder code generation, protocol abstractions | 34 protocol classes + `BoundRoutineAPI` with 42 methods |

### Naming Convention Consistency
- **Consistent**: `_private` functions, `PascalCase` classes, `snake_case` functions, `*Error` suffix for errors
- **Inconsistent**: Mixed `get_` prefix usage, `*Callable` vs `*Protocol` for protocols

## Proposed Separations

### `uv_head_target.py` → Remaining Modules

Some geometry has already been extracted into `machine/geometry/` as part of the UV layer rewrite (see `docs/UVlayerRewritePlan.md`):
- **`machine/geometry/uv_layout.py`** ✓ — pin layouts, nominal positions, face ranges, endpoint pins
- **`machine/geometry/uv_tangency.py`** ✓ — tangency analysis for UV winding paths
- **`machine/geometry/uv_calibration.py`** ✓ — calibration normalization and absolute position calculations

What remains to extract from `uv_head_target.py`:
1. **`data_models.py`**: UvHeadTargetRequest, UvTangentViewRequest, UvHeadTargetResult, UvTangentViewResult, WrappedPinResolution, AnchorToTargetCommand, AnchorToTargetViewResult, PinPairTangentGeometry (and any Point2D/Point3D/RectBounds/LineEquation not yet moved)
2. **`pin_resolution.py`**: `_wire_space_pin`, `_all_wire_space_pins`, `_pin_number`, pin resolution logic
3. **`route_planning.py`**: `_derive_wrap_context`, `_wrap_context_for_pin`, `_face_for_pin`, `_b_side_equivalent_pin`, tangent finding, path calculation
4. **`cache_manager.py`**: `clear_uv_head_target_caches`, cache utilities

> Coordinate the final split with the UV layer rewrite to avoid moving things twice.

### `manual_calibration.py` → 5 Modules
1. **`session_management.py`**: `_ManualCalibrationSession`, `_ManualCalibrationGXSession`
2. **`calibration_workflow.py`**: `ManualCalibration` class (67 methods)
3. **`geometric_transforms.py`**: `_solve_linear_system`, `_rigid_transform`, `build_transform`, `_cyclic_pin_distance`
4. **`file_operations.py`**: draft file management, `_loadPersistedSession`, `_persistSession`, `_loadPersistedGXSession`, `_persistGXSession`
5. **`calibration_models.py`**: `build_nominal_calibration`, `normalize_calibration`, `_side_for_pin`, `_bootstrap_pins_for_side`

### `segment_patterns.py` → 5 Modules
1. **`path_planning.py`**: `_nearest_neighbor_order`, `_two_opt_open_path`, `_order_waypoints_for_short_path`, path optimization
2. **`geometric_primitives.py`**: `_distance_xy`, `_path_length`, `_segments_within_bounds`, geometric operations
3. **`motion_profiling.py`**: `_enforce_min_arc_radius`, velocity/curvature constraints
4. **`trajectory_generation.py`**: `square_segments`, `lissajous_segments`, `fibonacci_spiral_segments`, `archimedean_spiral_segments`, `apsidal_precessing_orbit_segments`
5. **`validation.py`**: `validate_term_type`, `_point_within_bounds`, constraint checking

### `gcode/handler.py` + `gcode/handler_base.py` → 4 Modules

Both files (3,340 lines combined) should be refactored together since `handler.py` depends heavily on `handler_base.py` types:
1. **`gcode_model.py`**: `GCodeHandlerBase`, model, renderer, parser (from `handler_base.py`)
2. **`state_management.py`**: `_PreviewedQueuedLine`, `_QueuedMotionPreviewState`
3. **`hardware_interface.py`**: hardware-specific operations
4. **`command_executor.py`**: `GCodeHandler` core execution (67 methods, from `handler.py`)

### `plc_ladder/imperative.py` → 3 Modules
1. **`protocol_definitions.py`**: All `*Callable` protocol classes (34 classes)
2. **`runtime_api.py`**: `BoundRoutineAPI` (42 methods)
3. **`ast_nodes.py`**: `InstructionCall`, `Routine` handling, tag support classes

### `plc_ladder/runtime.py` → 4 Modules
1. **`execution_engine.py`**: `RoutineExecutor` (47 methods), `ExpressionEvaluator` (2 methods)
2. **`state_tracking.py`**: `RuntimeState`, `ScanContext` (8 methods), `ActiveMotion`
3. **`jump_handling.py`**: `_RoutineJump`
4. **`tag_operations.py`**: `TagRef` (32 methods), `Supports*Tag` protocols, `TagStore`

### `api/commands.py` → Domain-Split
1. **`validation_helpers.py`**: `_validateArgs`, `_as*` functions
2. **`type_conversions.py`**: Type conversion utilities
3. **`registry_builder.py`**: `build_command_registry`

### `plc_ladder/codegen.py` → 2 Modules
1. **`generators/`**: `StructuredPythonCodeGenerator`, `PythonCodeGenerator`
2. **`transpiler.py`**: `transpile_routine_to_python`, `transpile_routine_to_structured_python`

## Benefits of Proposed Structure

1. **Single Responsibility**: Each module has one clear purpose
2. **Reduced Cognitive Load**: Smaller files are easier to understand and navigate
3. **Better Testability**: Focused modules are easier to test in isolation
4. **Improved Collaboration**: Teams can work on different modules without conflicts
5. **Clearer Dependencies**: Module boundaries make dependencies explicit

## Migration Strategy

1. Create new module files in appropriate locations
2. Move classes/functions to new modules, updating imports
3. Update all internal imports throughout the codebase
4. Run tests to verify no functionality is broken
5. Remove old code from source files

## Naming Convention Standardization

- Continue using `_private` prefix for internal functions
- Keep `PascalCase` for public classes
- Use `snake_case` for public functions
- Consider standardizing protocols to `*Protocol` suffix for clarity
- Add module-level `__all__` exports for explicit public API