# Plan: Simplify Spine Calibration to a Plane

## Context

The current spine calibration model stores a **closed continuous 3D loop** of per-pin XYZ spine points (one point per pin number, 1..pin_count, covering up to 2401 pins per layer). The loop machinery — closed-loop interpolation, Gaussian residual smoothing, `forward_distance`/`neighbours`/`lerp` helpers, `SpineLoopIsClosed` and `SpineLoopCoversAllPinNumbers` invariants — exists to fill in per-pin XYZ for pins that weren't directly calibrated.

The physical reality is simpler: the APA spine is nearly a flat plane at Z≈207 mm, with at most a slight tilt. The per-pin loop model over-fits a structure that can be described with three numbers. The user wants to replace it with a **plane** `Z = a·X + b·Y + c` (defaulting to `c=207`, `a=b=0`), and remove all the closed-loop machinery.

The key insight: all same-side calibration observations, when back-projected to the spine (±half_board_width in Z), lie on this plane. Fitting the plane is already implemented as `ridge_fit_plane_z` in `spine.rs`.

## What changes

### 1. Spec — `specs/spine-calibration.allium`

- **Remove** `SpinePoint` value type (per-pin XYZ no longer stored)
- **Remove** `SpineLoop` value type (closed-loop structure gone)
- **Add** `SpinePlane { layer, a, b, c }` — three plane coefficients; default `(a=0, b=0, c=207)`
- **Update** `SpineCalibrationFile.loops → planes: List<SpinePlane>`
- **Update** `DerivePinPositionFromSpine` guidance: `spine_z = a·X + b·Y + c`; A/B displacement is ±half_board_width in Z as before; X and Y come from the winder observation at calibration time (stored in the calibration touch or passed by the caller)
- **Rename + simplify** `SolveSpineLoopFromCalibrationTouches → SolveSpinePlaneFromCalibrationTouches`: back-project touches to spine Z, fit plane to (X, Y, spine_Z) observations; if data is degenerate or absent, default to `(0, 0, 207)`
- **Remove** `SpineLoopIsClosed` invariant
- **Remove** `SpineLoopCoversAllPinNumbers` invariant
- **Keep** `DerivedABCoordsAreSymmetricAboutSpine` (still valid)
- **Keep** `ReplacesPerSidePinCalibration` (still valid)
- **Remove** both open questions (partial-perimeter sweep is now fine; plane fitting degrades gracefully; config question becomes moot when the only parameter is the default Z)

### 2. Rust — `rust/crates/dune_geometry/src/spine.rs`

**Remove:**
- `SpinePoint` struct
- `SpineLoop` struct + `impl SpineLoop`
- `SpineFitConfig` struct (was for tilt prior + smoothing; no longer needed since we drop smoothing and keep the plane fit with sensible defaults baked in)
- `solve_spine_loop()` and `solve_spine_loop_with_config()`
- `smooth_residual_at()`, `circular_distance()`, `lerp()`, `neighbours()`, `forward_distance()`
- `SpineError::NoObservationsInRange`

**Add:**
- `SpinePlane { layer: Layer, a: f64, b: f64, c: f64 }` with `impl Default` returning `(0.0, 0.0, 207.0)` for the Z constant, and `is_default()` helper if useful
- `solve_spine_plane(layer, touches) -> Result<SpinePlane, SpineError>`: back-project touches via `observe_spine_point_from_touch`, fit with `ridge_fit_plane_z` (keep), fall back to `SpinePlane::default()` on degenerate/empty fit

**Update:**
- `SpineCalibrationFile`: replace `loops: Vec<SpineLoop>` with `planes: Vec<SpinePlane>`; update `loop_for → plane_for`, `raw_pin_position` takes (pin, x, y) or accepts that X/Y come from caller context (see note below)
- Module doc comment

