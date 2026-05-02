//! Spine calibration: the closed continuous loop running around the APA
//! perimeter at the Z midplane on which every layer's boards are
//! physically centred.
//!
//! Spec source of truth: `specs/spine-calibration.allium` (and the
//! per-layer `*_board_width_z_mm` configs in
//! `specs/layer-geometry.allium`).
//!
//! This module owns:
//!
//! - [`SpinePoint`] / [`SpineLoop`] / [`SpineCalibrationFile`] — the
//!   types that replace today's per-side `PinCalibrationFile` for any
//!   reader that needs raw camera-space pin coordinates.
//! - [`derive_pin_position_from_spine`] — turns a spine XYZ at pin
//!   number `n` into the raw XYZ of `(layer, side, n)` by displacing
//!   ± half the layer's board width along Z. A is `+`, B is `-`.
//! - [`observe_spine_point_from_touch`] — the inverse: collapse a
//!   calibration touch (operator drove the camera to a pin and recorded
//!   the winder XYZ) into one observation of the spine point at that
//!   pin number.
//! - [`solve_spine_loop`] — fits a closed continuous 3D loop of spine
//!   points from a list of [`CalibrationTouch`]es. The model encodes
//!   three priors, in decreasing strength:
//!     1. `Z` is nearly constant across the APA (the spine is almost
//!        flat).
//!     2. Any tilt is small — by default, ≤ ~15 mm of `Z` change over
//!        the ~6000 mm APA span (slope ≈ 0.0025).
//!     3. Per-pin departures from that tilted plane are small and
//!        smoothly varying around the perimeter (length-scale ≈ 200
//!        pins).
//!   The fit therefore solves a ridge-regularised plane
//!   `Z = a·X + b·Y + c` with a tilt prior, then smooths observed
//!   residuals around the closed loop to fill in unknown pin numbers.
//!   X and Y for unknowns come from closed-loop linear interpolation
//!   between the nearest observed neighbours along the perimeter (the
//!   loop's XY shape is well-determined by corner observations and
//!   doesn't need the same statistical treatment as Z).

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::calibration::Vec3;
use crate::pins::{Layer, Pin};

/// One point on a per-layer spine loop: the spine XYZ in raw
/// camera-space at `pin number = number`. The two pin-bearing faces (A
/// and B) at that perimeter position derive from this point ± half the
/// layer's board width along Z.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SpinePoint {
    pub layer: Layer,
    pub number: u16,
    pub xyz: Vec3,
}

/// The closed continuous loop of spine points for a single layer.
/// `points` is ordered by pin number ascending (1..=pin_count); the
/// loop closes back to the first point.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpineLoop {
    pub layer: Layer,
    pub points: Vec<SpinePoint>,
}

impl SpineLoop {
    /// Look up the spine point for the given pin number, if present.
    pub fn point(&self, number: u16) -> Option<&SpinePoint> {
        self.points.iter().find(|p| p.number == number)
    }
}

/// A calibration capture: the operator drove the calibration camera to
/// `pin` and recorded the winder XYZ. The recorded XYZ is the raw
/// camera-space position of that pin's face — no offset baked in.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct CalibrationTouch {
    pub pin: Pin,
    pub winder_xyz: Vec3,
}

/// One spine calibration file per machine. Carries one [`SpineLoop`]
/// per layer (any of U, V, X, G); layers may be partial. Replaces the
/// per-side `PinCalibrationFile` for raw-coord lookup.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpineCalibrationFile {
    pub machine_id: String,
    pub loops: Vec<SpineLoop>,
}

impl SpineCalibrationFile {
    pub fn new(machine_id: String) -> Self {
        Self {
            machine_id,
            loops: Vec::new(),
        }
    }

    pub fn loop_for(&self, layer: Layer) -> Option<&SpineLoop> {
        self.loops.iter().find(|l| l.layer == layer)
    }

