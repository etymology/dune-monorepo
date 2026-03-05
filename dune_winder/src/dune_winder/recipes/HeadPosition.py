###############################################################################
# Name: HeadPosition.py
# Uses: Handling the passing around of the head via Z-axis.
# Date: 2016-04-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .gcode_functions import head_location


class HeadPosition:
  FRONT = 0
  PARTIAL_FRONT = 1
  PARTIAL_BACK = 2
  BACK = 3

  PARTIAL = 4
  OTHER_SIDE = 5

  # ---------------------------------------------------------------------
  def __init__(self, gCodePath, geometry, initialPosition):
    """
    Constructor.

    Args:
      gCodePath: An instance of GCodePath.
      geometry: An instance of LayerGeometry (or child of).
      initialPosition: Initial position of Z axis.
    """
    self._gCodePath = gCodePath
    self._geometry = geometry
    self._currentPostion = initialPosition

  # ---------------------------------------------------------------------
  def get(self):
    """
    Get the current position of the head.

    Returns:
      Current position of head (FRONT/PARTIAL_FRONT/PARTIAL_BACK/BACK).
    """
    return self._currentPostion

  # ---------------------------------------------------------------------
  def set(self, location):
    """
    Set new location of head.

    Args:
      location: Where to place the head (FRONT/PARTIAL_FRONT/PARTIAL_BACK/BACK).
    """

    # Partial for the current side.
    if HeadPosition.PARTIAL == location:
      if HeadPosition.BACK == self._currentPostion:
        location = HeadPosition.PARTIAL_BACK
      elif HeadPosition.FRONT == self._currentPostion:
        location = HeadPosition.PARTIAL_FRONT
      else:
        print(location, self._currentPostion)
        raise Exception()

    # Switch to other side.
    if HeadPosition.OTHER_SIDE == location:
      if (
        HeadPosition.BACK == self._currentPostion
        or HeadPosition.PARTIAL_BACK == self._currentPostion
      ):
        location = HeadPosition.FRONT
      elif (
        HeadPosition.FRONT == self._currentPostion
        or HeadPosition.PARTIAL_FRONT == self._currentPostion
      ):
        location = HeadPosition.BACK

    if self._currentPostion != location:
      self._gCodePath.pushG_Code(head_location(location))
      self._gCodePath.push()

      self._currentPostion = location
