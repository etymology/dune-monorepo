###############################################################################
# Name: OffsetG_Code.py
# Uses: G-Code to offset current position.
# Date: 2016-04-01
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .G_CodeFunction import G_CodeFunction
from dune_winder.machine.G_Codes import G_Codes


class OffsetG_Code(G_CodeFunction):
  """
  G-Code to offset current position.
  """

  # ---------------------------------------------------------------------
  def __init__(self, x=None, y=None, z=None):
    """
    Constructor.

    Args:
      pins: List of two pins.
    """
    parameters = []
    if x is not None:
      parameters.append("X" + str(x))

    if y is not None:
      parameters.append("Y" + str(y))

    if z is not None:
      parameters.append("Z" + str(z))

    G_CodeFunction.__init__(self, G_Codes.OFFSET, parameters)
