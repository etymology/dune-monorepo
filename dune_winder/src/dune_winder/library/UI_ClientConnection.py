###############################################################################
# Name: UI_ClientConnection.py
# Uses: Socket interface to remote system.
# Date: 2016-02-11
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import socket


class UI_ClientConnection:
  # ---------------------------------------------------------------------
  def __init__(self, address, port, maxReceiveSize):
    """
    Constructor.

    Args:
      address - Address of server.
      port - Port of server.
      maxReceiveSize - Largest packet that can be read.
    """

    self._connection = socket.socket()
    self._connection.connect((address, port))
    self._maxReceiveSize = maxReceiveSize

  # ---------------------------------------------------------------------
  def get(self, command):
    """
    Fetch data from remote server.

    Args:
      command: A command to execute on remote server.

    Returns:
      The results of the command to remote server.
    """

    self._connection.send(command)

    # Read results.
    # The maximum amount of data that can be read at once is
    # self._maxReceiveSize.  If we receive that amount, assume there is more.
    # Keep reading until the size of the received data is not
    # self._maxReceiveSize.
    result = ""
    chunkSize = self._maxReceiveSize
    while self._maxReceiveSize == chunkSize:
      subString = self._connection.recv(self._maxReceiveSize)
      chunkSize = len(subString)
      result += subString

    return result

  # ---------------------------------------------------------------------
  def __call__(self, command):
    """
    Emulating callable object is mapped to the "get" function.

    Args:
      command: A command to execute on remote server.

    Returns:
      The results of the command to remote server.
    """

    return self.get(command)
