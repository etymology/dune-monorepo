###############################################################################
# Name: G_CodeFunction.py
# Uses: Base object for a G-Code function.
# Date: 2016-03-23
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################


class G_CodeFunction:
  """
  Base object for a G-Code function.
  """

  # ---------------------------------------------------------------------
  def __init__(self, gCode, parameters=[]):
    """
    Constructor.

    Args:
      gCode: The G-Code function number (integer).
      parameters: A list of parameters for the function.
    """
    self._gCode = int(gCode)
    self._parameters = parameters

  # ---------------------------------------------------------------------
  def getParameter(self, index):
    """
    Return the parameter at the given index.

    Args:
      index: Which parameter to return.

    Returns:
      Parameter at the given index.
    """
    return self._parameters[index]

  # ---------------------------------------------------------------------
  def getFunction(self):
    """
    Get the G-Code function number.

    Returns:
      G-Code function number.
    """
    return self._gCode

  # ---------------------------------------------------------------------
  def toG_Code(self):
    """
    Translate object into G-Code text.

    Returns:
      String of G-Code text.
    """
    result = "G" + str(self._gCode)

    for parameter in self._parameters:
      result += " P" + str(parameter)

    return result
