###############################################################################
# Name: SerializableLocation.py
# Uses: Serializable version of Location.
# Date: 2016-04-19
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.library.Serializable import Serializable
from dune_winder.library.Geometry.Location import Location


class SerializableLocation(Location, Serializable):
  # ---------------------------------------------------------------------
  @staticmethod
  def fromLocation(location):
    result = SerializableLocation()
    result.x = location.x
    result.y = location.y
    result.z = location.z

    return result
