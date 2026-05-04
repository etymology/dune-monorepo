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
//! - [`tangent_for_pin_pair`] — the analytic single-tangent solver that
//!   takes two [`Pin`]s and uses each pin's `tangent_sides` rule to
//!   compute the unique wire-side tangent in closed form. Gated by
//!   fixtures at `tests/golden/geometry/tangent_for_pin_pair/`.
//! - [`line_equation_from_tangent_points`] — slope/intercept of the
//!   tangent line, with vertical lines flagged.
//! - [`compute_arm_corrected_outbound`] — solves the head pose so the
//!   active roller is tangent to the wire-tangent line and the head
//!   center sits within the transfer rectangle. Gated by fixtures at
//!   `tests/golden/geometry/compute_arm_corrected_outbound/`.
//! - [`actual_wire_point_from_machine_target`] — the roller-tilt math
//!   that turns a commanded head pose into the actual wire-end XY. Gated
//!   by fixtures at `tests/golden/geometry/actual_wire_point/`.
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

use crate::calibration::{HeadSide, MachineCalibrationModel, PinCoordinate, Vec3};
use crate::pins::{Layer, Pin, Side};
use crate::spine::SpineCalibrationFile;

/// Numerical tolerance shared with the Python reference for "is this two
/// solutions or one?" deduplication and "is this geometrically degenerate?"
/// checks. Matches the legacy implementation's hard-coded `1e-9` / `1e-6`.
const TANGENT_FEASIBILITY_EPS: f64 = 1.0e-9;

/// Interpolate a full set of X/G layer slot coordinates from four measured
/// corner points.
///
/// Corners are measured on the B side at the first and last slots of the head
/// and foot edges. The function yields the B-side coordinates for all slots
/// via linear interpolation, and derives the A-side coordinates by
/// displacing one board-width in +Z.
///
/// Returns a list of [`PinCoordinate`]s for the layer.
pub fn solve_xg_slots(
    layer: Layer,
    bh1: Vec3,
    bh_max: Vec3,
    bf1: Vec3,
    bf_max: Vec3,
) -> Vec<PinCoordinate> {
    let max = if layer == Layer::X { 480 } else { 481 };
    let mut out = Vec::with_capacity((max * 4) as usize);

    for n in 1..=max {
        let t = (n - 1) as f64 / (max - 1) as f64;
        let bh_n_b = Vec3::lerp(bh1, bh_max, t);
        let bf_n_b = Vec3::lerp(bf1, bf_max, t);

        // B side
        out.push(PinCoordinate {
            pin: Pin::new(layer, Side::B, n).unwrap(),
            xyz: bh_n_b,
        });
        out.push(PinCoordinate {
            pin: Pin::new(layer, Side::B, n + max).unwrap(),
            xyz: bf_n_b,
        });

        // A side: measurements are B side; A side is +board_width in Z.
        let dz = Vec3::new(0.0, 0.0, layer.board_width_z_mm());
        out.push(PinCoordinate {
            pin: Pin::new(layer, Side::A, n).unwrap(),
            xyz: bh_n_b.add(dz),
        });
        out.push(PinCoordinate {
            pin: Pin::new(layer, Side::A, n + max).unwrap(),
            xyz: bf_n_b.add(dz),
        });
    }
    out
}

/// Numerical tolerance for axis-side checks and clip-line degeneracy. Matches
/// the legacy Python `_AXIS_EPSILON` (1e-9).
const AXIS_EPS: f64 = 1.0e-9;
/// Tolerance used to dedupe coincident clip-line candidates. Matches the
/// legacy Python `math.isclose(..., abs_tol=1e-8)`.
const CLIP_DEDUP_EPS: f64 = 1.0e-8;

/// Axis-aligned transfer-zone rectangle. `top` >= `bottom`, `right` >=
/// `left`. Mirrors the legacy `RectBounds` dataclass.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct RectBounds {
    pub left: f64,
    pub top: f64,
    pub right: f64,
    pub bottom: f64,
}

fn try_add_clip_candidate(
    candidates: &mut Vec<(f64, (f64, f64))>,
    bounds: &RectBounds,
    parameter: f64,
    x: f64,
    y: f64,
) {
    if x < bounds.left - AXIS_EPS || x > bounds.right + AXIS_EPS {
        return;
    }
    if y < bounds.bottom - AXIS_EPS || y > bounds.top + AXIS_EPS {
        return;
    }
    let candidate = (x, y);
    for (existing_param, existing_point) in candidates.iter() {
        if (existing_param - parameter).abs() <= CLIP_DEDUP_EPS {
            return;
        }
        if (existing_point.0 - candidate.0).abs() <= CLIP_DEDUP_EPS
            && (existing_point.1 - candidate.1).abs() <= CLIP_DEDUP_EPS
        {
            return;
        }
    }
    candidates.push((parameter, candidate));
}

