# Rewrite of the PLC tag interface (Rust) and the STATE / NEXTSTATE / STATE_REQUEST contract

## Context

Three layered problems share the same load-bearing object:

**1. `PLC.Tag` is the wrong shape.** Cache, subscription, driver coupling, and name registry are mashed into one class held together by class-level mutable state, an empirical 14-tag batch limit, no freshness metadata, and a `pollAll(plc)` static method that depends on the application loop. ~76 `PLC.Tag(...)` constructor calls across 13 files duplicate the contract everywhere it appears.

**2. `STATE` / `NEXTSTATE` / `STATE_REQUEST` has no handshake.** `_requestState` (`plc_logic.py:339`) writes and returns; `isReady` (`plc_logic.py:106`) infers from cache; transient `ERROR` bounces are invisible; rejections are silent.

**3. Some sequencing logic in the ladder is dispensable** — completion-tolerance comparisons and error-code string composition. **The safety-load-bearing parts are not.** Movement interlocks (Z-extended gating, `MASTER_Z_GO`, `X_XFER_OK`/`Y_XFER_OK`, axis-fault catching, tension-stable gating, EOT, STO/SLS) must remain on the PLC and must not become bypassable from Python.

The plan rebuilds the tag layer in Rust (aligning with the in-flight `rust/crates/` migration), wires Python to it via PyO3, replaces the dispatch contract with an explicit handshake, and thins the ladder only along the dimensions that are not safety-load-bearing.

## What stays on the PLC vs. what moves to Python (final)

**Stays on PLC — safety, sub-scan latency, or both:**

- **All movement interlocks.** Per-state entry and during-motion checks: Z-extended/retracted gating for XY moves, `MASTER_Z_GO` for Z moves, `X_XFER_OK`/`Y_XFER_OK` for transfer moves, tension-stable for any move, axis-fault catching, EOT latching, latch-position preconditions for Z motion. The PLC owns the question "is this motion safe to start / continue?". Python cannot bypass it.
- STO and SLS in `Safety/`.
- `state_6_latch` pulse sequencing (25 ms / 600 ms).
- `tension_pid` loop.
- `queued_motion` FIFO during recipe playback.
- `state_11_eot_trip` latch.
- Servo enable/disable primitives (MSF/MSO/MAFR) and fault reset.

**Moves to Python — sequencing and judgement, never safety:**

