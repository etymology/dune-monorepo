###############################################################################
# Name: ProductionIO.py
# Uses: Map of I/O used by machine.
# Date: 2016-04-21
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .base_io import BaseIO
from dune_winder.io.devices.plc_backend import create_plc_backend
from dune_winder.io.devices.plc_backend import normalize_plc_mode
from dune_winder.io.devices.plc_backend import normalize_plc_sim_engine


class ProductionIO(BaseIO):
  # ---------------------------------------------------------------------
  def __init__(
    self, plcAddress, plcMode="REAL", plcSimEngine="LEGACY", plcShadowMode=False
  ):
    """
    Constructor.
    Only need to create the correct type of PLC and call the base I/O
    constructor.
    """
    self.plcMode = normalize_plc_mode(plcMode)
    self.plcSimEngine = normalize_plc_sim_engine(plcSimEngine)
    plc = create_plc_backend(
      plcAddress,
      self.plcMode,
      plcSimEngine=self.plcSimEngine,
      plcShadowMode=bool(plcShadowMode),
    )
    BaseIO.__init__(self, plc)


# end class
