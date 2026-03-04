###############################################################################
# Name: PinCenterG_Code.py
# Uses: G-Code for seeking between two pins.
# Date: 2016-03-31
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .G_CodeFunction import G_CodeFunction
from dune_winder.machine.G_Codes import G_Codes


class PinCenterG_Code(G_CodeFunction):
  """
  G-Code for seeking between two pins.
  """

  # ---------------------------------------------------------------------
  def __init__(self, pins, axises="XY"):
    """
    Constructor.

    Args:
      pins: List of two pins.
    """
    pins.append(axises)
    G_CodeFunction.__init__(self, G_Codes.PIN_CENTER, pins)
