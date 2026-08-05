# STATE / NEXTSTATE / STATE_REQUEST handshake (Python-only, on the current `.rung`/ACD toolchain)

## Context

Two problems share the `STATE` / `NEXTSTATE` / `STATE_REQUEST` dispatch path:

**1. The dispatch has no handshake.** `_requestState` (`plc_logic.py`) writes `STATE_REQUEST` and returns; `isReady` infers readiness from cache; transient `ERROR` bounces are invisible; a rejected request is silent. There is no way for Python to tell "the PLC saw my request and accepted it" from "the PLC saw my request and refused it on a safety interlock" from "nothing happened yet."

**2. Some sequencing logic in the ladder is dispensable** — the completion-tolerance comparisons (`|actual − target| < 0.1 mm`) and the error-code *string* composition. **The safety-load-bearing parts are not.** Movement interlocks (Z-extended gating, `MASTER_Z_GO`, `X_XFER_OK`/`Y_XFER_OK`, axis-fault catching, tension-stable gating, EOT, STO/SLS) must remain on the PLC and must not become bypassable from Python.

This plan adds an explicit request/acknowledge handshake and thins the ladder only along the non-safety dimensions. It is **Python-only** and rides the **existing `PLC.Tag` layer** and the **current `.rung`/ACD PLC toolchain**. There is no Rust crate, no new tag bus, no PyO3, and no `tags.toml`/`plc-sync`/`manifest.json`/`.rllscrap` (that toolchain is retired).

### Why no tag-layer rewrite

The handshake does not need one. `PLC_Logic` already carries the primitives it requires:

- Polled `PLC.Tag` objects updated by `PLC.Tag.pollAll(plc)` on the app loop (cached `.get()`).
- Immediate, non-cached access helpers already in `plc_logic.py`: `_writeTagNow(name, value)`, `_readTagNow(tag)`, `_readTagsNow(tags)` — a single-round-trip read/write that bypasses the poll cache. These are exactly what an accept-wait loop needs.

The `PLC.Tag` shape is imperfect (class-level registry, empirical 14-tag batch limit, no freshness metadata), but reworking it is orthogonal to the handshake and is explicitly **out of scope** here. If it is worth doing, it is a separate effort; the handshake below does not depend on it.

### Current state of play (what is already on disk)

- The six DINT tags already exist in `winder/plc/controller_level_tags.json` (all zeroed): `STATE_REQUEST_ID`, `STATE_REQUEST_ACK`, `STATE_REQUEST_RESULT`, `STATE_FAULT_FLAGS`, `STATE_ENTRY_COUNTER`, `LAST_STATE`. **No tag creation is needed.**
- `winder/plc/state_1_ready/main/main.rung` already carries an **inert** handshake stub: a `raw` rung that, on `STATE1_IND` and `STATE_REQUEST_ID ≠ STATE_REQUEST_ACK`, copies ID→ACK and clears `STATE_REQUEST_RESULT`/`STATE_FAULT_FLAGS`. Because nothing ever advances `STATE_REQUEST_ID`, the `NEQ` never fires; the real dispatch runs off `STATE_REQUEST != 0` (sets `RESULT = 1`, `NEXTSTATE = STATE_REQUEST`). The **rejection** branch does not exist.
- `winder/plc/main/main/main.rung` is unchanged: fourteen per-value copies `STATE = N when INIT_DONE and NEXTSTATE == N`; `LAST_STATE` and `STATE_ENTRY_COUNTER` are never written by any rung.
- `plc_logic.py` has **none** of the handshake Python: `_requestState` writes only `STATE_REQUEST`; `isReady` is legacy (`STATE == READY and STATE_REQUEST == 0`); `getErrorCode` reads the `ERROR_CODE` tag.

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
- Error-code *string composition*. The PLC publishes raw fault-flag bits; Python expands to the legacy `ERROR_CODES` strings.
- Multi-state *choreography* (transfer flows, retry policy, recovery sequencing). The PLC's per-state safety interlocks remain authoritative — Python issues a request, the PLC accepts or rejects based on safety, Python responds to the outcome.
- All retry / timeout / backoff policy.

