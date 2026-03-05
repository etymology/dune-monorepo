###############################################################################
# Name: AnalogInput.py
# Uses: Abstract class for analog inputs.
# Date: 2016-02-02
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .io_point import IO_Point


class AnalogInput(IO_Point):
  # Static list of all analog inputs.
  input_instances: list["AnalogInput"] = []
  input_lookup_table: dict[str, "AnalogInput"] = {}

  # ---------------------------------------------------------------------
  def __init__(self, name):
    """
    Constructor.

    Args:
      name: Name of input.
      isListed: True if analog input should show up in list.

    """

    # Make sure this name isn't already in use.
    assert name not in AnalogInput.input_instances

    IO_Point.__init__(self, name)

    AnalogInput.input_instances.append(self)
    AnalogInput.input_lookup_table[name] = self

  # ---------------------------------------------------------------------
  def __str__(self):
    """
    Convert level to string.

    Returns:
      String of the level.
    """

    return str(self.get())


# end class
