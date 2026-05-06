# Phase C — Per-State Handler Thinning (PLC ladder)

**Status:** Deferred. Phases A (Rust `dune_plc_bus`) and B (STATE_REQUEST handshake) are complete.

**Origin:** Plan at `~/.claude/plans/propose-a-rewrite-of-melodic-dream.md`. Phase A landed in commit `b8a397fc`, Phase B in `76ca86f9`.

## Goal

Strip two classes of rungs from each state handler:

1. Inline completion-tolerance comparisons — `CMP "ABS(actual − target) < 0.1"`. Python now owns move-completion judgement (`_isPrimitiveComplete` in `src/dune_winder/io/controllers/plc_logic.py`).
2. `ERROR_CODE` string composition — rungs of the form `CPT ERROR_CODE 5001`. Python now derives the legacy `ERROR_CODES` string from `(LAST_STATE, STATE_FAULT_FLAGS)` via `_FAULT_TO_LEGACY_CODE` in `plc_logic.py`.

**Preserve every safety interlock.** Tolerance and string composition are the only things going away.

## Non-negotiable: what stays

For each state handler, keep:

- **Entry interlocks**, evaluated when the state is entered:
  - Z-extended/retracted gating for XY moves
  - `MASTER_Z_GO` for Z moves
  - `X_XFER_OK` / `Y_XFER_OK` for transfer moves
  - Axis-fault check
  - Tension-stable gating
  - Latch-position preconditions for Z motion
- **During-motion interlocks** — same checks re-evaluated each scan.
- STO/SLS in `Safety/` (untouched).
- `state_6_latch` pulse sequencing (untouched).
- `tension_pid` loop (untouched).
- `queued_motion` FIFO (untouched).
- `state_11_eot_trip` latch (untouched).
- Servo enable/disable primitives (MSF/MSO/MAFR) and fault reset (untouched).

The PLC remains authoritative on "is this motion safe to start / continue?". Python cannot bypass it.

## Per-state recipe

For each state file `dune_winder/plc/state_<N>_*/main/pasteable.rll`:

### On entry

For each interlock that must hold for this state:
```
XIC STATE<N>_IND XIO <interlock_ok>
  CPT STATE_FAULT_FLAGS (STATE_FAULT_FLAGS OR <bit>)
  MOV 2 STATE_REQUEST_RESULT
  MOV 10 NEXTSTATE
```

`<bit>` from `STATE_FAULT_FLAGS` bitfield (defined in `plc_logic.py`):
- `0x01` interlock
- `0x02` axis fault
- `0x04` EOT
- `0x08` safety
- `0x10` tension
- `0x20` latch timeout
- `0x40` request out of range (Phase B only)

### During motion

Same interlocks, re-evaluated each scan. On drop:
```
XIC STATE<N>_IND XIO <interlock_ok>
  CPT STATE_FAULT_FLAGS (STATE_FAULT_FLAGS OR <bit>)
  MOV 4 STATE_REQUEST_RESULT
  MOV 10 NEXTSTATE
```

### On natural completion

When the underlying motion primitive reports done (`MoveStatus.PC` / `.DN` from the Logix motion instruction):
```
XIC STATE<N>_IND XIC <axis>.MoveStatus.PC
  MOV 3 STATE_REQUEST_RESULT
  MOV 1 NEXTSTATE
```

### What to delete

- Every `CMP "ABS(<axis>.ActualPosition − <target>) < 0.1"` rung used to drive `NEXTSTATE = 1`. Python's `_isPrimitiveComplete` covers this against `STATE_REQUEST_RESULT == 3`.
- Every `CPT ERROR_CODE <constant>` rung. The mapping is in `plc_logic.py::_FAULT_TO_LEGACY_CODE`.

## Rollout sequence (one PR per state)

The plan calls for incremental rollout — one state per PR — so a regression is bisectable:

1. `state_5_move_z`
2. `state_3_move_xy`
3. `state_12_move_xz`, `state_13_move_yz`
4. `state_9_unservo`, `state_14_hmi_stop`
5. `state_10_error` (keeps MSF/stop behaviour; drops translation rungs only; gate exit on `STATE_REQUEST → 0` as today)

States deliberately **not** touched in Phase C: `state_1_ready` (Phase B), `state_6_latch`, `state_11_eot_trip`, `init/`, `Safety/`, `tension_pid/`, `queued_motion/`, `Camera/`, `transfer/`.

## Per-state PR checklist

