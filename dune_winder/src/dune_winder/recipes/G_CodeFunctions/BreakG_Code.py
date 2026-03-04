###############################################################################
# Name: BreakG_Code.py
# Uses: G-Code to stop G-Code execution (break-point).
# Date: 2016-10-14
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .G_CodeFunction import G_CodeFunction
from dune_winder.machine.G_Codes import G_Codes


class BreakG_Code(G_CodeFunction):
  """
  G-Code to toggle the latch.
  """

  # ---------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """
    G_CodeFunction.__init__(self, G_Codes.BREAK_POINT, [])