fn clip_infinite_line_to_bounds(
    line_point: (f64, f64),
    line_direction: (f64, f64),
    bounds: RectBounds,
) -> Option<((f64, f64), (f64, f64))> {
    let (px, py) = line_point;
    let (dx, dy) = line_direction;
    if dx.abs() <= AXIS_EPS && dy.abs() <= AXIS_EPS {
        return None;
    }
    let mut candidates: Vec<(f64, (f64, f64))> = Vec::new();
    if dx.abs() > AXIS_EPS {
        for x in [bounds.left, bounds.right] {
            let parameter = (x - px) / dx;
            try_add_clip_candidate(&mut candidates, &bounds, parameter, x, py + parameter * dy);
        }
    }
    if dy.abs() > AXIS_EPS {
        for y in [bounds.bottom, bounds.top] {
            let parameter = (y - py) / dy;
            try_add_clip_candidate(&mut candidates, &bounds, parameter, px + parameter * dx, y);
        }
    }
    if candidates.len() < 2 {
        return None;
    }
    candidates.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));
    Some((candidates[0].1, candidates[candidates.len() - 1].1))
}

fn choose_outbound_intercept(
    tangent_a: (f64, f64),
    tangent_b: (f64, f64),
    clipped_start: (f64, f64),
    clipped_end: (f64, f64),
) -> (f64, f64) {
    let dx = tangent_b.0 - tangent_a.0;
    let dy = tangent_b.1 - tangent_a.1;
    let start_proj = (clipped_start.0 - tangent_a.0) * dx + (clipped_start.1 - tangent_a.1) * dy;
    let end_proj = (clipped_end.0 - tangent_a.0) * dx + (clipped_end.1 - tangent_a.1) * dy;
    if end_proj >= start_proj {
        clipped_end
    } else {
        clipped_start
    }
}

/// Two-dimensional line written as `y = slope * x + intercept`, or
/// `x = intercept` for `is_vertical = true` (in which case `slope` is
/// stored as `f64::INFINITY` to mirror the legacy Python dataclass).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct LineEquation {
    pub slope: f64,
    pub intercept: f64,
    pub is_vertical: bool,
}

/// Compute the line equation that passes through the two tangent points.
/// Mirrors the legacy `_line_equation_from_tangent_points`. When the
/// segment is (numerically) vertical the result has `is_vertical = true`
/// and `intercept = tangent_a.x`.
pub fn line_equation_from_tangent_points(
    tangent_a: (f64, f64),
    tangent_b: (f64, f64),
) -> LineEquation {
    let dx = tangent_b.0 - tangent_a.0;
    let dy = tangent_b.1 - tangent_a.1;
    if dx.abs() <= AXIS_EPS {
        return LineEquation {
            slope: f64::INFINITY,
            intercept: tangent_a.0,
            is_vertical: true,
        };
    }
    let slope = dy / dx;
    let intercept = tangent_a.1 - slope * tangent_a.0;
    LineEquation {
        slope,
        intercept,
        is_vertical: false,
    }
}

