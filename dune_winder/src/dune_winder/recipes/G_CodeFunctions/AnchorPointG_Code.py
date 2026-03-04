###############################################################################
# Name: AnchorPointG_Code.py
# Uses: G-Code to specify anchor point of wire during move.
# Date: 2016-08-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .G_CodeFunction import G_CodeFunction
from dune_winder.machine.G_Codes import G_Codes


class AnchorPointG_Code(G_CodeFunction):
  """
  G-Code to specify anchor point of wire during move.
  """

  # ---------------------------------------------------------------------
  def __init__(self, pin, orientation=None):
    """
    Constructor.

    Args:
      pin: Anchor pin.
      orientation: Orientation of wire around pin.  0=None, TR/TL/RB/RT/BL/BR/LT/LB.
    """

    if orientation is None:
      orientation = "0"

    G_CodeFunction.__init__(self, G_Codes.ANCHOR_POINT, [pin, orientation])
