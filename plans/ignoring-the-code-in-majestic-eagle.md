# DUNE Winder Host — Foundation + Winding Execution

## Context

Build a fresh host-side implementation of the DUNE winder interface, ignoring the existing Python in `src/dune_winder/`. The Allium specs in `specs/*.allium` are the behavioural source of truth; the PLC code in `dune_winder/plc/` is fixed source-of-truth on the PLC side. We're stopping at the "Foundation + winding execution" boundary: PLC bridge, state-machine mirror, motion-safety gate, queued-motion handshake, head-transfer choreography, recipe/macro processing, manual-motion + winding-run workflows, an HTTP/WS API, and an Elm operator UI. Tension control/measurement and calibration capture are deferred to follow-on plans.

The PLC's `transfer/main` ladder is empty — the host owns transfer choreography. Tension linearisation is hardcoded in PLC ladder (no `cal_c1..c4` tags); host reads tension only.

## Toolchain (chosen)

- **Rust** (edition 2021, MSRV 1.83 to match the existing `rust/` workspace) for the host control layer. Statically typed; sum types + exhaustive `match` cover the "functional safety" win, `Result` over `Either`, no GC pauses for hours-long winding runs.
- **`rust-ethernet-ip`** (pure Rust, async, Tokio-based) for EtherNet/IP CIP against Allen-Bradley ControlLogix. No FFI, no C build artifacts, no `unsafe` in the host code; `cargo build` is the only toolchain. Trade-off: at 0.7.0 it is younger than libplctag and earns an extra real-hardware smoke gate in P11.
- **`tokio`** runtime for async tasks; **`axum`** for type-safe HTTP + WebSockets; **`tower`** for middleware; **`serde`/`serde_json`** for wire types.
- **`elm_rs`** for Rust→Elm type generation; output committed and CI-checked for drift.
- **`winnow`** for the recipe parser (modern descendant of `nom`, ergonomic combinator style).
- **`proptest`** for property-based tests.
- **`arc-swap`** + **`tokio::sync::{watch, mpsc, broadcast}`** as the concurrency primitives (no STM, but the same shape — single shared snapshot, bounded queues, fan-out broadcasts).
- Targets: **Windows lab workstation** (`x86_64-pc-windows-msvc`, primary deployment) and **Linux** (`x86_64-unknown-linux-gnu`, primary CI / dev). Both are first-class.

## Architecture (onion, downward-only deps)

Add these as new **workspace member crates** under `/Users/ben/dune-monorepo/rust/crates/`. Layer enforcement is via the `[dependencies]` graph in each `Cargo.toml` — a violation is a compile error.

| Crate | Owns | Spec / PLC anchor |
|---|---|---|
| `dune-winder-domain` (no_std-friendly) | Enums (state codes 0–14, `MoveType` {1,2,4,5,8,9,11}, `ActuatorPos` {0..3}), `MotionSegment`, `Vec2`, `TagPath`, units. | `core.allium`, `winder-states.allium`, `winder-hardware-interfaces.allium` |
| `dune-winder-geometry` (pure) | Frames, calibration loader (`machineCalibration.json`), backlash compensation, arc chord-step iterator, envelopes/keepouts. | `layer-geometry.allium`, `uv-wrap-geometry.allium`, `winder-calibration.allium` |
| `dune-winder-safety` (pure) | `safety::gate::validate(state: &CollisionState, seg: &MotionSegment) -> Result<Validated, Violation>`. Envelope, transfer exclusion, headward-pivot, z-extended forbidden boxes, arc chord-step validation. Z `NoLatchCollision ∧ NoApaCollision ∧ NoSupportsCollision`. | `motion-safety.allium` |
| `dune-winder-plc` (async IO) | `PlcBackend` trait wrapping `rust-ethernet-ip::EipClient`, UDT byte-blob codecs (`MotionSeg`, `IncomingSeg`) with `bytes`, reconnect via the crate's `PlcManager`, sim backend. `#![forbid(unsafe_code)]` like every other crate. | `winder-hardware-interfaces.allium`; `plc/controller_level_tags.json`; `plc/queued_motion/programTags.json` |
| `dune-winder-mirror` (async) | Owns the polling task; publishes a `watch::Receiver<PlcSnapshot>` (machine switches, motion targets, queue state, tension reads, transfer sensors). | `winder-states.allium` controllers |
| `dune-winder-control` (async) | Movement-allowed predicate, queue submitter (caps on `QueueCount<32`, handshake `IncomingSeg`/`ReqID`/`Ack`), HMI Stop semantics. | `winder-states.allium` rules; `plc/queued_motion/main` |
| `dune-winder-transfer` (async) | Modern + legacy head-transfer FSMs with `latch_timeout`/`extend_timeout` and final-state verification. Total `match` over state enum; no `_ =>` arms. | `winder-states.allium` `Modern*`, `Legacy*`, `*Latch*`, `Z*` |
| `dune-winder-recipe` (pure) | `winnow` parser + expander; `continuous_wrap_order(layer)`. | `winder-macros.allium`, `layer-geometry.allium` |
| `dune-winder-workflows` (async) | `ManualMotionRequest` and `WindingRun` lifecycle FSMs. | `operator-workflows.allium` |
| `dune-winder-api` (async) | `axum` routes + WebSocket broadcast, `elm_rs` codegen entry point, static asset serving. | `operator-workflows.allium` `OperatorWorkflowConsole` |
| `dune-winder-host` (binary) | Wires crates, parses `configuration.toml`, opens libplctag, supervises tasks via `tokio::task::JoinSet`. | `dune_winder/configuration.toml` |
| `dune-winder-elm-codegen` (binary) | Re-emits `elm/src/Generated/Types.elm` from Rust types via `elm_rs::Elm`; CI runs and diffs. | — |