The line is sharp: the PLC says no when it isn't safe; the PLC says done when its primitive trajectory finishes; Python decides what to do next.

## Handshake tags (already registered — reused, not created)

| Tag | Type | Owner | Purpose |
|---|---|---|---|
| `STATE_REQUEST_ID` | DINT | Python writes | Monotonic counter; incremented on every `_requestState`. |
| `STATE_REQUEST_ACK` | DINT | PLC writes | Echoes the most recently consumed `STATE_REQUEST_ID`. |
| `STATE_REQUEST_RESULT` | DINT | PLC writes | `0`=idle, `1`=accepted, `2`=rejected, `3`=completed, `4`=faulted. |
| `STATE_FAULT_FLAGS` | DINT (bitfield) | PLC writes | `0x01` interlock, `0x02` axis-fault, `0x04` EOT, `0x08` safety, `0x10` tension, `0x20` latch-timeout, `0x40` request-out-of-range. |
| `STATE_ENTRY_COUNTER` | DINT | PLC writes | Incremented once per scan in which `STATE` actually changes. |
| `LAST_STATE` | DINT | PLC writes | Previous `STATE`, latched on transition. |

All six are controller-scope DINTs and already present in the ACD / `controller_level_tags.json`, so `rung-compile` synthesizes no new tags for this work.

## How ladder edits land (the current `.rung`/ACD loop)

Every ladder change below is made by editing the routine's `.rung` source and running it through the checked-in pipeline — never by hand-editing L5X or the tag JSONs:

1. **Edit** `winder/plc/<program>/<routine>/<routine>.rung`.
2. `uv run rung-compile <file.rung>` — parse + check + lower. It prints an **equivalence report** against the routine's current exported L5X (`+`/`−` rungs and a semantic verdict), lists any new *program-scope* tags the import will create, and writes `<routine>_import.L5X` (donor context + synthesized tags + new rungs). `--check-only` validates without writing.
3. **Studio 5000** → right-click the routine → *Import Routine…* → review the Import Configuration dialog → **save the ACD**.
4. `uv run plc-acd-export` regenerates all of `winder/plc` (L5X, `.rung`, tag JSONs + live values) from the ACD. A **clean `git diff` on the `.rung`** confirms the edit landed byte-for-byte.

Notes that constrain the edits:
- The routine's exported L5X (`<routine>_Routine_RLL.L5X`) is the single source of truth for rung text; `.rung` is rendered from it (`rung-render`).
- Tag JSONs (`controller_level_tags.json`, `programTags.json`) are export artifacts — **never hand-edited**.
- Controller-scope tags must already exist in the ACD (the six handshake tags do); only new *program-scope* tags are synthesized into the import L5X.
- Bit manipulation (e.g. `STATE_FAULT_FLAGS |= 0x40`) is expressed as a `raw` rung (as the existing handshake stub already does), since it is below the formula DSL's boolean/arithmetic surface. The exact `raw` text is finalized against the renderer during implementation; the equivalence report and simulator oracle validate it.

## Ladder changes

### `winder/plc/main/main/main.rung` — edge-driven transition + `LAST_STATE` + counter

Replace the fourteen per-value copies (`STATE = N when INIT_DONE and NEXTSTATE == N`) with one edge-driven transition block:

```
when INIT_DONE and NEXTSTATE != 0 and STATE != NEXTSTATE:
    LAST_STATE = STATE
    STATE_ENTRY_COUNTER = STATE_ENTRY_COUNTER + 1
    STATE = NEXTSTATE
```

