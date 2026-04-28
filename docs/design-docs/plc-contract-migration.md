# PLC Tag Freshness and State Request Contract Migration

## Overview

This document describes the current PLC contract, the problems it creates, and the target protocol for migration.

## Current Contract

### PLC.Tag Semantics (Value-Only Cache)

The current `PLC.Tag` class provides a simple value cache without freshness metadata:

- **Storage**: Single `_value` field holding the last read value
- **Read API**: `get()` returns cached value directly
- **Write API**: `set(value)` writes to PLC and updates cached value
- **Polling**: `poll()` and `pollAll()` update cached values from PLC reads
- **Default fallback**: If PLC is not functional, `get()` returns `_attributes.defaultValue`
- **No metadata**: No timestamp, quality flag, freshness indicator, or error information attached to cached values

**Limitation**: Callers cannot distinguish between:
- A fresh value that was just read
- A stale value from minutes ago
- A default value because the PLC is offline
- A cached value from before a read error

### STATE_REQUEST and MOVE_TYPE Dispatch

The `PLC_Logic` class uses two shared tags for state transitions:

- **STATE_REQUEST**: Shared command tag written by host to request a state transition
- **MOVE_TYPE**: Shared command tag written by host to specify motion type for multi-axis moves

**Limitations**:
- STATE_REQUEST is used as a command, acknowledgement flag, reset flag, and stop signal
- No request-id to correlate which state request was accepted/rejected
- No explicit status for request acceptance, active state, completion, or failure
- PLC ladder logic has implicit assumptions about when requests are ready to accept
- No explicit failure codes beyond ERROR_CODE

**Current dispatch flow**:
1. Host writes STATE_REQUEST = target_state
2. Host writes MOVE_TYPE = movement_type
3. PLC ladder logic reads STATE_REQUEST in READY state and transitions to it
4. PLC stays in target state until host clears STATE_REQUEST
5. Host reads ERROR_CODE to detect failures

### Queued Motion Request-ID Protocol (Reference Model)

The queued motion interface demonstrates a more explicit protocol:

**Tags**:
- `IncomingSegReqID`: Request ID being sent by host
- `LastIncomingSegReqID`: Last request ID acknowledged by PLC
- `IncomingSegAck`: Increment-based acknowledgement counter

**Flow**:
1. Host writes increment `IncomingSegReqID` with new segment data
2. Host polls `LastIncomingSegReqID` waiting for acknowledgement
3. PLC ladder logic reads new request ID, validates segment, increments acknowledgement
4. Host polls `LastIncomingSegReqID == IncomingSegReqID` to confirm acceptance
5. Motion completes and PLC returns to idle
6. PLC can emit fault codes distinct from the global ERROR_CODE

**Benefits**:
- Request ID allows host to confirm which request was accepted
- Explicit acknowledgement eliminates implicit readiness assumptions
- Separate status and fault codes for diagnostics
- Can distinguish between rejection (ack not updated), timeout, and motion errors

## Target Protocol

### Goal

Make host-side reads explicit about freshness and failure behavior. Introduce a request-id/state-status protocol similar to queued motion that improves reliability and diagnostics.

### PLC.Tag Enhancements (Task 3)

The new contract will add optional metadata without breaking existing `get()` callers:

- **Sample metadata**: value, read timestamp, scan id, quality status, last error
- **Backward compatibility**: `get()` continues to return cached value as before
- **New APIs**:
  - `sample()` → returns sample with metadata
  - `read_fresh()` → update metadata and require fresh data or raise
  - `read_with_policy(allow_stale=False, allow_error=False)` → explicit freshness policy
  - `write_result()` → returns success/error instead of boolean

### State Request Protocol (Tasks 4-5)

Replace STATE_REQUEST with an explicit request-id/status protocol:

**New controller-scope tags** (task 5):
- `STATE_REQ_ID`: Request ID from host (host increments/changes when requesting state transition)
- `STATE_REQ_TARGET`: Target state requested
- `STATE_REQ_ACK_ID`: Last request ID acknowledged by PLC
- `STATE_REQ_STATUS`: Current status (IDLE, ACCEPTED, ACTIVE, DONE, FAILED, CANCELLED)
- `STATE_REQ_RESULT`: Detailed result code (target rejected, timeout, motion error, etc.)
- `STATE_ACTIVE_ID`: Request ID of currently active state
- `STATE_ACTIVE_TARGET`: Target state of currently active state

**Protocol flow** (task 4 design, task 5 ladder):
1. Host checks current state and preconditions (fresh reads required for safety)
2. Host writes `STATE_REQ_ID`, `STATE_REQ_TARGET` to request state transition
3. Host polls `STATE_REQ_STATUS` waiting for `ACCEPTED` or `FAILED`
4. READY state routine validates target and increments `STATE_REQ_ACK_ID`
5. State machine transitions to target state
6. Target state routine sets `STATE_REQ_STATUS = ACTIVE` and latches active IDs
7. Target state routine completes physical action
8. Target state routine sets `STATE_REQ_STATUS = DONE` with result code
9. Host polls for DONE or FAILED and retrieves result code
10. Host can cancel by writing different `STATE_REQ_ID` at any time

**Backward compatibility** (task 5):
- READY state continues to check legacy STATE_REQUEST during migration window
- Simulator and tests explicitly mark legacy fallback as compatibility behavior
- Migration window ends when all callers use new protocol (task 8)

### Freshness Policies for Callers (Task 8)

After new APIs are available, require explicit policies for reads:

- **Interlock and safety reads**: Require fresh samples, fail closed on communication error
- **Status/UI getters**: Allow cached or stale samples, expose quality when useful
- **Collision detection reads**: Coherent snapshots across related tags
- **PLC state validation**: Distinguish stale data from true READY state

## Migration Stages

1. **Task 1**: Document and test current contract (this document + baseline tests)
2. **Task 2**: Fix immediate correctness gaps in current contract (bug fix)
3. **Task 3**: Add freshness-aware PLC.Tag samples (backward compatible)
4. **Task 4**: Host-side state command client with fallback to legacy
5. **Task 5**: PLC ladder-side protocol tags and READY dispatcher proposal
6. **Task 6**: Motion state routines publish terminal statuses
7. **Task 7**: State command watchdogs and failure taxonomy
8. **Task 8**: Migrate all callers to explicit freshness policies
9. **Task 9**: Finalize migration, sync artifacts, clean up legacy code

## Testing Strategy

### Current Contract Tests (Task 1)

Characterize existing behavior before changes:
- PLC.Tag.get() returns cached values without freshness metadata
- PLC_Logic._readTagNow falls back to cached data on read failure
- READY dispatch consumes STATE_REQUEST
- Queued motion request-id acknowledgement behavior
- ERROR_CODE reporting for motion errors

### Protocol Tests (Tasks 4-7)

- State command client: success, legacy fallback, timeouts, precondition failures
- READY dispatcher: acceptance, rejection, acknowledgement protocol
- Terminal state publishers: DONE and FAILED emission
- Failure taxonomy: all result codes exercised and mapped to exceptions

### Integration Tests (Task 8)

- All callers use explicit freshness policies
- No silent fallbacks to cached data for safety decisions
- Type checking passes

## References

- Queued motion interface: `src/dune_winder/queued_motion/plc_interface.py`
- PLC.Tag: `src/dune_winder/io/devices/plc.py`
- PLC_Logic: `src/dune_winder/io/controllers/plc_logic.py`
- PLC proposal workflow: `.harness/plans/improve-plc-contract-migration.json` tasks 5-6