    /// Derived raw camera-space XYZ for a `(layer, side, number)` pin.
    /// Returns `None` when the layer's loop is missing or the loop has
    /// no spine point at `number`.
    pub fn raw_pin_position(&self, pin: Pin) -> Option<Vec3> {
        let spine = self.loop_for(pin.layer)?.point(pin.number)?;
        Some(derive_pin_position_from_spine(spine.xyz, pin))
    }
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum SpineError {
    #[error("spine fit requires at least one calibration touch")]
    NoTouches,
    #[error("calibration touch references layer {found:?} but solver was given layer {expected:?}")]
    LayerMismatch { expected: Layer, found: Layer },
    #[error("at least one observed spine number must lie within 1..=pin_count for the layer")]
    NoObservationsInRange,
}

/// Derive the raw camera-space XYZ of a pin from the spine point at the
/// same pin number. Mirrors the `DerivePinPositionFromSpine` rule in
/// `specs/spine-calibration.allium`:
///
/// ```text
/// half_w = pin.layer.half_board_width_z_mm()
/// sign   = -1 when pin.side == A, +1 when pin.side == B
/// raw    = Vec3(spine.x, spine.y, spine.z + sign * half_w)
/// ```
pub fn derive_pin_position_from_spine(spine_xyz: Vec3, pin: Pin) -> Vec3 {
    let dz = pin.spine_to_face_sign() * pin.half_board_width_z_mm();
    Vec3::new(spine_xyz.x, spine_xyz.y, spine_xyz.z + dz)
}

/// Inverse of [`derive_pin_position_from_spine`]: given a recorded
/// winder XYZ at a calibration touch on `pin`, return the implied
/// spine XYZ at `pin.number`. Used by the spine solver to collapse
/// per-side touches into per-number observations.
pub fn observe_spine_point_from_touch(touch: CalibrationTouch) -> Vec3 {
    let dz = touch.pin.spine_to_face_sign() * touch.pin.half_board_width_z_mm();
    Vec3::new(touch.winder_xyz.x, touch.winder_xyz.y, touch.winder_xyz.z - dz)
}

fn average_xyz(points: &[Vec3]) -> Vec3 {
    let n = points.len() as f64;
    let sum = points.iter().fold(Vec3::ZERO, |acc, p| Vec3::new(
        acc.x + p.x,
        acc.y + p.y,
        acc.z + p.z,
    ));
    Vec3::new(sum.x / n, sum.y / n, sum.z / n)
}

/// Linear interpolate between two points along a closed loop. `step`
/// runs 1..total_gap; the wraparound case is handled by the caller.
fn lerp(a: Vec3, b: Vec3, step: u32, total: u32) -> Vec3 {
    Vec3::lerp(a, b, step as f64 / total as f64)
}

/// Configurable priors for [`solve_spine_loop_with_config`]. The
/// defaults reflect the operator's reported geometry: an APA span of
/// roughly 6000 mm, a `Z` deviation across that span of at most ~15 mm
/// (slope ≤ 0.0025), millimetre-scale per-pin measurement noise, and
/// non-planar departures from the spine plane that vary smoothly with
/// a length-scale of hundreds of pins.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SpineFitConfig {
    /// Expected upper-bound slope of the spine plane (rise/run). Used
    /// as the prior std on the plane's tilt parameters `(a, b)`. The
    /// fit's ridge weight is `λ = (data_noise_mm / tilt_prior_slope)²`
    /// — increasing this loosens the prior; setting it to a very large
    /// number recovers an unregularised least-squares plane.
    pub tilt_prior_slope: f64,

    /// Expected per-pin Z measurement noise, in millimetres. Sets the
    /// data-noise leg of the ridge weight. A larger value implicitly
    /// strengthens the tilt prior (because data residuals are noisier
    /// relative to the prior std).
    pub data_noise_mm: f64,

    /// Gaussian smoothing length-scale, in pin-number units, for the
    /// closed-loop residual smoothing. Each observation's residual
    /// (data Z minus plane Z) bleeds into nearby unknowns with weight
    /// `exp(-(circular_distance / σ)² / 2)`. Larger values pool
    /// residuals more broadly; smaller values keep each observation's
    /// influence local.
    pub residual_smoothing_pins: f64,
}

impl Default for SpineFitConfig {
    fn default() -> Self {
        SpineFitConfig {
            tilt_prior_slope: 15.0 / 6000.0,
            data_noise_mm: 1.0,
            residual_smoothing_pins: 200.0,
        }
    }
}

