# PLC Ladder Workflow

## Overview

This repository uses Rockwell Studio 5000 ladder-rung text as the exchange
format for PLC logic. The workflow is centered on copied rung text rather than
full `.ACD` project files because rung text is easy to diff, review, transform,
and paste back into Studio 5000.

At a high level:

1. Copy routine text out of Studio 5000.
2. Store the copied text as `.rllscrap`.
3. Transform or generate ladder text as needed.
4. Paste the resulting `.rll` text back into Studio 5000.

This document describes the storage conventions used in the current `plc/`
tree. For the runtime communication model between Python and the PLC, see
[plc-communication.md](plc-communication.md).

## Studio 5000 Text Formats

Studio 5000 copy/paste uses two related but different text formats:

- `.rllscrap`
  - copied out of Studio 5000
- `.rll`
  - pasteable ladder text accepted by Studio 5000

The rung text itself only contains ladder instructions. It does not include all
required controller tags, program tags, or UDT definitions, so those still
need to exist in the PLC project.

## Repository Layout

The checked-in PLC tree is `plc/`.

### Controller-level metadata

- `plc/controller_level_tags.json`

This file is the exported inventory of controller-scoped tags and controller
UDTs.

### Program folders

Each PLC program typically has:

- `plc/<program>/programTags.json`
- `plc/<program>/main/studio_copy.rllscrap`
- `plc/<program>/main/pasteable.rll`
- optional `plc/<program>/<subroutine>/studio_copy.rllscrap`
- optional `plc/<program>/<subroutine>/pasteable.rll`

Examples in this repository include:

- `plc/MainProgram/`
- `plc/Ready_State_1/`
- `plc/MoveXY_State_2_3/`
- `plc/MoveZ_State_4_5/`
- `plc/Latch_UnLatch_State_6_7_8/`
- `plc/Error_State_10/`
- `plc/motionQueue/`
- `plc/xz_move/`

### Standalone helper artifacts

The `plc/` tree also contains some checked-in files that are not organized as a
full program folder, for example:

- `plc/enqueueRoutineStateful`
- `plc/enqueueRoutine_3d_arc.txt`

These are still useful ladder references, but they are not laid out like the
exported program directories.

## Metadata Export Workflow

The repository includes two maintenance tools for pulling live PLC metadata
into the `plc/` tree.

### Export structure and tags

Use:

```bash
python src/export_plc_metadata.py 192.168.1.10
```

This connects with `pycomm3` and writes:

- `plc/controller_level_tags.json`
- `plc/<program>/programTags.json`
- empty `studio_copy.rllscrap` placeholders for each discovered main routine
  and subroutine

The exported JSON captures:

- controller-level tags
- program-level tags
- UDT definitions reachable from those tags
- inferred main routine names
- discovered routine/subroutine lists

### Export live values into the JSON files

Use:

```bash
python src/export_plc_tag_values.py 192.168.1.10
```

This reads every tag referenced by the existing metadata files in `plc/` and
writes the current values back into those same JSON files.

That is useful for:

- documenting the live controller contract
- debugging which queue/state tags exist and how they are populated
- comparing expected tag layouts with a real controller snapshot

## Tag Metadata Conventions

### Controller-level tags

Controller tags live in `plc/controller_level_tags.json`.

Each tag entry records fields such as:

- `name`
- `fully_qualified_name`
- `tag_type`
- `data_type_name`
- `dimensions`
- `array_dimensions`
- optional `udt_name`
- optional `value`
- optional `read_error`

### Program-level tags

Program-scoped tags live in `plc/<program>/programTags.json`.

Those files also include:

- `program_name`
- `main_routine_name`
- `main_routine_name_source`
- `routines`
- `subroutines`
- `udts`

The JSON files are the machine-readable source of truth for the tag layout that
the Python runtime, simulator, and ladder maintenance tooling all depend on.

## Translation and Transpilation Tools

### Copied-rung transformer

The copied-text to pasteable-text transformer lives in:

- `src/dune_winder/plc_rung_transform.py`
- `haskell/src/PlcRungTransform.hs`

These tools normalize `.rllscrap` text into `.rll` text that is easier to paste
back into Studio 5000.

### Python-to-ladder transpiler

The Python-to-ladder transpiler lives under:

- `src/dune_winder/transpiler/`
- `haskell/src/DuneWinder/Transpiler/`

It is used for selected motion-planning functions, especially around queued
motion helpers such as:

- `MaxAbsSinSweep`
- `MaxAbsCosSweep`
- `ArcSweepRad`
- `CircleCenterForSeg`
- `SegTangentBounds`
- `CapSegSpeed`

## Working Assumptions

The current repository structure should be interpreted as:

- `plc/` is the canonical checked-in PLC artifact tree
- `programTags.json` and `controller_level_tags.json` are exported metadata
  snapshots
- `.rllscrap` and `.rll` files are the human-reviewed routine text artifacts
- some ladder references exist outside the standard program-folder layout and
  should be treated as special-case helper files

If a future cleanup separates exported metadata from hand-maintained ladder
artifacts, this document should be updated to reflect that new source-of-truth
layout.
