# Plan — APA.html Spine Capture Panel

## Context

The UV layer rewrite (see `plans/UVlayerRewritePlan.md`) replaces the
"manually edit 12 per-placement offsets" workflow with a one-click pose
capture that runs *during* a UV recipe. After each `~anchorToTarget`
line, if the wire is not actually tangent at the target pin, the
operator pauses, jogs to where the wire *is* tangent, and clicks one
button. The system records the offset, propagates it to every line
that shares the same label across all wraps, and immediately rewrites
the recipe file so the rest of the run uses the corrected position.

The Phase E **backend** for this is already in place on the working
tree (uncommitted): `MachineCaptureService` (`record_capture`,
`get_state`), the `process.machine_capture.*` commands, the
`offset(x, y, z)` parser/emitter extension, and 3D propagation through
`_apply_anchor_to_target_override`. The Phase E **frontend** has not
been written: `#operatorOffsetCalibrationDiv` in `APA.html` is still a
literal placeholder. This plan covers that frontend slice plus the
small backend changes it depends on.

## Domain notes pinned during design

- `head_side` is **not** an operator-chosen field. It is fully
  determined by the `(anchor.side, target.side)` of the
  `~anchorToTarget` macro line:
  - `(A, A)` → head on stage side, Z extended below spine (`z < 207`)
  - `(A, B)` → head latched to fixed side, stage retracted
  - `(B, A)` → both heads retracted
  - `(B, B)` → head on stage side, Z extended above spine (`z > 207`)

  The capture UI must **not** present a `head_side` selector; the
  backend derives the 4-way head configuration from the pin pair.

- The line "label" for offset propagation is the
  `(wrap_number, wrap_line_number)` tuple injected by
  `template_gcode_common.wrap_identifier()` and matched by
  `extract_line_key()` (regex `\((\d+),(\d+)\)`). When the operator
  captures on `(5, 8)`, the offset must propagate to every wrap's line
  8, i.e. write `(1, 8) … (WRAP_COUNT, 8)` — not just `(5, 8)`. The
  dialog presents this as "applies to line 8 of every wrap (Head B
  corner)" so the operator sees the true scope.

- `lastTrace.resultingTarget.pinZ` is the calculated Z; there is no
  `z` field. Live machine position must be added to `get_state()` so
  the panel can poll one endpoint.

## Files to modify

### Backend (small, in support of the frontend)

- `src/dune_winder/core/machine_calibration_capture.py`
  - Add `currentXyz: {x, y, z}` to `get_state()` return, sourced from
    `self._process._io.{x,y,z}Axis.getPosition()`.
  - Add `headConfig: "stage_a" | "stage_b" | "fixed" | "retracted"` to
    `get_state()` return; derive by parsing the anchor/target Pin
    arguments out of `lastTrace.line` and applying the 4-way table
    above. Return `null` when the trace is not an `~anchorToTarget`
    line.
  - Add `propagationScope: { wrapLineNumber, wrapCount }` to
    `get_state()` return — the line index that will receive the
    offset and the total wrap count of the loaded recipe.
  - Remove the `head_side` argument from `record_capture()`; derive it
    internally from the trace's anchor/target pins. The
    `process.machine_capture.record` command's `args` shrinks to `{}`.
  - Replace `_apply_z_offset_to_recipe(label, delta_z)` with
    `_apply_xyz_offset_to_recipe(wrap_line_number, delta_xyz)` that
    iterates `range(1, wrap_count + 1)` and writes the `{x, y, z}`
    delta to every `(wrap, wrap_line_number)` key. Keep using
    `service.replaceLineOffsetOverrides(...)` and
    `service.generateRecipeFile(...)` to persist + regenerate.

- `rust/crates/dune_geometry/src/calibration.rs` and `python.rs`
  - Widen the existing `HeadSide` enum (currently `Stage`/`Fixed`) to
    a 4-variant `HeadConfig` (`StageA`, `StageB`, `Fixed`,
    `Retracted`). `CalibrationPoint.head_side` becomes
    `head_config: HeadConfig`. Update the PyO3 surface to accept the
    string forms above. Update existing Rust tests.
  - The capture service uses the new field; record_capture computes
    `HeadConfig` from `(anchor.side, target.side)` and stores it.

- `src/dune_winder/api/commands.py`
  - `process.machine_capture.record` now validates with no required
    args.

### Frontend

- `dune_winder/web/scripts/CommandCatalog.js`
  - Add under `process:`:
    ```js
    machineCaptureGetState: "process.machine_capture.get_state",
    machineCaptureRecord:   "process.machine_capture.record",
    ```

- `dune_winder/web/desktop/pages/APA.html`
  - Replace the `<article id="operatorOffsetCalibrationDiv">` body
    (currently `<h3>Operator Offset Calibration</h3><p>Placeholder</p>`)
    with the panel markup described in **Panel layout** below.
  - Append a confirmation dialog `<section>` after the `#column4`
    block, modelled on the existing `manualCalibrationBoardDialog`
    pattern in `Calibrate.html` (fixed bottom-right card, toggled via
    `.hidden`).

- `dune_winder/web/desktop/pages/APA.css`
  - Add styles for `.spineCaptureGrid`, `.spineCaptureRow`,
    `.spineCaptureValue`, `.spineCaptureWarning`, and
    `.spineCaptureDialog` (re-using the dark/translucent panel idiom
    already in `apaGCodeSubbox` and the fixed-card idiom from
    `manualCalibrationBoardDialog`).