1. Edit `dune_winder/plc/state_<N>_*/main/pasteable.rll` per the recipe above. **Do not edit `studio_copy.rllscrap` directly** — see `dune_winder/plc/RLL_FORMAT.md`.
2. Mirror the strip in `src/dune_winder/io/devices/simulated_plc.py`. Phase B already wired the `RESULT` and `FAULT_FLAGS` codes through the simulator; verify each state still produces the same outcome with the trimmed rungs.
3. Add a focused safety regression test under `tests/dune_winder/`. For each interlock the state enforces, deliberately violate the precondition and assert:
   - `getStateRequestResult() == 2` (rejected at entry) or `4` (faulted mid-motion)
   - `getStateFaultFlags() & <bit>` is set
   - `getErrorCodeString()` matches the legacy operator-facing string
4. Run the existing simulated-ladder coverage:
   - `tests/dune_winder/test_head_g106_transfer.py::G206TransferLadderTests`
   - `tests/dune_winder/test_plc_logic_handshake.py`
   - any `test_*_paths.py` that exercises the state being thinned
   All must remain green.
5. Human ladder round-trip (per `RLL_FORMAT.md`):
   - Paste `pasteable.rll` into Studio at the right routine
   - Copy the routine back from Studio
   - Save as `studio_copy.rllscrap`
   - Run `uv run plc-sync --offline` to regenerate `manifest.json`
6. Hardware smoke test (operator-supervised):
   - Manual exercise of the state via the normal HMI flow
   - For each interlock: deliberately violate it, confirm rejection and that `getErrorCodeString()` produces the legacy string the operator expects
   - Confirm `getStateEntryCounter()` increments on every transition into and out of the state

## Relevant Python references (already implemented in Phase B)

In `src/dune_winder/io/controllers/plc_logic.py`:

- `_RESULT_IDLE / _ACCEPTED / _REJECTED / _COMPLETED / _FAULTED` constants (0–4)
- `FAULT_INTERLOCK / _AXIS / _EOT / _SAFETY / _TENSION / _LATCH_TIMEOUT / _REQUEST_OUT_OF_RANGE` bit constants (0x01 … 0x40)
- `_FAULT_TO_LEGACY_CODE` — maps `(LAST_STATE, FAULT_FLAGS_bit) → legacy ERROR_CODE int`
- `getStateRequestResult / getStateFaultFlags / getStateEntryCounter / getLastState` — diagnostics
- `_isPrimitiveComplete` — Python-side completion judgement against `STATE_REQUEST_RESULT == 3`

In `src/dune_winder/io/devices/simulated_plc.py`:

- `_setStateAndTrack` — maintains `LAST_STATE` and `STATE_ENTRY_COUNTER` on state-change edge
- `_setError` — sets `RESULT = 4` and OR's in `FAULT_AXIS`
- `_completePendingMove` — sets `RESULT = 3` and transitions to READY
- `_setStateRequest` — handshake validation for valid / out-of-range / ERROR-state interlock

## Other deferred items (not Phase C, but worth knowing)

- **Phase B ladder follow-up:** add explicit out-of-range guard rung to `state_1_ready/main/pasteable.rll` (`RESULT = 2`, `FLAGS |= 0x40`). Python and the simulator already reject; the ladder rung is belt-and-braces.
- **`tools/plc-sync --tags`:** diff-checker between `tags.toml` and `controller_level_tags.json`. Plan calls for it; not yet implemented.
- **Rust `SimulatedDriver`:** port full `simulated_plc.py` ladder semantics into Rust so `G206TransferLadderTests` runs against the native driver. Currently the bridge driver wraps the Python simulator.
- **Native EIP/CIP driver:** replace `PycommBridge` with a Rust-native driver (`enip`/`cip` crate or hand-written). Blocks deletion of `plc.py`, `controllogix_plc.py`, `simulated_plc.py`, `shadow_plc.py`.
- **PyTagBus teardown:** cosmetic panic at interpreter finalization (`rust/crates/dune_plc_bus/src/lifecycle.rs:247`). Add `__del__`/`atexit` to call `bus.stop()` cleanly.
- **Latency budget instrumentation:** plan's verification step #7 (60s loop, 95p staleness < 30 ms, ≥ 3× baseline throughput) hasn't been measured.

## Verification acceptance (from the plan)

- All targeted handshake tests pass against the simulator.
- `G206TransferLadderTests` passes — full Python ↔ PLC contract through `Head`.
- Specific safety regression for each interlock: e.g. request `Z_SEEK` with `MASTER_Z_GO` low → `RESULT == 2`, `FLAGS & 0x01`. Request `XY_SEEK` with Z extended → rejection. Request `XZ_SEEK` with `Y_XFER_OK` low → rejection. **Must pass on simulated ladder and on hardware.**
- Round-trip latency: Python `setZ_Position` → `STATE_REQUEST_RESULT == 3` within one `CRITICAL` tier period (~30 ms) plus one PLC scan, on the simulated ladder.
