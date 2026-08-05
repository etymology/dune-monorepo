# Surface head-transfer lockout conflicts as an operator popup

## Context

`~anchorToTarget` and bare `G206` currently **degrade silently to an XY-only move** when the
head cannot transfer. The operator sees a wind that appears to run normally while the head
never changes side — wire gets laid with the head on the wrong plane.

The cause is a conflation in `Head._getCurrentStrictTransferSide()`
(`src/dune_winder/io/controllers/head.py:146-156`). It returns `HEAD_ABSENT` (-1) for two
completely different situations:

1. **No head mounted** — `not stagePresent and not fixedPresent`. Skipping the transfer here
   is correct and must stay silent (dry-run / no-head operation).
2. **Head mounted, latch in a conflicting position** — the catch-all `return self.HEAD_ABSENT`
   at line 156. Reached when e.g. the head is fixed-latched with `ACTUATOR_POS == 3`
   (`rocker_at_fixed`), both latches engaged, or neither latch engaged. This is a real fault
   during a real wind.

`GCodeHandler._isHeadPresent()` (`src/dune_winder/gcode/handler.py:120-121`) collapses both to
"no head", and every transfer site is wrapped in `if head_present:` —
`handler_base.py:696, 723, 729, 760, 766` (`~anchorToTarget`) and `handler_base.py:1370`
(`G206`). Case 2 therefore produces no `GCodeExecutionError`, no `_set_gcode_error`, not even a
log line. Because the interpreter never queues the transfer, `Head.setTransferPosition` is never
called and the PLC interlock never gets a chance to fault either.

Case 2 is exactly the `no_latch_collision` term of the PLC's `MASTER_Z_GO` going false
(`winder/plc/state_5_move_z/main/main.rung:13-19`), which on a real Z move would raise
`ERROR_CODE 5001` — *"Z Seek, Master Z Transfer Enable Not Ready"*.

**Intended outcome:** case 1 stays silent; case 2 raises a descriptive error that stops the run
and shows the operator a modal popup naming which `MASTER_Z_GO` term is blocking and why.

This is squarely what `specs/winder-states.allium:1724-1728` (`RuntimeAndPLCBothEnforceSafety`)
already asks for: *"Python preflight checks are user-facing and provide descriptive messages.
PLC interlocks remain authoritative."*

---

## Design

### A. Classify head availability — `src/dune_winder/io/controllers/head.py`

Add a three-way classifier that separates the two `HEAD_ABSENT` cases. Reuses the existing
`_readTransferStateNow()`, `_getCurrentStrictTransferSide()` and `_formatTransferState()`.

```python
class Head:
    # Transfer availability classes.
    TRANSFER_ABSENT  = "absent"   # no head mounted -> silently skip (unchanged behaviour)
    TRANSFER_READY   = "ready"    # sitting on a clean, known side
    TRANSFER_BLOCKED = "blocked"  # mounted, but latch/actuator conflict

    def getTransferAvailability(self):
        """
        Classify whether a head transfer can start.

        Returns (availability, state) where state is the _readTransferStateNow() dict,
        so callers can reuse it instead of re-reading the PLC.
        """
```

- `TRANSFER_ABSENT` when `not state["stagePresent"] and not state["fixedPresent"]`.
- `TRANSFER_READY` when `_getCurrentStrictTransferSide(state) != HEAD_ABSENT`.
- `TRANSFER_BLOCKED` otherwise.

Add a companion that turns a blocked state into prose — the `no_latch_collision` half of the
message. Encode the four distinguishable conflicts:

| State | Explanation |
| --- | --- |
| `fixedLatched and actuatorPos != 2` | fixed-latched but latch actuator at position *N*; needs 2 (`mid_engagement`) before the arm can extend, or the latch fouls the fixed mount |
| `stageLatched and actuatorPos != 1` | stage-latched but latch actuator at position *N*; needs 1 (`stage_latched`) |
| `stageLatched and fixedLatched` | both latches engaged |
| neither latched, a presence sensor asserted | head present but unlatched (floating) |

`ACTUATOR_POS` names come from `specs/winder-states.allium:95-99`.

### B. Mirror all three `MASTER_Z_GO` terms — new `src/dune_winder/core/master_z_go.py`

A pure function mirroring `winder/plc/state_5_move_z/main/main.rung:13-19` symbol-for-symbol,
returning one result per named term so the message can say which are blocking.

```python
@dataclass(frozen=True)
class MasterZGoTerm:
    name: str      # "no_latch_collision" | "no_apa_collision" | "no_supports_collision"
    ok: bool
    detail: str    # why it fails; "" when ok

def evaluate_master_z_go(*, transfer_state, x_transfer_ok, y_transfer_ok,
                        x_position, y_position, limits, collision_state) -> list[MasterZGoTerm]
```

