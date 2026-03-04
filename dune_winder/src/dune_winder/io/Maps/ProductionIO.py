###############################################################################
# Name: ProductionIO.py
# Uses: Map of I/O used by machine.
# Date: 2016-04-21
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.io.Devices.ControllogixPLC import ControllogixPLC
from .BaseIO import BaseIO


class ProductionIO(BaseIO):
  # ---------------------------------------------------------------------
  def __init__(self, plcAddress):
    """
    Constructor.
    Only need to create the correct type of PLC and call the base I/O
    constructor.
    """
    plc = ControllogixPLC(plcAddress)
    BaseIO.__init__(self, plc)


# end class
