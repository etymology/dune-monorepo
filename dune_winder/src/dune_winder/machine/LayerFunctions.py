###############################################################################
# Name: LayerFunctions.py
# Uses: Collection of functions for layer related operations.
# Date: 2017-01-17
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################


class LayerFunctions:
  # -------------------------------------------------------------------
  @staticmethod
  def offsetPin(geometry, pin, offset):
    """
    Offset the given pin number.

    Args:
      geometry: Instance of LayerGeometry.
      pin: Starting pin number (number, not name).
      offset: Value (+/-) to adjust by.

    Returns:
      Modified pin number.
    """

    pin += offset
    if pin > geometry.pins:
      pin -= geometry.pins
      pin += 1
    elif pin <= 0:
      pin += geometry.pins

    return pin

  # -------------------------------------------------------------------
  @staticmethod
  def translateFrontBack(geometry, pin):
    """
    Translate a pin number to same pin on opposite side.

    Args:
      geometry: Instance of LayerGeometry.
      pin: Pin number to translate.

    Returns:
      Pin number on opposite side.
    """

    pin = geometry.startPinFront - pin - 1
    pin %= geometry.pins
    pin += geometry.startPinBack
    pin %= geometry.pins
    pin += 1

    return pin
