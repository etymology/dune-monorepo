###############################################################################
# Name: ControllogixPLC.py
# Uses: Functions for communicating to Allen-Bradley Controllogix PLC.
# Date: 2016-02-10
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#     The Controllogix PLC provides access to I/O through "tags".  Tags are
#   text names.  Communications to the PLC is done over an Ethernet connection
#   using Common Industrial Protocol (CIP) which specifies how tags are read
#   and written.  The library "pycomm" handles the CIP connection and this
#   class provides the I/O device.
###############################################################################

from .plc import PLC
import threading


class ControllogixPLC(PLC):
  # ---------------------------------------------------------------------
  def initialize(self):
    """
    Try and establish a connection to the PLC.

    Returns:
      True if there was an error, False if connection was made.
    """
    self._lock.acquire()
    isFunctional = True
    try:
      # Attempt to open a connection to PLC if plcDriver is not already connected.
      isOk = True
      if not self._plcDriver.connected:
        isOk = self._plcDriver.open()
      if not isOk:
        isFunctional = False
    except Exception:
      isFunctional = False

    self._isFunctional = isFunctional
    if not self._isFunctional:
      self._plcDriver.close()

    self._lock.release()

    return self._isFunctional

  # ---------------------------------------------------------------------
  def isNotFunctional(self):
    """
    See if the PLC is communicating correctly.

    Returns:
      True there is a problem with hardware, false if not.
    """
    return not self._isFunctional

  # ---------------------------------------------------------------------
  def read(self, tag):
    """
    Read a tag(s) from the PLC.

    Args:
      tag: A single or a list of PLC tags.

    Returns:
      Result of the data read, or None if there was a problem.
    """

    self._lock.acquire()
    result = None

    if self._isFunctional:
      try:
        result = self._plcDriver.read(*tag)
        if result is not None and not isinstance(result, list):
          result = [result]
      except Exception:
        # If tag reading threw an exception, the connection is dead.
        self._isFunctional = False

    self._lock.release()

    return result

  # ---------------------------------------------------------------------
  def write(self, tag, data=None, typeName=None):
    """
    Write a tag(s) to the PLC.

    Args:
      tag: A single or a list of PLC tags.
      data: Data to be written.
      typeName: Type of the tag to write.

    Returns:
        None is returned in case of error otherwise the tag list is returned.
    """

    self._lock.acquire()
    result = None
    if self._isFunctional:
      try:
        result = self._plcDriver.write(tag)
      except Exception as e:
        print(e)
        # If tag writting threw an exception, the connection is dead.
        self._isFunctional = False

    self._lock.release()
    return result

  # ---------------------------------------------------------------------
  def __init__(self, ipAddress):
    """
    Constructor.

    Args:
      ipAddress: IP address of PLC to communicate with.
    """
    # Use logger only for DEBUG
    # configure_default_logger(level="ERROR", filename='C:/dune/bin/T05-Winder-test/src/winder/pycomm3.log')
    try:
      from pycomm3 import LogixDriver as ClxDriver
    except Exception as exception:
      raise RuntimeError(
        "pycomm3 is required for PLC REAL mode. Install pycomm3 or use PLC_MODE=SIM."
      ) from exception

    self._ipAddress = ipAddress
    self._plcDriver = ClxDriver(self._ipAddress)
    self._isFunctional = False
    self._lock = threading.Lock()
    self.initialize()


# end class
