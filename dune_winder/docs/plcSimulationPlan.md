## PLC Simulator Option Plan (Aligned With Completed P7)

### Summary
Implement simulator mode on top of the new P7 configuration/persistence stack (`AppConfig` + TOML, calibration/APA JSON), not the legacy XML stack.  
This plan assumes P7 is already merged and focuses on simulator behavior, backend selection, and cleanup of simulator-adjacent legacy references.

### Key Implementation Changes
- Configuration/runtime selection (P7-native):
  - Add `plcMode: str = "REAL"` to `AppConfig` (TOML-backed).
  - Keep CLI override `PLC_MODE=SIM|REAL`; precedence: CLI > `AppConfig.plcMode`.
  - Keep `REAL` default behavior unchanged.
- Backend wiring:
  - Switch PLC backend via a factory/constructor path that selects `ControllogixPLC` vs `SimulatedPLC`.
  - Keep `pycomm3` lazy-imported so `SIM` mode runs without `pycomm3`.
- Simulated PLC behavior (same domain contract as prior plan):
  - One-cycle settle model.
  - `MOVE_TYPE` -> busy `STATE` mapping, then `READY`.
  - Limits violation sets `STATE=ERROR` and existing PLC codes (`3003` XY, `5003` Z), reset clears.
  - `HEAD_POS` map: `-1/0/3`; `ACTUATOR_POS` map: `0/1/2`.
  - Derive all mapped `MACHINE_SW_STAT[*]` bits with documented assumptions plus manual override support.
  - No camera simulation; keep FIFO empty and camera tags writable/readable.
- Simulator control API:
  - Add `sim_plc.get_status`, `sim_plc.get_tag`, `sim_plc.set_tag`, `sim_plc.clear_override`, `sim_plc.inject_error`, `sim_plc.clear_error`.
  - Return explicit “SIM mode required” errors when backend is `REAL`.
- P7 integration cleanup:
  - Ensure simulator codepaths only use `AppConfig` typed fields and JSON calibration/state objects.
  - Remove/replace simulator-adjacent XML assumptions in docs/tests (`configuration.xml`, `*_Calibration.xml`, `state.xml`) except intentional legacy-fallback tests.
  - Update operator docs to show TOML key + SIM startup usage.

### Public Interface Changes
- `configuration.toml`:
  - New field: `plcMode = "REAL" | "SIM"`.
- CLI:
  - `PLC_MODE=SIM|REAL` override.
- Command API:
  - New `sim_plc.*` command namespace (listed above).

### Test Plan
- Config/backend tests:
  - `AppConfig` loads/saves `plcMode`; CLI override works.
  - `SIM` startup does not require `pycomm3`.
- Simulator behavior tests:
  - Startup healthy state, move/latch transitions, limit-error/reset path.
  - Derived input-bit behavior and override precedence.
- API tests:
  - `sim_plc.*` success in `SIM`, rejection in `REAL`.
- Regression tests:
  - Existing `REAL` flow unchanged.
  - P7 persistence paths remain canonical (TOML/JSON), with legacy XML fallback behavior still passing where intentionally covered.

### Assumptions
- P7 migration is already implemented and is the canonical baseline.
- XML support remains fallback-only for legacy file migration, not primary runtime format.
- Default simulator pose remains stage-side machine-ready.