Term definitions, matching the rung exactly:

- `no_latch_collision = (fixedLatched and actuatorPos == 2) or not fixedLatched`
- `no_apa_collision = x_transfer_ok or y_transfer_ok`
- `no_supports_collision = (x_transfer_ok and (head_band or foot_band or no_y_window)) or y_transfer_ok`
  - `support_window_{bttm,mid,top}` = `y_position` inside
    `limits.support_collision_{bottom,middle,top}_{min,max}_y` (inclusive, like ladder `LIM`)
  - `head_band` = `x_position` in `[limits.transfer_zone_head_min_x, ..._max_x]` **and** any
    active Y window whose matching `FRAME_LOC_HD_*` is deasserted
  - `foot_band` = same with `transfer_zone_foot_*` and `FRAME_LOC_FT_*`
  - `no_y_window` = no support window active

**Reuse, do not redefine, the geometry constants.** All bands already exist on
`MotionSafetyLimits` (`src/dune_winder/queued_motion/safety.py:50-59`), built from calibration by
`motion_safety_limits_from_calibration` (same file, `:88-152`); the handler already reaches them
via `GCodeHandler._motion_safety_limits()` (`handler.py:375-376`). Frame-lock inputs already
arrive as `QueuedMotionCollisionState` from `GCodeHandler._queued_motion_collision_state()`
(`handler.py:81-104`). The labelled keepout table in `_queued_motion_forbidden_boxes`
(`safety.py:318-367`) is a useful reference for wording but must **not** be reused directly — it
is gated behind `_z_collision_is_active`, which is a different (current-Z) question.

Also add a small fresh-read accessor next to the existing `getTransferStateNow()` in
`src/dune_winder/io/controllers/plc_logic.py` (tags `_xTransferOk` / `_yTransferOk` already exist
at `:651-668`; use the batched `_readTagsNow`, same pattern as `setXZ_Position` at `:235-237`):

```python
def getTransferWindowStateNow(self):
    return {"xTransferOk": bool(...), "yTransferOk": bool(...)}
```

### C. Raise from the interpreter

Add a no-op hook on the base class so offline/simulation handlers are unaffected
(`src/dune_winder/gcode/handler_base.py`, beside `_isHeadPresent` at `:1133-1138`):

```python
def _requireHeadTransferReady(self, data):
    """
    Hardware subclasses raise GCodeExecutionError when the head is mounted but a
    transfer cannot start.  No-op in the base interpreter.
    """
    return
```

Override in `src/dune_winder/gcode/handler.py`: read `head.getTransferAvailability()`; return on
`TRANSFER_ABSENT` or `TRANSFER_READY`; on `TRANSFER_BLOCKED` build the message from §A + §B and
`raise GCodeExecutionError(message, data)`. Guard the call with `hasattr`, consistent with the
existing defensive style in this file (`_apply_head_controller_error` at `:1152-1176`,
`_queued_motion_collision_state` at `:82-89`) so the test mocks in `test_wrap_runtime.py` and
`test_g_code_handler_safety.py` keep working.

Call it from both silent-skip sites, **before** the existing `_isHeadPresent()` gate:

- `handler_base.py:696` in `_plan_explicit_wrap_transition`, data `[normalized_anchor, normalized_target]`
- `handler_base.py:1370` in `_headTransfer` (G206), data `[str(target)]`

`GCodeExecutionError` is already handled on both paths — `runNextLine` (`handler.py:1469-1478`)
sets `_isG_CodeError` for a wind, and `executeG_CodeLine` (`handler.py:1416-1421`) returns the
`{line, message, data}` dict for a manual line. Nothing new is needed to stop the run:
`isDone |= self._isG_CodeError` at `handler.py:151` already ends it.

To avoid a second PLC round-trip per line, have `_requireHeadTransferReady` stash the state it
read and let `_isHeadPresent()` reuse it for the remainder of the line.

Approved message shape:

```text
Head transfer blocked: MASTER_Z_GO transfer lockout is not ready.

Blocking terms:
  - no_latch_collision: fixed-latched, ACTUATOR_POS=3
    (needs 2 before the arm can extend)
  - no_apa_collision:   X_XFER_OK=0, Y_XFER_OK=0
    (gantry not parked in a transfer window)
  - no_supports_collision: OK

(PLC would raise ERROR_CODE 5001.)
```

Append the existing `Head._formatTransferState(state)` dump as the trailing diagnostic line — it
already renders every relevant sensor and is what the other head errors use.

### D. Latch the error and expose it