/// Fit a closed continuous spine loop to a set of calibration touches
/// using the default [`SpineFitConfig`]. See
/// [`solve_spine_loop_with_config`] for the full algorithm.
pub fn solve_spine_loop(
    layer: Layer,
    touches: &[CalibrationTouch],
) -> Result<SpineLoop, SpineError> {
    solve_spine_loop_with_config(layer, touches, SpineFitConfig::default())
}

/// Fit a closed continuous spine loop to a set of calibration touches.
///
/// Steps, mirroring `SolveSpineLoopFromCalibrationTouches` in
/// `specs/spine-calibration.allium`:
///
/// 1. Each touch maps to one observed spine point at `touch.pin.number`
///    via [`observe_spine_point_from_touch`].
/// 2. Multiple touches on the same number collapse to one observation
///    by component-wise mean (so an A-touch and a B-touch at the same
///    number both vote on the spine point there).
/// 3. A ridge-regularised plane `Z = a·X + b·Y + c` is fitted through
///    every observed spine point. The ridge term penalises the tilt
///    parameters `(a, b)` with weight
///    `λ = (config.data_noise_mm / config.tilt_prior_slope)²`, so the
///    fit collapses toward the mean Z when data is sparse or when the
///    observed tilt would exceed the prior; it recovers a real tilt
///    when many well-spread observations strongly support one.
/// 4. Each observed pin keeps its observed XYZ exactly. For each
///    unobserved pin number, X and Y come from a closed-loop linear
///    interpolation between the two nearest observed neighbours along
///    the perimeter, and Z is `plane(X, Y) + smoothed_residual(n)`,
///    where `smoothed_residual` is a circular Gaussian-weighted
///    average of the residuals at observed pins, with kernel width
///    `config.residual_smoothing_pins`. Pins far from any observation
///    are pulled toward the plane (residual ≈ 0) by a fixed
///    regularisation weight on the kernel denominator.
pub fn solve_spine_loop_with_config(
    layer: Layer,
    touches: &[CalibrationTouch],
    config: SpineFitConfig,
) -> Result<SpineLoop, SpineError> {
    if touches.is_empty() {
        return Err(SpineError::NoTouches);
    }
    for touch in touches {
        if touch.pin.layer != layer {
            return Err(SpineError::LayerMismatch {
                expected: layer,
                found: touch.pin.layer,
            });
        }
    }

    let pin_count = layer.pin_count();
    let mut grouped: BTreeMap<u16, Vec<Vec3>> = BTreeMap::new();
    for touch in touches {
        let number = touch.pin.number;
        if number == 0 || number > pin_count {
            continue;
        }
        let observed = observe_spine_point_from_touch(*touch);
        grouped.entry(number).or_default().push(observed);
    }
    if grouped.is_empty() {
        return Err(SpineError::NoObservationsInRange);
    }

    let observed: BTreeMap<u16, Vec3> = grouped
        .into_iter()
        .map(|(n, points)| (n, average_xyz(&points)))
        .collect();

    let observed_xyz: Vec<Vec3> = observed.values().copied().collect();
    let plane = ridge_fit_plane_z(&observed_xyz, &config);

    let observed_residuals: BTreeMap<u16, f64> = observed
        .iter()
        .map(|(&n, xyz)| {
            let plane_z = plane_z_at(plane, xyz.x, xyz.y).unwrap_or(xyz.z);
            (n, xyz.z - plane_z)
        })
        .collect();

    let observed_numbers: Vec<u16> = observed.keys().copied().collect();
    let mut points = Vec::with_capacity(pin_count as usize);
    for number in 1..=pin_count {
        if let Some(xyz) = observed.get(&number) {
            points.push(SpinePoint {
                layer,
                number,
                xyz: *xyz,
            });
            continue;
        }
        let (prev_n, next_n) = neighbours(&observed_numbers, number, pin_count);
        let prev_xyz = observed[&prev_n];
        let next_xyz = observed[&next_n];
        let span = forward_distance(prev_n, next_n, pin_count);
        let step = forward_distance(prev_n, number, pin_count);
        let lerped = lerp(prev_xyz, next_xyz, step, span);
        let plane_z = plane_z_at(plane, lerped.x, lerped.y).unwrap_or(lerped.z);
        let residual = smooth_residual_at(
            number,
            &observed_residuals,
            pin_count,
            config.residual_smoothing_pins,
        );
        points.push(SpinePoint {
            layer,
            number,
            xyz: Vec3::new(lerped.x, lerped.y, plane_z + residual),
        });
    }

    Ok(SpineLoop { layer, points })
}

