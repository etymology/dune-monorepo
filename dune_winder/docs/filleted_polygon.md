filleted polygon path planner

The default motion planning mode should be the following:

min_radius is the greater of the default minimum radius for the machine and the radius for which, at the speed that the segment will be traversed in, the componentwise acceleration in x and y do not exceed the acceleration limits or jerk limits.

For a path between A B and C, construct the interior angle bisector of ABC and the CIRCLE of min_radius centered on the bisector on the interior of ABC which passes through B. Then construct tangent lines from A to CIRCLE and CIRCLE to C. The path consists of the tangent segments and the portion of the arc between the segments. If either A or C fall within this circle, a path is impossible and we should use the fallback case of using straight lines with 0 (come to a stop) termination type.

As a check, the arc length of the resulting arc should be approximately equal to the pi - ABC radians, so approximately pi for A=C and equal to 0 for colinear ABC.

Acceleration and jerk limits should be centralized and user adjustable, and controlled from the sliders in the interface Wind page. 