**Keep:**
- `CalibrationTouch` (unchanged)
- `observe_spine_point_from_touch()` (unchanged)
- `derive_pin_position_from_spine()` — signature stays the same; spine_xyz is now `(x, y, plane_z_at(x,y))` rather than a stored point
- `ridge_fit_plane_z()` (keep, with `SpineFitConfig` collapsed into inline constants or a simpler `data_noise_mm` parameter)
- `average_xyz()`, `plane_z_at()`, `determinant_3x3()`, `replace_column()` (keep)
- `SpineError::NoTouches`, `SpineError::LayerMismatch` (keep)

**Primary API — `z_at(layer, side, x, y) -> f64`:** Callers (path-planning, wire solver) know the winder (X, Y) position, the layer, and the side. They ask "what Z should the wire be at?" The spine plane answers: `spine_z = a*x + b*y + c`, then displace by ±half_board_width for side. The caller already has (X, Y) and constructs the full 3D position as `(x, y, z_returned)`. The old `raw_pin_position(pin) -> Option<Vec3>` is replaced by this pure Z-returning function — no longer fallible, since the plane evaluates at any (X, Y). Update `wire.rs` and any other callers accordingly.

### 3. Python bindings — `rust/crates/dune_geometry/src/python.rs`

- Remove `PySpinePoint`, `PySpineLoop`
- Add `PySpinePlane` (layer, a, b, c; pyo3 frozen class)
- Update `PySpineCalibrationFile`: replace `loop_for` with `plane_for`; update `raw_pin_position` to take `(pin, x, y)`
- Update `py_solve_spine_loop → py_solve_spine_plane`
- Remove `py_observe_spine_point_from_touch` if it's only used as a solve intermediate (or keep if Python callers need it)

### 4. Tests

**`rust/crates/dune_geometry/src/spine.rs` (inline tests)**

Remove:
- `solve_with_two_observations_interpolates_between_them`
- `solve_collapses_a_b_observations_at_same_number_to_spine_average`
- `weak_prior_recovers_an_extreme_tilt_exactly`
- `default_prior_shrinks_extreme_tilts_in_the_fitted_plane`
- `default_prior_recovers_modest_tilt_with_well_spread_observations`
- `residual_smoothing_carries_local_bumps_to_neighbours`
- `ridge_handles_two_observations_without_falling_back`
- `ridge_handles_colinear_observations_without_singularity`

Keep / adapt:
- `derive_pin_position_a_side_is_minus_half_width_in_z`
- `derive_pin_position_b_side_is_plus_half_width_in_z`
- `derive_pin_position_is_symmetric_about_spine`
- `observe_spine_round_trip_via_derive`
- `solve_rejects_empty_touches`
- `solve_rejects_layer_mismatch`
- `round_trip_via_spine_calibration_file` (adapt for SpinePlane)
- `serde_roundtrip_spine_calibration_file`

Add:
- `solve_with_flat_observations_returns_default_z` — flat touches → plane ≈ (0, 0, z_mean)
- `solve_tilted_observations_recovers_tilt` — tilted touches → plane coefficients match

**`tests/dune_geometry/test_spine_surface.py`**

Remove/simplify the interpolation and loop tests; keep symmetry and derivation.

### 5. Wire integration — `rust/crates/dune_geometry/src/wire.rs`

- Update callers of `raw_pin_position(pin)` → `raw_pin_position(pin, x, y)` passing the winder X/Y from the wire request

## Critical files

| File | Change |
|---|---|
| `specs/spine-calibration.allium` | Replace SpineLoop → SpinePlane throughout |
| `rust/crates/dune_geometry/src/spine.rs` | Core implementation rewrite |
| `rust/crates/dune_geometry/src/python.rs` | Update PyO3 bindings |
| `rust/crates/dune_geometry/src/wire.rs` | Update `raw_pin_position` call sites |
| `tests/dune_geometry/test_spine_surface.py` | Simplify Python tests |

## Verification

1. `cargo test -p dune_geometry` — all Rust unit tests pass
2. `pytest tests/dune_geometry/test_spine_surface.py` — Python surface tests pass
3. `pytest tests/dune_geometry/test_convert_legacy_pin_calibration.py` — legacy conversion still works
4. Check that `wire.rs` still compiles with the updated `raw_pin_position` signature