- Move *completion* judgement (today's `|actual − target| < 0.1 mm` rungs). Tolerance is a calibration choice, not a safety condition; if Python misjudges, the PLC's interlocks still hold the line.
- Error-code *string composition*. The PLC publishes raw fault flag bits; Python expands to the legacy `ERROR_CODES` strings.
- Multi-state *choreography* (transfer flows, retry policy, recovery sequencing). The PLC's per-state safety interlocks remain authoritative — Python issues a request, the PLC accepts or rejects based on safety, Python responds to the outcome.
- All retry / timeout / backoff policy.

The line is sharp: the PLC says no when it isn't safe; the PLC says done when its primitive trajectory finishes; Python decides what to do next.

# Part 1 — Rust tag bus with Python bindings

## Why Rust

The `rust/crates/` migration is already underway (per the existing `port_strategy` memory and `dune_tension_core`, `dune-audio` crates on disk). The PLC bus is exactly the layer that benefits most from leaving Python:

- Real-time poll-wheel scheduling without GIL contention. The CRITICAL-tier 20 ms cadence is tight enough that a Python worker thread fights itself.
- Compile-time capability separation. Rust's type system makes `Read<T>` / `Write<T>` / `ReadWrite<T>` static, not protocol-based suggestions.
- Compile-time freshness invariants (newtype wrappers around `Snapshot<T>` make stale values syntactically obvious).
- Crossbeam channels + tokio for coalescing and pipelining without the Python threading footguns.
- Native instrumentation with negligible overhead.

Python keeps speaking to the bus; the bus is just a native extension. Maintenance follows the existing port strategy.

## Crate layout

```
rust/crates/dune_plc_bus/
  Cargo.toml
  build.rs                      -- generates Tags from tags.toml at compile time
  src/
    lib.rs                      -- public API + PyO3 module
    schema.rs                   -- generated Tags definitions
    bus.rs                      -- TagBus, poll wheel, coalescing
    snapshot.rs                 -- Snapshot, Source, freshness
    capability.rs               -- Read/Write/ReadWrite phantom types
    driver.rs                   -- PlcDriver trait
    drivers/
      simulated.rs              -- in-process simulator (port of SimulatedPLC)
      pycomm_bridge.rs          -- Python-side pycomm3 driver, called via PyO3 callback
      shadow.rs                 -- two-driver validation wrapper
    metrics.rs
    error.rs                    -- StaleReadError, WriteFailed, etc.
  tests/
    schedule.rs
    coalesce.rs
    freshness.rs
    capability_compile_fail/    -- trybuild tests proving misuse fails to compile
```

`tags.toml` lives at `dune_winder/plc/tags.toml` (next to the existing `controller_level_tags.json`); a small `tools/plc-sync --tags` step keeps them in sync. `build.rs` parses the TOML and emits a typed `Tags` module with one constant per tag, carrying name, CIP type, semantic Rust type, capability, default tier, and doc string.

## Architectural commitments

1. **Schema-first.** One TOML file declares every tag. Rust generates strongly-typed handles at compile time. Python receives the same schema via the PyO3 module — no second source of truth.
2. **Bus owns lifecycle.** The bus runs its own poll loop in a Rust thread. The Python side never calls `pollAll`. Application shutdown calls `bus.stop()`.
3. **No global mutable state.** Bus is constructed once and injected. Tests build their own bus with their own driver.
4. **Capability enforced at compile time.** `Read<T>` and `Write<T>` are distinct types. `bus.snapshot::<S>(STATE_REQUEST)` does not type-check because `STATE_REQUEST: Write<i32>`. The Python side gets the same enforcement at the binding boundary: PyO3 generates separate Python-visible methods for read-only vs writable tags, and the type stubs carry the constraint.
5. **Tags are passive identifiers.** `TagId<T, Cap>` holds name, CIP type, capability, default tier. No cache, no driver reference. All access is through the bus.
6. **Symmetric API.** `bus.snapshot(t)` / `bus.read_fresh(t, within_ms)` / `bus.observe(t)` for reads; `bus.write(t, v)` / `bus.write_async(t, v)` / `bus.write_many(updates)` for writes.
7. **Freshness is first-class.** Every cached value carries `(value, timestamp_ns, sequence, source)`. `read_fresh(within_ms=W)` is a hard guarantee.
8. **Synchronous default, async opt-in.** `bus.write` blocks on driver acknowledgement (timeout-bounded). `bus.write_async` returns a future. `bus.observe` is a generator on the Python side (PyO3 streams the channel).
9. **Drivers are pure I/O.** `PlcDriver` trait: `connect`, `disconnect`, `health`, `read(names) -> map`, `write(updates) -> map`. No tag state, no caches.
10. **Connection state is observable.** `bus.health` is a single source of truth.

## Schema (excerpt of `tags.toml`)

```toml
[tag.STATE]
cip = "DINT"
type = "i32"
capability = "read"
tier = "critical"
default = 0
doc = "PLC active state machine slot."

[tag.STATE_REQUEST]
cip = "DINT"
type = "i32"
capability = "write"
tier = "critical"
doc = "Direct PLC state request."

[tag.STATE_REQUEST_ID]
cip = "DINT"
type = "i32"
capability = "write"
tier = "critical"
doc = "Monotonic ID for handshake correlation."

[tag.STATE_REQUEST_ACK]
cip = "DINT"
type = "i32"
capability = "read"
tier = "critical"
default = 0
doc = "Most recent STATE_REQUEST_ID consumed by PLC."

[tag.STATE_REQUEST_RESULT]
cip = "DINT"
type = "i32"
capability = "read"
tier = "critical"
default = 0
doc = "0=idle, 1=accepted, 2=rejected, 3=completed, 4=faulted."

[tag.STATE_FAULT_FLAGS]
cip = "DINT"
type = "i32"
capability = "read"
tier = "critical"
default = 0
doc = "Bitfield: 0x01 interlock, 0x02 axis-fault, 0x04 EOT, 0x08 safety, 0x10 tension, 0x20 latch-timeout, 0x40 request-out-of-range."

[tag.xz_position_target]
cip = "REAL[2]"
type = "[f32; 2]"
capability = "write"
tier = "on_demand"
```

Parametric bundles (`X_axis.*`, `Y_axis.*`, `Z_axis.*`, latch tags, queue tags) are expressed via `[bundle.*]` sections and expanded by `build.rs`.

## Bus API (Rust, PyO3 surface)

```rust
pub struct TagBus { /* ... */ }

impl TagBus {
    pub fn new(driver: Box<dyn PlcDriver>, config: BusConfig) -> Self;
    pub fn start(&self);
    pub fn stop(&self);

    // Reads (only callable for TagId<T, Read | ReadWrite>)
    pub fn snapshot<T, C: Readable>(&self, tag: TagId<T, C>) -> Snapshot<T>;
    pub fn read_fresh<T, C: Readable>(&self, tag: TagId<T, C>, within_ms: u32, timeout_ms: u32) -> Result<Snapshot<T>, StaleReadError>;
    pub fn read_many(&self, tags: &[ErasedTagId]) -> HashMap<ErasedTagId, Snapshot<Value>>;
    pub fn observe<T, C: Readable>(&self, tag: TagId<T, C>) -> Receiver<Snapshot<T>>;
    pub fn subscribe(&self, tag: ErasedTagId, max_age_ms: u32) -> Subscription;

    // Writes (only callable for TagId<T, Write | ReadWrite>)
    pub fn write<T, C: Writable>(&self, tag: TagId<T, C>, value: T, timeout_ms: u32) -> Result<WriteOutcome, WriteFailed>;
    pub fn write_async<T, C: Writable>(&self, tag: TagId<T, C>, value: T) -> Future<Result<WriteOutcome, WriteFailed>>;
    pub fn write_many(&self, updates: Vec<(ErasedTagId, Value)>, timeout_ms: u32) -> HashMap<ErasedTagId, Result<WriteOutcome, WriteFailed>>;

    pub fn health(&self) -> Health;
    pub fn metrics(&self) -> &Metrics;
}
```

The PyO3 binding exposes `TagBus` and the generated `Tags` constants. Python code writes:

```python
from dune_plc_bus import TagBus, Tags

bus = TagBus(driver=PycommDriver(ip="192.168.1.10"))
bus.start()

snap = bus.snapshot(Tags.STATE)            # Snapshot[int]
bus.write_many({
    Tags.STATE_REQUEST_ID: next_id,
    Tags.STATE_REQUEST: PLCMode.XY_SEEK,
})
ack = bus.read_fresh(Tags.STATE_REQUEST_ACK, within_ms=20)
```

## Bus internals

- **Poll wheel.** Each tag has an effective period = `min(max_age_ms across live subscribers)`. A worker thread runs a tick at the granularity of the smallest configured tier (~5 ms). Each tick computes due tags, packs them into batches up to the driver's connection-size budget, and dispatches.
- **Read coalescing.** Concurrent `read_fresh` for the same tag in the same tick share one driver round-trip via a per-tag pending-read promise.
- **Write coalescing.** Repeated writes to the same tag inside one tick collapse to the latest value. Mixed-tag writes go out as one bulk write; per-caller outcomes resolve when the bulk write returns.
- **Pipelined batching.** Next read batch dispatches as soon as the previous response is parsed.
- **Cache invalidation on write.** Successful write updates cache with `Source::WriteEcho`; the next poll confirms.
- **Backoff and reconnect.** Driver error → tags become `Source::Stale`, exponential backoff, single-tag probe drives reconnection. `read_fresh` returns `StaleReadError` while down. No "permanently unfunctional" mode.
- **Metrics.** `plc_tag_reads_total{tier,outcome}`, `plc_tag_writes_total{outcome}`, `plc_read_latency_ms`, `plc_write_latency_ms`, `plc_batch_fill_ratio`, `plc_batch_size`, `plc_subscription_count{tier}`, `plc_freshness_age_ms{tier}` (sampled at every `snapshot()`), `plc_stale_read_errors_total`. Exported through PyO3 to the existing `core/metrics_collector.py`.

## Drivers

```rust
pub trait PlcDriver: Send {
    fn connect(&mut self) -> Result<(), DriverError>;
    fn disconnect(&mut self);
    fn health(&self) -> Health;
    fn read(&mut self, names: &[&str]) -> Result<HashMap<String, Value>, DriverError>;
    fn write(&mut self, updates: &[(&str, Value)]) -> Result<HashMap<String, bool>, DriverError>;
}
```

- **`SimulatedDriver`** — pure Rust port of `simulated_plc.py`. Same semantics; the existing simulator's behaviour (state-machine writes, MACHINE_SW_STAT bit derivation, queued-motion handling) is reproduced, validated by running the existing `tests/dune_winder/test_head_g106_transfer.py::G206TransferLadderTests` against the new simulator.
- **`PycommBridge`** — Rust shim that calls back into Python pycomm3 via PyO3. Keeps the mature pycomm3 driver in place during the migration; the Rust bus owns scheduling, coalescing, and freshness; pycomm3 is just the wire. Bridge overhead is small (~tens of µs per batch); it is acceptable while we get the rest of the system stabilised.
- **`ShadowDriver`** — runs two backends in parallel and reports mismatches; mirrors today's `shadow_plc.py`.

A future PR can replace `PycommBridge` with a native Rust EIP/CIP driver (`enip`/`cip` crate or hand-written) once the bus is settled. Out of scope for this plan.

## Migration mechanics

The migration is broad but mechanical. Each step is independently revertable.

1. **Land the Rust crate.** `dune_plc_bus` builds, has unit tests, generates `Tags` from `tags.toml`. Python can `import dune_plc_bus` and construct a bus over `SimulatedDriver`.
2. **Convert consumers in dependency order.** `plc_motor.py`, `plc_input.py`, `camera.py`, `queued_motion/plc_interface.py`, `base_io.py`, `plc_logic.py`, `plc_direct.py`. Each consumer drops `PLC.Tag(...)` constructions and accepts a `TagBus` instead of a `PLC`. Per-consumer PRs.
3. **Migrate tests.** `_FreshReadPLC` is replaced by a small `FakeDriver` (Rust or Python helper around `SimulatedDriver`). Each consumer's test file converts when the consumer does.
4. **Delete legacy.** `src/dune_winder/io/devices/plc.py`, `controllogix_plc.py`, `simulated_plc.py`, `shadow_plc.py` are deleted once unused.

The public API of `PLC_Logic` (the freeze list — `setXY_Position`, `setZ_Position`, `move_latch`, `isReady`, `getState`, `getErrorCode`, `getTransferStateNow`, `setupLimits`, `States`, `MoveTypes`, `LatchPosition`, `ERROR_CODES`) is preserved. The `__init__` signature changes from `(plc, xyAxis, zAxis)` to `(bus, xyAxis, zAxis)` — a single-line edit at every construction site.

# Part 2 — STATE / NEXTSTATE / STATE_REQUEST handshake

The dispatch handshake sits on top of the bus.

## New tags (additive, polled at `Tier::Critical`)

| Tag | Type | Owner | Purpose |
|---|---|---|---|
| `STATE_REQUEST_ID` | DINT | Python writes | Monotonic counter; incremented on every `_requestState`. |
| `STATE_REQUEST_ACK` | DINT | PLC writes | Echoes the most recently consumed `STATE_REQUEST_ID`. |
| `STATE_REQUEST_RESULT` | DINT | PLC writes | `0`=idle, `1`=accepted, `2`=rejected, `3`=completed, `4`=faulted. |
| `STATE_FAULT_FLAGS` | DINT (bitfield) | PLC writes | `0x01` interlock, `0x02` axis-fault, `0x04` EOT, `0x08` safety, `0x10` tension, `0x20` latch-timeout, `0x40` request-out-of-range. |
| `STATE_ENTRY_COUNTER` | DINT | PLC writes | Incremented every scan in which `STATE` actually changes. |
| `LAST_STATE` | DINT | PLC writes | Previous `STATE` latched on transition. |

## Ladder changes

**`dune_winder/plc/main/main/`** — make the `NEXTSTATE → STATE` copy edge-driven and maintain `STATE_ENTRY_COUNTER` and `LAST_STATE`:

```
XIC INIT_DONE CMP "NEXTSTATE=N" XIO "STATE=N"
  CPT LAST_STATE STATE
  CPT STATE_ENTRY_COUNTER (STATE_ENTRY_COUNTER + 1)
  CPT STATE N
```

**`state_1_ready/main/`** — explicit handshake. On `STATE_REQUEST ∈ valid set` AND `STATE_REQUEST_ID ≠ STATE_REQUEST_ACK`: copy ID into ACK, `RESULT = 1`, clear `STATE_FAULT_FLAGS`, dispatch via `NEXTSTATE`. Out-of-range request: `RESULT = 2`, `STATE_FAULT_FLAGS |= 0x40`, clear `STATE_REQUEST` without changing `NEXTSTATE`.

**`state_3_move_xy`, `state_5_move_z`, `state_12_move_xz`, `state_13_move_yz`, `state_9_unservo`, `state_14_hmi_stop`** — **safety interlocks preserved**, sequencing thinned. Each handler:

- **Keeps every entry interlock.** Z-extended/retracted gating, `MASTER_Z_GO`, `X_XFER_OK`/`Y_XFER_OK`, axis fault, tension stable, latch position. On any interlock failing at entry: set the appropriate `STATE_FAULT_FLAGS` bit, `RESULT = 2` (rejected), `NEXTSTATE = 10`.
- **Keeps every during-motion interlock.** Same checks re-evaluated each scan; on drop: set the appropriate flag, `RESULT = 4` (faulted), `NEXTSTATE = 10`.
- **Drops** the inline `CMP "ABS(actual − target) < 0.1"` rungs. Python evaluates done.
- **Drops** the `CPT ERROR_CODE 5001`-style rungs. Python composes from `(LAST_STATE, STATE_FAULT_FLAGS)`.
- On natural completion (`MoveStatus.PC` / `.DN`): `RESULT = 3`, `NEXTSTATE = 1`.

**`state_10_error`** — keeps its safety-adjacent stop/MSF behaviour; drops the error-code translation rungs; gates exit on `STATE_REQUEST → 0` as today.

**Untouched:** `state_6_latch`, `state_11_eot_trip`, `Safety/`, `tension_pid/`, `queued_motion/`, `init/`.

The safety story is unchanged: every PLC-side gate that prevents unsafe motion is still there. What goes away is decorative — tolerance comparisons whose miscalibration would not endanger anything, and string composition that has no bearing on whether the move is permitted.

## Python changes (`plc_logic.py`)

After the bus migration, `PLC_Logic` is re-expressed against the bus. The handshake additions:

1. `__init__(self, bus, xyAxis, zAxis)` — store `self._bus`. `self._lastIssuedRequestId = 0`. Subscribe `STATE_REQUEST_ACK`, `STATE_REQUEST_RESULT`, `STATE_FAULT_FLAGS`, `STATE_ENTRY_COUNTER`, `LAST_STATE` at `max_age_ms=20`.
2. `_requestState(state)` — keep `_DIRECT_STATE_REQUESTS` validation. Increment `_lastIssuedRequestId`. `bus.write_many({Tags.STATE_REQUEST_ID: id, Tags.STATE_REQUEST: state})` — single round-trip; the bus orders the writes inside one packet. Non-blocking from the caller's perspective.
3. `_awaitRequestAccepted(timeout_ms=250)` — `bus.read_fresh(Tags.STATE_REQUEST_ACK, within_ms=20)` until ACK matches `_lastIssuedRequestId`. With the CRITICAL tier the cache is usually already fresh.
4. `isReady` — preserve signature: ready iff `RESULT in {0, 3}` once ACK matches; legacy fallback (`STATE == READY ∧ STATE_REQUEST == 0`) used only when the new tags are zeroed (transitional firmware).
5. `getErrorCode` / `getErrorCodeString` — derive the legacy code from `(LAST_STATE, STATE_FAULT_FLAGS)`; the existing `ERROR_CODES` dict stays as the canonical string source.
6. `_isPrimitiveComplete(target_axes, target_position, tolerance=0.1)` — `bus.read_fresh` of axis positions, compare. Public `setXY_Position`, `setZ_Position`, `setXZ_Position`, `setYZ_Position` keep their signatures.
7. New diagnostics: `getStateRequestResult()`, `getStateFaultFlags()`, `getStateEntryCounter()`, `getLastState()` for `Head._updateG206` and `ControlStateMachine` to detect transient `ERROR` bounces.

# Sequencing

Three phases, each independently revertable:

1. **Phase A — Rust bus + drivers + consumer migration.** Land `dune_plc_bus`; convert consumers in dependency order; delete legacy Python tag layer once unused. Behaviour preserved.
2. **Phase B — handshake.** Add the six schema entries and the corresponding ladder edits in `main/main/` and `state_1_ready/main/` only. Python `_requestState` / `isReady` / `_awaitRequestAccepted` / diagnostics changes. Per-state handlers untouched.
3. **Phase C — thin per-state handlers.** Strip completion-tolerance and `ERROR_CODE` composition rungs; **leave every interlock**. Roll out one state at a time: `state_5_move_z`, then `state_3_move_xy`, then `state_12_move_xz` / `state_13_move_yz`, then `state_9_unservo` / `state_14_hmi_stop`, then `state_10_error`. Each cut is a separate PR with simulated-ladder coverage.

# Files in scope

**Rust (new):**
- `rust/crates/dune_plc_bus/Cargo.toml`, `build.rs`, `src/`, `tests/`.

**Python:**
- `src/dune_winder/io/devices/plc.py` — deleted at end of Phase A.
- `src/dune_winder/io/devices/controllogix_plc.py`, `simulated_plc.py`, `shadow_plc.py` — deleted at end of Phase A.
- `src/dune_winder/io/primitives/plc_motor.py`, `plc_input.py` — accept a `TagBus`.
- `src/dune_winder/io/maps/base_io.py` — construct the bus, wire it.
- `src/dune_winder/io/controllers/plc_logic.py`, `camera.py` — converted; `plc_logic.py` also gets the handshake additions.
- `src/dune_winder/queued_motion/plc_interface.py` — converted.
- `src/dune_tension/plc_direct.py` — converted.
- `src/dune_winder/core/metrics_collector.py`, `io_log.py` — wire bus metrics.

**Schema and tooling:**
- `dune_winder/plc/tags.toml` (new) — schema source of truth.
- `tools/plc-sync` — extend with `--tags` mode that diff-checks `tags.toml` against `controller_level_tags.json`.

**PLC ladder:**
- `dune_winder/plc/main/main/source.rllscrap` — transition counter, `LAST_STATE`.
- `dune_winder/plc/state_1_ready/main/source.rllscrap` — handshake, `RESULT`, range check.
- `dune_winder/plc/state_3_move_xy/`, `state_5_move_z/`, `state_12_move_xz/`, `state_13_move_yz/`, `state_9_unservo/`, `state_14_hmi_stop/`, `state_10_error/` — Phase C: drop tolerance + error-code-string rungs only; keep every interlock.
- `dune_winder/plc/controller_level_tags.json` — register six new DINT tags.
- `dune_winder/plc/manifest.json` — regenerated by `uv run plc-sync --offline`.

# Verification

1. **Rust unit tests (`rust/crates/dune_plc_bus/tests/`):**
   - Tier scheduling: tags poll at the configured cadence; verify with a fake clock.
   - Read coalescing: two concurrent `read_fresh` for the same tag → one driver `read()`.
   - Write coalescing: `write(t,1); write(t,2)` in one tick → one driver `write()` carrying value 2.
   - Capability: `trybuild`-style compile-fail tests prove `bus.snapshot(WRITE_TAG)` and `bus.write(READ_TAG)` do not compile.
   - Freshness: `read_fresh(within_ms=10)` against a 50 ms-old cache triggers a network read; against a 5 ms-old cache returns immediately.
   - Stale on disconnect: simulate driver failure → `read_fresh` returns `StaleReadError`; `snapshot()` returns the cached value with `Source::Stale`.
   - Backoff/recovery.
   - Subscription refcount.

2. **PyO3 binding tests.** Python smoke test that imports `dune_plc_bus`, constructs a bus over `SimulatedDriver`, exercises `snapshot`, `read_fresh`, `write`, `write_many`, `observe`, `subscribe`. Verifies that the Python type stubs reject `bus.snapshot(Tags.STATE_REQUEST)` (a static check via mypy/pyright on the test).

3. **Per-consumer tests.** Every converted file (`plc_logic.py`, `camera.py`, `plc_interface.py`, `plc_direct.py`, `plc_motor.py`, `plc_input.py`) keeps its existing test file passing against a `FakeDriver`. No behavioural change from the consumer's perspective.

4. **Dispatch handshake tests.** Ack ordering, each `RESULT` outcome (1/2/3/4), fault-flag → error-code mapping covering states 3/5/6/12/13. **Specific safety regression tests** for each interlock: e.g. request Z_SEEK with `MASTER_Z_GO` low and assert `RESULT == 2`, `STATE_FAULT_FLAGS & 0x01`; request XY_SEEK with Z extended and assert rejection; request XZ_SEEK with `Y_XFER_OK` low and assert rejection. These tests must pass on the simulated ladder and on hardware.

5. **Ladder simulation.** `tests/dune_winder/test_head_g106_transfer.py::G206TransferLadderTests` running against the Rust `SimulatedDriver` — full Python ↔ PLC contract through `Head`. Stage→fixed and fixed→stage transfers complete with no regression in timing or final-state validation.

6. **Manifest integrity.** `uv run plc-sync --offline` regenerates `manifest.json` and `pasteable.rll` files without warnings; `controller_level_tags.json` parses cleanly. `uv run plc-sync --tags` diff-checks `tags.toml` against `controller_level_tags.json` and fails if drifted.

7. **Bandwidth measurement (instrumented).** 60-second loop in the simulator that exercises every tier; record `plc_tag_reads_total / interval` and `plc_freshness_age_ms` histograms. Acceptance: `CRITICAL` tier 95p staleness < 30 ms; aggregate read throughput ≥ 3× the measured baseline of the existing implementation. The Rust scheduler is the reason this is realistic.

8. **Hardware smoke test (operator-supervised).**
   - Manual XY/Z/XZ/YZ sequence from `specs/operator-workflows.allium`.
   - `getStateEntryCounter()` increments on every transition.
   - **Interlock regression**: each interlock listed in the safety section above is exercised by deliberately violating its precondition; assert the PLC rejects the request and that `getErrorCodeString()` produces the same legacy string the operator is used to.
   - `reset()` clears flags and returns to READY.
   - Pull the Ethernet cable mid-move: `read_fresh` raises `StaleReadError`; reconnect; bus recovers; metrics show one `plc_stale_read_errors_total` and clean reconnection.

9. **Latency budget check.** Round-trip from Python `setZ_Position` → `STATE_REQUEST_RESULT == 3` is within one `CRITICAL` tier period (~30 ms) plus one PLC scan, on the simulated ladder. Latch pulse, tension PID, and queued-motion paths show no measurable change because their ladder code is untouched.
