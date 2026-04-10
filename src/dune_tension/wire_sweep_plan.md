<proposed_plan>
# U/V Single-Wire Pin-Tangent Streaming

## Summary
- Add a new `stream_single_wire` measurement mode for U/V only.
- This mode will ignore historical wire XY targeting and instead derive each wire’s sweep path from live dune_winder pin calibration plus a persisted laser offset for side `A` or `B`.
- V1 rollout is limited to this new U/V streaming path. Legacy mode, the existing multi-wire `stream_sweep`, and X/G behavior stay unchanged.

## Key Changes
- Add a read-only dune_winder command `process.get_layer_calibration(layer)`.
- Return `{layer, activeLayer, calibrationFile, source, pinDiameterMm, locations}` where `locations` is the normalized absolute pin map.
- Reject the call if the requested layer is not the active loaded recipe layer, so tension never silently uses the wrong calibration.

- Add dune_tension desktop helpers `desktop_get_layer_calibration(layer)` and `desktop_seek_pin(pin_name, velocity)`.
- In desktop mode, fetch calibration and seek pins through the dune_winder API.
- In direct/server mode, fall back to local calibration loading from the repo/workspace.

- Add a persisted laser-offset store keyed by measurement side only: `A` and `B`.
- Store one XY vector per side, shared across U and V, plus capture metadata `{captured_layer, captured_pin, captured_focus, updated_at}`.
- Define the stored value with the winder sign convention: `laser_offset = calibrated_pin_xy - captured_stage_xy`.
- Keep this in a calibration file, not GUI state.
- Block `stream_single_wire` if the selected side has no saved offset.

- Add a pin-based geometry planner for U/V.
- Use back-pin calibration only.
- Map wire number to pin pair with the explicit rules:
- `V`: `delta = 1151 - wire_number`, pins = `Bwrap(1199 - delta, 1..2399)` and `Bwrap(1200 + delta, 1..2399)`.
- `U`: `delta = 1151 - wire_number`, pins = `Bwrap(1600 - delta, 1..2401)` and `Bwrap(1601 + delta, 1..2401)`.
- Use the side-specific tangent normal:
- `(V,B)` positive `y`
- `(V,A)` negative `y`
- `(U,B)` negative `y`
- `(U,A)` positive `y`
- Build the wire line by offsetting the ordered pin-center line by `pinDiameterMm / 2` along that normal, then subtract the saved side laser offset vector to get laser-target coordinates.

- Turn the infinite tangent line into a usable sweep segment.
- Clip to the measurable rectangle.
- Subtract comb keep-out bands `|x - comb| < 300 mm`.
- Subtract pin keep-outs for calibrated back pins near the line using `max(10 mm, 5 * pin_radius_mm)`.
- Trim surviving intervals by `10 mm` at each end.
- Pick the longest interval.
- If the top two intervals differ by at most `max(25 mm, 5% of the longer interval)`, pick the one with the lower midpoint `y`.
- Use that interval midpoint for zone lookup and expected wire length.

- Add `run_single_wire_sweep(wire_number)` to the streaming controller.
- Sweep forward and backward over the chosen segment while keeping the current continuous-audio plus pulsed-air pipeline.
- Analyze windows with `expected_frequency_hz` and `wire_hint=wire_number`.
- Aggregate only the requested wire’s observations.
- Accept when support count, mean pitch confidence, and line-adherence score pass.
- Default to `6` passes max, stopping early on acceptance or interrupt.
- If those passes do not accept, fall back to a generalized rescue routine seeded from the pin-based segment midpoint, not the historical wire-position provider.

- Add GUI support for the new mode.
- Add `stream_single_wire` to the mode selector and persistence.
- Reuse the existing `Calibrate`, `Seek Wire(s)`, and `Measure Auto` buttons by running wires one at a time through `run_single_wire_sweep`.
- Add a small laser-offset subsection with:
- a pin token entry accepting `PB1199`, `B1199`, or a bare number
- a `Seek Camera To Pin` button
- a `Capture Laser Offset` button
- a readout of the saved offset for the selected side
- `Seek Camera To Pin` should use the calibrated pin seek from dune_winder, so the user can calibrate the laser offset even before any laser offset exists.

- Update stale U/V upper bounds to include wire `1151`.
- Keep the lower bound at `8`.
- Update the U/V `wire_max` settings and missing-wire summary range accordingly.

## Test Plan
- Verify the wire-to-pin mapping with the provided examples:
- `V/B 1151 -> B1199,B1200`
- `V/B 1150 -> B1198,B1201`
- `U/B 1151 -> B1600,B1601`
- `U/B 1150 -> B1599,B1602`
- Include wrap-around cases near the low-wire end.

- Verify tangent-side selection for all four `(layer, side)` cases.
- Verify segment planning removes comb and pin keep-outs, picks the longest interval, and applies the lower-`y` tiebreak.
- Verify offset capture stores `calibrated_pin_xy - current_stage_xy`, keyed by side `A` or `B`.
- Verify missing offsets prevent `stream_single_wire` runs.
- Verify the new dune_winder calibration export and pin-seek helpers.
- Verify `run_single_wire_sweep` emits alternating sweep segments, can accept from streaming evidence, and falls back to rescue with the pin-based seed.
- Verify GUI dispatch and state persistence for the new mode and offset controls.
- Verify U/V list and auto workflows can target wire `1151`.

## Assumptions
- Side `A` uses the same back-pin family as side `B`; only the tangent normal flips.
- The laser offset is calibrated at a fixed operator focus and treated as focus-independent in v1; existing focus/X compensation still handles focus-induced X motion during measurement.
- V1 does not replace legacy positioning or the existing multi-wire streaming sweep.
</proposed_plan>