# PLC/Winder Architecture Proposals

## Summary

The current PLC/winder link works, but the contract is spread across several
places:

- string tag names in Python
- runtime polling/cache behavior in `PLC.Tag`
- simulator behavior in `SimulatedPLC`
- ladder artifacts in `plc/`
- exported metadata in `plc/*.json`

That makes the system harder to evolve safely than it needs to be. The changes
below are ordered by leverage, not by difficulty alone.

## P0: Make the Contract Explicit

### 1. Generate a shared PLC contract package

Problem:

- Tag names, UDT field names, and state/move meanings are duplicated manually.
- The queue contract is repeated in `plc_interface.py`, `SimulatedPLC`,
  ladder text, and exported metadata.

Proposal:

- Generate a Python `plc_contract` package from the exported metadata in
  `plc/controller_level_tags.json` and `plc/*/programTags.json`.
- Centralize:
  - tag constants
  - UDT serializers/deserializers
  - move/state enums
  - queue tag groups

Why it helps:

- Reduces silent drift between runtime, simulator, and PLC.
- Makes refactors grepable and safer.
- Creates one obvious place to review the PLC boundary.

Suggested first step:

- Start with generated constants for queue tags and direct-motion tags only.
- Leave the rest of the runtime using the old names until the generated module
  proves stable.

### 2. Separate exported PLC metadata from hand-maintained ladder artifacts

Problem:

- `plc/` currently mixes:
  - exported live-controller metadata
  - manually maintained routine text
  - alternate or historical queue artifacts
- It is not obvious which files are authoritative for production behavior.

Proposal:

- Keep the same content, but add an explicit structure or manifest, for example:
  - `plc/exported/`
  - `plc/routines/`
  - `plc/experimental/`
  - `plc/manifest.md`
- At minimum, declare which queue artifact is the primary integration target.

Why it helps:

- Makes maintenance safer for both controls and software work.
- Reduces the chance of reading the wrong ladder file when debugging.
- Clarifies whether `motionQueue`, `enqueueRoutineStateful`, and
  `enqueueRoutine_3d_arc.txt` are current, alternate, or experimental.

Suggested first step:

- Add a `plc/README.md` or manifest that names the active ladder entry points
  before changing the directory structure.

### 3. Fix cross-platform package casing

Problem:

- The repository stores Python packages under uppercase paths such as:
  - `src/dune_winder/io/Devices`
  - `src/dune_winder/io/Maps`
  - `src/dune_winder/io/Primitives`
- Much of the code imports them with lowercase module paths such as
  `dune_winder.io.devices.*`.
- That works on Windows but is a portability risk on case-sensitive filesystems.

Proposal:

- Normalize those package directories to lowercase, or add a deliberate
  compatibility layer if renaming is too disruptive.

Why it helps:

- Makes the advertised Linux/macOS support credible.
- Removes a class of environment-specific import failures.

Suggested first step:

- Add a CI job on a case-sensitive filesystem before or during the rename so the
  repo can catch remaining mixed-case imports automatically.

## P1: Make Runtime Semantics Less Implicit

### 4. Replace the global `PLC.Tag` registry with a scoped snapshot service

Problem:

- `PLC.Tag.instances` and `PLC.Tag.tag_lookup_table` are global process-wide
  singletons.
- Poll behavior, freshness, and ownership are implicit.
- Tests already need to save and restore global tag state manually.

Proposal:

- Introduce a per-backend or per-`BaseIO` tag registry, for example:
  - `PlcSnapshotCache`
  - `PlcTagRegistry`
- Expose explicit APIs for:
  - polling a snapshot
  - reading cached values
  - performing fresh reads
  - registering groups of related tags

Why it helps:

- Prevents hidden cross-talk between unrelated PLC objects or test fixtures.
- Makes polling behavior easier to reason about.
- Creates a cleaner seam for simulator and diagnostics work.

Suggested first step:

- Wrap the existing global behavior behind a registry object without changing
  call sites, then migrate consumers gradually.

