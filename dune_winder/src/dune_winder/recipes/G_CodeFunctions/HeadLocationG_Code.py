###############################################################################
# Name: HeadLocationG_Code.py
# Uses: G-Code to set the head location.
# Date: 2016-04-26
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .G_CodeFunction import G_CodeFunction
from dune_winder.machine.G_Codes import G_Codes


class HeadLocationG_Code(G_CodeFunction):
  """
  G-Code to set the Z latch position.
  """

  # Locations.
  FRONT = 0
  PARTIAL_FRONT = 1
  PARTIAL_BACK = 2
  BACK = 3

  # ---------------------------------------------------------------------
  def __init__(self, location):
    """
    Constructor.

    Args:
      location: Which side (FRONT/PARTIAL_FRONT/PARTIAL_BACK/BACK) to latch to.
    """
    G_CodeFunction.__init__(self, G_Codes.HEAD_LOCATION, [location])
