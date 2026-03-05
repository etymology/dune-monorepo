# G-code Domain Architecture

This document defines the canonical G-code domain introduced for P1.

## Canonical Package

All G-code domain logic now lives in:

- `src/dune_winder/gcode/model.py`
- `src/dune_winder/gcode/parser.py`
- `src/dune_winder/gcode/renderer.py`
- `src/dune_winder/gcode/runtime.py`

### `model`

Defines the shared domain objects:

- `Opcode` enum (100-112)
- `OPCODE_CATALOG` / `OPCODE_NAME_CATALOG` as the single opcode source of truth
- `CommandWord`, `FunctionCall`, `Comment`, `ProgramLine`, `Program`

### `parser`

Parses text into canonical model objects:

- Preserves command order
- Preserves comments as line items
- Binds `P...` to the previous command/function exactly like legacy behavior

### `renderer`

Renders canonical model objects back to normalized text:

- Single-space token separation
- Preserved command/comment ordering
- `FunctionCall` rendering via `G... P...`

### `runtime`

Executes `ProgramLine` objects against callback tables used by legacy runtime:

- `X/Y/Z/F/N` callback payloads are typed to match historical behavior
- `G` callback payload remains list-shaped (`[opcode, *params]`)

## Legacy Removal

Legacy wrapper paths were removed after parity validation:

- `library/G_Code.py`
- `machine/G_Codes.py`
- `recipes/G_CodeFunctions/*`
- `recipes/G_CodePath.py`

Runtime and recipe generation now use canonical modules directly:

- Runtime execution: `gcode.runtime` (`GCodeCallbacks`, `GCodeProgramExecutor`)
- Runtime dispatch catalog: `gcode.model.Opcode`
- Recipe helper constructors: `recipes/gcode_functions.py`
- Recipe path object: `recipes/gcode_path.py`

## Output Normalization and Hashes

Rendering is normalized, so regenerated recipe text can differ in formatting
from legacy output. This can produce new recipe hash values even when machine
behavior is unchanged.
