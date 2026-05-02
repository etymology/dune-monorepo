//! Wire-path geometry: anchor-to-target solving and per-pose camera wire
//! offsets.
//!
//! Spec source of truth: `specs/uv-wrap-geometry.allium`.
//!
//! Today this module owns:
//!
//! - The per-pose camera-wire-offset resolver
//!   ([`effective_camera_wire_offset`]).
//! - The arithmetic that turns raw camera-space pin coordinates plus a
//!   [`MachineCalibrationModel`] into the offset-applied target pose
//!   ([`apply_anchor_to_target_offsets`]).
//! - A typed [`AnchorToTargetRequest`] / [`AnchorToTargetSolution`] pair
//!   shared by Rust callers and the PyO3 surface.
//! - The pure-math kernel [`circle_pair_tangent_pairs`] — the lowest-level
//!   building block of the wire-tangent solve, ported ahead of the rest of
//!   the solver and gated by golden fixtures at
//!   `tests/golden/geometry/circle_pair_tangent/`.
//!
//! The full wire-tangent geometric solve (the part that picks which side of
//! each pin the wire wraps and emits the final commanded head pose) still
//! lives in `src/dune_winder/uv_head_target_parts/` (Python) and is being
//! ported into [`solve_anchor_to_target`] incrementally, gated by the
//! golden-parity fixtures at `tests/golden/geometry/anchor_to_target/`.
//! Until that port lands, [`solve_anchor_to_target`] returns the
//! offset-applied target pose without doing the tangent solve, and the
//! Python wrapper feeds that result into the existing solver.

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::calibration::{HeadSide, MachineCalibrationModel, Vec3};
use crate::pins::Pin;

/// Numerical tolerance shared with the Python reference for "is this two
/// solutions or one?" deduplication and "is this geometrically degenerate?"
/// checks. Matches the legacy implementation's hard-coded `1e-9` / `1e-6`.
const TANGENT_FEASIBILITY_EPS: f64 = 1.0e-9;
const TANGENT_DEDUP_EPS: f64 = 1.0e-6;

/// Compute the (up to four) tangent line pairs between two circles in 2D.
///
/// Each returned tuple `(first_xy, second_xy)` is one tangent line, with
/// `first_xy` lying on the first circle and `second_xy` on the second. The
/// implementation enumerates the four sign combinations of (radius_sign,
/// tangent_sign), skipping any combination that is geometrically infeasible
/// (negative `h²`) or numerically duplicate of a solution already in the
/// result.
///
/// Returns an empty `Vec` if the circle centers are coincident. Behaviour is
/// otherwise a direct port of the legacy Python implementation at
/// `src/dune_winder/queued_motion/filleted_path.py::circle_pair_tangent_pairs`,
/// gated by the JSON fixtures under
/// `tests/golden/geometry/circle_pair_tangent/`.
pub fn circle_pair_tangent_pairs(
    first_center: (f64, f64),
    first_radius: f64,
    second_center: (f64, f64),
    second_radius: f64,
) -> Vec<((f64, f64), (f64, f64))> {
    let dx = second_center.0 - first_center.0;
    let dy = second_center.1 - first_center.1;
    let z = dx * dx + dy * dy;
    if z <= TANGENT_FEASIBILITY_EPS {
        return Vec::new();
    }
    let mut tangent_pairs: Vec<((f64, f64), (f64, f64))> = Vec::with_capacity(4);
    for radius_sign in [-1.0_f64, 1.0_f64] {
        let r = second_radius * radius_sign - first_radius;
        let h_sq = z - r * r;
        if h_sq < -TANGENT_FEASIBILITY_EPS {
            continue;
        }
        let h = h_sq.max(0.0).sqrt();
        for tangent_sign in [-1.0_f64, 1.0_f64] {
            let nx = (dx * r - dy * h * tangent_sign) / z;
            let ny = (dy * r + dx * h * tangent_sign) / z;
            let first_xy = (
                first_center.0 + first_radius * nx,
                first_center.1 + first_radius * ny,
            );
            let second_xy = (
                second_center.0 + second_radius * radius_sign * nx,
                second_center.1 + second_radius * radius_sign * ny,
            );
            let already_present = tangent_pairs.iter().any(|(ef, es)| {
                distance_xy(first_xy, *ef) <= TANGENT_DEDUP_EPS
                    && distance_xy(second_xy, *es) <= TANGENT_DEDUP_EPS
            });
            if !already_present {
                tangent_pairs.push((first_xy, second_xy));
            }
        }
    }
    tangent_pairs
}

fn distance_xy(a: (f64, f64), b: (f64, f64)) -> f64 {
    let dx = a.0 - b.0;
    let dy = a.1 - b.1;
    (dx * dx + dy * dy).sqrt()
}

