## Simulated PLC Backend Option for `dune_winder`

### Summary
Add a selectable PLC backend so `dune_winder` can run in `SIM` mode without `pycomm3`, while preserving current `REAL` behavior.  
The simulator will model command-driven PLC state/motion/tag behavior (one-cycle settle), derive mapped machine input bits, expose simulator control commands, and keep camera behavior effectively disabled/stubbed.

### Implementation Changes
- Startup/backend selection:
  - Add config key `plcMode` (default `REAL`) in settings defaults.
  - Add runtime override `PLC_MODE=SIM|REAL` in main arg parsing.
  - Resolve backend as `CLI override > config`.
  - Keep default behavior unchanged (`REAL`) if unset.
- Decouple `pycomm3` import:
  - Move real PLC import to lazy path so `SIM` mode starts even if `pycomm3` is missing.
  - Keep real backend error behavior unchanged when `PLC_MODE=REAL`.
- Add new PLC implementation:
  - Create `SimulatedPLC` implementing `PLC` interface (`initialize`, `isNotFunctional`, `read`, `write`) with thread-safe tag store.
  - Support read/write shapes used today:
    - `read("TAG") -> [value]`
    - `read(["A","B"]) -> [("A", vA), ("B", vB)]`
    - `write(("TAG", value))` and list forms.
- Simulated command/state model:
  - On `MOVE_TYPE` write, set busy `STATE`, set motion flags, and complete on next control cycle.
  - Busy-state mapping:
    - `RESET->READY`
    - `JOG_XY->XY_JOG`
    - `SEEK_XY->XY_SEEK`
    - `JOG_Z->Z_JOG`
    - `SEEK_Z->Z_SEEK`
    - `LATCH->LATCHING`
    - `HOME_LATCH->LATCH_HOMEING`
    - `LATCH_UNLOCK->LATCH_RELEASE`
    - `UNSERVO->UNSERVO`
    - `PLC_INIT->INIT`
    - completion returns `READY` unless errored.
  - Motion behavior (one-cycle settle):
    - XY/Z seek writes target to `*_axis.ActualPosition` on completion.
    - Jog applies one-cycle delta from speed+direction (`speed * 0.1s`) then settles.
    - `*_axis.CoordinatedMotionStatus` set while busy, cleared on completion.
  - Limit violations:
    - If target exceeds configured limits, set `STATE=ERROR`, preserve position, and set `ERROR_CODE` using existing table (`3003` XY, `5003` Z).
    - Require `RESET` move type to clear error.
- Head/latch modeling:
  - Canonical tags:
    - `HEAD_POS`: `-1` absent, `0` stage, `3` fixed.
    - `ACTUATOR_POS`: `0/1/2`.
  - `LATCH` toggles head side (`0 <-> 3`) and advances actuator position cyclically.
  - `HOME_LATCH` sets actuator to `0`.
  - If latch command is invalid for current head condition, set PLC error using existing table nearest match (`6001` family).
- Derived digital input mapping (`MACHINE_SW_STAT[*]`):
  - Auto-drive all mapped bits each cycle unless manually overridden.
  - Mapping policy:
    - `[0]=ACTUATOR_POS==0`
    - `[1],[2],[3],[4]=Z retracted condition`
    - `[5]=Z extended condition`
    - `[6]=HEAD_POS==0`
    - `[7]=HEAD_POS==3`
    - `[8]=Z at limit`
    - `[9]=HEAD_POS==0`
    - `[10]=HEAD_POS==3`
    - `[11]=derived spring-comp assumption (documented)`
    - `[12]=ACTUATOR_POS top assumption`
    - `[13]=ACTUATOR_POS mid assumption`
    - `[14]=X park window`
    - `[15]=X transfer window`
    - `[16],[17]=Y transfer windows (documented assumptions)`
    - `[18],[19],[20],[21]=XY end-of-travel from limits`
    - `[22]=rotation-lock safe default`
    - `[23]=estop default off`
    - `[24]=park default off`
    - `[25]=light-curtain default clear`
    - `[26..31]=frame-lock safe defaults`
    - `MORE_STATS_S[0]=gate-key safe default`.
  - All ambiguous assumptions are explicitly documented and overrideable.
- Simulator runtime control API (new commands):
  - `sim_plc.get_status`
  - `sim_plc.get_tag`
  - `sim_plc.set_tag` (sets manual override)
  - `sim_plc.clear_override`
  - `sim_plc.inject_error`
  - `sim_plc.clear_error`
  - Commands return clear “not in SIM mode” errors when backend is `REAL`.
- Limits/config handoff:
  - Add simulator limit configuration hook so `Process` passes machine calibration limits after load.
- Camera handling in SIM mode:
  - Do not simulate camera internals.
  - Keep camera tags writable/readable, keep FIFO empty (`FIFO status 0`), no synthetic generation.
- Docs:
  - Update README with `PLC_MODE=SIM` usage, config key, and new sim commands.

### Public Interfaces / API Additions
- New runtime option: `PLC_MODE=SIM|REAL`.
- New config key: `plcMode` (default `REAL`).
- New command namespace: `sim_plc.*` (commands listed above).

### Test Plan
- Add simulator backend tests:
  - Startup in `SIM` without importing `pycomm3`.
  - Initial machine-ready state and required functional tags.
  - Seek/jog/latch command transitions (`STATE`, motion flags, positions).
  - Limit violation -> `ERROR` + correct code -> reset clears.
  - Derived input bits for key scenarios (stage side, fixed side, at limits, estop/park defaults).
  - Override precedence over derived values.
- Add command API tests:
  - `sim_plc.*` success paths in `SIM`.
  - `sim_plc.*` rejection in `REAL`.
- Add regression tests:
  - Existing `REAL` startup path unchanged when `PLC_MODE` not set.
  - Existing command registry behavior unaffected.

### Assumptions / Defaults Locked
- Default simulator pose: stage-side loaded, machine-ready.
- Simulator fidelity: behavior model (not full physics).
- Completion timing: one-cycle settle.
- Error code policy: reuse existing PLC error table.
- Sensor policy: all mapped bits derived with documented assumptions + manual override.
- Camera policy: not simulated.
