###############################################################################
# Name: SerializableLocation.py
# Uses: Location subclass used by calibration classes.
# Date: 2016-04-19
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.Geometry.location import Location


class SerializableLocation(Location):
  # ---------------------------------------------------------------------
  @staticmethod
  def fromLocation(location):
    result = SerializableLocation()
    result.x = location.x
    result.y = location.y
    result.z = location.z

    return result
