from __future__ import annotations

from dataclasses import dataclass


class UvHeadTargetError(ValueError):
    pass


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class Point3D:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class RectBounds:
    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class LineEquation:
    slope: float
    intercept: float
    is_vertical: bool = False


@dataclass(frozen=True)
class RecipeSite:
    anchor_pin: str
    orientation_token: str
    recipe_pair_pin_a: str
    recipe_pair_pin_b: str
    site_label: str
    side: str
    position: str


@dataclass(frozen=True)
class UvHeadTargetRequest:
    layer: str
    anchor_pin: str
    wrapped_pin: str
    head_z_mode: str


@dataclass(frozen=True)
class UvTangentViewRequest:
    layer: str
    pin_a: str
    pin_b: str
    g103_adjacent_pin: str | None = None


@dataclass(frozen=True)
class UvHeadTargetResult:
    request: UvHeadTargetRequest
    site_label: str
    site_side: str
    site_position: str
    wrap_sides: tuple[str, str]
    orientation_token: str
    anchor_pin_point: Point3D
    wrapped_pin_point: Point3D
    inferred_pair_pin: str
    inferred_pair_pin_point: Point3D
    midpoint_point: Point3D
    transfer_point: Point2D
    effective_anchor_point: Point3D
    final_head_point: Point3D
    final_wire_point: Point3D
    transfer_bounds: RectBounds
    pin_radius: float
    head_arm_length: float
    head_roller_radius: float
    head_roller_gap: float
    validation_error: str | None = None


@dataclass(frozen=True)
class UvTangentViewResult:
    request: UvTangentViewRequest
    pin_a_point: Point3D
    pin_b_point: Point3D
    tangent_point_a: Point2D
    tangent_point_b: Point2D
    line_equation: LineEquation
    clipped_segment_start: Point2D
    clipped_segment_end: Point2D
    outbound_intercept: Point2D
    transfer_bounds: RectBounds
    apa_bounds: RectBounds
    apa_pin_points: tuple[Point2D, ...]
    apa_pin_points_by_name: tuple[tuple[str, Point2D], ...]
    pin_radius: float
    tangent_selection_rule: str
    anchor_side: str
    anchor_face: str
    anchor_tangent_sides: tuple[str, str]
    wrapped_side: str
    wrapped_face: str
    wrap_sides: tuple[str, str] | None = None
    runtime_orientation_token: str | None = None
    runtime_tangent_point: Point2D | None = None
    runtime_target_point: Point2D | None = None
    runtime_line_equation: LineEquation | None = None
    runtime_clipped_segment_start: Point2D | None = None
    runtime_clipped_segment_end: Point2D | None = None
    runtime_outbound_intercept: Point2D | None = None
    arm_head_center: Point2D | None = None
    arm_left_endpoint: Point2D | None = None
    arm_right_endpoint: Point2D | None = None
    roller_centers: tuple[Point2D, ...] = ()
    arm_corrected_outbound_point: Point2D | None = None
    arm_corrected_head_center: Point2D | None = None
    arm_corrected_selected_roller_index: int | None = None
    arm_corrected_quadrant: str | None = None
    arm_corrected_available: bool = False
    arm_corrected_error: str | None = None
    head_arm_length: float = 0.0
    head_roller_radius: float = 0.0
    head_roller_gap: float = 0.0
    alternating_plane: str | None = None
    alternating_face: str | None = None
    alternating_anchor_center: Point2D | None = None
    alternating_wrapped_center: Point2D | None = None
    alternating_anchor_segment_start: Point2D | None = None
    alternating_anchor_segment_end: Point2D | None = None
    alternating_wrapped_segment_start: Point2D | None = None
    alternating_wrapped_segment_end: Point2D | None = None
    alternating_anchor_contact: Point2D | None = None
    alternating_wrapped_contact: Point2D | None = None
    alternating_wrap_line_start: Point2D | None = None
    alternating_wrap_line_end: Point2D | None = None
    alternating_g109_projection: Point2D | None = None
    alternating_g103_projection: Point2D | None = None
    alternating_g108_projection: Point2D | None = None
    z_retracted: float = 0.0
    z_extended: float = 0.0
    matches_runtime_line: bool | None = None
    validation_error: str | None = None


@dataclass(frozen=True)
class WrappedPinResolution:
    wrapped_pin: str
    adjacent_pin: str
    wrap_sides: tuple[str, str]


@dataclass(frozen=True)
class AnchorToTargetCommand:
    raw_text: str
    anchor_pin: str
    target_pin: str
    target_offset: tuple[float, float] | None
    hover: bool


@dataclass(frozen=True)
class AnchorToTargetViewResult:
    command: AnchorToTargetCommand
    raw_result: UvTangentViewResult
    interpreter_head_point: Point2D
    interpreter_wire_point: Point2D
