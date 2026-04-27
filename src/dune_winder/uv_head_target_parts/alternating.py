from __future__ import annotations

from dune_winder.library.Geometry.location import Location

from .calibration import _location_to_point3
from .constants import _AXIS_EPSILON
from .models import Point2D, Point3D, UvHeadTargetError


def _alternating_plane_for_face(face: str) -> str:
    face_value = str(face).strip().lower()
    if face_value in ("top", "bottom"):
        return "xz"
    if face_value in ("head", "foot"):
        return "yz"
    raise UvHeadTargetError(f"Unsupported face {face!r} for alternating-side view.")


def _project_point3_to_plane(point: Point3D, plane: str) -> Point2D:
    if plane == "xz":
        return Point2D(point.x, point.z)
    if plane == "yz":
        return Point2D(point.z, point.y)
    raise UvHeadTargetError(f"Unsupported alternating plane {plane!r}.")


def _project_location_to_plane(location: Location, plane: str) -> Point2D:
    return _project_point3_to_plane(_location_to_point3(location), plane)


def _segment_endpoints_for_plane(
    center: Point2D,
    *,
    plane: str,
    pin_radius: float,
) -> tuple[Point2D, Point2D]:
    if plane == "xz":
        return (
            Point2D(center.x - pin_radius, center.y),
            Point2D(center.x + pin_radius, center.y),
        )
    if plane == "yz":
        return (
            Point2D(center.x, center.y - pin_radius),
            Point2D(center.x, center.y + pin_radius),
        )
    raise UvHeadTargetError(f"Unsupported alternating plane {plane!r}.")


def _segment_contact_for_wrap_side(
    center: Point2D,
    *,
    plane: str,
    pin_radius: float,
    tangent_sides_value: tuple[str, str],
) -> Point2D:
    negative_endpoint, positive_endpoint = _segment_endpoints_for_plane(
        center,
        plane=plane,
        pin_radius=pin_radius,
    )
    axis = "x" if plane == "xz" else "y"
    if _side_sign_for_axis(tangent_sides_value, axis) == "plus":
        return positive_endpoint
    return negative_endpoint


def _side_sign_for_axis(tangent_sides_value: tuple[str, str], axis: str) -> str:
    if axis == "x":
        return tangent_sides_value[0]
    if axis == "y":
        return tangent_sides_value[1]
    raise UvHeadTargetError(f"Unsupported axis {axis!r}.")


def _extend_segment_to_machine_z_planes(
    start: Point2D,
    end: Point2D,
    *,
    plane: str,
    z_retracted: float,
    z_extended: float,
) -> tuple[Point2D, Point2D]:
    if plane == "xz":
        delta_z = end.y - start.y
        if abs(delta_z) <= _AXIS_EPSILON:
            return (Point2D(start.x, z_retracted), Point2D(end.x, z_extended))

        def point_at_z(z_value: float) -> Point2D:
            parameter = (z_value - start.y) / delta_z
            return Point2D(start.x + (parameter * (end.x - start.x)), z_value)

        return (point_at_z(z_retracted), point_at_z(z_extended))

    if plane == "yz":
        delta_z = end.x - start.x
        if abs(delta_z) <= _AXIS_EPSILON:
            return (Point2D(z_retracted, start.y), Point2D(z_extended, end.y))

        def point_at_z(z_value: float) -> Point2D:
            parameter = (z_value - start.x) / delta_z
            return Point2D(z_value, start.y + (parameter * (end.y - start.y)))

        return (point_at_z(z_retracted), point_at_z(z_extended))

    raise UvHeadTargetError(f"Unsupported alternating plane {plane!r}.")


def _compute_alternating_projection_data(
    *,
    plane: str,
    pin_a_point: Point3D,
    pin_b_point: Point3D,
    pin_radius: float,
    anchor_tangent_sides: tuple[str, str],
    wrapped_tangent_sides: tuple[str, str],
    z_retracted: float,
    z_extended: float,
    runtime_g109_location: Location,
    runtime_g103_location: Location,
) -> dict[str, Point2D | None]:
    anchor_center = _project_point3_to_plane(pin_a_point, plane)
    wrapped_center = _project_point3_to_plane(pin_b_point, plane)
    anchor_segment_start, anchor_segment_end = _segment_endpoints_for_plane(
        anchor_center,
        plane=plane,
        pin_radius=pin_radius,
    )
    wrapped_segment_start, wrapped_segment_end = _segment_endpoints_for_plane(
        wrapped_center,
        plane=plane,
        pin_radius=pin_radius,
    )
    anchor_contact = _segment_contact_for_wrap_side(
        anchor_center,
        plane=plane,
        pin_radius=pin_radius,
        tangent_sides_value=anchor_tangent_sides,
    )
    wrapped_contact = _segment_contact_for_wrap_side(
        wrapped_center,
        plane=plane,
        pin_radius=pin_radius,
        tangent_sides_value=wrapped_tangent_sides,
    )
    wrap_line_start, wrap_line_end = _extend_segment_to_machine_z_planes(
        anchor_contact,
        wrapped_contact,
        plane=plane,
        z_retracted=z_retracted,
        z_extended=z_extended,
    )
    return {
        "anchor_center": anchor_center,
        "wrapped_center": wrapped_center,
        "anchor_segment_start": anchor_segment_start,
        "anchor_segment_end": anchor_segment_end,
        "wrapped_segment_start": wrapped_segment_start,
        "wrapped_segment_end": wrapped_segment_end,
        "anchor_contact": anchor_contact,
        "wrapped_contact": wrapped_contact,
        "wrap_line_start": wrap_line_start,
        "wrap_line_end": wrap_line_end,
        "g109_projection": _project_location_to_plane(runtime_g109_location, plane),
        "g103_projection": _project_location_to_plane(runtime_g103_location, plane),
        "g108_projection": None,
    }
