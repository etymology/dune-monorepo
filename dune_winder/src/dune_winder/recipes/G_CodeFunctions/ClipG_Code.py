###############################################################################
# Name: ClipG_Code.py
# Uses: G-Code to clip the position based on Z-transfer location.
# Date: 2016-03-31
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .G_CodeFunction import G_CodeFunction
from dune_winder.machine.G_Codes import G_Codes


class ClipG_Code(G_CodeFunction):
  """
  G-Code to clip the position based on Z-transfer location.
  """

  # ---------------------------------------------------------------------
  def __init__(self):
    """
    Constructor.
    """
    G_CodeFunction.__init__(self, G_Codes.CLIP, [])
