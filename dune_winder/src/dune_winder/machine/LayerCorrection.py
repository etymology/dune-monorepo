###############################################################################
# Name: LayerCorrection.py
# Uses:
# Date: 2016-10-31
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

import math


from .GeometrySelection import GeometrySelection


class LayerCorrection:
  # -------------------------------------------------------------------
  def __init__(self, layerCalibration):
    """
    Constructor.

    Args:
      layerCalibration: Instance of LayerCalibration.
    """

    self.layerCalibration = layerCalibration

  # -------------------------------------------------------------------
  def getCalibrationError(self):
    """
    Compute how much variance there is on pin calibration.

    The calibration system attempts to location the exact pin centers/valleys
    of each pin.  Spacing between pins should be quote accurate, so errors in
    the observed position are a reflection of the inaccuracy of the vision
    system used to acquire these positions.

    The measurement is made by computing the coefficient of determination (or
    R squared) for each row/column of pins.  The assumption is that the frame
    only has rotational error distortion and no other deformation.
    """
    pass

  # -------------------------------------------------------------------
  def getSag(self):
    """
    Calculate the amount of sag in both the top and bottom row of pins.

    This is done by computing quadratic regression and then using the x^2
    coefficient to compute the sag over the total distance.
    """
    pass

  # -------------------------------------------------------------------
  def getRotation(self):
    """
    Compute the angle of rotation of the APA.

    Although attempt are made to minimize this, one side of the APA could be
    higher than the other.  This introduces a small rotational error in pin
    locations which can be extracted from pin locations.  This error is not
    part of the calibration inaccuracy.

    Returns:
      Degrees of clockwise rotation of APA's rotational error.
    """

    # Get the geometry for the layer.
    layerName = self.layerCalibration.getLayerNames()
    geometry = GeometrySelection(layerName)

    # Pin number.
    pinNumber = geometry.startPinFront

    # Account for direction in row/column.
    sign = 1

    # Summation for angle (used for average angle).
    degreeSum = 0

    # Number of rows/columns to average (skip
    averageCount = 0

    for row in geometry.gridFront:
      # Number of pins in this row/column.
      count = row[0]

      #
      # Calculate slope for the current row/column of pins using linear
      # regression.  Regression will filter out individual pin position error.
      #
      # Linear regression equation:
      #      [ Sx^0  Sx^1 ][ b ] = [ Sy  ]
      #      [ Sx^1  Sx^2 ][ m ]   [ Sxy ]
      #   Where b is the intercept, and m the slope.  Here, S is the summation of
      # the array.  So Sxy is the summation of x*y for each element.  Note that
      # Sx^0 is just the number of elements in x, or n.
      #   Intercept is not calculated here because it isn't used.
      #

      # Zero sums.
      n = 0
      sumX = 0
      sumY = 0
      sumXX = 0
      sumXY = 0

      # For all pins in this row/column...
      for _ in range(0, count):
        # Get the pin location.
        pinName = "F" + str(pinNumber)
        layerPinLocation = self.layerCalibration.getPinLocation(pinName)

        # X and Y data depend on if this is a row or column, which is determined
        # by the sign.  Columns use slope of X/Y, rows use slope of Y/X.
        if 1 == sign:
          x = layerPinLocation.y
          y = layerPinLocation.x
        else:
          x = layerPinLocation.x
          y = layerPinLocation.y

        # Add pin's location to sums.
        n += 1
        sumX += x
        sumY += y
        sumXX += x**2
        sumXY += x * y

        # Next pin.
        pinNumber += geometry.directionFront

        # Roll-over.
        if 0 == pinNumber:
          pinNumber = geometry.pins
        elif pinNumber > geometry.pins:
          pinNumber = 1

      # Denominator for slope calculation.
      denominator = n * sumXX - sumX**2

      # Avoid divide-by-zero.
      if denominator > 0:
        # Calculate slope.
        slope = n * sumXY - sumY * sumX
        slope /= denominator
      else:
        # Angle is vertical.
        # (Should never happen.)
        slope = float("inf")

      # If there were pins in this row of the grid table...
      if n > 0:
        # Get angle of this row/column.
        degrees = math.degrees(math.atan(sign * slope))

        # print degrees

        # Accumulate degrees.
        degreeSum += degrees

        # Count this.
        averageCount += 1

      # Alternate the sign.
      sign *= -1

    # Take average of all rows/columns used.
    # (Always 2 or 4.)
    degrees = degreeSum / averageCount

    return degrees

