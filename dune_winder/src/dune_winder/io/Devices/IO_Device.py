###############################################################################
# Name: IO_Device.py
# Uses: Abstract class to describe an I/O device.
# Date: 2016-02-02
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   An I/O device is some system that contains one or more I/O points.
#   Examples include the PCF8575 I2C I/O expander, TLC5940 serial 16-channel
#   PWM chip, and MCP3008 SPI 8-channel 10-bit ADC.  Each of these chips
#   would have be an IO_Device child.
###############################################################################

from abc import ABCMeta, abstractmethod


class IO_Device(metaclass=ABCMeta):
  # Make class abstract.
  device_instances: list["IO_Device"] = []

  # ---------------------------------------------------------------------
  def __init__(self, name):
    """
    Constructor.

    Args:
      name: Name of IO device.

    """

    self._name = name
    IO_Device.device_instances.append(self)

  # ---------------------------------------------------------------------
  def getName(self):
    """
    Return the name of this instance.

    Returns:
      String name of this instance.
    """

    return self._name

  # ---------------------------------------------------------------------
  @abstractmethod
  def initialize(self):
    """
    Abstract method to initialize/reinitialize hardware.

    Returns:
      True if the initialization had an error, false if not.
    """

    return True

  # ---------------------------------------------------------------------
  @abstractmethod
  def isNotFunctional(self):
    """
    Abstract method to see if hardware is in working order.

    Returns:
      True there is a problem with hardware, false if not.
    """

    return True


# end class
