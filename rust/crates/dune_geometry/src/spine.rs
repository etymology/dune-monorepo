//! Spine calibration: the APA-wide nearly-flat plane at Z≈207 mm shared
//! by all layers.
//!
//! Spec source of truth: `specs/spine-calibration.allium`.
//!
//! - [`SpinePlane`] — APA-wide `Z = a·X + b·Y + c`; no layer field.
//! - [`SpineCalibrationFile`] — holds a single optional `SpinePlane`.
//!   Written by the machine calibration solver; absent before first solve.
//! - [`SpineCalibrationFile::z_at`] — primary API: `(layer, side, x, y)`
//!   → pin Z. Layer determines the board-width offset; the plane itself
//!   is layer-independent.
//! - [`derive_pin_position_from_spine`] — `(spine_xyz, pin)` → raw XYZ.
//! - [`observe_spine_point_from_touch`] — inverse: recorded winder XYZ →
//!   spine Z observation.
//! - [`solve_spine_plane`] — ridge-regularised plane fit from
//!   [`CalibrationTouch`]es spanning any layers; defaults to `(0,0,207)`
//!   on degenerate input.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::calibration::Vec3;
use crate::pins::{Layer, Pin, Side};

/// APA-wide spine plane: `Z = a·X + b·Y + c` in raw camera-space.
/// Shared by all layers. Default is `a = b = 0, c = 207`.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SpinePlane {
    pub a: f64,
    pub b: f64,
    pub c: f64,
}

impl SpinePlane {
    pub fn default() -> Self {
        SpinePlane { a: 0.0, b: 0.0, c: 207.0 }
    }

    pub fn z_at(&self, x: f64, y: f64) -> f64 {
        self.a * x + self.b * y + self.c
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

/// APA-wide spine calibration file. Holds a single [`SpinePlane`] shared
/// by all layers; absent until the first machine calibration solve.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpineCalibrationFile {
    pub machine_id: String,
    pub plane: Option<SpinePlane>,
}

impl SpineCalibrationFile {
    pub fn new(machine_id: String) -> Self {
        Self { machine_id, plane: None }
    }

    /// Z coordinate of a `(layer, side)` pin at winder position `(x, y)`.
    /// Uses the calibrated plane when present; falls back to `Z = 207`.
    pub fn z_at(&self, layer: Layer, side: Side, x: f64, y: f64) -> f64 {
        let plane = self.plane.unwrap_or_else(SpinePlane::default);
        let spine_z = plane.z_at(x, y);
        let half_w = layer.half_board_width_z_mm();
        let sign = match side {
            Side::A => -1.0,
            Side::B => 1.0,
        };
        spine_z + sign * half_w
    }
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum SpineError {
    #[error("spine fit requires at least one calibration touch")]
    NoTouches,
}

/// Derive the raw camera-space XYZ of a pin from the spine XYZ at the
/// same position. Mirrors the `PinZFromSpine` rule in
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
/// spine XYZ at that winder (X, Y) position.
pub fn observe_spine_point_from_touch(touch: CalibrationTouch) -> Vec3 {
    let dz = touch.pin.spine_to_face_sign() * touch.pin.half_board_width_z_mm();
    Vec3::new(touch.winder_xyz.x, touch.winder_xyz.y, touch.winder_xyz.z - dz)
}

/// Fit the APA-wide spine plane `Z = a·X + b·Y + c` from calibration
/// touches spanning any combination of layers and sides. Falls back to
/// `(a=0, b=0, c=207)` on degenerate input.
///
/// Steps, mirroring `SolveSpinePlaneFromCalibrationTouches` in
/// `specs/spine-calibration.allium`:
///
/// 1. Back-project each touch to a spine observation via
///    [`observe_spine_point_from_touch`] (uses `touch.pin` for board-width).
/// 2. Multiple touches on the same `(layer, pin_number)` collapse to one
///    observation by component-wise mean.
/// 3. Fit the plane with [`ridge_fit_plane_z`]. On degenerate input,
///    fall back to `(0, 0, 207)`.
pub fn solve_spine_plane(touches: &[CalibrationTouch]) -> Result<SpinePlane, SpineError> {
    if touches.is_empty() {
        return Err(SpineError::NoTouches);
    }

    // Key by (layer, pin_number) so touches from different layers are distinct.
    let mut grouped: BTreeMap<(Layer, u16), Vec<Vec3>> = BTreeMap::new();
    for touch in touches {
        let number = touch.pin.number;
        let pin_count = touch.pin.layer.pin_count();
        if number == 0 || number > pin_count {
            continue;
        }
        let observed = observe_spine_point_from_touch(*touch);
        grouped.entry((touch.pin.layer, number)).or_default().push(observed);
    }

    let observed_xyz: Vec<Vec3> = grouped
        .into_values()
        .map(|pts| average_xyz(&pts))
        .collect();

    let (a, b, c) = ridge_fit_plane_z(&observed_xyz).unwrap_or((0.0, 0.0, 207.0));

    Ok(SpinePlane { a, b, c })
}

fn average_xyz(points: &[Vec3]) -> Vec3 {
    let n = points.len() as f64;
    let sum = points.iter().fold(Vec3::ZERO, |acc, p| {
        Vec3::new(acc.x + p.x, acc.y + p.y, acc.z + p.z)
    });
    Vec3::new(sum.x / n, sum.y / n, sum.z / n)
}

/// Ridge-regularised least-squares fit of `Z = a·X + b·Y + c` to a set
/// of 3D points. The tilt parameters `(a, b)` carry a Gaussian prior
/// with std `TILT_PRIOR_SLOPE`, encoded as a Tikhonov penalty
/// `λ·(a² + b²)` with `λ = (DATA_NOISE_MM / TILT_PRIOR_SLOPE)²`.
///
/// Returns `None` for empty input or when the regularised normal
/// equations are numerically singular.
fn ridge_fit_plane_z(points: &[Vec3]) -> Option<(f64, f64, f64)> {
    const TILT_PRIOR_SLOPE: f64 = 15.0 / 6000.0;
    const DATA_NOISE_MM: f64 = 1.0;

    if points.is_empty() {
        return None;
    }
    let lambda = (DATA_NOISE_MM / TILT_PRIOR_SLOPE).powi(2);
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
        let result = solve_spine_plane(&[]);
        assert!(matches!(result, Err(SpineError::NoTouches)));
    }