- `dune_winder/web/desktop/pages/APA.js`
  - Add a single 1-second poll that calls
    `commands.process.machineCaptureGetState`. Use the existing
    `requestId` / `handledId` stale-callback guard pattern (see
    `forecastLogRequestId`). Store the result in a module-scoped
    `lastCaptureState` and call `updateCapturePanel()`.
  - Implement `updateCapturePanel(state)` that fills in the panel
    fields and toggles the capture button.
  - Bind `#spineCaptureButton` click → open the confirmation dialog,
    populated with the *frozen* offset/values from the moment of
    click. Bind `#spineCaptureConfirmButton` → call
    `commands.process.machineCaptureRecord` with `{}`. Bind
    `#spineCaptureCancelButton` → `addClass("hidden")`.
  - Use `modules.registerRestoreCallback` for the click bindings (per
    existing `bindControls()` pattern) and
    `modules.registerShutdownCallback` to clear the poll interval.

## Panel layout (`#operatorOffsetCalibrationDiv`)

```
Spine Capture
─────────────
Last line:        ~anchorToTarget(UA1, UB40, ...)            ← truncated to 1 line
Anchor → Target:  UA1 → UB40                                  ← derived from trace
Head config:      stage, Z extended to B   (B → B, z > 207)   ← 4-way label
Calculated XYZ:   123.456  78.910  272.000
Current XYZ:      123.876  79.020  271.500                    ← live, polled
Delta (cur−calc): +0.420   +0.110  −0.500                     ← coloured if any |Δ| > 5

Will propagate to: line 8 of every wrap (12 wraps × line 8)

[ Use Current Position ]                                      ← disabled unless canRecord
```

When `available === false`, replace the table with
"`dune_geometry` not loaded — capture unavailable" and disable the
button. When `lastTrace == null` or `headConfig == null`, show "—" for
all rows and disable the button. When `canRecord === false` (gcode
running, or no valid trace), keep the data visible but disable the
button.

## Confirmation dialog

Modelled on `manualCalibrationBoardDialog` (fixed bottom-right,
`.hidden` toggled). Contents:

```
Use current position?
─────────────────────
Captured offset:   +0.420  +0.110  −0.500   (mm)
Will rewrite:      line 8 of every wrap (12 wraps)
Head config:       stage, Z extended to B

⚠ Z offset exceeds 5 mm.   ← only when any |Δ| > 5; red text
   Are you sure?

[ Cancel ]   [ Use Current Position ]   ← second button label gains
                                          " (override 5mm warning)" when warning is shown
```

The warning region uses a `.spineCaptureWarning` class toggled by
`.hidden`. The Confirm button itself stays enabled in both cases —
the warning is informational, not blocking. (The user said "warning
the user … asking if they are sure they want to use it"; a single
extra confirm click satisfies that.)

## Existing utilities to reuse

- `uiServices.call(commandName, args, onSuccess)` — existing wrapper
  used everywhere in `APA.js`.
- `winder.addPeriodicEndCallback` — for any state-driven button
  enable/disable that should sync with the rest of the page (we don't
  strictly need this; the 1 s poll already drives our enable state).
- `modules.registerRestoreCallback` and
  `modules.registerShutdownCallback` — pattern already used by
  `bindControls()` and `forecastPollTimer` in `APA.js:568, 1130`.
- `.hidden` class + fixed-position card CSS from
  `Calibrate.css:302-312` (`manualCalibrationBoardDialog` rules) —
  reuse the same idiom for `.spineCaptureDialog`.
- `extract_line_key()` / `parse_line_key()` /
  `normalize_line_offset_overrides()` /
  `apply_line_offset_overrides()` in
  `src/dune_winder/recipes/line_offset_overrides.py` — already
  3D-aware on the working tree; `_apply_xyz_offset_to_recipe` in the
  capture service just builds the dict and calls
  `service.replaceLineOffsetOverrides()`.
- `Pin` PyO3 type from `dune_geometry` — for parsing pin strings like
  `UA1` out of the trace line during head-config derivation.

## Verification

1. **Rust unit tests** — `cargo test -p dune_geometry` keeps passing
   (52 → ~55+ after `HeadConfig` widening adds tests for the 4-way
   classification and CalibrationPoint round-trip).
2. **Python unit tests for the capture service** — add
   `tests/dune_winder/test_machine_calibration_capture.py` covering:
   - `get_state()` shape: `currentXyz`, `headConfig`,
     `propagationScope`, `canRecord` flags.
   - Head-config classification table (4 cases).
   - `record_capture()` with no `head_side` argument; offset propagates
     across all wraps for the captured line index, not just one wrap.
3. **Manual end-to-end** on the desktop UI:
   - Load a UV recipe on `APA.html`.
   - Step until paused on an `~anchorToTarget` line.
   - Verify the panel shows the line, calculated XYZ, current XYZ,
     non-zero delta when you jog, and the right head-config label for
     all four `(anchor.side, target.side)` combinations.
   - Click capture; verify the dialog shows the offset and propagation
     scope. Confirm; verify `lineOffsetOverrides` now contains entries
     for *every* wrap at the captured line index, that the recipe file
     was regenerated, and that resuming the run uses the corrected
     position.
   - Force a `>5 mm` delta in Z; verify the dialog shows the warning.
4. **Spec parity** — `specs/uv-machine-calibration.allium` already
   describes the capture flow; the only spec edit needed is to update
   `head_side: stage | fixed` to `head_config` with the 4 variants.
   That edit is in scope for this slice and gates the Allium tests.
