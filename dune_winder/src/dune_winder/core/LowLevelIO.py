###############################################################################
# Name: LowLevelIO.py
# Uses: Low-level I/O functions for use by GUI.
# Date: 2016-03-09
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   Designed to provide access to all the low-level primitive I/O lists.
###############################################################################

from dune_winder.io.Primitives.IO_Point import IO_Point
from dune_winder.io.Primitives.DigitalIO import DigitalIO
from dune_winder.io.Primitives.DigitalInput import DigitalInput
from dune_winder.io.Primitives.DigitalOutput import DigitalOutput
from dune_winder.io.Primitives.Motor import Motor
from dune_winder.io.Primitives.AnalogInput import AnalogInput
from dune_winder.io.Primitives.AnalogOutput import AnalogOutput
from dune_winder.io.Devices.PLC import PLC


class LowLevelIO:
  # ---------------------------------------------------------------------
  @staticmethod
  def _getIO_List(ioPoints: list[IO_Point]):
    """
    Get a list of each I/O point name and the current value.

    Args:
      ioList: List of I/O instances to fetch.

    Returns:
      A list of two lists.  The first element of sub-list is the I/O name and
      the second element is the I/O value.
    """
    result = []
    for ioPoint in ioPoints:
      result.append([ioPoint.getName(), ioPoint.get()])

    return result

  # ---------------------------------------------------------------------
  @staticmethod
  def getInputs():
    """
    Get a list of digital input in system.

    Returns:
      A list of two lists.  The first element of sub-list is the I/O name and
      the second element is the I/O value.
    """
    return LowLevelIO._getIO_List(DigitalInput.digital_input_instances)

  # ---------------------------------------------------------------------
  @staticmethod
  def getInput(name):
    """
    Retrieve the current state of a specific digital input by name.

    Args:
      name: Name of I/O point.

    Returns:
      Current value of requested I/O point.
    """
    return DigitalInput.digital_input_lookup[name].get()

  # ---------------------------------------------------------------------
  @staticmethod
  def getOutputs():
    """
    Get a list of every digital output in system.

    Returns:
      A list of two lists.  The first element of sub-list is the I/O name and
      the second element is the I/O value.
    """
    return LowLevelIO._getIO_List(DigitalOutput.output_instances)

  # ---------------------------------------------------------------------
  @staticmethod
  def getOutput(name):
    """
    Retrieve the current state of a specific digital output by name.

    Args:
      name: Name of I/O point.

    Returns:
      Current value of requested I/O point.
    """
    return DigitalOutput.name_to_output_map[name].get()

  # ---------------------------------------------------------------------
  @staticmethod
  def getTags():
    """
    Get a list of every PLC tag in system.

    Returns:
      A list of two lists.  The first element of sub-list is the tag name and
      the second element is the tag value.
    """
    tags = []
    result = []
    for tag in PLC.Tag.instances:
      name = tag.getName()
      if name not in tags:
        tags.append(name)
        result.append([name, tag.get()])

    return result

  # ---------------------------------------------------------------------
  @staticmethod
  def getTag(name):
    """
    Retrieve the current state of a specific PLC tag by name.

    Args:
      name: Name of PLC tag.

    Returns:
      Current value of tag.
    """
    return PLC.Tag.tag_lookup_table[name][0].get()

  # ---------------------------------------------------------------------
  @staticmethod
  def getAllDigitalIO():
    """
    Get a list of all digital I/O points in system.

    Returns:
      A list of two lists.  The first element of sub-list is the I/O name and
      the second element is the I/O value.
    """
    return LowLevelIO._getIO_List(DigitalIO.digital_i_o_instances)

  # ---------------------------------------------------------------------
  @staticmethod
  def getDigitalIO(name):
    """
    Retrieve the current state of a specific digital I/O by name.

    Args:
      name: Name of I/O point.

    Returns:
      Current value of requested I/O point.
    """
    return DigitalIO.lookup[name].get()

  # ---------------------------------------------------------------------
  @staticmethod
  def getAllIO():
    """
    Get a list of every I/O point in system.

    Returns:
      A list of two lists.  The first element of sub-list is the I/O name and
      the second element is the I/O value.
    """
    return LowLevelIO._getIO_List(IO_Point.io_point_instances)

  # ---------------------------------------------------------------------
  @staticmethod
  def getIO(name):
    """
    Retrieve the current state of a specific I/O point by name.

    Args:
      name: Name of I/O point.

    Returns:
      Current value of requested I/O point.
    """
    return IO_Point.lookup[name].get()

  # ---------------------------------------------------------------------
  @staticmethod
  def getMotors():
    """
    Get a list of every motor in system.

    Returns:
      A list of two lists.  The first element of sub-list is the motor name and
      the second element is a representation of the motor state.
    """
    return LowLevelIO._getIO_List(Motor.motor_instances)

  # ---------------------------------------------------------------------
  @staticmethod
  def getMotor(name):
    """
    Retrieve the current state of a specific motor by name.

    Args:
      name: Name of motor.

    Returns:
      String representation current of motor state.
    """
    return Motor.motor_instance_map[name].get()

  # ---------------------------------------------------------------------
  @staticmethod
  def getAnalogInputs():
    """
    Get a list of every analog input in system.

    Returns:
      A list of two lists.  The first element of sub-list is the I/O name and
      the second element is the I/O value.
    """
    return LowLevelIO._getIO_List(AnalogInput.input_instances)

  # ---------------------------------------------------------------------
  @staticmethod
  def getAnalogInput(name):
    """
    Retrieve the current state of a specific analog input by name.

    Args:
      name: Name of I/O point.

    Returns:
      Current value of requested I/O point.
    """
    return AnalogInput.input_lookup_table[name].get()

  # ---------------------------------------------------------------------
  @staticmethod
  def getAnalogOutputs():
    """
    Get a list of every analog output in system.

    Returns:
      A list of two lists.  The first element of sub-list is the I/O name and
      the second element is the I/O value.
    """
    return LowLevelIO._getIO_List(AnalogOutput.instances)

  # ---------------------------------------------------------------------
  @staticmethod
  def getAnalogOutput(name):
    """
    Retrieve the current state of a specific analog output by name.

    Args:
      name: Name of I/O point.

    Returns:
      Current value of requested I/O point.
    """
    return AnalogOutput.lookup[name].get()
