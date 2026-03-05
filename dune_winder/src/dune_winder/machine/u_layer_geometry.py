###############################################################################
# Name: U_LayerGeometry.py
# Uses: Geometry specific to the 2nd induction layer, U.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .uv_layer_geometry import UV_LayerGeometry


class U_LayerGeometry(UV_LayerGeometry):
  # -------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """

    UV_LayerGeometry.__init__(self)

    self._configure_induction_layer(
      pins=2 * self.rows + 2 * self.columns + 1,
      front_back_offset=self.rows,
      front_back_modulus=2 * self.rows + 2 * self.columns,
      depth_mm=104.7,
      start_pin_front=400,
    )

    # Alias names for several equations.
    # This makes the patterns in the equations more obvious.
    x = self.deltaX
    y = self.deltaY
    t = self.boardHalfThickness
    s = self.boardSpacing

    # Offset from APA's (0,0,0) position.
    # (Exactly -8.2875 -4.9375).
    self._set_apa_offset(-2 * s - t, -s - t, 0)

    # Offsets of pins.
    offsetXF0 = 0
    offsetXF1 = -s * (x / y - 1) + t * x / y
    offsetXF2 = s * (x / y + 1) + t * x / y + x / 2
    offsetXF3 = s * (x / y - 1) - t * x / y - x / 2

    offsetYF0 = s * (y / x + 1) + t
    offsetYF1 = -s * (y / x - 1) + t + y
    offsetYF2 = -s * (y / x + 1) - t + y / 2
    offsetYF3 = s * (y / x - 1) - t - y / 2

    offsetXB0 = 0
    offsetXB1 = s * (x / y + 1) + t * x / y
    offsetXB2 = -s * (x / y - 1) + t * x / y + x / 2
    offsetXB3 = -s * (x / y + 1) - t * x / y - x / 2

    offsetYB0 = -s * (y / x - 1) + t + y
    offsetYB1 = s * (y / x + 1) + t
    offsetYB2 = s * (y / x - 1) - t - y / 2
    offsetYB3 = -s * (y / x + 1) - t + y / 2

    # The grid parameters are a list of parameters for how the grid is constructed.
    # Columns:
    #   Count - Number of pins this row in the table represents.
    #   dx - Change in x each iteration.
    #   dy - Change in y each iteration.
    #   off.x - Starting x offset for initial position of first pin in this set.
    #   off.y - Starting y offset for initial position of first pin in this set.
    #   ort - Wire orientation.
    self.gridFront = [
      # Count                    dx            dy       off.x      off.y  ort.
      [self.rows, 0, self.deltaY, offsetXF0, offsetYF0, "TL"],  # Right
      [self.columns, self.deltaX, 0, offsetXF1, offsetYF1, "RB"],  # Top
      [self.rows + 1, 0, -self.deltaY, offsetXF2, offsetYF2, "BR"],  # Left
      [self.columns, -self.deltaX, 0, offsetXF3, offsetYF3, "LT"],  # Bottom
    ]

    # For back side.
    self.gridBack = [
      # Count                    dx            dy      off.x      off.y  ort.
      [self.rows, 0, self.deltaY, offsetXB0, offsetYB0, "BL"],  # Right
      [self.columns, self.deltaX, 0, offsetXB1, offsetYB1, "LB"],  # Top
      [self.rows + 1, 0, -self.deltaY, offsetXB2, offsetYB2, "TR"],  # Left
      [self.columns, -self.deltaX, 0, offsetXB3, offsetYB3, "RT"],  # Bottom
    ]
