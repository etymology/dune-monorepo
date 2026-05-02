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
//!   points from a list of [`CalibrationTouch`]es. The full solver is
//!   pending; this commit lands the foundational scaffold:
//!   observation collapsing, simple averaging across multiple touches
//!   on the same number, and a closed-loop interpolation pass for any
//!   missing pin numbers between observed ones. A higher-fidelity
//!   smoothing fit (B-spline, etc.) lands in a follow-up gated by
//!   golden fixtures under `tests/golden/geometry/spine_loop/`.

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
/// sign   = +1 when pin.side == A, -1 when pin.side == B
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
    let t = step as f64 / total as f64;
    Vec3::new(
        a.x + (b.x - a.x) * t,
        a.y + (b.y - a.y) * t,
        a.z + (b.z - a.z) * t,
    )
}

/// Fit a closed continuous spine loop to a set of calibration touches.
///
/// Today's implementation is the foundational scaffold described in
/// `specs/spine-calibration.allium`:
///
/// 1. Each touch maps to one observed spine point at `touch.pin.number`
///    via [`observe_spine_point_from_touch`].
/// 2. Multiple touches on the same number collapse to one observation
///    by component-wise mean.
/// 3. Pin numbers without an observation are filled by linear
///    interpolation between the two nearest observed numbers along the
///    closed loop (the search wraps around `pin_count`).
///
/// The output covers every pin number `1..=pin_count(layer)`. Layers
/// not yet representable in `Layer` (X, G) panic via the exhaustive
/// match in `Layer::pin_count` — they will gain coverage when those
/// layer variants are added.
///
/// A higher-fidelity smoothing fit (closed B-spline, total-variation
/// regularised, etc.) replaces the linear-interpolation fallback in a
/// follow-up commit gated by golden fixtures.
pub fn solve_spine_loop(
    layer: Layer,
    touches: &[CalibrationTouch],
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
            // Pin::new validation already excludes these, but the layer
            // pin_count check is a cheap belt-and-braces.
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
        let xyz = lerp(prev_xyz, next_xyz, step, span);
        points.push(SpinePoint {
            layer,
            number,
            xyz,
        });
    }

    Ok(SpineLoop { layer, points })
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
    fn derive_pin_position_a_side_is_plus_half_width_in_z() {
        let spine = Vec3::new(10.0, 20.0, 100.0);
        let derived = derive_pin_position_from_spine(spine, ua(1));
        assert_eq!(derived, Vec3::new(10.0, 20.0, 100.0 + 65.0));
    }

    #[test]
    fn derive_pin_position_b_side_is_minus_half_width_in_z() {
        let spine = Vec3::new(10.0, 20.0, 100.0);
        let derived = derive_pin_position_from_spine(spine, ub(1));
        assert_eq!(derived, Vec3::new(10.0, 20.0, 100.0 - 65.0));
    }

    #[test]
    fn derive_pin_position_is_symmetric_about_spine() {
        let spine = Vec3::new(0.0, 0.0, 50.0);
        let a = derive_pin_position_from_spine(spine, ua(123));
        let b = derive_pin_position_from_spine(spine, ub(123));
        assert_eq!(a.x, b.x);
        assert_eq!(a.y, b.y);
        assert_eq!((a.z + b.z) / 2.0, spine.z);
        assert_eq!(a.z - b.z, Layer::U.board_width_z_mm());
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
