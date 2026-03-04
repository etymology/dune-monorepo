###############################################################################
# Name: DigitalOutput.py
# Uses: Abstract class defining functions digital outputs have.
# Date: 2016-02-02
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
from abc import ABCMeta, abstractmethod
from .DigitalIO import DigitalIO


class DigitalOutput(DigitalIO, metaclass=ABCMeta):
  # Make class abstract.
  output_instances: list["DigitalOutput"] = []
  name_to_output_map: dict[str, "DigitalOutput"] = {}

  _state = False

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
  def __init__(self, name, initialState=0):
    """
    Constructor.

    Args:
      name: Name of output.
      initialState: State output is assumed to be in on creation.

    """

    # Make sure this name isn't already in use.
    assert name not in DigitalOutput.output_instances

    DigitalIO.__init__(self, name)
    DigitalOutput.output_instances.append(self)
    DigitalOutput.name_to_output_map[name] = self

    self._state = initialState

  # ---------------------------------------------------------------------
  def setAll(self):
    """
    Set all outputs. Call after serial data has been initialized. Accounts for inversion.

    """

    for output in self.output_instances:
      output.set(output.get())

  # ---------------------------------------------------------------------
  @abstractmethod
  def _doSet(self):
    """
    Abstract function that must be define in child to preform output operations.

    Args:
      state: True for on, False for off.

    """

    pass

  # ---------------------------------------------------------------------
  def set(self, state):
    """
    Set the output to a given state.

    Args:
      state: True for on, False for off.

    """

    # Save the state for requests.
    self._state = state

    # Actually set the state.
    self._doSet(state)

  # ---------------------------------------------------------------------
  def _doGet(self):
    """
    Return current state of output.

    Returns:
      State of output. True of on, False for off.
    """

    return self._state


# end class