**`PlcBackend` shape** — an async trait, since `rust-ethernet-ip` is async-native. The trait composes with `Arc<dyn PlcBackend>` for the real/sim swap.

```rust
#[async_trait::async_trait]
pub trait PlcBackend: Send + Sync {
    async fn read_tags(&self, paths: &[TagPath]) -> Result<Vec<TagValue>, PlcError>;
    async fn write_tag(&self, path: &TagPath, value: TagValue) -> Result<(), PlcError>;
    async fn close(self: Arc<Self>);
}
```

Subscription is owned by `dune-winder-mirror`, not the backend — the mirror runs the poll task and exposes a `watch::Receiver<PlcSnapshot>` to consumers. `TagValue` is an enum: `VBool(bool) | VDInt(i32) | VReal(f32) | VRaw(Bytes)`; `VRaw` carries UDT blobs decoded by pure codecs in `dune-winder-plc`. The sim backend is just another `impl PlcBackend` — a `parking_lot::RwLock<HashMap<TagPath, TagValue>>` plus a worker that flips `IncomingSegAck`.

## Concurrency model

One `tokio` task per long-lived responsibility, sharing an `AppState` of `Arc`s, supervised by a root `JoinSet` with cancellation via a `CancellationToken`.

- **PollLoop** (~50 ms) — owns the `Arc<dyn PlcBackend>`, awaits async batch reads, publishes the new snapshot via `watch::Sender<PlcSnapshot>`. Single sender, many receivers.
- **QueueSubmitter** consumes from `mpsc::channel::<ValidatedSegment>(N)` (filled only after `safety::gate::validate` returns `Ok`). Reads `QueueCount` from a `watch::Receiver<PlcSnapshot>` via `changed().await` — no polling races with the poll loop because the same snapshot drives the cap check and the wake-up. Writes `IncomingSeg`/`IncomingSegReqID`; awaits `IncomingSegAck` flip on the same receiver. Backpressure is the channel's capacity.
- **TransferDriver** is a per-command task running the modern/legacy FSM with `tokio::time::timeout`.
- **WorkflowController** holds an `Arc<RwLock<WorkflowState>>` (or an actor-style task with an `mpsc::Receiver<WorkflowCmd>`); emits `DomainEvent`s on a `broadcast::Sender`.
- **WS broadcaster**: each WebSocket client subscribes via `broadcast::Receiver`; broadcaster diffs snapshot+workflow and pushes JSON deltas.
- HMI Stop: drain the segment `mpsc`, write `IncomingSeg.Valid=false`, transition runs to `paused/stopped`.

