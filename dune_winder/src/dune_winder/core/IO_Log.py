###############################################################################
# Name: IO_LogThread.py
# Uses: System to log I/O.
# Date: 2016-03-03
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from dune_winder.io.Primitives.IO_Point import IO_Point
from dune_winder.io.Devices.PLC import PLC
import os.path


class IO_Log:
  # ---------------------------------------------------------------------
  def __init__(self, outputFileName):
    """
    Constructor.

    Args:
      outputFileName: Name of log file to create/append.
    """

    # Create the path if it does not exist.
    path = os.path.dirname(outputFileName)
    if path and not os.path.exists(path):
      os.makedirs(path)

    needsHeader = not os.path.isfile(outputFileName)
    self._outputFile = open(outputFileName, "a")

    if needsHeader:
      names = "Time\tLoop time\t"
      for ioPoint in IO_Point.io_point_instances:
        names += ioPoint.getName() + "\t"

      for tag in PLC.Tag.instances:
        names += tag.getName() + "\t"

      self._outputFile.write(names + "\n")

  # ---------------------------------------------------------------------
  def log(self, timeStamp, loopTime):
    """
    Add to log the current state of all I/O.

    Args:
      timeStamp: The current time (any string).
      loopTime: The time it took for the main-loop to run (in milliseconds).
    """
    result = str(timeStamp) + "\t" + str(loopTime) + "\t"
    for ioPoint in IO_Point.io_point_instances:
      result += str(ioPoint.get()) + "\t"

    for tag in PLC.Tag.instances:
      result += str(tag.get()) + "\t"

    self._outputFile.write(result + "\n")


# end class
