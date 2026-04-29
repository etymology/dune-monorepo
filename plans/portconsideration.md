# Port consideration

## Recommendation

If starting from scratch, use:

- **Rust** for live control, hardware I/O, audio processing, inference, state
  machines, local services, and deployment.
- **TypeScript + SvelteKit** for operator interfaces.
- **Tauri 2** for desktop apps, especially `dune_tension`.
- **Haskell** for offline pure/code-generation work where it is already strong:
  the PLC transpiler/rung transformer, and possibly recipe or motion-plan
  compilation.
- **Python** only as a temporary compatibility sidecar where a Rust library gap
  is proven, especially PLC communication.

The central split should be:

> Rust for the machine. TypeScript for the operator. Haskell for compilers and
> pure planners. Python only as a bridge.

Do this in the existing monorepo. Add Rust, TypeScript, generated bindings,
golden fixtures, and calibration artifacts next to the current Python system so
the working code remains available while the replacement earns trust. The port
should be parallel first, continuously integrated, and only then cut into live
responsibility at narrow boundaries.

## Why change

The current Python stack works, but its weak spots line up with the most
important parts of the system:

- Offline geometry, recipe expansion, and motion planning want stronger types.
- Winder control and head-transfer state machines need exhaustive modeling to
  avoid undefined or unsafe edge cases.
- The web UI and Python backend share ad hoc JSON/string contracts.
- `dune_tension` does live audio processing and neural inference where latency
  and throughput matter.
- Tkinter and the current static web UI limit usability and extensibility.

## Proposed stack

### Repository layout

Keep the migration in this repository rather than creating a separate Rust repo.
This system's hardest contracts are shared across languages: machine geometry,
recipe semantics, motion segments, PLC tags, tension data, calibration, and
operator workflows. Keeping those contracts in one repo makes parity testing,
artifact versioning, and cutover review much easier.

Use side-by-side workspaces:

```text
dune-monorepo/
  pyproject.toml
  uv.lock
  Cargo.toml
  crates/
    dune-domain/
    dune-recipes/
    dune-motion/
    dune-api-types/
    dune-winder-core/
    dune-tension-core/
    dune-plc-bridge/
  apps/
    winder-service/
    tension-service/
    winder-ui/
    tension-ui/
  src/
    dune_winder/
    dune_tension/
    spectrum_analysis/
  tests/
    dune_winder/
    dune_tension/
    golden/
  calibration/
    machines/
    sensors/
    tension/
    plc/
    historical/
  docs/
    architecture/
    migration/
    calibration/
    operations/
    dune_winder/
    dune_tension/
```

The important rule is ownership by purpose:

- `crates/` contains reusable Rust libraries.
- `apps/` contains runnable Rust, SvelteKit, or Tauri applications.
- `src/` keeps the current Python packages until each responsibility is retired.
- `tests/golden/` contains Python-versus-Rust comparison fixtures and outputs.
- `calibration/` contains versioned machine and sensor facts.
- `docs/` contains architecture, migration decisions, procedures, and runbooks.

Start with library crates and comparison tests before introducing new live
services. The Rust code should share artifacts with Python immediately, but it
should not become the live authority until the relevant behavior is boringly
well tested.

### Rust core

Use a Cargo workspace with shared crates for machine geometry, recipes, motion
segments, commands, errors, and API types.

Recommended libraries:

- `tokio` for async runtime.
- `axum` for HTTP/WebSocket services.
- `serde` for typed command, event, recipe, and state payloads.
- `tracing` for structured logs.
- `thiserror` for domain errors and `anyhow` for app-level error handling.
- `rusqlite` for local tension data.
- `cpal` for cross-platform audio capture.
- `realfft` or `rustfft` for spectrum analysis.
- `ort` for ONNX Runtime inference.

Rust is the right default for the live system because it gives exhaustive enums,
explicit ownership, predictable deployment, good concurrency primitives, and a
much stronger ecosystem for hardware/audio/ML integration than Haskell.

### PLC communication

Do not assume the Rust PLC path is safe until tested.

Run a dedicated spike against the real ControlLogix payloads:

- ordinary tag reads/writes;
- UDTs;
- `MotionSeg`-style queue payloads;
- queue handshake tags;
- failure and reconnect behavior.

Try `rseip` first. If it handles the actual payloads cleanly, use it. If not,
keep a small Python `pycomm3` sidecar behind a typed Rust boundary and replace
it later. Do not let the whole migration depend on an unproven PLC crate.

### Operator UI

Use TypeScript + SvelteKit for both winder and tension interfaces.

