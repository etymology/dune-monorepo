###############################################################################
# Name: DigitalInput.py
# Uses: Abstract class to define digital inputs.
# Date: 2016-02-02
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .DigitalIO import DigitalIO


class DigitalInput(DigitalIO):
  # Static list of all digital inputs, and map of names to instances.
  digital_input_instances: list["DigitalInput"] = []
  digital_input_lookup: dict[str, "DigitalInput"] = {}

  # ---------------------------------------------------------------------
  def __str__(self):
    """
    Convert state to string.

    Returns:
      "1" for on, "0" for off.
    """

    result = "0"
    if self.get():
      result = "1"

    return result

  # ---------------------------------------------------------------------
  def __init__(self, name):
    """
    Constructor.

    Args:
      name: Name of input.

    """

    # Make sure this name isn't already in use.
    assert name not in DigitalInput.digital_input_instances

    DigitalIO.__init__(self, name)
    DigitalInput.digital_input_instances.append(self)
    DigitalInput.digital_input_lookup[name] = self


# end class
