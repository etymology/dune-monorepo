###############################################################################
# Name: Location.py
# Uses: Location in 2d or 3d space.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.MathExtra import MathExtra


# ==============================================================================
class Location:
  # ---------------------------------------------------------------------
  def __init__(self, x=0, y=0, z=0):
    """
    Constructor.

    Args:
      x: Position on the x-axis.
      y: Position on the y-axis.
      z: Position on the z-axis.
    """
    self.x = float(x)
    self.y = float(y)
    self.z = float(z)

  # ---------------------------------------------------------------------
  def center(self, location):
    """
    Return the center point between this and an other location.

    Args:
      location: The second location to center between.

    Returns:
      Instance of Location with the center point.
    """
    deltaX = abs(self.x - location.x)
    deltaY = abs(self.y - location.y)
    deltaZ = abs(self.z - location.z)

    x = deltaX / 2 + min(self.x, location.x)
    y = deltaY / 2 + min(self.y, location.y)
    z = deltaZ / 2 + min(self.z, location.z)

    return Location(x, y, z)

  # ---------------------------------------------------------------------
  def add(self, location):
    """
    Add/offset this location by an other location.

    Args:
      location: Location to add to this instance.

    Returns:
      Instance of Location with results of add.

    Note:
      Does not modify self.
    """
    return Location(self.x + location.x, self.y + location.y, self.z + location.z)

  # ---------------------------------------------------------------------
  def sub(self, location):
    """
    Subtract/offset this location by an other location.

    Args:
      location: Location to subtract to this instance.

    Returns:
      Instance of Location with results of subtract.

    Note:
      Does not modify self.
    """
    return Location(self.x - location.x, self.y - location.y, self.z - location.z)

  # ---------------------------------------------------------------------
  def asList(self):
    """
    Return the location as a list of three floating point values for X/Y/Z.

    Returns:
      A list with 3 elements, [ x, y, z ].
    """
    return [self.x, self.y, self.z]

  # ---------------------------------------------------------------------
  def copy(self, x=None, y=None, z=None):
    """
    Return a copy of this location.

    Input:
      x: Override X value.  Omit to copy.
      y: Override Y value.  Omit to copy.
      z: Override Z value.  Omit to copy.

    Returns:
      New instance at the same location.
    """

    if x is None:
      x = self.x

    if y is None:
      y = self.y

    if z is None:
      z = self.z

    return Location(x, y, z)

  # ---------------------------------------------------------------------
  def __str__(self):
    """
    Get a string representation of object.

    Returns:
      String representation of object in form (x, y, z) where x/y/z are
      numbers.
    """

    return "(" + str(self.x) + ", " + str(self.y) + ", " + str(self.z) + ")"

  # ---------------------------------------------------------------------
  def __eq__(self, other):
    """
    Check to see if this location is equal to an other.

    Input:
      other: An other instance of Location to compare.

    Returns:
      True if equal, False if not.
    """

    result = False
    if isinstance(other, Location):
      result = (
        MathExtra.isclose(self.x, other.x)
        and MathExtra.isclose(self.y, other.y)
        and MathExtra.isclose(self.z, other.z)
      )

    return result

  # ---------------------------------------------------------------------
  def __ne__(self, other):
    """
    Check to see if this location are not equal to an other.

    Input:
      other: An other instance of Location to compare.

    Returns:
      False if equal, True if not.
    """

    result = True
    if isinstance(object, Location):
      result = (
        not MathExtra.isclose(self.x, other.x)
        or not MathExtra.isclose(self.y, other.y)
        or not MathExtra.isclose(self.z, other.z)
      )

    return result