/// Compute the unique wire-side tangent line between two pins, derived
/// directly from each pin's `tangent_sides` rule.
///
/// Each U/V pin's wrap-side normal is determined by `(layer, side, n)` alone,
/// so the tangent line is given in closed form once both pin centers and radii
/// are known.
///
/// Returns `(tangent_a, tangent_b)` — the tangent point on the anchor circle
/// and on the target circle. Errors when:
///
/// - either pin is on layer X or G (slots, no wrap normal),
/// - the two pins are on different layers,
/// - the pin centers are coincident,
/// - the requested wrap sides are geometrically incompatible — only possible
///   if the two pins are on opposite sides of the board, since the same-face
///   `tangent_sides` rule already guarantees axial agreement,
/// - or the circles are too close to admit a tangent under the chosen
///   radius_sign (`h² < -eps`).
pub fn tangent_for_pin_pair(
    anchor: Pin,
    anchor_xy: (f64, f64),
    anchor_radius: f64,
    target: Pin,
    target_xy: (f64, f64),
    target_radius: f64,
) -> Result<((f64, f64), (f64, f64)), WireError> {
    if anchor.layer != target.layer {
        return Err(WireError::LayerMismatch { anchor, target });
    }
    let (sa_x, sa_y) = anchor.tangent_normal_sign();
    if sa_x == 0 || sa_y == 0 {
        return Err(WireError::TangentSidesUndefinedForLayer {
            layer: anchor.layer,
        });
    }
    let (sb_x, sb_y) = target.tangent_normal_sign();
    if sb_x == 0 || sb_y == 0 {
        return Err(WireError::TangentSidesUndefinedForLayer {
            layer: target.layer,
        });
    }
    let rs_x = i32::from(sa_x) * i32::from(sb_x);
    let rs_y = i32::from(sa_y) * i32::from(sb_y);
    if rs_x != rs_y {
        return Err(WireError::IncompatibleWrapSides {
            anchor_sides: (sa_x, sa_y),
            target_sides: (sb_x, sb_y),
        });
    }
    let radius_sign = rs_x as f64;

    let dx = target_xy.0 - anchor_xy.0;
    let dy = target_xy.1 - anchor_xy.1;
    let z = dx * dx + dy * dy;
    if z <= TANGENT_FEASIBILITY_EPS {
        return Err(WireError::CoincidentPinCenters);
    }
    let r = target_radius * radius_sign - anchor_radius;
    let h_sq = z - r * r;
    if h_sq < -TANGENT_FEASIBILITY_EPS {
        return Err(WireError::TangentInfeasible);
    }
    let h = h_sq.max(0.0).sqrt();

    // With radius_sign fixed by (sa · sb), the two tangent_sign choices give
    // mirror-image tangent points across the AB line. Pick the one whose
    // anchor-side normal matches (sa_x, sa_y).
    let want_x = i32::from(sa_x);
    let want_y = i32::from(sa_y);
    let mut chosen_normal: Option<(f64, f64)> = None;
    for tangent_sign in [-1.0_f64, 1.0_f64] {
        let nx = (dx * r - dy * h * tangent_sign) / z;
        let ny = (dy * r + dx * h * tangent_sign) / z;
        if sign_with_eps(nx) == want_x && sign_with_eps(ny) == want_y {
            chosen_normal = Some((nx, ny));
            break;
        }
    }
    let (nx, ny) = chosen_normal.ok_or(WireError::TangentSidesUnreachable {
        anchor_sides: (sa_x, sa_y),
        target_sides: (sb_x, sb_y),
    })?;

    let tangent_a = (anchor_xy.0 + anchor_radius * nx, anchor_xy.1 + anchor_radius * ny);
    let tangent_b = (
        target_xy.0 + target_radius * radius_sign * nx,
        target_xy.1 + target_radius * radius_sign * ny,
    );
    Ok((tangent_a, tangent_b))
}

fn sign_with_eps(value: f64) -> i32 {
    if value > AXIS_EPS {
        1
    } else if value < -AXIS_EPS {
        -1
    } else {
        0
    }
}

fn arm_correction_head_shift_signs(
    anchor: (f64, f64),
    target: (f64, f64),
) -> Option<(i32, i32)> {
    let sign_x = sign_with_eps(anchor.0 - target.0);
    let sign_y = sign_with_eps(anchor.1 - target.1);
    if sign_x == 0 || sign_y == 0 {
        None
    } else {
        Some((sign_x, sign_y))
    }
}

fn roller_index_for_head_shift_signs(sign_x: i32, sign_y: i32) -> u8 {
    match (sign_x, sign_y) {
        (-1, -1) => 0,
        (-1, 1) => 1,
        (1, -1) => 2,
        (1, 1) => 3,
        _ => panic!("invalid head shift signs ({sign_x}, {sign_y})"),
    }
}

fn roller_offset_for_index(
    roller_index: u8,
    head_arm_length: f64,
    head_roller_radius: f64,
    head_roller_gap: f64,
    roller_arm_y_offsets: Option<(f64, f64, f64, f64)>,
) -> (f64, f64) {
    let y_offset = if let Some((y0, y1, y2, y3)) = roller_arm_y_offsets {
        match roller_index {
            0 => y0,
            1 => y1,
            2 => y2,
            3 => y3,
            _ => panic!("invalid roller index {roller_index}"),
        }
    } else {
        head_roller_gap / 2.0 + head_roller_radius
    };
    let y_sign = if matches!(roller_index, 0 | 2) {
        -1.0
    } else {
        1.0
    };
    let x_offset = if matches!(roller_index, 0 | 1) {
        -head_arm_length
    } else {
        head_arm_length
    };
    (x_offset, y_sign * y_offset)
}

fn distance_point_to_line(
    point: (f64, f64),
    line_point: (f64, f64),
    line_direction: (f64, f64),
) -> Result<f64, WireError> {
    let numerator = ((point.0 - line_point.0) * line_direction.1
        - (point.1 - line_point.1) * line_direction.0)
        .abs();
    let denominator = (line_direction.0 * line_direction.0
        + line_direction.1 * line_direction.1)
        .sqrt();
    if denominator <= AXIS_EPS {
        return Err(WireError::DegenerateLine);
    }
    Ok(numerator / denominator)
}

