###############################################################################
# Name: PLC_Input.py
# Uses: Digital input from a PLC.
# Date: 2016-02-22
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.io.Primitives.digital_input import DigitalInput
from dune_winder.io.Devices.plc import PLC


class PLC_Input(DigitalInput):
  input_instances: list["PLC_Input"] = []

  # ---------------------------------------------------------------------
  def __init__(
    self, name, plc, tagName=None, bit=0, defaultState=False, tagType="DINT"
  ):
    """
    Constructor.

    Args:
      name: Name of output.
      plc: Instance of IO_Device.PLC.
      tagName: Which PLC tag this input is assigned.  Default is None for when
        the tag and name are the same.
      bit: Which bit of the tag.  Defaults to bit 0.
      defaultState: Default state if input is unreadable.
      tagType: Tag data type.  Default is "DINT".
    """
    DigitalInput.__init__(self, name)
    PLC_Input.input_instances.append(self)

    # Just use the name for the tag?
    if tagName is None:
      tagName = name

    self._plc = plc
    attributes = PLC.Tag.Attributes()
    attributes.canWrite = False
    attributes.defaultValue = defaultState
    attributes.isPolled = True
    self._tag = plc.Tag(plc, tagName, attributes, tagType)

    self._bit = bit
    self._defaultState = defaultState
    self._state = defaultState

  # ---------------------------------------------------------------------
  def _doGet(self):
    """
    Fetch state of input.

    Returns:
      Returns whatever was passes as the initial state.

    Note:
      Does not reflect any useful value until polled.  If the PLC isn't
      functional, this value returns a default value.
    """
    value = self._tag.get()
    if value is not None:
      value = int(value)
      value >>= self._bit
      value &= 0x01
      value = bool(value == 1)
    else:
      value = self._defaultState

    return value


# end class