`arc-swap::ArcSwap<PlcSnapshot>` is the alternative if `watch` ergonomics chafe; the plan starts with `watch` because it gives `changed().await` for free.

## Phased work plan

Each phase is independently mergeable and verifiable.

1. **P1 — Domain skeleton + workspace crates.** Add the twelve crates to the `rust/` workspace; fill `dune-winder-domain`. Verify: `cargo build --workspace` and `cargo clippy -- -D warnings` pass; proptest round-trip of enums against PLC numeric codes.
2. **P2 — Geometry & calibration.** Frames, backlash, arc chord-steps, `machineCalibration.json` loader. Property: backlash-comp X stays in `[limit_left, limit_right]` or returns `Err`.
3. **P3 — Motion safety gate.** Envelope, transfer exclusion, headward-pivot, z-extended forbidden boxes, Z conjunction. proptest suite generated via the `propagate` skill from `motion-safety.allium`.
4. **P4 — PLC client + sim backend.** Wrap `rust-ethernet-ip::EipClient` behind the async `PlcBackend` trait. UDT offsets transcribed from `controller_level_tags.json` and `plc/queued_motion/programTags.json` (raw byte-blob reads → pure-Rust offset decoders for `MotionSeg`, `IncomingSeg`). Sim backend is an `impl PlcBackend` over a `parking_lot::RwLock<HashMap<TagPath, TagValue>>`. Verify: round-trip read/write through sim; loopback of `MotionSeg` blob = original.
5. **P5 — Mirror + poll groups.** Snapshot `watch` channel, poll loop, reconnect/backoff. Verify: sim tag flips observed via `changed().await` within one poll period; reconnect after disconnect.
6. **P6 — Queue submitter + handshake.** `mpsc`-driven feed, cap on `QueueCount<32` from the snapshot, `IncomingSeg`/`ReqID`/`Ack` handshake. Verify: 100-segment ordered submission against sim, no overrun, channel backpressure observable.
7. **P7 — Head-transfer choreography.** Modern + legacy + latch + Z-extension FSMs as `enum State { … }` with total `match`. Verify: state-machine property test driven by sim-injected `ACTUATOR_POS`/`MASTER_Z_GO` transitions; final-state verification gate.
8. **P8 — Recipe parser + expansion.** `winnow` parser; expansion to `Vec<ProgramItem>`. Verify: round-trip + golden fixtures; monotone advance through `continuous_wrap_order`.
9. **P9 — Workflows: manual + winding run.** Manual (jog, seeks XY/Z/XZ/YZ, pin seek, head transfer, servo idle, stop) and winding run (start/pause/resume/stop). Verify: end-to-end one-layer wind against sim — no safety violations, monotonic step advance.
10. **P10 — `axum` API + Elm UI + bridge.** `dune-winder-elm-codegen` writes `elm/src/Generated/Types.elm`; `axum` routes for commands; WebSocket for snapshot deltas. Elm pages: dashboard, manual, wind. Verify: UI smoke against sim; type-drift check in CI (`cargo run -p dune-winder-elm-codegen -- --check`).
11. **P11 — Cross-platform packaging.** Single `cargo build --release` per target (no C deps to vendor). Bundle Elm assets (e.g., `rust-embed`); CI matrix for `x86_64-pc-windows-msvc` and `x86_64-unknown-linux-gnu`; smoke on lab Windows workstation in sim mode, then read-only against real PLC (extra dwell here because `rust-ethernet-ip` is younger than libplctag — verify scalar reads, then UDT reads, then UDT writes, then handshake), then small jog with safety gate, then scripted modern transfer, then full-layer wind.

## Critical files to create

Workspace: edit `/Users/ben/dune-monorepo/rust/Cargo.toml` to add the twelve new members, plus shared `[workspace.dependencies]` for `tokio`, `axum`, `tower`, `tokio-tungstenite`, `serde`, `serde_json`, `bytes`, `rust-ethernet-ip`, `async-trait`, `winnow`, `proptest`, `arc-swap`, `parking_lot`, `tracing`, `tracing-subscriber`, `clap`, `elm_rs`.

Crates under `/Users/ben/dune-monorepo/rust/crates/`:

- `dune-winder-domain/src/{lib,types,state,motion,tag}.rs`
- `dune-winder-geometry/src/{lib,segment,arc,calibration}.rs`
- `dune-winder-safety/src/{lib,gate,collision,forbidden}.rs`
- `dune-winder-plc/src/{lib,backend,tags,layout,eip,sim}.rs`
- `dune-winder-mirror/src/{lib,snapshot,poll}.rs`
- `dune-winder-control/src/{lib,movement,queue_submitter,handshake}.rs`
- `dune-winder-transfer/src/{lib,modern,legacy,latch,z}.rs`
- `dune-winder-recipe/src/{lib,parse,expand,program}.rs`
- `dune-winder-workflows/src/{lib,manual,wind,run}.rs`
- `dune-winder-api/src/{lib,server,routes,ws,elm_bridge}.rs`
- `dune-winder-host/src/main.rs`
- `dune-winder-elm-codegen/src/main.rs`

Tests live alongside crates (`#[cfg(test)] mod tests`) plus an integration harness at `dune-winder-host/tests/end_to_end_sim.rs`.

Elm under `/Users/ben/dune-monorepo/dune_winder/elm/`:

- `elm.json`
- `src/{Main,Api,Api/Ws}.elm`
- `src/Pages/{Dashboard,Manual,Wind}.elm`
- `src/Generated/Types.elm` (committed; CI-checked)

Build tooling: none — single-toolchain `cargo` builds for both platforms.

## Risks & mitigations

1. **`rust-ethernet-ip` maturity (0.7.0).** Younger than libplctag; ControlLogix UDT corner cases may surface. Mitigation: pin the version in `Cargo.lock`; in P4 verify against sim first, then in P11 walk a longer real-PLC ladder than originally planned (scalar read → UDT read → UDT write → segment handshake) before motion. If a blocker shows up, the swap back to libplctag-via-FFI is bounded to the `dune-winder-plc` crate by design.
2. **Elm/Rust type drift.** `dune-winder-elm-codegen` runs in CI with `--check`; build fails if `Generated/Types.elm` differs from regenerated output.
3. **Snapshot race: poll loop vs queue submitter.** Single `watch::Sender<PlcSnapshot>`; submitter blocks on `changed().await`, never sleeps. proptest concurrent-timeline tests against sim using `tokio::task::spawn` and deterministic clocks (`tokio::time::pause`).
4. **Recipe macro expansion correctness.** Parse → expand → re-print round-trip property; golden fixtures; cross-check with `propagate` skill against `winder-macros.allium`.
5. **Head-transfer protocol edge cases.** Encode FSM as explicit `enum State` with total `match` (deny `_ =>` via clippy lint `clippy::wildcard_enum_match_arm`); generate state-machine property tests from `winder-states.allium`; final-state verification is a hard gate before declaring transfer complete.
6. **`unsafe` discipline.** With `rust-ethernet-ip` there is no FFI; every winder crate gets `#![forbid(unsafe_code)]`. If a future regression forces the FFI fallback, lift the lint in `dune-winder-plc` only.

## Verification

**CI (no hardware), matrix on `ubuntu-latest` and `windows-latest`:**

- `cargo build --workspace --all-targets`
- `cargo test --workspace`
- `cargo clippy --workspace --all-targets -- -D warnings`
- `cargo fmt --all -- --check`
- `cargo run -p dune-winder-elm-codegen -- --check` (drift check)
- proptest suites: enum/code round-trip; safety gate; arc chord-steps; queue-submitter timelines; transfer FSM; recipe expansion.
- Integration test through `dune-winder-plc::sim`, including a full one-layer winding run end-to-end.
- `elm make` of the UI; `elm-format --validate`.
- No native artifact reproducibility step — pure-Rust toolchain.

**On hardware (lab Windows workstation), in this order:**

1. Sim-mode host: `dune-winder-host --backend=sim` with `axum` + Elm + workflows running.
2. Real-PLC read-only: connect to `192.168.140.13`, mirror only; verify snapshot matches expected idle state. No writes.
3. Real-PLC manual jog: smallest-possible jog with safety gate enabled; verify `IncomingSeg`/`Ack` handshake and `QueueCount` behaviour.
4. Real-PLC modern head transfer: scripted, operator present, HMI Stop reachable.
5. Full layer wind: gated on (4) succeeding twice without intervention.