/// Which corner of the head the active roller sits in. Mirrors the legacy
/// `"NW" | "NE" | "SW" | "SE"` strings.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum HeadQuadrant {
    NW,
    NE,
    SW,
    SE,
}

/// Output of [`compute_arm_corrected_outbound`]: the commanded head-center
/// pose, the resulting outbound point on the wire-tangent line, the index
/// of the active roller (0..=3), and the head-quadrant the roller occupies.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ArmCorrectedOutbound {
    pub corrected_outbound: (f64, f64),
    pub corrected_head_center: (f64, f64),
    pub roller_index: u8,
    pub quadrant: HeadQuadrant,
}

/// Solve the head pose so the active roller is tangent to the chosen wire
/// line and the head center sits within the transfer rectangle. Mirrors
/// the legacy `_compute_arm_corrected_outbound` in
/// `src/dune_winder/uv_head_target_parts/geometry2d.py`.
///
/// `roller_arm_y_offsets`, when present, overrides the nominal
/// `(head_roller_gap / 2 + head_roller_radius)` for each of the four
/// rollers (indices 0..=3 = SW, NW, SE, NE).
#[allow(clippy::too_many_arguments)]
pub fn compute_arm_corrected_outbound(
    anchor_pin_point: (f64, f64),
    target_pin_point: (f64, f64),
    tangent_point_a: (f64, f64),
    tangent_point_b: (f64, f64),
    transfer_bounds: RectBounds,
    head_arm_length: f64,
    head_roller_radius: f64,
    head_roller_gap: f64,
    roller_arm_y_offsets: Option<(f64, f64, f64, f64)>,
) -> Result<ArmCorrectedOutbound, WireError> {
    let head_shift_signs = arm_correction_head_shift_signs(anchor_pin_point, target_pin_point);
    let tangent_x_side = sign_with_eps(target_pin_point.0 - anchor_pin_point.0);
    let Some((sign_x, sign_y)) = head_shift_signs else {
        return Err(WireError::ArmCorrectionAnchorTargetIndeterminate);
    };
    if tangent_x_side == 0 {
        return Err(WireError::ArmCorrectionAnchorTargetIndeterminate);
    }
    let roller_index = roller_index_for_head_shift_signs(sign_x, sign_y);
    let quadrant = match (sign_x, sign_y) {
        (-1, -1) => HeadQuadrant::SW,
        (-1, 1) => HeadQuadrant::NW,
        (1, -1) => HeadQuadrant::SE,
        (1, 1) => HeadQuadrant::NE,
        _ => unreachable!(),
    };
    let roller_offset = roller_offset_for_index(
        roller_index,
        head_arm_length,
        head_roller_radius,
        head_roller_gap,
        roller_arm_y_offsets,
    );
    let direction = (
        tangent_point_b.0 - tangent_point_a.0,
        tangent_point_b.1 - tangent_point_a.1,
    );
    let direction_length = (direction.0 * direction.0 + direction.1 * direction.1).sqrt();
    if direction_length <= AXIS_EPS {
        return Err(WireError::ArmCorrectionDegenerateTangent);
    }
    let unit_direction = (direction.0 / direction_length, direction.1 / direction_length);
    let candidate_normals = [
        (-unit_direction.1, unit_direction.0),
        (unit_direction.1, -unit_direction.0),
    ];
    let matching: Vec<(f64, f64)> = candidate_normals
        .iter()
        .copied()
        .filter(|n| sign_with_eps(n.0) == tangent_x_side)
        .collect();
    if matching.len() != 1 {
        return Err(WireError::ArmCorrectionAmbiguousNormal);
    }
    let normal = matching[0];
    let locus_origin = (
        tangent_point_a.0 + normal.0 * head_roller_radius - roller_offset.0,
        tangent_point_a.1 + normal.1 * head_roller_radius - roller_offset.1,
    );
    let Some((clipped_start, clipped_end)) =
        clip_infinite_line_to_bounds(locus_origin, direction, transfer_bounds)
    else {
        return Err(WireError::ArmCorrectionNoTransferZoneIntersection);
    };
    let corrected_outbound = choose_outbound_intercept(
        locus_origin,
        (locus_origin.0 + direction.0, locus_origin.1 + direction.1),
        clipped_start,
        clipped_end,
    );
    let corrected_head_center = corrected_outbound;
    let selected_roller_center = (
        corrected_head_center.0 + roller_offset.0,
        corrected_head_center.1 + roller_offset.1,
    );
    let dist = distance_point_to_line(selected_roller_center, tangent_point_a, direction)?;
    if (dist - head_roller_radius).abs() > 1.0e-6 {
        return Err(WireError::ArmCorrectionRollerTangentMismatch);
    }
    Ok(ArmCorrectedOutbound {
        corrected_outbound,
        corrected_head_center,
        roller_index,
        quadrant,
    })
}

