Spec for calibrating the Z positions of the pins.

The A-side and B-side pin planes on the APA are not perfectly level. During wrapping we want to estimate a plane for each side and use that to adjust pin Z positions.

For the U layer, treat the calibration pins as lying on two planes that are roughly parallel to the XY plane. The B plane is offset from the A plane by `boardWidth = 130 mm` in Z. The planes are assumed to be coplanar in the sense that they share the same tilt, so the B plane can be modeled as the A plane shifted by `boardWidth`.

Each calibration point is a same-side `~anchorToTarget(pin1,pin2) -> Z` observation. The tangent geometry is evaluated in XY using `uv_head_target`, and the observed wire Z at the transfer zone becomes the target value for the fit.

The fit should solve for a plane of the form:

`z_A(x,y) = a*x + b*y + c`

The B-side plane is:

`z_B(x,y) = z_A(x,y) + boardWidth`

Minimum data:

* At least 3 non-collinear measurements are required to determine a plane.
* More points may be supplied; the solver should use least squares.

Sanity check:

* Reject fits where the implied side-plane tilt deviates by more than `20 mm` from the side mean.

Example measurements:

* `~anchorToTarget(A1010,A2192) -> Z143`
* `~anchorToTarget(B610,B191,offset=(0,1)) -> Z276`
* `~anchorToTarget(A210,A591) -> Z149`
* `~anchorToTarget(B2212,B991) -> Z270`
* `~anchorToTarget(B1411,B1791) -> Z280`