fn plane_z_at(plane: Option<(f64, f64, f64)>, x: f64, y: f64) -> Option<f64> {
    plane.map(|(a, b, c)| a * x + b * y + c)
}

/// Ridge-regularised least-squares fit of `Z = a·X + b·Y + c` to a set
/// of 3D points. The constant term `c` is unpenalised; the tilt
/// parameters `(a, b)` carry a Gaussian prior with std
/// `config.tilt_prior_slope`, encoded as a Tikhonov penalty
/// `λ·(a² + b²)` with `λ = (data_noise_mm / tilt_prior_slope)²`.
///
/// Returns `None` for an empty input or when the regularised normal
/// equations are still numerically singular (which only happens when
/// `tilt_prior_slope` is set extremely large to disable the prior and
/// the observed XY positions are colinear).
fn ridge_fit_plane_z(points: &[Vec3], config: &SpineFitConfig) -> Option<(f64, f64, f64)> {
    if points.is_empty() {
        return None;
    }
    let lambda = (config.data_noise_mm / config.tilt_prior_slope).powi(2);
    let (mut sx, mut sy, mut sz) = (0.0, 0.0, 0.0);
    let (mut sxx, mut sxy, mut syy) = (0.0, 0.0, 0.0);
    let (mut sxz, mut syz) = (0.0, 0.0);
    for p in points {
        sx += p.x;
        sy += p.y;
        sz += p.z;
        sxx += p.x * p.x;
        sxy += p.x * p.y;
        syy += p.y * p.y;
        sxz += p.x * p.z;
        syz += p.y * p.z;
    }
    let n = points.len() as f64;
    let m = [
        [sxx + lambda, sxy, sx],
        [sxy, syy + lambda, sy],
        [sx, sy, n],
    ];
    let rhs = [sxz, syz, sz];
    let det = determinant_3x3(&m);
    if det.abs() < 1e-12 {
        return None;
    }
    let a = determinant_3x3(&replace_column(&m, 0, &rhs)) / det;
    let b = determinant_3x3(&replace_column(&m, 1, &rhs)) / det;
    let c = determinant_3x3(&replace_column(&m, 2, &rhs)) / det;
    Some((a, b, c))
}

/// Closed-loop Gaussian-weighted residual smoothing. Each observed
/// residual contributes with weight `exp(-(circular_distance / σ)² / 2)`
/// where `σ = sigma_pins` and circular distance wraps around the loop.
/// A fixed regularisation weight (≈ exp(-2)) is added to the
/// denominator so that pins far from any observation are pulled toward
/// zero residual (i.e. trust the plane), rather than picking up the
/// only-by-default value of a distant observation.
fn smooth_residual_at(
    target: u16,
    observed_residuals: &BTreeMap<u16, f64>,
    pin_count: u16,
    sigma_pins: f64,
) -> f64 {
    if observed_residuals.is_empty() || sigma_pins <= 0.0 {
        return 0.0;
    }
    const PRIOR_WEIGHT: f64 = 0.135_335_283_236_613; // exp(-2.0)
    let mut numerator = 0.0;
    let mut denominator = PRIOR_WEIGHT;
    for (&n, &r) in observed_residuals {
        let d = circular_distance(target, n, pin_count) as f64;
        let w = (-(d / sigma_pins).powi(2) / 2.0).exp();
        numerator += w * r;
        denominator += w;
    }
    numerator / denominator
}

fn circular_distance(a: u16, b: u16, pin_count: u16) -> u32 {
    let pc = pin_count as u32;
    let raw = if a >= b {
        (a - b) as u32
    } else {
        (b - a) as u32
    };
    raw.min(pc - raw)
}

fn determinant_3x3(m: &[[f64; 3]; 3]) -> f64 {
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
}

