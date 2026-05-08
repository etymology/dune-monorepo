# Plan — state_3_move_xy: pre-XY Z servo-on + auto-retract

## Context

Today, `state_3_move_xy/main` requires Z to already be retracted before it
will permit an XY move:

- If `Z_RETRACTED` is off **and** `Z_axis.ActualPosition >= MAX_TOLERABLE_Z`,
  state 3 errors with `ERROR_CODE 3001` and jumps to state 10.
- It also only enables the X and Y servos (`MSO X_axis`, `MSO Y_axis`); the
  Z servo has to have been turned on by some prior state.

The user wants state 3 to take care of Z itself before any XY motion:

1. **Always turn on the Z servo** as part of the state-3 entry sequence
   (alongside the existing X/Y MSO).
2. **Auto-retract Z to 0** when `MASTER_Z_GO` is true and the head is not
   docked at the Z stage (`XIO Z_STAGE_PRESENT`). This replaces the
   `ERROR_CODE 3001` path. If `MASTER_Z_GO` is false, the existing 3001
   error still fires (Z is unsafe and we have no permission to move it).
3. **Block the XY move** until the auto-retract completes (i.e., until
   `Z_RETRACTED` is asserted), so XY only kicks off once Z is safely at 0.

The retract uses the same fast parameters as `z_axis_fast_move` in
`state_5_move_z` (1000 ups / 10000 ups² / 10000 ups² / 10000 / 10000 ups³,
S-curve).

## Files to modify

- `dune_winder/plc/state_3_move_xy/main/pasteable.rll` — proposed new ladder
  (the artefact this task produces).
- `dune_winder/plc/state_3_move_xy/main/studio_copy.rllscrap` — **not edited
  by the agent**; the human round-trips this through Studio per
  `RLL_FORMAT.md` §6.

No changes needed to `programTags.json` or `controller_level_tags.json` —
all tags used already exist (`Z_axis`, `MASTER_Z_GO`, `Z_STAGE_PRESENT`,
`Z_RETRACTED`, `XY_AXIS_STAT[]` is sized 32 so slots 7 and 8 are free).
`ERROR_CODE 3006` is a new value but `ERROR_CODE` itself is an existing
controller tag, so no tag declaration is required.

## New tags to declare

None. (Per `RLL_FORMAT.md` §4 the agent must enumerate new tags; there are
none in this proposal.)

## Rung-level changes to `pasteable.rll`

The existing rung 2 has the gate that drives `STATE3_IND`. Today its
inner branch is:

```
BST
  BST XIO Z_RETRACTED NXB GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z BND
    CPT ERROR_CODE 3001 CPT NEXTSTATE 10
  NXB
  XIC Z_RETRACTED
    BST XIC APA_IS_VERTICAL
        NXB XIO APA_IS_VERTICAL CPT ERROR_CODE 3005 CPT NEXTSTATE 10
    BND
    OTE STATE3_IND
BND
```

Change rung 2's first leg (the 3001 path) to gate on
`MASTER_Z_GO`-not-true: only error 3001 if we have no permission to retract
Z ourselves. The new shape of that leg:

```
BST XIO Z_RETRACTED NXB GEQ Z_axis.ActualPosition MAX_TOLERABLE_Z BND
  XIO MASTER_Z_GO
  CPT ERROR_CODE 3001 CPT NEXTSTATE 10
```

Keep the second leg (`XIC Z_RETRACTED` → APA gate → `OTE STATE3_IND`)
unchanged. The result: `STATE3_IND` still requires `Z_RETRACTED`, so the
XY move is still blocked until Z is at 0 — but now an in-flight auto
retract can satisfy that condition without an error.

### New rungs (inserted between current rung 4 and current rung 5)

Add Z-servo enable plus a retract-trigger one-shot, gated on the same
prerequisites that gate the X/Y servo enable today (rung 3 → rung 4: tension
ready, axis fault checks, then `oneshotob[0]`):

1. **Z servo on, alongside X/Y MSO.** Extend rung 4 (`XIC oneshotob[0]
   BST MSO X_axis XY_AXIS_STAT[0] NXB MSO Y_axis XY_AXIS_STAT[1] BND`) to
   also include `MSO Z_axis XY_AXIS_STAT[7]`.

2. **Decide whether a pre-XY retract is needed.** New rung:

   ```
   XIC oneshotob[0] XIO Z_RETRACTED XIC MASTER_Z_GO XIO Z_STAGE_PRESENT
     OTE need_z_retract
   ```

   `need_z_retract` is a new program-scoped BOOL (declare in
   `programTags.json` — see "New tags" addendum below).

3. **Wait for Z servo enabled, then fire the retract.** New rung, modeled
   on `state_5_move_z` rung 12:

   ```
   XIC need_z_retract XIC Z_axis.DriveEnableStatus
     MAM Z_axis z_axis_pre_xy_retract 0 0 1000 "Units per sec"
       10000 "Units per sec2" 10000 "Units per sec2" S-Curve
       10000 10000 "Units per sec3" Disabled Programmed 0 None 0 0
   ```

   `z_axis_pre_xy_retract` is a new program-scoped MOTION_INSTRUCTION.