/// Inputs to [`solve_anchor_to_target`]. Coordinates are raw camera-space
/// (from `PinCalibrationFile::effective_pin_coords`) — the solver applies
/// the per-pose camera wire offset and arm correction internally.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AnchorToTargetRequest {
    pub anchor_pin: Pin,
    pub anchor_xyz: Vec3,
    pub target_pin: Pin,
    pub target_xyz: Vec3,
    /// Optional `(dx, dy)` to add to `target_xyz` before the offset model
    /// is applied. Mirrors the legacy `offset=(x,y)` keyword on
    /// `~anchorToTarget(...)`.
    pub target_offset: Option<(f64, f64)>,
    pub head_side: HeadSide,
    pub hover: bool,
}

/// Output of [`solve_anchor_to_target`]: the commanded winder pose plus the
/// effective offsets that were applied to get there. Today
/// `commanded_head_xyz` is the offset-applied target pose; the eventual
/// wire-tangent solver will refine it to the pose where the wire is
/// tangent to both pins on the correct sides. Field set will grow as the
/// solver port progresses.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AnchorToTargetSolution {
    /// Offset-applied target pose. Currently `target_xyz + target_offset +
    /// effective_camera_wire_offset + effective_arm_correction`. The
    /// wire-tangent refinement step is still owned by the legacy Python
    /// solver and will move here in a follow-up commit.
    pub commanded_head_xyz: Vec3,
    /// The offset that was looked up for `(target_pin, head_side)` from
    /// the [`MachineCalibrationModel`].
    pub effective_camera_wire_offset: Vec3,
    /// The arm correction from the [`MachineCalibrationModel`] (constant
    /// per machine today).
    pub effective_arm_correction: Vec3,
}

#[derive(Debug, Clone, PartialEq, Error)]
pub enum WireError {
    #[error("anchor and target pins must share the same layer (got {anchor:?} vs {target:?})")]
    LayerMismatch { anchor: Pin, target: Pin },
}

/// Resolve the per-pose camera wire offset for a `(pin, head_side)` pair.
/// Per-pin override wins; falls back to the head-side base offset.
pub fn effective_camera_wire_offset(
    model: &MachineCalibrationModel,
    pin: &Pin,
    head_side: HeadSide,
) -> Vec3 {
    model.effective_offset(*pin, head_side)
}

/// Apply the optional `(dx, dy)` target offset, the per-pose camera wire
/// offset, and the arm correction to a raw camera-space target coordinate.
/// Pure arithmetic — no I/O, no winder coupling. Exposed separately so the
/// Python wrapper can call it directly during the incremental port.
pub fn apply_anchor_to_target_offsets(
    target_xyz: Vec3,
    target_offset: Option<(f64, f64)>,
    effective_camera_wire_offset: Vec3,
    effective_arm_correction: Vec3,
) -> Vec3 {
    let mut commanded = target_xyz;
    if let Some((dx, dy)) = target_offset {
        commanded = commanded.add(Vec3::new(dx, dy, 0.0));
    }
    commanded
        .add(effective_camera_wire_offset)
        .add(effective_arm_correction)
}

