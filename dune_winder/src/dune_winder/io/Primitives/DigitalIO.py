###############################################################################
# Name: DigitalIO.py
# Uses: Abstract class used for all digital I/O.
# Date: 2016-02-02
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################

from .IO_Point import IO_Point
from abc import ABCMeta, abstractmethod


class DigitalIO(IO_Point, metaclass=ABCMeta):
  # Make class abstract.
  digital_i_o_instances: list["DigitalIO"] = []

  # Software overrides of state.
  _isForced = False
  _forcedState = False

  # ---------------------------------------------------------------------
  def __init__(self, name):
    """
    Constructor.

    Args:
      name: Name of input.

    """

    # Make sure this name isn't already in use.
    assert name not in DigitalIO.digital_i_o_instances

    IO_Point.__init__(self, name)

    DigitalIO.digital_i_o_instances.append(self)
    DigitalIO.lookup[name] = self

  # ---------------------------------------------------------------------
  @abstractmethod
  def _doGet(self):
    """
    Abstract function that must be define in the child class that will return the state of this input.

    Returns:
      Current state of input.
    """

    pass

  # ---------------------------------------------------------------------
  def get(self):
    """
    Get the state of the input.

    Returns:
      Current state of input.
    """

    result = self._doGet()

    if self._isForced:
      result = self._forcedState

    return result

  # ---------------------------------------------------------------------
  def force(self, state):
    """
    Force the software to see an input in the specified state. Debug function only!

    Args:
      state: State that will be returned by input.

    """

    self._isForced = True
    self._forcedState = state

  # ---------------------------------------------------------------------
  def unforce(self):
    """
    Release forced state. Debug function only!

    """

    self._isForced = False

  #   Returns True if the inputs are being forced to a state rather than
  #   reporting their True value.
  @property
  def isForced(self):
    return self._isForced

  #   Returns the forced state of the input.  Does not reflect if this
  #   state is being used or not.
  @property
  def forcedState(self):
    return self._forcedState

  # ---------------------------------------------------------------------
  def forceUpdate(self):
    """
    Force this I/O point to update. Some I/O update immediately while others have buffers. Those that are buffered must override this function to flush the buffer.

    Returns:
      True if the update took place correctly.
    """

    # By default the update is assumed to have happened.
    return True


# end class