The `NEXTSTATE != 0` guard preserves the original semantics (the old rungs cover `N ∈ 1..14` only; `NEXTSTATE == 0` never drove `STATE`). The `STATE != NEXTSTATE` gate makes it fire exactly on the transition scan, so `LAST_STATE` latches the prior state and the counter increments once per real transition. The equivalence report will show the fourteen removed rungs and this added rung — expected, and the simulator oracle confirms the `STATE` value is unchanged.

### `winder/plc/state_1_ready/main/main.rung` — complete the handshake

Three behaviours (the first already exists as the inert stub; the third is new):

- **Consume a newly-issued request.** On `STATE1_IND` and `STATE_REQUEST_ID != STATE_REQUEST_ACK`: `STATE_REQUEST_ACK = STATE_REQUEST_ID`, `STATE_REQUEST_RESULT = 0`, `STATE_FAULT_FLAGS = 0`. (Keeps the current `raw` rung.)
- **Accept** an in-range request:

  ```
  when STATE1_IND and STATE_REQUEST != 0 and <STATE_REQUEST in valid set>:
      STATE_REQUEST_RESULT = 1
      NEXTSTATE = STATE_REQUEST
  ```

- **Reject** an out-of-range request (new): set `STATE_REQUEST_RESULT = 2`, set the request-out-of-range bit (`STATE_FAULT_FLAGS |= 0x40`, `raw` rung), and clear `STATE_REQUEST` **without** touching `NEXTSTATE`.

The "valid set" is the single source of truth for accepted direct requests (`{XY_SEEK, Z_SEEK, LATCHING, UNSERVO, EOT, XZ_SEEK, YZ_SEEK, HMI_STOP}`); it mirrors Python's `_DIRECT_STATE_REQUESTS`. In ladder it is a range/membership check.

Leave the `STATE1_IND`, `MOVE_TYPE`-based mappings, and `STATE1_IND` indicator rung as-is.

### `state_3_move_xy`, `state_5_move_z`, `state_12_move_xz`, `state_13_move_yz`, `state_9_unservo`, `state_14_hmi_stop` — Phase B

**Safety interlocks preserved, sequencing thinned.** Each handler:

- **Keeps every entry interlock** (Z-extended/retracted gating, `MASTER_Z_GO`, `X_XFER_OK`/`Y_XFER_OK`, axis fault, tension stable, latch position). On any entry interlock failing: set the matching `STATE_FAULT_FLAGS` bit, `STATE_REQUEST_RESULT = 2` (rejected), `NEXTSTATE = 10`.
- **Keeps every during-motion interlock**, re-evaluated each scan; on drop: set the matching flag, `STATE_REQUEST_RESULT = 4` (faulted), `NEXTSTATE = 10`.
- **Drops** the inline `CMP "ABS(actual − target) < 0.1"` completion rungs — Python evaluates done.
- **Drops** the `CPT ERROR_CODE …`-style rungs — Python composes the code from `(LAST_STATE, STATE_FAULT_FLAGS)`.
- On natural completion (`MoveStatus.PC` / `.DN`): `STATE_REQUEST_RESULT = 3`, `NEXTSTATE = 1`.

### `state_10_error` — Phase B

Keeps its safety-adjacent stop/MSF behaviour; drops the error-code translation rungs; gates exit on `STATE_REQUEST → 0` as today.

### Untouched

`state_6_latch`, `state_11_eot_trip`, `Safety/`, `tension_pid/`, `queued_motion/`, `init/`.

The safety story is unchanged: every PLC-side gate that prevents unsafe motion is still there. What goes away is decorative — tolerance comparisons whose miscalibration would not endanger anything, and string composition that has no bearing on whether the move is permitted.

## Python changes (`plc_logic.py`)

Built entirely on the existing tag layer. **`__init__` signature is unchanged** (`(plc, xyAxis, zAxis)` — the PLC object stays). There is no `write_many`, no `read_fresh`, no subscription API; the mechanism is `_writeTagNow` / `_readTagNow` / `_readTagsNow` plus polled `PLC.Tag`s.

