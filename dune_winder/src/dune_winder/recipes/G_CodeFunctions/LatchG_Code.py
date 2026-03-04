###############################################################################
# Name: LatchG_Code.py
# Uses: G-Code to set the Z latch position.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .G_CodeFunction import G_CodeFunction
from dune_winder.machine.G_Codes import G_Codes


class LatchG_Code(G_CodeFunction):
  """
  G-Code to toggle the latch.
  """

  # ---------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.

    Args:
      side: Which side (FRONT/PARTIAL_FRONT/PARTIAL_BACK/BACK) to latch to.
    """
    G_CodeFunction.__init__(self, G_Codes.LATCH, [])