/// Project the wire-end point given a commanded head pose, the
/// compensated anchor-pin XY, the anchor and head Z, and head geometry.
/// Mirrors the legacy `_actual_wire_point_from_machine_target` in
/// `src/dune_winder/uv_head_target_parts/anchor_to_target.py` byte-for-byte,
/// including the legacy quirk that `roller_offset_z` is computed but never
/// applied to the returned XY (preserved here as a `let _` to keep behaviour
/// identical under golden parity).
#[allow(clippy::too_many_arguments)]
pub fn actual_wire_point_from_machine_target(
    final_head_xy: (f64, f64),
    compensated_anchor_xy: (f64, f64),
    anchor_z: f64,
    head_z: f64,
    head_arm_length: f64,
    head_roller_radius: f64,
    head_roller_gap: f64,
) -> (f64, f64) {
    let mut delta_x = final_head_xy.0 - compensated_anchor_xy.0;
    let mut delta_z = head_z - anchor_z;
    let mut length_xz = (delta_x * delta_x + delta_z * delta_z).sqrt();
    if length_xz <= AXIS_EPS {
        return final_head_xy;
    }
    let head_ratio = head_arm_length / length_xz;
    let x = final_head_xy.0 - delta_x * head_ratio;
    let y = final_head_xy.1;
    let z = head_z - delta_z * head_ratio;

    delta_x = x - compensated_anchor_xy.0;
    let delta_y = y - compensated_anchor_xy.1;
    delta_z = z - anchor_z;
    length_xz = (delta_x * delta_x + delta_z * delta_z).sqrt();
    let length_xyz =
        (delta_x * delta_x + delta_y * delta_y + delta_z * delta_z).sqrt();
    if length_xz <= AXIS_EPS || length_xyz <= AXIS_EPS {
        return (x, y);
    }

    let mut roller_offset_y = head_roller_radius * length_xz / length_xyz;
    let roller_offset_xz = head_roller_radius * delta_y / length_xyz;
    let mut roller_offset_x = (roller_offset_xz * delta_x / length_xz).abs();
    // Computed by the legacy but never used in the returned XY — kept here
    // as `let _` so future readers don't reintroduce the dead path under the
    // assumption the legacy applied it.
    let _roller_offset_z = (roller_offset_xz * delta_z / length_xz).abs();
    roller_offset_y -= head_roller_radius;
    roller_offset_y -= head_roller_gap / 2.0;

    if delta_x < 0.0 {
        roller_offset_x = -roller_offset_x;
    }
    if delta_y > 0.0 {
        roller_offset_y = -roller_offset_y;
    }
    (x - roller_offset_x, y - roller_offset_y)
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
    #[error("cannot compute a tangent for coincident pin centers")]
    CoincidentPinCenters,
    #[error(
        "arm correction is unavailable because the anchor-to-target pin direction is indeterminate"
    )]
    ArmCorrectionAnchorTargetIndeterminate,
    #[error("arm correction requires a non-degenerate tangent line")]
    ArmCorrectionDegenerateTangent,
    #[error("arm correction could not determine a unique tangent side for the selected roller")]
    ArmCorrectionAmbiguousNormal,
    #[error("arm correction could not find a transfer-zone point tangent to the selected roller")]
    ArmCorrectionNoTransferZoneIntersection,
    #[error("arm correction did not place the selected roller tangent to the outbound line")]
    ArmCorrectionRollerTangentMismatch,
    #[error("cannot measure distance to a degenerate line")]
    DegenerateLine,
    #[error("layer {layer:?} has slots, not pins — wrap-side normals are undefined")]
    TangentSidesUndefinedForLayer { layer: Layer },
    #[error(
        "anchor wrap sides {anchor_sides:?} and target wrap sides {target_sides:?} do not agree on radius_sign \
         (sa·sb disagrees axially) — pins must be on the same face"
    )]
    IncompatibleWrapSides {
        anchor_sides: (i8, i8),
        target_sides: (i8, i8),
    },
    #[error("circles too close to admit a tangent under the chosen radius_sign")]
    TangentInfeasible,
    #[error(
        "no tangent_sign produced a normal matching anchor wrap sides {anchor_sides:?} \
         (target sides {target_sides:?}) — degenerate geometry"
    )]
    TangentSidesUnreachable {
        anchor_sides: (i8, i8),
        target_sides: (i8, i8),
    },
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

