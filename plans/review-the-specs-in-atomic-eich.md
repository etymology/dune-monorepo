# Spec Review: APA Geometry & Winder Pose Invariants

## Context

The user wants the specs in `specs/` to be sufficient for a reimplementer to
replicate the repo's behaviour without seeing the implementation, while
remaining implementation-agnostic. Two areas in scope:

1. **APA geometry** — physical workpiece definition (frame, board cross
   section, X/G board teeth, mid-APA combs).
2. **Winder pose invariants** — constraints on (X, Y, Z) of the head across
   runtime states, matched to the PLC's XYZ / XZ / YZ move modes and to the
   frame-lock sensor inputs.

Specs cover behaviour at the rule/trigger level but treat APA physical
geometry and pose-workspace constraints largely as calibration data. A
reimplementer would not be able to construct the APA from the specs alone
or know which moves are legal in which states.

## Findings

### APA geometry — gaps

A reimplementer cannot reconstruct the APA from the specs alone:

- **Frame envelope absent.** Implementation defines APA length 6060.2 mm,
  height 2300 mm, thickness 76.2 mm in
  [src/dune_winder/machine/geometry/apa.py:23-25](src/dune_winder/machine/geometry/apa.py#L23-L25);
  no spec mentions these. Also missing: nominal **board width in Z** and
  the **board thickness away from the APA plane in X and Y** (the side
  rail / head / foot stock that protrudes from the APA plane and drives
  the winder keepouts).
- **Pin physical dimensions absent.** `pin_radius` is consumed by tangent
  computations
  ([uv_head_target.py](src/dune_winder/uv_head_target.py),
  [uv_head_target_gui.py:39-47](src/dune_winder/uv_head_target_gui.py#L39-L47))
  but is not declared in [layer-geometry.allium](specs/layer-geometry.allium)
  or [uv-wrap-geometry.allium](specs/uv-wrap-geometry.allium).
- **X/G board teeth not specified.** The X and G boards run along the head
  and foot edges of the APA. Each board has teeth in two columns A and B
  per edge, at a pitch of `apa_height / 480` (= 2300/480 ≈ 4.792 mm). The
  X/G wrap visits teeth in the order
  `head A_n → foot A_n → foot B_n → head B_n → head A_{n+1} → …`, where
  teeth are numbered bottom-to-top. None of this is in the specs.
- **Combs not specified.** There are **four combs** positioned vertically
  in the middle of the APA at four comb positions (distinct from the
  head/foot X/G boards). The spec must capture: count (4), positions
  along the APA, and that they sit mid-APA rather than on the head/foot
  edges.
- **Wrap-side parity rule** in [layer-geometry.allium](specs/layer-geometry.allium)
  is correct as written — leave it alone.
- **Winding angles are out of scope.** The U/V (and X/G) winding angle is
  derived from pin locations on the fly and is **not part of the spec**.
  Do not add winding angle declarations.

### Winder pose invariants — gaps

Pose constraints follow the PLC's three move modes (see
[src/dune_winder/io/controllers/plc_logic.py:213-250](src/dune_winder/io/controllers/plc_logic.py#L213-L250)):

- **XYZ (general) move** — combined X/Y/Z motion. Requires Z to be
  **retracted**. Agnostic to head presence/absence.
- **XZ move** — motion in the X–Z plane. The PLC requires
  `Y_Transfer_OK` before accepting an XZ seek
  ([plc_logic.py:227](src/dune_winder/io/controllers/plc_logic.py#L227)),
  i.e. Y must be parked in a Y transfer zone (`y = 0` or `y = 2683`). The
  Z component of the move keeps Z held under power throughout.
- **YZ move** — motion in the Y–Z plane. The PLC requires `X_Transfer_OK`
  ([plc_logic.py:247](src/dune_winder/io/controllers/plc_logic.py#L247)),
  i.e. X must be parked in an X transfer zone (head or foot). Allowed
  either with Z retracted **or** with Z not retracted, in which case the
  path must not pass through any frame-lock / frame-support region
  currently asserted by the frame-lock sensors. Z being part of the move
  keeps it under power.
- **Z-axis held under power during XY motion.** Independently of encoder
  position, the Z axis must be held under power whenever any X or Y
  motion is in progress. The fact that the PLC's only horizontal move
  modes are XYZ, XZ, and YZ — not bare X, Y, or XY — is precisely what
  enforces this in the implementation; the spec should make the
  invariant explicit (separate from the position-based invariants
  above).
- **Z encoder position vs Z held under power are distinct concepts.**
  Position-based pose invariants reference `z_position`; the
  held-under-power invariant references `z_held` (or equivalent
  actuator-state field).

Spec-side gaps:

- No formal `invariant` blocks expressing the four bullets above.
- `ZMoveBlockedDuringFloating` covers a single transition; there is no
  comprehensive table of allowed moves under each Z and frame-lock state.
- Frame-lock sensors are modelled as fields but **the specs do not name
  the underlying PLC tags**:
  - `MACHINE_SW_STAT[26]` → `frame_lock_head_top`
  - `MACHINE_SW_STAT[27]` → `frame_lock_head_mid`
  - `MACHINE_SW_STAT[28]` → `frame_lock_head_btm`
  - `MACHINE_SW_STAT[29]` → `frame_lock_foot_top`
  - `MACHINE_SW_STAT[30]` → `frame_lock_foot_mid`
  - `MACHINE_SW_STAT[31]` → `frame_lock_foot_btm`
  ([src/dune_winder/queued_motion/plc_interface.py:40-45](src/dune_winder/queued_motion/plc_interface.py#L40-L45)).
- Calibration parameters (~30) consumed by
  [src/dune_winder/core/safety_validation_service.py:55-164](src/dune_winder/core/safety_validation_service.py#L55-L164)
  are not enumerated as a calibration contract.
- Rocker settling has no timeout / failure rule (open question in
  [winder-states.allium](specs/winder-states.allium)).

### Implementation leakage to remove

- [tension-physics.allium](specs/tension-physics.allium):118 —
  `rule EstimateFrequencyFromSamples` is implementation detail (Scott's
  rule, 1000 grid points). **Remove the rule entirely.**
- Duplicate `AudioCapture` / `PitchAnalysis` / `MeasurementArtifacts`
  contracts in [tension-measurement.allium](specs/tension-measurement.allium).
- Numeric PLC opcode values in
  [gcode-opcodes.allium](specs/gcode-opcodes.allium) are firmware
  coupling — keep but mark as a porting constraint.

## Recommended Changes

### 1. Extend `layer-geometry.allium` with an APA Physical Envelope section

Add a config / value-type block declaring:

- **APA frame**: `length` (≈6060.2 mm), `height` (2300 mm), `thickness`
  (76.2 mm). Calibration-loaded.
- **Board cross-section**: nominal **board width in Z** and **board
  thickness away from the APA plane in X and Y**.
- **Pin**: nominal `radius`; `PinCalibration` contract returning per-pin
  position.
- **X/G board teeth**: along head and foot edges, two columns A and B per
  edge, pitch = `apa_height / 480`. Encode the X/G wrap order as a
  derived sequence:
  `head A_n, foot A_n, foot B_n, head B_n, head A_{n+1}, …`, teeth
  numbered bottom-to-top.
- **Combs**: four combs positioned vertically in the middle of the APA
  at four comb positions (mid-APA, not on the head/foot edges).
- **Do not** add winding angles — derived on the fly from pin locations.
- **Do not** modify the wrap-side parity rule.

### 2. Add formal pose invariants to `motion-safety.allium`

Model the move modes the PLC actually supports
(`MoveMode = xyz | xz | yz`) and add `invariant` blocks:

- `XYZRequiresZRetracted` — `move.mode = xyz ⇒ z_retracted`. Agnostic
  to head presence.
- `XZRequiresYInTransferZone` — `move.mode = xz ⇒ y ∈ y_transfer_zones`
  (`y = 0` or `y = 2683`). Mirrors the PLC's `Y_Transfer_OK` precondition.
- `YZAllowedWhen` — `move.mode = yz ⇒ x ∈ x_transfer_zones ∧
  (z_retracted ∨ ¬path_intersects_active_frame_lock_regions)`. Mirrors
  the PLC's `X_Transfer_OK` precondition plus the frame-lock keepout
  rule.
- `ZHeldDuringHorizontalMotion` — whenever any X or Y axis is commanded,
  the Z axis is held under power. Separate invariant on actuator state,
  not on encoder position.

State explicitly that pose invariants split into encoder-position
invariants (referencing `z_position`) and actuator-state invariants
(referencing `z_held` or equivalent), and that these are independent.

### 3. Tie frame-lock keepouts to PLC sensor inputs

In [motion-safety.allium](specs/motion-safety.allium), under the
`FrameLockCollisionState` (or equivalent) entity, add `@guidance` lines
giving the canonical PLC tag for each sensor field:

```text
frame_lock_head_top  -- PLC tag MACHINE_SW_STAT[26]
frame_lock_head_mid  -- PLC tag MACHINE_SW_STAT[27]
…
frame_lock_foot_btm  -- PLC tag MACHINE_SW_STAT[31]
```

State the invariant `ActiveFrameLockKeepoutsRespected`: when sensor
`frame_lock_<edge>_<row>` is asserted, the head pose ∉ corresponding
keepout region during any Z-extended move through that edge.

### 4. Tighten `winder-states.allium`

- Replace the single `ZMoveBlockedDuringFloating` rule with a table of
  allowed Z transitions per runtime mode.
- Resolve or formalise the rocker-settling open question
  (`RockerSettlingTimeout` config + error rule, or explicit
  open-question text).

### 5. New spec: `winder-calibration.allium`

Single `WinderCalibration` contract enumerating every calibration
parameter the geometry / safety rules read (the ~30 values in
[safety_validation_service.py](src/dune_winder/core/safety_validation_service.py),
plus pin radius, APA frame dims, board cross-section, X/G tooth pitch,
comb positions). Makes the implicit "you must supply these" obligation a
first-class contract.

### 6. Cleanup

- **Remove** `rule EstimateFrequencyFromSamples` from
  [tension-physics.allium](specs/tension-physics.allium):118.
- Deduplicate the three repeated contracts in
  [tension-measurement.allium](specs/tension-measurement.allium).
- Update [specs/README.md](specs/README.md) to reference the new
  `winder-calibration.allium` and the APA-envelope additions.

## Critical Files

- [specs/layer-geometry.allium](specs/layer-geometry.allium) — APA envelope, X/G teeth, combs, X/G wrap order
- [specs/motion-safety.allium](specs/motion-safety.allium) — XYZ/XZ/YZ pose invariants, PLC tag bindings
- [specs/winder-states.allium](specs/winder-states.allium) — Z transitions, rocker
- [specs/winder-calibration.allium](specs/winder-calibration.allium) — new
- [specs/tension-physics.allium](specs/tension-physics.allium) — remove EstimateFrequencyFromSamples
- [specs/tension-measurement.allium](specs/tension-measurement.allium) — dedupe
- [specs/README.md](specs/README.md) — index update

Implementation references (read-only, source of facts):

- [src/dune_winder/machine/geometry/apa.py:23-25](src/dune_winder/machine/geometry/apa.py#L23-L25)
- [src/dune_winder/uv_head_target.py](src/dune_winder/uv_head_target.py)
- [src/dune_winder/io/controllers/plc_logic.py:213-250](src/dune_winder/io/controllers/plc_logic.py#L213-L250)
- [src/dune_winder/core/safety_validation_service.py:55-164](src/dune_winder/core/safety_validation_service.py#L55-L164)
- [src/dune_winder/queued_motion/safety.py:20-63](src/dune_winder/queued_motion/safety.py#L20-L63)
- [src/dune_winder/queued_motion/plc_interface.py:40-45](src/dune_winder/queued_motion/plc_interface.py#L40-L45)

## Verification

1. `allium check specs/*.allium` — all specs parse.
2. `allium analyse specs/motion-safety.allium specs/winder-states.allium`
   — new invariants are well-formed.
3. **Reimplementer dry-run**: read only `specs/` and confirm answers to:
   "What are the APA frame and board dimensions?", "What is the X/G tooth
   pitch and wrap order, and where are the combs?", "Which moves (XYZ /
   XZ / YZ) are legal under each Z state and frame-lock pattern?", "When
   must Z be held under power?", "Which calibration parameters must I
   supply?", "Which PLC tags drive the frame-lock keepouts?". All six
   should be answerable from specs alone.
4. Confirm no rule references `EstimateFrequencyFromSamples` after
   removal.
