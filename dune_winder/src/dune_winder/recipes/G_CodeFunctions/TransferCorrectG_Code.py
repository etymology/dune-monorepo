###############################################################################
# Name: TransferCorrectG_Code.py
# Uses: G-Code to
# Date: 2016-09-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .G_CodeFunction import G_CodeFunction
from dune_winder.machine.G_Codes import G_Codes


class TransferCorrectG_Code(G_CodeFunction):
  """
  G-Code to
  """

  # ---------------------------------------------------------------------
  def __init__(self, axis):
    """
    Constructor.

    Args:
      axis: The axis to make correction (X or Y).
    """
    G_CodeFunction.__init__(self, G_Codes.TRANSFER_CORRECT, [axis])