### 5. Split telemetry reads from command writes at the API level

Problem:

- The current `PLC` abstraction is intentionally thin, but it hides important
  differences between:
  - cached reads
  - fresh reads
  - command writes
  - stateful wait conditions
- Safety-sensitive paths have already needed ad hoc escape hatches such as
  `_readTagNow()`.

Proposal:

- Introduce an explicit command/telemetry boundary, for example:
  - `plc.read_cached(...)`
  - `plc.read_fresh(...)`
  - `plc.write_command(...)`
  - `plc.await(...)`

Why it helps:

- Makes freshness expectations visible in code review.
- Reduces the number of places where safety logic depends on stale cache data.
- Helps document which reads are allowed to be eventually consistent.

Suggested first step:

- Start with queue and X/Z interlock paths, where freshness matters most.

### 6. Consolidate queued-motion implementations around one port and one state machine

Problem:

- The queue behavior is currently split across:
  - `QueuedMotionPLCInterface`
  - `QueuedMotionSession`
  - `queue_client.py`
  - `queue_client_3d_arc.py`
  - simulator queue behavior
  - multiple ladder artifacts
- That is manageable today, but expensive to evolve.

Proposal:

- Keep `QueuedMotionSession` as the main runtime state machine.
- Treat everything else as one of:
  - a transport adapter
  - a test utility
  - an experimental extension
- Give the 3D arc path a clearly separate namespace or explicitly fold it into
  the same port abstraction.

Why it helps:

- Reduces duplication in reset/start/ack/idle logic.
- Makes queue behavior easier to test consistently.
- Clarifies what the production queue contract actually is.

Suggested first step:

- Refactor `queue_client.py` to call the same port/session primitives the
  runtime already uses, instead of carrying a second copy of the handshake.

## P2: Improve Confidence and Diagnostics

### 7. Make the simulator contract-driven

Problem:

- `SimulatedPLC` is useful, but it can still drift from the real PLC contract
  because it is maintained by hand.
- Its behavior is close enough for current tests, but not obviously proven
  against the exported metadata or ladder artifacts.

Proposal:

- Add a compatibility suite that verifies the simulator against the shared PLC
  contract and representative queue/direct-motion scenarios.
- Derive more of the simulator's default tag inventory from exported metadata
  rather than hand-seeding every field manually.

Why it helps:

- Preserves confidence in `PLC_MODE=SIM`.
- Makes future queue and state-machine changes safer.
- Turns the simulator into a better developer tool instead of just a test stub.

Suggested first step:

- Add contract tests that compare generated tag constants, required queue tags,
  and move/state enums against both the simulator and the exported metadata.

### 8. Capture structured fault snapshots

Problem:

- Queue faults and direct-motion failures currently require hopping between
  logs, cached tags, and ladder text to reconstruct what happened.
- The queue ladder already publishes good diagnostic tags, but the Python side
  does not consistently capture them as one structured event.

Proposal:

- When a queue or direct-motion fault occurs, write a structured snapshot into
  the application log containing:
  - `STATE`
  - `ERROR_CODE`
  - queue handshake tags
  - relevant axis status
  - preview/block metadata when available

Why it helps:

- Speeds up debugging on real hardware.
- Makes field reports actionable.
- Gives Grafana/log tooling richer context without requiring a live controller
  after the fact.

Suggested first step:

- Start with queued-motion failures because the queue ladder already exposes
  `FaultCode`, `ActiveSeq`, `PendingSeq`, and queue diagnostic bits.

## Recommended Order

If only a few changes are funded, the most useful sequence is:

1. Shared PLC contract module
2. Active-artifact manifest for `plc/`
3. Cross-platform package casing cleanup
4. Scoped tag registry plus explicit fresh-read API
5. Queued-motion consolidation
6. Simulator compatibility suite and structured fault snapshots

That sequence improves correctness first, then reduces maintenance cost, then
improves debugging depth.
