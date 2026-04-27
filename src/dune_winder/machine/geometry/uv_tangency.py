from __future__ import annotations

from dune_winder.machine.geometry.uv_wrap_geometry import (
    LineEquation,
    Point2D,
    Point3D,
    RectBounds,
    UvWrapGeometryError,
    matches_tangent_sides,
    plan_wrap_transition,
    tangent_sides,
)
from dune_winder.uv_head_target import (
    PinPairTangentGeometry,
    RecipeSite,
    UvHeadTargetRequest,
    UvHeadTargetResult,
    UvTangentViewRequest,
    UvTangentViewResult,
    WrappedPinResolution,
    compute_pin_pair_tangent_geometry,
    compute_uv_head_target,
    compute_uv_tangent_view,
    iter_uv_wrap_primary_sites,
    resolve_wrapped_pin_from_g103_pair,
)


UvHeadTargetError = UvWrapGeometryError


__all__ = [
    "LineEquation",
    "PinPairTangentGeometry",
    "Point2D",
    "Point3D",
    "RecipeSite",
    "RectBounds",
    "UvHeadTargetError",
    "UvWrapGeometryError",
    "UvHeadTargetRequest",
    "UvHeadTargetResult",
    "UvTangentViewRequest",
    "UvTangentViewResult",
    "WrappedPinResolution",
    "compute_pin_pair_tangent_geometry",
    "compute_uv_head_target",
    "compute_uv_tangent_view",
    "iter_uv_wrap_primary_sites",
    "matches_tangent_sides",
    "plan_wrap_transition",
    "resolve_wrapped_pin_from_g103_pair",
    "tangent_sides",
]