Generate frontend types from Rust API structs/enums with `specta` or `ts-rs`.
The command envelope, PLC state snapshots, live events, and recipe/motion types
should have one source of truth in Rust and generated TypeScript bindings.

Use WebSockets or Tauri events for live state instead of polling or manually
coordinated string commands.

### Desktop apps

Use Tauri 2 for `dune_tension` and any desktop-only operator tools.

The Rust side should own audio capture, FFT, ONNX inference, PLC access, file
I/O, and SQLite. The Svelte side should own controls, plots, status views, and
operator workflow.

This gives a much better UI path than Tkinter while still shipping a native app.

### Haskell

Keep Haskell where it is already a good fit:

- PLC rung transformation;
- PLC transpilation;
- offline recipe lowering;
- pure motion-plan or template compilation, if separated cleanly from live I/O.

Do not use Haskell for the full live backend unless the project is willing to
build or bind missing infrastructure for EtherNet/IP, audio capture, ONNX
inference, desktop packaging, and deployment. Haskell is attractive for the pure
center of the system, but the weak ecosystem is concentrated at the exact I/O
edges this project depends on.

### Calibration and artifacts

Treat calibration as source data, not as scattered notes or generated output.
Keep machine-readable calibration files under `calibration/`, and keep the human
procedure and interpretation under `docs/calibration/`.

Suggested artifact split:

```text
calibration/
  README.md
  machines/
    apa-test-stand-01.toml
  sensors/
    tension-load-cell-serial-1234.toml
    microphone-serial-5678.toml
  tension/
    2026-04-26-load-cell-check.toml
  plc/
    control-logix-tags.snapshot.json
  historical/
    old-calibrations/
```

Prefer `toml` for edited calibration facts and `json` for generated snapshots or
interchange data. Markdown should explain why the values exist and how to
reproduce them; it should not be the only machine-readable source of truth.

Keep bulky raw captures, derived datasets, and experiment outputs out of the
runtime package paths. If they are small and required for tests, place them under
`tests/golden/` or a clearly named fixture directory. If they are large, store
only manifests, checksums, summaries, or reduced fixtures in the repo.

## Rewrite units and priority

Do not rewrite everything at once. Split the port by risk boundary and migrate
the areas with the best benefit-to-risk ratio first.

### 1. Same-repo Rust workspace and artifact skeleton

**Priority:** highest. **Benefit:** high. **Risk:** low.

Add the root Cargo workspace, the first Rust crates, the calibration directory,
and a golden-test location without changing live behavior. This creates a place
for the port to grow while the current Python system remains the operating
system of record.

Initial targets:

- root `Cargo.toml`;
- `crates/dune-domain`;
- `crates/dune-api-types`;
- `tests/golden`;
- `calibration/README.md`;
- `docs/migration/rust-port-plan.md`.

This step should be intentionally boring. It is infrastructure for comparison,
review, and gradual cutover, not a runtime replacement.

### 2. Shared domain model and API contracts

**Priority:** highest. **Benefit:** high. **Risk:** low.

Start with a Rust crate for shared types:

- commands and command responses;
- machine state and state transitions;
- recipes and template inputs;
- motion segment descriptions;
- PLC-facing snapshots/events;
- structured error types.

Generate TypeScript bindings from these Rust types with `specta` or `ts-rs`.
This removes the ad hoc Python/JavaScript JSON contract without touching live
hardware behavior. It also creates the foundation for every later rewrite.

### 3. Golden parity tests and deterministic adapters

**Priority:** highest. **Benefit:** high. **Risk:** low.

Before replacing Python modules, build comparison harnesses that run Python and
Rust against the same fixtures. Use these for deterministic behavior:

- recipe parsing and validation;
- geometry calculations;
- waypoint and motion-plan generation;
- serialized motion segment construction;
- tension FFT or inference preprocessing, where stable enough to compare.

Golden tests are the main guardrail against accidental behavior drift. They also
make the Rust implementation useful before it controls hardware.

### 4. Operator UI contract and one narrow screen

**Priority:** high. **Benefit:** high. **Risk:** low to medium.

Build one SvelteKit operator screen against generated types and a thin adapter
to the existing backend. Pick a workflow that is useful but not safety-critical,
such as status display, command inspection, recipe preview, or tension result
review.

The goal is to prove the UI architecture, generated types, live updates, and
component patterns before replacing the full winder or tension GUI.

### 5. Offline pure calculations

**Priority:** high. **Benefit:** high. **Risk:** medium.

Port or isolate deterministic logic where stronger types pay off immediately:

- geometry calculations;
- recipe expansion;
- template validation;
- waypoint and motion-plan generation;
- serialized motion segment construction.