    #[test]
    fn solve_flat_observations_recover_mean_z() {
        let touches: Vec<CalibrationTouch> = [(1u16, 0.0, 0.0), (500, 100.0, 50.0), (1200, 200.0, 0.0)]
            .into_iter()
            .map(|(n, x, y)| {
                let spine = Vec3::new(x, y, 207.0);
                CalibrationTouch { pin: ua(n), winder_xyz: derive_pin_position_from_spine(spine, ua(n)) }
            })
            .collect();
        let plane = solve_spine_plane(&touches).unwrap();
        assert!((plane.c - 207.0).abs() < 1.0);
        assert!(plane.a.abs() < 0.01);
        assert!(plane.b.abs() < 0.01);
    }

    #[test]
    fn solve_accepts_mixed_layer_touches() {
        // Touches from U and V layers should both contribute to the same plane.
        let ua_touch = CalibrationTouch {
            pin: ua(1),
            winder_xyz: derive_pin_position_from_spine(Vec3::new(0.0, 0.0, 207.0), ua(1)),
        };
        let vb_touch = CalibrationTouch {
            pin: Pin::new(Layer::V, Side::B, 1).unwrap(),
            winder_xyz: {
                let vb = Pin::new(Layer::V, Side::B, 1).unwrap();
                derive_pin_position_from_spine(Vec3::new(100.0, 0.0, 207.0), vb)
            },
        };
        let plane = solve_spine_plane(&[ua_touch, vb_touch]).unwrap();
        assert!((plane.c - 207.0).abs() < 1.0);
    }

    #[test]
    fn solve_tilted_observations_recover_tilt() {
        let slope = 5.0 / 6000.0;
        let touches: Vec<CalibrationTouch> = [
            (1u16, 0.0, 0.0),
            (601, 3000.0, 0.0),
            (1201, 6000.0, 0.0),
            (1801, 3000.0, 1500.0),
        ]
        .into_iter()
        .map(|(n, x, y)| {
            let spine_z = slope * x + 207.0;
            let spine = Vec3::new(x, y, spine_z);
            CalibrationTouch { pin: ua(n), winder_xyz: derive_pin_position_from_spine(spine, ua(n)) }
        })
        .collect();
        let plane = solve_spine_plane(&touches).unwrap();
        assert!(
            (plane.a - slope).abs() < slope * 0.3,
            "fitted a = {} vs true slope = {}",
            plane.a,
            slope
        );
    }

    #[test]
    fn z_at_applies_side_displacement() {
        let file = SpineCalibrationFile {
            machine_id: "test".to_string(),
            plane: Some(SpinePlane { a: 0.0, b: 0.0, c: 207.0 }),
        };
        let z_a = file.z_at(Layer::U, Side::A, 0.0, 0.0);
        let z_b = file.z_at(Layer::U, Side::B, 0.0, 0.0);
        assert_eq!(z_a, 207.0 - 65.0);
        assert_eq!(z_b, 207.0 + 65.0);
    }

    #[test]
    fn z_at_falls_back_to_default_when_absent() {
        let file = SpineCalibrationFile::new("test".to_string());
        let z_a = file.z_at(Layer::U, Side::A, 0.0, 0.0);
        assert_eq!(z_a, 207.0 - 65.0);
    }

    #[test]
    fn z_at_same_plane_for_all_layers() {
        let file = SpineCalibrationFile {
            machine_id: "test".to_string(),
            plane: Some(SpinePlane { a: 0.0, b: 0.0, c: 207.0 }),
        };
        // Both U and V use the same spine Z; only their board widths differ.
        let u_mid = (file.z_at(Layer::U, Side::A, 0.0, 0.0) + file.z_at(Layer::U, Side::B, 0.0, 0.0)) / 2.0;
        let v_mid = (file.z_at(Layer::V, Side::A, 0.0, 0.0) + file.z_at(Layer::V, Side::B, 0.0, 0.0)) / 2.0;
        assert_eq!(u_mid, 207.0);
        assert_eq!(v_mid, 207.0);
    }

    #[test]
    fn serde_roundtrip_spine_calibration_file() {
        let file = SpineCalibrationFile {
            machine_id: "demo".to_string(),
            plane: Some(SpinePlane { a: 0.001, b: -0.0005, c: 207.3 }),
        };
        let json = serde_json::to_string(&file).unwrap();
        let parsed: SpineCalibrationFile = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed, file);
    }
}