4. **Surface a Z fault during the auto-retract.** New rung:

   ```
   XIC need_z_retract XIC Z_axis.PhysicalAxisFault
     CPT ERROR_CODE 3006 CPT NEXTSTATE 10
   ```

   Reuses the existing pattern for `X_Y.PhysicalAxisFault` → 3002. New
   error code 3006 = "pre-XY Z retract fault".

### XY-move trigger gate (rung 6 today)

Today rung 6 OSRs `trigger_xy_move` once both X and Y MSOs are done:

```
BST XIC oneshotob[1] NXB
    XIC XY_AXIS_STAT[0].DN XIC XY_AXIS_STAT[1].DN XIC oneshotob[0]
BND OSR oneshotsb[3] trigger_xy_move
```

Add `XIC Z_RETRACTED` to this rung so the XY move only kicks off after
Z has finished retracting (or was already at 0):

```
BST XIC oneshotob[1] NXB
    XIC XY_AXIS_STAT[0].DN XIC XY_AXIS_STAT[1].DN XIC oneshotob[0]
BND XIC Z_RETRACTED OSR oneshotsb[3] trigger_xy_move
```

This is the key safety interlock: even though `STATE3_IND` already requires
`Z_RETRACTED`, gating the OSR explicitly makes the dependency obvious and
survives any future edits to the `STATE3_IND` rung.

### Cleanup at end of state (rung 21 today)

Add `MOV 0 z_axis_pre_xy_retract.FLAGS` alongside the existing
`MOV 0 main_xy_move.FLAGS` so the motion-instruction is fully reset on
state-exit, mirroring how state_5 clears both its z-axis MAM blocks at exit.

## New tags to declare (corrected)

Two new program-scoped tags in
`dune_winder/plc/state_3_move_xy/programTags.json`:

| Name                       | Scope     | Type                | Notes                              |
| -------------------------- | --------- | ------------------- | ---------------------------------- |
| `need_z_retract`           | Program   | BOOL                | gates the pre-XY retract           |
| `z_axis_pre_xy_retract`    | Program   | MOTION_INSTRUCTION  | MAM control block for the retract  |

(`XY_AXIS_STAT[7]` already exists — `XY_AXIS_STAT` is dimensioned [32].)

No new controller-scope tags. No changes to `controller_level_tags.json`.

## Verification

Per `RLL_FORMAT.md` §6 the agent cannot drive Studio. The verification
loop is therefore:

1. **Static review.** Re-read the proposed `pasteable.rll` and confirm:
   - rung 2 still has `OTE STATE3_IND` only when `Z_RETRACTED`;
   - rung 4 has three MSOs (X, Y, Z);
   - the new `need_z_retract` rung is ANDed with `oneshotob[0]`,
     `XIO Z_RETRACTED`, `XIC MASTER_Z_GO`, `XIO Z_STAGE_PRESENT`;
   - the trigger-XY rung includes `XIC Z_RETRACTED`;
   - the cleanup rung clears `z_axis_pre_xy_retract.FLAGS`.
2. **Tag enumeration.** Confirm the two new program-scoped tags above are
   added to `programTags.json` before the human pastes.
3. **Human paste & round-trip** (per `RLL_FORMAT.md` §6):
   - Human declares `need_z_retract` and `z_axis_pre_xy_retract` at
     program scope in Studio.
   - Human pastes `pasteable.rll` into the `main` routine of program
     `state_3_move_xy`.
   - Human copies the routine back, overwrites `studio_copy.rllscrap`,
     runs `uv run plc-sync --offline`, and verifies the regenerated
     `.rll` matches the proposal.
4. **Bench test, in this order**:
   - **Z servo on test.** Enter state 3 with Z already at 0 and head
     undocked → confirm `Z_axis.DriveEnableStatus` goes high and no
     retract motion fires (`need_z_retract` stays off because
     `Z_RETRACTED` is on).
   - **Auto-retract test.** Park Z above 0 with `MASTER_Z_GO=1`,
     `Z_STAGE_PRESENT=0`, then request state 3 → confirm Z drives to 0
     before the XY MCLM kicks off, and the eventual XY move starts
     after `Z_RETRACTED` asserts.
   - **Permission-denied test.** Same Z position but `MASTER_Z_GO=0`
     → confirm `ERROR_CODE 3001` fires, state goes to 10, no Z motion.
   - **Head-docked test.** Z above 0, `MASTER_Z_GO=1`, but
     `Z_STAGE_PRESENT=1` → confirm `ERROR_CODE 3001` fires (we don't
     want to yank Z while the head is docked at the stage).
   - **Z fault during retract.** Force `Z_axis.PhysicalAxisFault`
     during the retract → confirm `ERROR_CODE 3006`, state 10.