Use Rust if the logic must run inside the live control process. Use Haskell if
it is naturally compiler-like and can emit stable JSON/CBOR consumed by Rust.
This area is attractive because it can be tested heavily against the existing
Python outputs before it controls hardware.

### 6. Tension audio and inference engine

**Priority:** medium-high. **Benefit:** high. **Risk:** medium.

Move the performance-sensitive `dune_tension` core into Rust:

- audio capture with `cpal`;
- FFT/spectrum analysis with `realfft` or `rustfft`;
- ONNX inference with `ort`;
- local persistence with `rusqlite`;
- typed events for plots and operator state.

Keep the current Python GUI or CLI as a comparison harness during the port, then
wrap the Rust engine with a Tauri/Svelte app. This gives a large performance and
deployment payoff without first taking on the PLC risk.

### 7. Winder service shell and state machine

**Priority:** medium. **Benefit:** very high. **Risk:** medium-high.

Build a Rust service that models the winder state machine and command dispatch
without owning PLC communication yet. It should expose typed HTTP/WebSocket APIs
and run against either a simulator or the existing Python PLC bridge.

This is where Rust's exhaustive enums and state modeling should reduce the
unsafe/undefined edge cases in manual mode, winding, pause/resume, head
transfer, homing, and stop behavior.

### 8. PLC communication

**Priority:** gated. **Benefit:** high. **Risk:** highest.

Do this only after a hardware spike proves the path.

Try `rseip` against the real ControlLogix payloads. The spike must cover:

- ordinary tag reads/writes;
- UDTs;
- `MotionSeg`-style queue payloads;
- queue handshake tags;
- reconnects, timeouts, and partial failures.

If `rseip` works cleanly, move PLC I/O into Rust. If it does not, keep a tiny
Python `pycomm3` sidecar behind a typed IPC boundary and let Rust own the rest
of the runtime. The migration should not block on native PLC I/O.

### 9. Full desktop/operator consolidation

**Priority:** last. **Benefit:** medium-high. **Risk:** medium.

After the domain types, one UI slice, tension engine, winder service shell, and
PLC boundary are proven, consolidate the operator apps:

- replace the static winder web UI with SvelteKit;
- replace Tkinter tension screens with Tauri/Svelte;
- share components where workflows genuinely overlap;
- keep hardware control, audio, persistence, and file I/O in Rust.

This is mostly product polish and maintainability. It should follow the core
runtime decisions, not lead them.

## Suggested order

1. Add the same-repo Cargo workspace, initial `crates/`, `tests/golden/`, and
   `calibration/` skeleton.
2. Define shared Rust domain/API types and generate TypeScript bindings.
3. Add Python-versus-Rust golden parity tests for one deterministic workflow.
4. Build one SvelteKit UI slice against existing behavior.
5. Port offline geometry, recipe, and motion planning behind parity tests.
6. Build the Rust `dune_tension` audio/inference core with comparison harnesses.
7. Build the Rust winder service shell and exhaustive state machine.
8. Run the PLC hardware spike, then choose native Rust PLC I/O or typed Python
   sidecar.
9. Consolidate the full Svelte/Tauri operator apps after the core boundaries are
   proven.

## Main risks

- **PLC support:** highest technical risk. Resolve with a hardware spike before
  committing to the port.
- **Rewrite size:** avoid both a big-bang migration and an isolated second
  system. Keep the Rust port in the same repo, continuously tested against
  Python, and cut over only at narrow boundaries.
- **Artifact drift:** calibration files, PLC tag snapshots, generated bindings,
  and golden fixtures can silently diverge. Give each artifact a clear owner,
  location, schema, and regeneration procedure.
- **Rust compile times:** manage with crate boundaries and `cargo watch`.
- **Team skill cost:** Rust and Svelte are worth it only if they become the
  project standard rather than a parallel experiment.
- **Overusing Haskell:** keep it at pure boundaries; avoid placing live hardware
  reliability on missing ecosystem pieces.

## Bottom line

The best fresh-start stack is not one language everywhere. It is a typed,
hardware-capable Rust runtime; a generated-type TypeScript/Svelte UI; Tauri for
desktop delivery; and Haskell retained for compiler-like offline work.

The best migration path is same-repo and parallel-first: add Rust beside the
working Python system, share artifacts and calibration data, prove behavior with
golden tests, then transfer live responsibility one narrow boundary at a time.

That stack addresses the actual complaints: stronger state modeling, safer API
contracts, better real-time behavior, more maintainable UIs, and a credible path
to deployment on lab machines.