/// Pin-keyed variant of [`AnchorToTargetRequest`] for the spine-based
/// adoption path. The caller supplies the winder (X, Y) position for
/// each pin; the spine plane provides the Z coordinate via
/// [`SpineCalibrationFile::z_at`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AnchorToTargetSpineRequest {
    pub anchor_pin: Pin,
    pub anchor_xy: (f64, f64),
    pub target_pin: Pin,
    pub target_xy: (f64, f64),
    /// Optional `(dx, dy)` to add to the resolved target XYZ before the
    /// offset model is applied. Mirrors the legacy `offset=(x,y)` keyword.
    pub target_offset: Option<(f64, f64)>,
    pub head_side: HeadSide,
    pub hover: bool,
}

/// Spine-backed parallel of [`solve_anchor_to_target`]: resolves Z
/// for each pin from `spine_file` (via [`SpineCalibrationFile::z_at`])
/// and delegates to the existing solver.
pub fn solve_anchor_to_target_from_spine(
    request: &AnchorToTargetSpineRequest,
    spine_file: &SpineCalibrationFile,
    model: &MachineCalibrationModel,
) -> Result<AnchorToTargetSolution, WireError> {
    if request.anchor_pin.layer != request.target_pin.layer {
        return Err(WireError::LayerMismatch {
            anchor: request.anchor_pin,
            target: request.target_pin,
        });
    }
    let (ax, ay) = request.anchor_xy;
    let anchor_xyz = Vec3::new(
        ax,
        ay,
        spine_file.z_at(request.anchor_pin.layer, request.anchor_pin.side, ax, ay),
    );
    let (tx, ty) = request.target_xy;
    let target_xyz = Vec3::new(
        tx,
        ty,
        spine_file.z_at(request.target_pin.layer, request.target_pin.side, tx, ty),
    );
    let xyz_request = AnchorToTargetRequest {
        anchor_pin: request.anchor_pin,
        anchor_xyz,
        target_pin: request.target_pin,
        target_xyz,
        target_offset: request.target_offset,
        head_side: request.head_side,
        hover: request.hover,
    };
    solve_anchor_to_target(&xyz_request, model)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::calibration::PerPinOffset;
    use crate::pins::{Layer, Side};
    use crate::spine::SpinePlane;

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

    fn unit_bounds(half: f64) -> RectBounds {
        RectBounds {
            left: -half,
            right: half,
            bottom: -half,
            top: half,
        }
    }

    #[test]
    fn line_equation_horizontal_line() {
        let eq = line_equation_from_tangent_points((0.0, 5.0), (10.0, 5.0));
        assert!(!eq.is_vertical);
        assert_eq!(eq.slope, 0.0);
        assert_eq!(eq.intercept, 5.0);
    }

    #[test]
    fn line_equation_vertical_line() {
        let eq = line_equation_from_tangent_points((3.0, 0.0), (3.0, 7.0));
        assert!(eq.is_vertical);
        assert!(eq.slope.is_infinite());
        assert_eq!(eq.intercept, 3.0);
    }

    #[test]
    fn line_equation_diagonal_line() {
        // y = 2x + 1
        let eq = line_equation_from_tangent_points((0.0, 1.0), (1.0, 3.0));
        assert!(!eq.is_vertical);
        assert_eq!(eq.slope, 2.0);
        assert_eq!(eq.intercept, 1.0);
    }

    #[test]
    fn compute_arm_corrected_outbound_rejects_axis_aligned_pins() {
        // anchor and target share x → indeterminate.
        let result = compute_arm_corrected_outbound(
            (0.0, 0.0),
            (0.0, 5.0),
            (0.0, 0.0),
            (1.0, 0.0),
            unit_bounds(10.0),
            10.0,
            1.0,
            2.0,
            None,
        );
        assert!(matches!(
            result,
            Err(WireError::ArmCorrectionAnchorTargetIndeterminate)
        ));
    }

    #[test]
    fn compute_arm_corrected_outbound_returns_quadrant_for_diagonal_pins() {
        // anchor at (5, 5), target at (-5, -5) → anchor.x - target.x > 0
        // and anchor.y - target.y > 0 → quadrant NE, roller_index 3.
        // Tangent line through (0, 0) toward target → direction (-1, -1).
        let bounds = RectBounds {
            left: -100.0,
            right: 100.0,
            bottom: -100.0,
            top: 100.0,
        };
        let result = compute_arm_corrected_outbound(
            (5.0, 5.0),
            (-5.0, -5.0),
            (0.0, 0.0),
            (-1.0, -1.0),
            bounds,
            10.0,
            1.0,
            2.0,
            None,
        )
        .unwrap();
        assert_eq!(result.roller_index, 3);
        assert_eq!(result.quadrant, HeadQuadrant::NE);
    }

    #[test]
    fn actual_wire_point_collapses_when_anchor_at_head_xz() {
        // length_xz == 0 short-circuit returns final_head_xy.
        let p = actual_wire_point_from_machine_target(
            (10.0, 5.0),
            (10.0, 99.0),
            7.0,
            7.0,
            10.0,
            1.0,
            2.0,
        );
        assert_eq!(p, (10.0, 5.0));
    }

    #[test]
    fn actual_wire_point_returns_finite_for_realistic_geometry() {
        let p = actual_wire_point_from_machine_target(
            (10.0, 0.0),
            (0.0, 0.0),
            0.0,
            5.0,
            10.0,
            1.0,
            2.0,
        );
        assert!(p.0.is_finite() && p.1.is_finite());
    }

    fn va(n: u16) -> Pin {
        Pin::new(Layer::V, Side::A, n).unwrap()
    }

    fn xa(n: u16) -> Pin {
        Pin::new(Layer::X, Side::A, n).unwrap()
    }

    fn assert_tangent_normals_match_pins(
        anchor: Pin,
        anchor_xy: (f64, f64),
        anchor_r: f64,
        target: Pin,
        target_xy: (f64, f64),
        target_r: f64,
        result: ((f64, f64), (f64, f64)),
    ) {
        let (ta, tb) = result;
        let (sa_x, sa_y) = anchor.tangent_normal_sign();
        let nx = (ta.0 - anchor_xy.0) / anchor_r;
        let ny = (ta.1 - anchor_xy.1) / anchor_r;
        assert_eq!(
            sign_with_eps(nx),
            i32::from(sa_x),
            "anchor normal x-sign mismatch (n=({nx},{ny}), want sa=({sa_x},{sa_y}))"
        );
        assert_eq!(sign_with_eps(ny), i32::from(sa_y), "anchor normal y-sign mismatch");
        let (sb_x, sb_y) = target.tangent_normal_sign();
        let mx = (tb.0 - target_xy.0) / target_r;
        let my = (tb.1 - target_xy.1) / target_r;
        assert_eq!(sign_with_eps(mx), i32::from(sb_x), "target normal x-sign mismatch");
        assert_eq!(sign_with_eps(my), i32::from(sb_y), "target normal y-sign mismatch");
    }

    #[test]
    fn tangent_for_pin_pair_ua_realistic_geometry() {
        // Two UA pins with sa = (1, -1). Realistic spacing.
        let anchor = ua(100);
        let target = ua(101);
        let anchor_xy = (100.0, 50.0);
        let target_xy = (105.0, 51.0);
        let r = 0.5;
        let result =
            tangent_for_pin_pair(anchor, anchor_xy, r, target, target_xy, r).unwrap();
        assert_tangent_normals_match_pins(
            anchor, anchor_xy, r, target, target_xy, r, result,
        );
    }

    #[test]
    fn tangent_for_pin_pair_ub_pair() {
        // UB pins with sa = (1, 1).
        let anchor = ub(50);
        let target = ub(51);
        let anchor_xy = (10.0, 10.0);
        let target_xy = (15.0, 9.0);
        let result = tangent_for_pin_pair(anchor, anchor_xy, 0.5, target, target_xy, 0.5)
            .unwrap();
        assert_tangent_normals_match_pins(
            anchor, anchor_xy, 0.5, target, target_xy, 0.5, result,
        );
    }

    #[test]
    fn tangent_for_pin_pair_va_head_pair() {
        // VA pins in the head edge: sa = (1, 1). For the wrap-side normal at
        // the anchor to land in the +x/+y quadrant, the perpendicular to AB
        // must have positive components, so AB direction sits in the SE
        // quadrant (positive dx, negative dy).
        let anchor = va(100);
        let target = va(101);
        let anchor_xy = (0.0, 0.0);
        let target_xy = (5.0, -1.0);
        let result = tangent_for_pin_pair(anchor, anchor_xy, 0.5, target, target_xy, 0.5)
            .unwrap();
        assert_tangent_normals_match_pins(
            anchor, anchor_xy, 0.5, target, target_xy, 0.5, result,
        );
    }

    #[test]
    fn tangent_for_pin_pair_ua_past_n1200_pair() {
        // UA pins with n > 1200: sa = (-1, 1). Different sa pattern from the
        // n ≤ 1200 case, ensures the analytic solver picks the right
        // tangent_sign for the flipped x-side.
        let anchor = ua(1300);
        let target = ua(1301);
        let anchor_xy = (0.0, 0.0);
        let target_xy = (5.0, 1.0);
        let result = tangent_for_pin_pair(anchor, anchor_xy, 0.5, target, target_xy, 0.5)
            .unwrap();
        assert_tangent_normals_match_pins(
            anchor, anchor_xy, 0.5, target, target_xy, 0.5, result,
        );
    }

    #[test]
    fn tangent_for_pin_pair_rejects_layer_mismatch() {
        let result = tangent_for_pin_pair(ua(1), (0.0, 0.0), 0.5, vb(1), (5.0, 0.0), 0.5);
        assert!(matches!(result, Err(WireError::LayerMismatch { .. })));
    }

    #[test]
    fn tangent_for_pin_pair_rejects_xg_slot() {
        let result = tangent_for_pin_pair(xa(1), (0.0, 0.0), 0.5, xa(2), (5.0, 0.0), 0.5);
        assert!(matches!(
            result,
            Err(WireError::TangentSidesUndefinedForLayer { layer: Layer::X })
        ));
    }

    #[test]
    fn tangent_for_pin_pair_rejects_coincident_centers() {
        let result =
            tangent_for_pin_pair(ua(1), (1.0, 1.0), 0.5, ua(2), (1.0, 1.0), 0.5);
        assert!(matches!(result, Err(WireError::CoincidentPinCenters)));
    }

    fn spine_file_flat(_layer: Layer, z: f64) -> SpineCalibrationFile {
        SpineCalibrationFile {
            machine_id: "test".to_string(),
            plane: Some(SpinePlane { a: 0.0, b: 0.0, c: z }),
        }
    }

    #[test]
    fn spine_solve_matches_xyz_solve_for_flat_plane() {
        let model = MachineCalibrationModel {
            base_camera_wire_offset_stage: Vec3::new(1.0, 2.0, 0.0),
            base_camera_wire_offset_fixed: Vec3::ZERO,
            per_pin_camera_wire_offset: vec![],
            arm_correction: Vec3::new(0.5, 0.0, -0.25),
        };
        // Flat spine at Z=207. Anchor at (100, 100), target at (200, 200).
        let spine = spine_file_flat(Layer::U, 207.0);
        let anchor_xy = (100.0, 100.0);
        let target_xy = (200.0, 200.0);
        let spine_request = AnchorToTargetSpineRequest {
            anchor_pin: ua(1),
            anchor_xy,
            target_pin: ub(2),
            target_xy,
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        let spine_sol = solve_anchor_to_target_from_spine(&spine_request, &spine, &model).unwrap();

        // Recompute via the existing XYZ-based path with the same Z values.
        let (ax, ay) = anchor_xy;
        let anchor_xyz = Vec3::new(ax, ay, spine.z_at(Layer::U, Side::A, ax, ay));
        let (tx, ty) = target_xy;
        let target_xyz = Vec3::new(tx, ty, spine.z_at(Layer::U, Side::B, tx, ty));
        let xyz_request = AnchorToTargetRequest {
            anchor_pin: ua(1),
            anchor_xyz,
            target_pin: ub(2),
            target_xyz,
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        let xyz_sol = solve_anchor_to_target(&xyz_request, &model).unwrap();
        assert_eq!(spine_sol, xyz_sol);
    }

    #[test]
    fn spine_solve_falls_back_to_default_when_layer_absent() {
        // No calibration for U — should still succeed using the default plane.
        let model = MachineCalibrationModel::empty();
        let spine = SpineCalibrationFile::new("test".to_string());
        let request = AnchorToTargetSpineRequest {
            anchor_pin: ua(1),
            anchor_xy: (0.0, 0.0),
            target_pin: ub(2),
            target_xy: (10.0, 10.0),
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        // Should not error — the plane defaults to Z=207.
        let result = solve_anchor_to_target_from_spine(&request, &spine, &model);
        assert!(result.is_ok() || matches!(result, Err(WireError::LayerMismatch { .. })));
    }

    #[test]
    fn spine_solve_rejects_layer_mismatch() {
        let model = MachineCalibrationModel::empty();
        let spine = spine_file_flat(Layer::U, 207.0);
        let request = AnchorToTargetSpineRequest {
            anchor_pin: ua(1),
            anchor_xy: (0.0, 0.0),
            target_pin: vb(2),
            target_xy: (10.0, 10.0),
            target_offset: None,
            head_side: HeadSide::Stage,
            hover: false,
        };
        assert!(matches!(
            solve_anchor_to_target_from_spine(&request, &spine, &model),
            Err(WireError::LayerMismatch { .. })
        ));
    }

    #[test]
    fn tangent_for_pin_pair_rejects_opposite_face_pair() {
        // UA1 has sa=(1,-1); UB1 has sa=(1,1). rs_x=1 but rs_y=-1 → incompatible.
        let result = tangent_for_pin_pair(ua(1), (0.0, 0.0), 0.5, ub(1), (5.0, 1.0), 0.5);
        assert!(matches!(
            result,
            Err(WireError::IncompatibleWrapSides { .. })
        ));
    }
}
