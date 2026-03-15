###############################################################################
# Name: ProductionIO.py
# Uses: Map of I/O used by machine.
# Date: 2016-04-21
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .base_io import BaseIO


def normalize_plc_mode(plcMode):
  mode = str(plcMode).strip().upper()
  if mode not in ("REAL", "SIM"):
    raise ValueError("PLC mode must be REAL or SIM.")
  return mode


def create_plc_backend(plcAddress, plcMode="REAL"):
  mode = normalize_plc_mode(plcMode)
  if mode == "SIM":
    from dune_winder.io.devices.simulated_plc import SimulatedPLC

    return SimulatedPLC(plcAddress)

  from dune_winder.io.devices.controllogix_plc import ControllogixPLC

  return ControllogixPLC(plcAddress)


class ProductionIO(BaseIO):
  # ---------------------------------------------------------------------
  def __init__(self, plcAddress, plcMode="REAL"):
    """
    Constructor.
    Only need to create the correct type of PLC and call the base I/O
    constructor.
    """
    self.plcMode = normalize_plc_mode(plcMode)
    plc = create_plc_backend(plcAddress, self.plcMode)
    BaseIO.__init__(self, plc)


# end class
