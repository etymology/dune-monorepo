# PLC Ladder Workflow

## Overview

Our current Studio 5000 version restricts structured-text programming, so the
PLC workflow in this repository is built around ladder-rung text.

The practical workaround is:

1. Copy rung text out of an existing Studio 5000 routine.
2. Save that copied text as `.rllscrap`.
3. Transform or transpile source text into pasteable ladder text.
4. Paste the resulting `.rll` text back into Studio 5000 as ladder logic.

`plc_routines/` at the repo root is the canonical location for these routine
artifacts.

## Studio 5000 Text Formats

Studio 5000 copy and paste use different text formats:

- `.rllscrap` is the copied-from-Studio 5000 format.
- `.rll` is the pasteable ladder-logic format that Studio 5000 accepts when
  pasting into a routine.

The important limitation is that ladder-rung text only contains the rungs. It
does not carry the required tag definitions. Users must create any required
controller-level tags, routine-level tags, and referenced UDTs in Studio 5000
separately.

## Repository Layout

Each routine lives in its own folder under `plc_routines/`:

- `studio_copy.rllscrap`: copied source text taken from Studio 5000.
- `pasteable.rll`: ladder text that can be pasted into Studio 5000.
- `tags.md`: operator-facing notes about required tags and setup.
- `tags.json`: machine-readable tag requirements for tooling and validation.

This structure keeps the Studio 5000 source artifact, the generated/pasteable
artifact, and the tag requirements together.

## Tag Metadata

There are two levels of tags in this workflow:

- Controller-level tags: shared PLC tags defined at controller scope.
- Routine-level tags: tags defined locally for a specific routine.

`tags.json` is the machine-readable source of truth and supports both scalar and
UDT-backed tags.

Recommended shape:

```json
{
  "schema_version": 1,
  "routine_name": "exampleRoutine",
  "udts": [
    {
      "name": "ExampleStatus",
      "fields": [
        {"name": "Ready", "type": "BOOL"},
        {"name": "ErrorCode", "type": "DINT"}
      ]
    }
  ],
  "controller_tags": [
    {
      "name": "QueueFault",
      "type": "BOOL",
      "description": "Shared fault flag used by multiple routines."
    }
  ],
  "routine_tags": [
    {
      "name": "LocalStatus",
      "type": "ExampleStatus",
      "routine": "exampleRoutine",
      "description": "Routine-local state."
    }
  ]
}
```

Notes:

- Atomic types such as `BOOL`, `REAL`, and `DINT` are supported directly.
- UDT fields may reference other UDT names when nested composition is needed.
- Controller-level tags omit `routine`.
- Routine-level tags include a `routine` field naming the owning routine.

## Translation And Transpilation Tools

The translator from copied Studio 5000 rung text into pasteable ladder text is:

- [`src/dune_winder/plc_rung_transform.py`](../src/dune_winder/plc_rung_transform.py)
- [`haskell/src/PlcRungTransform.hs`](../haskell/src/PlcRungTransform.hs)

These tools handle the copied `.rllscrap` form and rewrite it into pasteable
`.rll` text.

The Python-to-ladder transpiler lives under
[`src/dune_winder/transpiler/`](../src/dune_winder/transpiler) with a future
Haskell port under development. It transforms Python code into pasteable ladder
logic while assuming PLC tags are available, including scalar registers such as
`BOOL`, `REAL`, and `DINT`, plus UDT-backed tags where needed.

The detailed grammar assumptions and format handling for `.rllscrap` and `.rll`
are documented in the rung-transform and transpiler source.