fn replace_column(m: &[[f64; 3]; 3], col: usize, rhs: &[f64; 3]) -> [[f64; 3]; 3] {
    let mut out = *m;
    for i in 0..3 {
        out[i][col] = rhs[i];
    }
    out
}

/// Forward distance from `from` to `to` along the closed loop of
/// `1..=pin_count`. Returns `pin_count` when `from == to` so callers
/// treat a single-observation degenerate case as "the full loop".
fn forward_distance(from: u16, to: u16, pin_count: u16) -> u32 {
    let pc = pin_count as i64;
    let raw = (to as i64 - from as i64).rem_euclid(pc);
    if raw == 0 {
        pin_count as u32
    } else {
        raw as u32
    }
}

/// Find the two nearest observed numbers `(prev, next)` to `target`
/// along the closed loop, with `prev` strictly behind `target` and
/// `next` strictly ahead (in the forward sense). When only one
/// observation exists, both `prev` and `next` are it (lerp degenerates
/// to a constant).
fn neighbours(observed_numbers: &[u16], target: u16, pin_count: u16) -> (u16, u16) {
    if observed_numbers.len() == 1 {
        let only = observed_numbers[0];
        return (only, only);
    }
    let prev = observed_numbers
        .iter()
        .copied()
        .filter(|&n| n != target)
        .min_by_key(|&n| forward_distance(n, target, pin_count))
        .unwrap();
    let next = observed_numbers
        .iter()
        .copied()
        .filter(|&n| n != target)
        .min_by_key(|&n| forward_distance(target, n, pin_count))
        .unwrap();
    (prev, next)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pins::Side;

    fn ua(n: u16) -> Pin {
        Pin::new(Layer::U, Side::A, n).unwrap()
    }

    fn ub(n: u16) -> Pin {
        Pin::new(Layer::U, Side::B, n).unwrap()
    }

    #[test]
    fn derive_pin_position_a_side_is_minus_half_width_in_z() {
        let spine = Vec3::new(10.0, 20.0, 100.0);
        let derived = derive_pin_position_from_spine(spine, ua(1));
        assert_eq!(derived, Vec3::new(10.0, 20.0, 100.0 - 65.0));
    }

    #[test]
    fn derive_pin_position_b_side_is_plus_half_width_in_z() {
        let spine = Vec3::new(10.0, 20.0, 100.0);
        let derived = derive_pin_position_from_spine(spine, ub(1));
        assert_eq!(derived, Vec3::new(10.0, 20.0, 100.0 + 65.0));
    }

    #[test]
    fn derive_pin_position_is_symmetric_about_spine() {
        let spine = Vec3::new(0.0, 0.0, 50.0);
        let a = derive_pin_position_from_spine(spine, ua(123));
        let b = derive_pin_position_from_spine(spine, ub(123));
        assert_eq!(a.x, b.x);
        assert_eq!(a.y, b.y);
        assert_eq!((a.z + b.z) / 2.0, spine.z);
        assert_eq!(b.z - a.z, Layer::U.board_width_z_mm());
    }

    #[test]
    fn observe_spine_round_trip_via_derive() {
        let spine = Vec3::new(1.0, 2.0, 3.0);
        for pin in [ua(7), ub(7)] {
            let derived = derive_pin_position_from_spine(spine, pin);
            let observed = observe_spine_point_from_touch(CalibrationTouch {
                pin,
                winder_xyz: derived,
            });
            assert_eq!(observed, spine);
        }
    }

    #[test]
    fn solve_rejects_empty_touches() {
        let result = solve_spine_loop(Layer::U, &[]);
        assert!(matches!(result, Err(SpineError::NoTouches)));
    }

    #[test]
    fn solve_rejects_layer_mismatch() {
        let touches = [CalibrationTouch {
            pin: Pin::new(Layer::V, Side::A, 1).unwrap(),
            winder_xyz: Vec3::ZERO,
        }];
        let result = solve_spine_loop(Layer::U, &touches);
        assert!(matches!(result, Err(SpineError::LayerMismatch { .. })));
    }

    #[test]
    fn solve_with_two_observations_interpolates_between_them() {
        // Two observations at numbers 1 and 1201 (halfway around U's
        // 2401-pin loop). The spine point at number 601 should be the
        // linear midpoint along the forward arc from 1 → 1201.
        let touch_at_1 = CalibrationTouch {
            pin: ua(1),
            winder_xyz: derive_pin_position_from_spine(
                Vec3::new(0.0, 0.0, 0.0),
                ua(1),
            ),
        };
        let touch_at_1201 = CalibrationTouch {
            pin: ua(1201),
            winder_xyz: derive_pin_position_from_spine(
                Vec3::new(100.0, 0.0, 10.0),
                ua(1201),
            ),
        };
        let loop_ = solve_spine_loop(Layer::U, &[touch_at_1, touch_at_1201]).unwrap();
        assert_eq!(loop_.points.len(), Layer::U.pin_count() as usize);

        let spine_at_1 = loop_.point(1).unwrap().xyz;
        assert_eq!(spine_at_1, Vec3::new(0.0, 0.0, 0.0));
        let spine_at_1201 = loop_.point(1201).unwrap().xyz;
        assert_eq!(spine_at_1201, Vec3::new(100.0, 0.0, 10.0));

        // Halfway between 1 and 1201 along the forward arc is 601 →
        // (50, 0, 5).
        let mid = loop_.point(601).unwrap().xyz;
        assert!((mid.x - 50.0).abs() < 1e-9);
        assert!((mid.y - 0.0).abs() < 1e-9);
        assert!((mid.z - 5.0).abs() < 1e-9);
    }

    #[test]
    fn solve_collapses_a_b_observations_at_same_number_to_spine_average() {
        // Capture both A and B at the same pin number with a slight
        // mismatch — the implied spine should be the average of both
        // implied spines, NOT the average of the recorded XYZs.
        let pin_a = ua(100);
        let pin_b = ub(100);
        let xyz_a = derive_pin_position_from_spine(Vec3::new(5.0, 5.0, 0.0), pin_a);
        let xyz_b = derive_pin_position_from_spine(Vec3::new(5.0, 5.0, 0.4), pin_b);
        let loop_ = solve_spine_loop(
            Layer::U,
            &[
                CalibrationTouch {
                    pin: pin_a,
                    winder_xyz: xyz_a,
                },
                CalibrationTouch {
                    pin: pin_b,
                    winder_xyz: xyz_b,
                },
            ],
        )
        .unwrap();
        let spine = loop_.point(100).unwrap().xyz;
        assert!((spine.x - 5.0).abs() < 1e-9);
        assert!((spine.y - 5.0).abs() < 1e-9);
        // Average of the two implied spine Zs (0.0 and 0.4).
        assert!((spine.z - 0.2).abs() < 1e-9);
    }

    fn weak_prior_config() -> SpineFitConfig {
        // Effectively disables the ridge prior so plane recovery is
        // exact (within float precision). Used only by tests that
        // verify the unregularised math, not the operational defaults.
        SpineFitConfig {
            tilt_prior_slope: 1.0e6,
            data_noise_mm: 1.0,
            residual_smoothing_pins: 200.0,
        }
    }

    #[test]
    fn weak_prior_recovers_an_extreme_tilt_exactly() {
        // With the ridge effectively disabled, observations on a steep
        // plane (slope 0.5 — 200× the operator's prior) are fit
        // exactly. This covers the unregularised math; see
        // `default_prior_shrinks_extreme_tilts_toward_constant_z` for
        // the realistic operational behaviour.
        let plane_z = |x: f64, y: f64| 0.5 * x + 0.25 * y + 1.0;
        let touches: Vec<CalibrationTouch> = [(1u16, 0.0, 0.0), (601u16, 60.0, 30.0), (1201u16, 120.0, 0.0)]
            .into_iter()
            .map(|(n, x, y)| {
                let spine = Vec3::new(x, y, plane_z(x, y));
                CalibrationTouch {
                    pin: ua(n),
                    winder_xyz: derive_pin_position_from_spine(spine, ua(n)),
                }
            })
            .collect();
        let loop_ =
            solve_spine_loop_with_config(Layer::U, &touches, weak_prior_config()).unwrap();
        // Pin 301 lerps to (30, 15); plane Z there is 19.75.
        let mid = loop_.point(301).unwrap().xyz;
        assert!((mid.x - 30.0).abs() < 1e-9);
        assert!((mid.y - 15.0).abs() < 1e-9);
        assert!((mid.z - 19.75).abs() < 1e-6);
    }

    #[test]
    fn default_prior_shrinks_extreme_tilts_in_the_fitted_plane() {
        // Three observations of a steep plane (slope 0.5) on a small
        // 120 mm XY footprint. The unregularised LS slope `a*` would
        // be 0.5 (200× the operator's prior). The ridge must shrink
        // the fitted `a` by at least 10× — i.e. the plane component
        // refuses to chase a tilt this far outside the prior. (The
        // observed residuals are then large; the smoothed-residual
        // step carries them around the loop, which is the intended
        // separation of concerns: "what tilt the spine actually has"
        // vs. "what the data is telling us locally".)
        let plane_z = |x: f64, y: f64| 0.5 * x + 0.25 * y + 1.0;
        let observed_xyz: Vec<Vec3> = [(0.0_f64, 0.0_f64), (60.0, 30.0), (120.0, 0.0)]
            .into_iter()
            .map(|(x, y)| Vec3::new(x, y, plane_z(x, y)))
            .collect();
        let (a, b, _c) =
            ridge_fit_plane_z(&observed_xyz, &SpineFitConfig::default()).unwrap();
        assert!(
            a.abs() < 0.05,
            "ridge fit slope a = {a} should be ≪ unregularised 0.5"
        );
        assert!(
            b.abs() < 0.05,
            "ridge fit slope b = {b} should be ≪ unregularised 0.25"
        );
    }

    #[test]
    fn default_prior_recovers_modest_tilt_with_well_spread_observations() {
        // A tilt within the prior envelope: 5 mm of Z change over
        // ~6000 mm of XY span (slope ≈ 0.000833). With four
        // observations spread around all four perimeter quadrants the
        // ridge has plenty of evidence and shouldn't shrink much.
        let slope_x = 0.000_8;
        let plane_z = |x: f64, y: f64| slope_x * x + 100.0;
        let observations: Vec<(u16, f64, f64)> = vec![
            (1, 0.0, 0.0),
            (601, 3000.0, 1500.0),
            (1201, 6000.0, 0.0),
            (1801, 3000.0, -1500.0),
        ];
        let touches: Vec<CalibrationTouch> = observations
            .iter()
            .map(|&(n, x, y)| CalibrationTouch {
                pin: ua(n),
                winder_xyz: derive_pin_position_from_spine(
                    Vec3::new(x, y, plane_z(x, y)),
                    ua(n),
                ),
            })
            .collect();
        let loop_ = solve_spine_loop(Layer::U, &touches).unwrap();
        // At pin 901 (between 601 and 1201), lerp XY ≈ (4500, 750).
        // Plane Z ≈ 103.6. Allow generous tolerance because the ridge
        // still pulls a bit and residuals aren't exactly zero on
        // sparse data.
        let p = loop_.point(901).unwrap().xyz;
        assert!(
            (p.z - plane_z(p.x, p.y)).abs() < 1.0,
            "pin 901 z {} did not approximate plane Z {}",
            p.z,
            plane_z(p.x, p.y)
        );
    }

    #[test]
    fn residual_smoothing_carries_local_bumps_to_neighbours() {
        // One observation has a residual lift above the otherwise-flat
        // spine. Within ~one smoothing length-scale the smoothed
        // residual should still carry a meaningful fraction of that
        // bump; far away it should attenuate to near zero.
        let mut observations: Vec<(u16, f64, f64, f64)> = vec![
            (1, 0.0, 0.0, 0.0),
            (1201, 0.0, 0.0, 0.0),
            (601, 0.0, 0.0, 5.0), // 5 mm lift on the spine
        ];
        // Sort by number so we can drop them through the touch builder.
        observations.sort_by_key(|&(n, _, _, _)| n);
        let touches: Vec<CalibrationTouch> = observations
            .into_iter()
            .map(|(n, x, y, z)| CalibrationTouch {
                pin: ua(n),
                winder_xyz: derive_pin_position_from_spine(Vec3::new(x, y, z), ua(n)),
            })
            .collect();
        let loop_ = solve_spine_loop(Layer::U, &touches).unwrap();
        let near = loop_.point(750).unwrap().xyz.z; // ~150 pins from the bump
        let far = loop_.point(2000).unwrap().xyz.z; // ~800 pins from the bump (forward arc)
        assert!(
            near > 1.0,
            "pin 750 z {} should retain part of the 5 mm bump",
            near
        );
        assert!(
            far.abs() < 1.0,
            "pin 2000 z {} should have decayed back to the plane",
            far
        );
    }

    #[test]
    fn ridge_handles_two_observations_without_falling_back() {
        // Two observations are no longer a degenerate case for the fit
        // — the ridge regularises (a, b) and the system stays
        // solvable. With a symmetric Z = ±5 setup the plane collapses
        // to the mean and the smoothed residual cancels at the
        // forward-arc midpoint.
        let touches = [
            CalibrationTouch {
                pin: ua(1),
                winder_xyz: derive_pin_position_from_spine(Vec3::new(0.0, 0.0, 0.0), ua(1)),
            },
            CalibrationTouch {
                pin: ua(1201),
                winder_xyz: derive_pin_position_from_spine(
                    Vec3::new(100.0, 0.0, 10.0),
                    ua(1201),
                ),
            },
        ];
        let loop_ = solve_spine_loop(Layer::U, &touches).unwrap();
        let mid = loop_.point(601).unwrap().xyz;
        assert!((mid.z - 5.0).abs() < 1e-6);
    }

    #[test]
    fn ridge_handles_colinear_observations_without_singularity() {
        // All observations on Y = 0 — the unregularised normal
        // equations would be singular, but the ridge stays well-posed.
        // The fit should produce sensible Z values along the loop.
        let touches: Vec<CalibrationTouch> = [(1u16, 0.0, 0.0), (601u16, 60.0, 1.0), (1201u16, 120.0, 2.0)]
            .into_iter()
            .map(|(n, x, z)| CalibrationTouch {
                pin: ua(n),
                winder_xyz: derive_pin_position_from_spine(Vec3::new(x, 0.0, z), ua(n)),
            })
            .collect();
        let loop_ = solve_spine_loop(Layer::U, &touches).unwrap();
        // We don't assert exact values — just that every pin got a
        // finite Z and observed pins were preserved exactly.
        for n in 1..=Layer::U.pin_count() {
            assert!(loop_.point(n).unwrap().xyz.z.is_finite());
        }
        assert!((loop_.point(1).unwrap().xyz.z - 0.0).abs() < 1e-9);
        assert!((loop_.point(601).unwrap().xyz.z - 1.0).abs() < 1e-9);
        assert!((loop_.point(1201).unwrap().xyz.z - 2.0).abs() < 1e-9);
    }

    #[test]
    fn round_trip_via_spine_calibration_file() {
        let spine = Vec3::new(7.0, 8.0, 9.0);
        let loop_ = SpineLoop {
            layer: Layer::U,
            points: vec![SpinePoint {
                layer: Layer::U,
                number: 42,
                xyz: spine,
            }],
        };
        let file = SpineCalibrationFile {
            machine_id: "test".to_string(),
            loops: vec![loop_],
        };
        let raw_a = file.raw_pin_position(ua(42)).unwrap();
        let raw_b = file.raw_pin_position(ub(42)).unwrap();
        assert_eq!(raw_a, derive_pin_position_from_spine(spine, ua(42)));
        assert_eq!(raw_b, derive_pin_position_from_spine(spine, ub(42)));
        assert!(file.raw_pin_position(ua(7)).is_none());
    }

    #[test]
    fn serde_roundtrip_spine_calibration_file() {
        let spine = Vec3::new(1.0, 2.0, 3.0);
        let file = SpineCalibrationFile {
            machine_id: "demo".to_string(),
            loops: vec![SpineLoop {
                layer: Layer::U,
                points: vec![SpinePoint {
                    layer: Layer::U,
                    number: 1,
                    xyz: spine,
                }],
            }],
        };
        let json = serde_json::to_string(&file).unwrap();
        let parsed: SpineCalibrationFile = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed, file);
    }
}