A wind-time G-code error is currently logged and then **cleared immediately**
(`src/dune_winder/core/wind_mode.py:149-161`), so nothing can poll it. Latch it first.

On `GCodeHandler` (`src/dune_winder/gcode/handler.py`, beside `clearCodeError` at `:1294-1301`):

```python
def latchG_CodeError(self)        # snapshot {message, data} if _isG_CodeError
def getLatchedG_CodeError(self)   # dict or None
def clearLatchedG_CodeError(self)
```

Initialise `self._latchedG_CodeError = None` alongside the existing error fields at `:1741-1743`.
In `wind_mode.py`, call `latchG_CodeError()` immediately before the existing
`clearCodeError()` at line 159.

Delegate through the existing chain — `GCodePlaybackService` (owns `_gCodeHandler`,
`src/dune_winder/core/gcode_playback_service.py:47`) → `Process` (delegates a dozen methods via
`_playbackService()`, e.g. `src/dune_winder/core/process.py:696-697`). Register two commands in
`src/dune_winder/api/commands.py` beside `process.acknowledge_error` (`:1131-1135`):

- `process.get_gcode_error` → `{message, data}` or `null`
- `process.acknowledge_gcode_error` → clears the latch

Add both to `winder/web/Scripts/CommandCatalog.js` (`acknowledgeError` is at line 27).

### E. Modal popup — `winder/web/Desktop/`

There is no error modal today, but the primitive exists: `Modules/Overlay.{html,js,css}` with
`show()` / `close()`, hosted by `<div id="modalDiv">` (`index.html:97-98`). Follow the existing
two-stage `loadSubPage` pattern from `Modules/RunStatus.js:39-66` (`Overlay` → `#modalDiv`, then
content → `#overlayBox`).

New files, mirroring the `RunStatus` → `PLC_Status` split:

- `Modules/GCodeErrorWatch.{html,js}` — always-loaded watcher. Polls `process.get_gcode_error`
  via `winder.addPeriodicCallback` (already fires only on value change, `Scripts/Winder.js:330-336`).
  Exposes `showError({message, data})` so other modules can push an error straight in.
- `Modules/GCodeErrorDetails.{html,css,js}` — modal body: message (preserve newlines), the
  `data` array (line number + line text), and a Dismiss button that calls
  `process.acknowledge_gcode_error` then `overlay.close()`.

Wiring:

- `index.html` — add a host element, e.g. `<article id="gCodeErrorDiv"></article>`.
- `main.js:202-205` — `page.addCommonPage("/Desktop/Modules/GCodeErrorWatch", "#gCodeErrorDiv")`
  inside the `if (!popupMode)` block, next to `RunStatus` / `Version`.
- `Modules/ManualMove.js:124-130` — in `onGCodeError`, keep the existing `#manualMoveStatus`
  text and additionally call `GCodeErrorWatch.showError(response.error)`. Guard on the module
  being present: common pages are skipped in `popupMode`, so `ManualMovePopup` must fall back to
  the inline status only.

This satisfies the chosen scope — the modal fires for **all** G-code runtime errors (XY/XZ/YZ
bounds, head-controller faults, syntax errors, queued-block errors), not just the new one.

---

## Files to change

### Backend

| File | Change |
| --- | --- |
| `src/dune_winder/io/controllers/head.py` | `getTransferAvailability()` + latch-conflict prose (§A) |
| `src/dune_winder/io/controllers/plc_logic.py` | `getTransferWindowStateNow()` (§B) |
| `src/dune_winder/core/master_z_go.py` | **new** — three-term `MASTER_Z_GO` mirror (§B) |
| `src/dune_winder/gcode/handler_base.py` | no-op `_requireHeadTransferReady`; call at `:696` and `:1370` (§C) |
| `src/dune_winder/gcode/handler.py` | hardware `_requireHeadTransferReady`; error latch accessors (§C, §D) |
| `src/dune_winder/core/wind_mode.py` | latch before `clearCodeError()` at `:159` (§D) |
| `src/dune_winder/core/gcode_playback_service.py`, `core/process.py`, `api/commands.py` | expose get/acknowledge (§D) |

### Frontend

`winder/web/Scripts/CommandCatalog.js`,
`winder/web/Desktop/Modules/GCodeErrorWatch.{html,js}` (new),
`winder/web/Desktop/Modules/GCodeErrorDetails.{html,css,js}` (new),
`winder/web/Desktop/Modules/ManualMove.js`, `winder/web/Desktop/index.html`,
`winder/web/Desktop/main.js`.

**No PLC changes.** The ladder already enforces this correctly; only the Python preflight and the
UI are wrong. Do not touch `winder/plc/`.