1. **`__init__`** — add `self._lastIssuedRequestId = 0`. Add polled read-only `PLC.Tag`s for `STATE_REQUEST_RESULT`, `STATE_REQUEST_ACK`, `STATE_FAULT_FLAGS`, `STATE_ENTRY_COUNTER`, `LAST_STATE`, and a write tag for `STATE_REQUEST_ID`. They join the existing `pollAll` set (the `MAX_TAG_READS = 14` batching already handles overflow).
2. **`_requestState(state)`** — keep the `_DIRECT_STATE_REQUESTS` validation. `self._lastIssuedRequestId += 1`, then write **ID first, `STATE_REQUEST` second** via `_writeTagNow` (updating each tag's cache with `updateFromReadTag`). The layer writes one tag per round-trip — there is no atomic multi-write — so ID-before-STATE guarantees the PLC never sees a new `STATE_REQUEST` paired with a stale ID; the ladder consume rung keys on `ID ≠ ACK`, so the one-scan skew is harmless.
3. **`_awaitRequestAccepted(timeout_ms=250)`** — bounded loop calling `_readTagNow(self._stateRequestAck)` (immediate read, not the poll cache) until it equals `self._lastIssuedRequestId` or the timeout elapses; return the match as a bool.
4. **`isReady`** — preserve the signature. Ready iff the last `STATE_REQUEST_RESULT ∈ {0, 3}` once `STATE_REQUEST_ACK` matches `_lastIssuedRequestId`. Retain the legacy fallback (`STATE == READY and STATE_REQUEST == 0`) for when the handshake tags read zero (transitional firmware / ladder edits not yet imported).
5. **`getErrorCode` / `getErrorCodeString`** — compose the legacy code from `(LAST_STATE, STATE_FAULT_FLAGS)` via a small mapping; fall back to reading the `ERROR_CODE` tag while the ladder still publishes it (during Phase B rollout). Keep the existing `ERROR_CODES` dict as the canonical string source.
6. **`_isPrimitiveComplete(target_axes, target_position, tolerance=0.1)`** — `_readTagsNow` the axis positions and compare. Public `setXY_Position`, `setZ_Position`, `setXZ_Position`, `setYZ_Position` keep their signatures.
7. **New diagnostics** — `getStateRequestResult()`, `getStateFaultFlags()`, `getStateEntryCounter()`, `getLastState()` for `Head._updateG206` and `ControlStateMachine` to detect transient `ERROR` bounces.

The `PLC_Logic` public freeze list (`setXY_Position`, `setZ_Position`, `move_latch`, `isReady`, `getState`, `getErrorCode`, `getTransferStateNow`, `setupLimits`, `States`, `MoveTypes`, `LatchPosition`, `ERROR_CODES`) is preserved.

## Sequencing

Two phases, each independently revertable:

1. **Phase A — handshake dispatch.**
   - Ladder (via rung-compile → import → export): the `main/main` edge-driven transition + `LAST_STATE`/counter rung, and the `state_1_ready` accept/reject rungs.
   - Python: `_lastIssuedRequestId`, `_requestState` writing ID+STATE, `_awaitRequestAccepted`, the `isReady` RESULT path (with legacy fallback), and the diagnostics getters.
   - Per-state handlers untouched. Legacy fallbacks keep the old firmware / not-yet-imported ladder working, so Python and ladder can land in either order.
2. **Phase B — thin per-state handlers.** One state at a time — `state_5_move_z`, then `state_3_move_xy`, then `state_12_move_xz` / `state_13_move_yz`, then `state_9_unservo` / `state_14_hmi_stop`, then `state_10_error`. Each: keep every interlock, publish `STATE_FAULT_FLAGS` + `STATE_REQUEST_RESULT`, drop the tolerance and `ERROR_CODE`-string rungs. Once all states publish flags, flip `getErrorCode` off the `ERROR_CODE`-tag fallback. Each state is a separate rung-compile → import → export → PR with equivalence-report review and simulator coverage.

## Files in scope

**PLC ladder (`.rung` sources, edited; L5X/tag-JSON/renders regenerated by `plc-acd-export`):**
- `winder/plc/main/main/main.rung` — transition counter + `LAST_STATE` (Phase A).
- `winder/plc/state_1_ready/main/main.rung` — accept/reject handshake (Phase A).
- `winder/plc/state_3_move_xy/`, `state_5_move_z/`, `state_12_move_xz/`, `state_13_move_yz/`, `state_9_unservo/`, `state_14_hmi_stop/`, `state_10_error/` `.rung` files — Phase B: drop tolerance + error-code-string rungs, publish flags; keep every interlock.

**Python:**
- `src/dune_winder/io/controllers/plc_logic.py` — handshake additions (both phases).

**Regenerated, never hand-edited:**
- `winder/plc/controller_level_tags.json`, `winder/plc/**/*_Routine_RLL.L5X`, program tag JSONs, and the `.rung` renders — all produced by `uv run plc-acd-export`.

**Explicitly out of scope (removed from the earlier Rust-based draft):** the `dune_plc_bus` Rust crate, PyO3 bindings, `tags.toml`, `tools/plc-sync`, and the retired `manifest.json` / `pasteable.rll` / `*.rllscrap` artifacts. Any `PLC.Tag` refactor is a separate effort.

## Verification

1. **Compile-time equivalence.** For each edited routine, `uv run rung-compile <file.rung>` — reviewer confirms the `+`/`−` rung set matches intent (the `STATE` copy is semantically unchanged in `main/main`; the handshake rungs are additive in `state_1_ready`; Phase B removals are only tolerance/error-code rungs, never interlocks).
2. **Simulator oracle / equivalence tests.** `tests/dune_winder/test_rung_simulator_equiv.py` — the edited routines still agree with the simulator oracle; `tests/dune_winder/test_ladder_simulated_plc.py` stays green.
3. **Python handshake tests** (`tests/dune_winder/test_plc_logic.py`, against the simulated / ladder-simulated PLC): `STATE_REQUEST_ID` advances once per `_requestState`; `STATE_REQUEST_ACK` echoes it; `_awaitRequestAccepted` returns `True` on accept and `False` on timeout; each `STATE_REQUEST_RESULT` outcome (1/2/3/4); the fault-flag → error-code mapping for states 3/5/6/12/13.
4. **Interlock regression** (simulated ladder, and repeated on hardware): request `Z_SEEK` with `MASTER_Z_GO` low → `RESULT == 2` and `STATE_FAULT_FLAGS & 0x01`; request `XY_SEEK` with Z extended → rejected; request `XZ_SEEK` with `Y_XFER_OK` low → rejected.
5. **Full contract through `Head`.** `tests/dune_winder/test_head_g106_transfer.py::G206TransferLadderTests` against the ladder-simulated PLC — stage→fixed and fixed→stage transfers complete with no regression in timing or final-state validation. `tests/dune_winder/test_z_move_paths.py` stays green.
6. **Hardware smoke test (operator-supervised).**
   - Manual XY/Z/XZ/YZ sequence from `specs/operator-workflows.allium`.
   - `getStateEntryCounter()` increments on every transition.
   - **Interlock regression:** each interlock above is exercised by deliberately violating its precondition; assert the PLC rejects the request and that `getErrorCodeString()` produces the same legacy string the operator is used to.
   - `reset()` clears flags and returns to READY.
7. **Latency sanity.** Round-trip from `_requestState` → `STATE_REQUEST_RESULT == 3` completes within a few poll cycles on the simulated ladder. Latch pulse, tension PID, and queued-motion paths show no change — their ladder code is untouched.
