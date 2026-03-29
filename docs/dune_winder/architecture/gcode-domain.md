# G-code Domain Architecture

## Canonical Package

All G-code domain logic lives in `src/dune_winder/gcode/`:

- `model.py`
- `parser.py`
- `renderer.py`
- `runtime.py`
- `handler.py`
- `handler_base.py`

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

Executes `ProgramLine` objects via a single `on_instruction(line: ProgramLine)`
callback per parsed line. Handlers receive the complete instruction atomically
and extract parameters directly — no per-letter dispatch, no dirty flags.

### `handler_base`

`GCodeHandlerBase` consumes complete instructions via `handle_instruction(line:
ProgramLine)`. Per-letter setter callbacks and dirty-flag fields are absent;
all parameters are read from the `ProgramLine` in one place.

### `handler`

`GCodeHandler` in `core/g_code_handler.py` implements queued instruction actions
(`xy`, `z`, `head`, `latch`) and deferred stop requests, building on
`handler_base`.

## Removed Legacy Paths

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