---

## Tests

Three existing tests assert the current silent skip and must be re-scoped to the
*genuinely-absent* case (they use a mock `_Head` exposing only `readCurrentPosition()`, which the
`hasattr` guard in §C treats as not-blocked, so they should keep passing as-is — confirm, and
rename for clarity):

- `tests/dune_winder/test_wrap_runtime.py:712` `test_anchor_to_target_skips_head_motion_when_head_absent_same_side`
- `tests/dune_winder/test_wrap_runtime.py:747` `test_anchor_to_target_skips_head_motion_when_head_absent_alternating`
- `tests/dune_winder/test_wrap_runtime.py:898` `test_g206_silently_skips_head_transfer_when_head_absent`

New coverage:

1. **Unit — `master_z_go.py`**: a table over each term. Fixed-latched + `ACTUATOR_POS=3` fails
   only `no_latch_collision`; both transfer windows false fails `no_apa_collision` (and
   `no_supports_collision`); an asserted `FRAME_LOC_HD_MID` with Y in the middle support window
   and X in the head band fails `no_supports_collision`. Cross-check against
   `winder/tools/check_z_move_paths.py:59-67`, which blocks `MASTER_Z_GO` by forcing
   `MACHINE_SW_STAT[15]`/`[17]` low.
2. **Unit — `Head.getTransferAvailability()`**: absent / ready / blocked, extending the
   existing `stage_present`/`fixed_present` fixtures in `tests/dune_winder/test_head.py:26-341`.
3. **Interpreter — `test_wrap_runtime.py`**: mock head returning `TRANSFER_BLOCKED`;
   `~anchorToTarget(...)` returns an error dict whose message contains `MASTER_Z_GO` and
   `no_latch_collision`, and `io.head.transfer_moves == []` **and** `io.plcLogic.xy_moves == []`
   (the run must not proceed with a bare XY move).
4. **Interpreter — bare `G206`**: same assertion via `handler.executeG_CodeLine("G206 P2")`.
5. **Latching — `wind_mode`**: after an errored `poll()`, `getLatchedG_CodeError()` is populated
   and survives the existing `clearCodeError()`; `acknowledge` clears it.
6. **Ladder integration**: extend `tests/dune_winder/test_z_move_paths.py:66-79` style coverage
   so the Python mirror and `LadderSimulatedPLC`'s real `MASTER_Z_GO` agree on the blocked cases
   — this is the check that keeps §B from drifting from the rung.

---

## Spec updates

- `specs/motion-safety.allium:375-412` — note that the Python preflight mirrors the same three
  terms, and fix the stale reference at line 368 to
  `winder/plc/state_5_move_z/main/pasteable.rll` (that file is retired; the rung source is
  `winder/plc/state_5_move_z/main/main.rung`).
- `specs/winder-states.allium` — add a rule beside `HeadTransferRequiresStableStart` (`:997`)
  and `StageTransferRequiresActuatorOne` (`:1009`), in the same
  `OperatorDiagnostic.created(message:, code:)` style, stating that a mounted-but-blocked head
  produces a diagnostic while an unmounted head skips silently.
- `specs/winder-macros.allium:174` `ExecuteAnchorToTarget` — record the head-present precondition
  in the step sequence.

---

## Verification

```bash
uv run pytest tests/dune_winder/test_wrap_runtime.py tests/dune_winder/test_head.py \
              tests/dune_winder/test_z_move_paths.py tests/dune_winder/test_head_g106_transfer.py
uv run pytest tests/dune_winder          # full package
uv run ruff check src tests && uv run ruff format src tests
uv run ty check
npm run markdown:lint -- "specs/**/*.md"  # only if spec prose files change
```

Ladder-vs-Python agreement, without hardware:

```bash
uv run python winder/tools/check_z_move_paths.py   # includes _case_blocked_master_z_go
```

End-to-end in the app:

1. `uv run dune-winder`, open the Desktop UI.
2. Drive `LadderSimulatedPLC` into a blocked state (fixed-latched with `ACTUATOR_POS = 3`, or
   force `MACHINE_SW_STAT[15]`/`[17]` low as `check_z_move_paths.py` does).
3. Manual Move panel → run `G206 P2`. Expect the modal naming `MASTER_Z_GO` and
   `no_latch_collision`, plus the inline status text.
4. Load a recipe and run a wind containing `~anchorToTarget`. Expect the wind to stop, a
   `WIND_ERROR` row in Recent Log, and the same modal. Dismiss → modal closes and does not
   immediately reopen.
5. Regression: with **both** presence sensors clear (no head mounted), the same recipe must run
   XY-only with no modal and no error — the silent-skip path is unchanged.