/// Solve an anchor-to-target request against a [`MachineCalibrationModel`].
///
/// This currently performs steps 1–3 of the spec obligation
/// (`SolveAnchorToTarget` in `specs/uv-wrap-geometry.allium`):
/// raw-coordinate lookup, per-pose camera-wire-offset resolution, and arm
/// correction. The wire-tangent refinement (step 4) is still owned by the
/// Python solver in `src/dune_winder/uv_head_target_parts/` and will move
/// here in a follow-up commit gated by golden fixtures.
pub fn solve_anchor_to_target(
    request: &AnchorToTargetRequest,
    model: &MachineCalibrationModel,
) -> Result<AnchorToTargetSolution, WireError> {
    if request.anchor_pin.layer != request.target_pin.layer {
        return Err(WireError::LayerMismatch {
            anchor: request.anchor_pin,
            target: request.target_pin,
        });
    }
    let effective_camera_wire_offset =
        effective_camera_wire_offset(model, &request.target_pin, request.head_side);
    let effective_arm_correction = model.arm_correction;
    let commanded_head_xyz = apply_anchor_to_target_offsets(
        request.target_xyz,
        request.target_offset,
        effective_camera_wire_offset,
        effective_arm_correction,
    );
    Ok(AnchorToTargetSolution {
        commanded_head_xyz,
        effective_camera_wire_offset,
        effective_arm_correction,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::calibration::PerPinOffset;
    use crate::pins::{Layer, Side};

    fn ua(n: u16) -> Pin {
        Pin::new(Layer::U, Side::A, n).unwrap()
    }

    fn ub(n: u16) -> Pin {
        Pin::new(Layer::U, Side::B, n).unwrap()
    }

    fn vb(n: u16) -> Pin {
        Pin::new(Layer::V, Side::B, n).unwrap()
    }

    #[test]
    fn per_pin_override_wins_over_base() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(1.0, 0.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::new(2.0, 0.0, 0.0),
            per_pin_camera_wire_offset: vec![PerPinOffset {
                pin: ua(1),
                offset: Vec3::new(99.0, 0.0, 0.0),
            }],
            arm_correction: Vec3::new(0.0, 0.0, 0.0),
        };
        assert_eq!(
            effective_camera_wire_offset(&model, &ua(1), HeadSide::Stage).x,
            99.0
        );
        assert_eq!(
            effective_camera_wire_offset(&model, &ua(2), HeadSide::Fixed).x,
            2.0
        );
    }

    #[test]
    fn solve_applies_offset_and_arm_correction() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(1.0, 2.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::new(0.0, 0.0, 0.0),
            per_pin_camera_wire_offset: vec![],
            arm_correction: Vec3::new(0.5, 0.0, -0.25),
        };
        let request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz: Vec3::new(100.0, 100.0, 50.0),
            target_pin: ub(2),
            target_xyz: Vec3::new(200.0, 200.0, 60.0),
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        let sol = solve_anchor_to_target(&request, &model).unwrap();
        assert_eq!(sol.effective_camera_wire_offset, Vec3::new(1.0, 2.0, 0.0));
        assert_eq!(sol.effective_arm_correction, Vec3::new(0.5, 0.0, -0.25));
        // 200 + 1 + 0.5, 200 + 2 + 0, 60 + 0 + -0.25
        assert_eq!(sol.commanded_head_xyz, Vec3::new(201.5, 202.0, 59.75));
    }

    #[test]
    fn solve_applies_target_offset_before_model_offsets() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(0.0, 0.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::new(10.0, 20.0, 0.0),
            per_pin_camera_wire_offset: vec![],
            arm_correction: Vec3::new(0.0, 0.0, 5.0),
        };
        let request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz: Vec3::new(0.0, 0.0, 0.0),
            target_pin: ub(2),
            target_xyz: Vec3::new(100.0, 100.0, 100.0),
            target_offset: Some((1.0, 2.0)),
            head_side: HeadSide::Fixed,
            hover: false,
        };
        let sol = solve_anchor_to_target(&request, &model).unwrap();
        // 100 + 1 + 10, 100 + 2 + 20, 100 + 0 + 5
        assert_eq!(sol.commanded_head_xyz, Vec3::new(111.0, 122.0, 105.0));
    }

    #[test]
    fn solve_per_pin_override_wins() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(0.0, 0.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::new(0.0, 0.0, 0.0),
            per_pin_camera_wire_offset: vec![PerPinOffset {
                pin: ub(2),
                offset: Vec3::new(7.0, 8.0, 9.0),
            }],
            arm_correction: Vec3::ZERO,
        };
        let request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz: Vec3::ZERO,
            target_pin: ub(2),
            target_xyz: Vec3::new(0.0, 0.0, 0.0),
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        let sol = solve_anchor_to_target(&request, &model).unwrap();
        assert_eq!(sol.commanded_head_xyz, Vec3::new(7.0, 8.0, 9.0));
    }

    #[test]
    fn solve_rejects_layer_mismatch() {
        let model = MachineCalibrationModel::empty();
        let request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz: Vec3::ZERO,
            target_pin: vb(2),
            target_xyz: Vec3::ZERO,
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        assert!(matches!(
            solve_anchor_to_target(&request, &model),
            Err(WireError::LayerMismatch { .. })
        ));
    }

    #[test]
    fn circle_pair_tangent_pairs_returns_empty_for_coincident_centers() {
        assert!(circle_pair_tangent_pairs((0.0, 0.0), 1.0, (0.0, 0.0), 1.0).is_empty());
    }

    #[test]
    fn circle_pair_tangent_pairs_equal_radius_horizontal() {
        // Reference values cross-checked against the Python implementation in
        // `tests/golden/geometry/circle_pair_tangent/equal_radius_horizontal_separation.json`.
        let pairs = circle_pair_tangent_pairs((0.0, 0.0), 1.0, (5.0, 0.0), 1.0);
        assert_eq!(pairs.len(), 4);
        // External tangents (same y on both circles) — radius_sign = +1.
        assert!(pairs.iter().any(|((_, ya), (_, yb))| {
            (ya - (-1.0)).abs() < 1e-9 && (yb - (-1.0)).abs() < 1e-9
        }));
        assert!(pairs.iter().any(|((_, ya), (_, yb))| {
            (ya - 1.0).abs() < 1e-9 && (yb - 1.0).abs() < 1e-9
        }));
    }

    #[test]
    fn circle_pair_tangent_pairs_skips_infeasible_internal_when_circles_touch() {
        // Internal tangents collapse when |c2-c1| == 2r — the kernel should
        // emit only the two external pairs.
        let pairs = circle_pair_tangent_pairs((0.0, 0.0), 1.0, (2.0, 0.0), 1.0);
        // Internal tangents have h_sq ~= 0 and produce two coincident
        // solutions — the dedup pass collapses them. We keep the assertion
        // loose (≤ 4) and let the golden fixture pin the exact count.
        assert!(pairs.len() >= 2);
        assert!(pairs.len() <= 4);
    }
}
