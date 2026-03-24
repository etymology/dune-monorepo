# Filleted Polygon Path Planner

## Overview

`filleted_polygon_segments` generates a smooth path through a list of waypoints
by replacing each interior waypoint with a tangent arc of a given radius. The
result is a sequence of alternating line and arc `MotionSegment` objects ready
to stream to the PLC queue.

Implementation: `src/dune_winder/queued_motion/filleted_path.py`

Related modules:

- `src/dune_winder/queued_motion/segment_types.py` — `MotionSegment`,
  `SEG_TYPE_LINE`, `SEG_TYPE_CIRCLE`, `CIRCLE_TYPE_CENTER`,
  `MCCM_DIR_2D_CCW`, `MCCM_DIR_2D_CW`
- `src/dune_winder/queued_motion/jerk_limits.py` — acceleration/jerk limit
  helpers used upstream to compute the minimum radius for a given speed

## Main Function

```python
def filleted_polygon_segments(
    *,
    start_xy: tuple[float, float],
    waypoints: list[tuple[float, float]],
    radius: float,
    line_term_type: int,
    arc_term_type: int,
    final_term_type: int,
) -> Optional[list[MotionSegment]]
```

Returns a list of `MotionSegment` objects, or `None` if no valid path can be
constructed (e.g. the radius is too large relative to the waypoint spacing).

An empty `waypoints` list returns `[]`. A single waypoint returns a single
line segment to that point.

## Algorithm

For each interior waypoint B (between A and C):

1. Place a circle of `radius` centered on the angle bisector of the interior
   angle ABC, at the correct distance from B so that it is tangent to both AB
   and BC.
2. Compute the tangent points from the previous line's endpoint to this circle,
   and from this circle to the next line's start point.
3. Between consecutive circles, compute the external tangent line connecting
   circle _i_ to circle _i+1_.

The path then consists of:

- A straight line from the current position to the first tangent point.
- An arc through the fillet circle (passing through the original waypoint,
  choosing CW or CCW to match the interior angle direction).
- A straight line to the next tangent point.
- Repeat for each waypoint.
- A final straight line to the last waypoint (which is not filleted).

The implementation uses a recursive best-first search
(`search(circle_index, line_start_xy, incoming_xy)`) to find the tangent point
combination across all circles that minimizes arc-sweep error relative to the
expected interior angle.

## Dynamic Radius Helper

```python
def dynamic_min_radius(
    *,
    speed: float,
    base_min_radius: float,
    accel_limit: float,
    jerk_limit: float,
) -> float
```

Returns the minimum radius that keeps centripetal acceleration and jerk within
limits at the given speed. The caller should pass this as the `radius` argument
to `filleted_polygon_segments` to ensure the fillet arcs stay within machine
dynamics.

## Fallback Behavior

If `filleted_polygon_segments` returns `None` (geometry is degenerate or the
radius is too large), the caller should fall back to straight line moves with
`term_type=0` (stop at each waypoint).
