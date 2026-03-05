###############################################################################
# Name: UI_ServerThread.py
# Uses: User Interface server thread.
# Date: 2016-02-03
# Author(s):
#   Andrew Que <aque@bb7.com>
# Notes:
#   The user interface server is a TCP socket that accepts commands and
#   dispatches these commands to a handler.  The handler processes the command
#   and returns results which are then sent back to the client.
###############################################################################
from dune_winder.threads.primary_thread import PrimaryThread
from dune_winder.machine.settings import Settings
import select
import socket
import threading  # For additional threads.


# ------------------------------------------------------------------------------
# Thread to handle an individual connection from a client socket.
# ------------------------------------------------------------------------------
class _CommandClientThread(threading.Thread):
  # ---------------------------------------------------------------------
  def __init__(self, client_connection, command_callback, log):
    """
    Constructor.

    Args:
      clientSocket: Connection to client.
      address: Address of client (ignored)
      command_callback: Function to send data from client. What the callback
        returns is then sent back to client.

    """
    clientSocket, address = client_connection
    threading.Thread.__init__(self)

    _ = address
    self._socket = clientSocket
    self._callback = command_callback
    self._log = log
    self.start()

  # ---------------------------------------------------------------------
  def run(self):
    """
    Handle request from client.

    """
    (address, port) = self._socket.getpeername()

    self._log.add(
      self.__class__.__name__,
      "UI_CONNECT",
      "Connection from " + str(address) + ":" + str(port) + " established.",
      [address, port],
    )

    isRunning = True
    while isRunning:
      try:
        # Get the client request.
        requestData = self._socket.recv(Settings.SERVER_MAX_DATA_SIZE)
      except Exception:
        # If there was a problem it is probably because the socket was
        # closed.  Just shutdown the client thread.
        isRunning = False

      # Did we get anything?
      if isRunning and not "" == requestData:
        # Process the request.
        responseText = str(self._callback(None, requestData))

        # Break sting into chunks that are no larger than
        # Settings.SERVER_MAX_DATA_SIZE characters.
        chunks = [
          responseText[index : index + Settings.SERVER_MAX_DATA_SIZE]
          for index in range(0, len(responseText), Settings.SERVER_MAX_DATA_SIZE)
        ]

        # Send each chunk of data.
        chunkSize = 0
        for responseChunk in chunks:
          # Send the results back to client.
          self._socket.send(responseChunk)
          chunkSize = len(responseChunk)

        # If the last chunk was either empty or exactly the max data size, send
        # a blank line as the client will expect at least/one more packet.
        if Settings.SERVER_MAX_DATA_SIZE == chunkSize or 0 == chunkSize:
          self._socket.send("")

      else:
        # If there is no data, it is also an indication the socket was closed.
        isRunning = False

    # End the connection.
    self._socket.close()

    self._log.add(
      self.__class__.__name__,
      "UI_CONNECT",
      "Connection from " + str(address) + ":" + str(port) + " closed.",
      [address, port],
    )


# end class


# ------------------------------------------------------------------------------
# User interface server thread.
# ------------------------------------------------------------------------------
class UICommandServerThread(PrimaryThread):
  # ---------------------------------------------------------------------
  def __init__(self, commandCallback, log):
    """
    Constructor.

    Args:
      callback: Function to send data from client.

    """

    PrimaryThread.__init__(self, "UICommandServerThread", log)
    self._callback = commandCallback
    self._log = log

  # ---------------------------------------------------------------------
  def body(self):
    """
    Body of thread. Accepts client connections and spawns threads to deal with client requests.

    """

    # Assume all is well.
    isError = False

    # Attempt to open a listening socket...
    serverSocket = None
    try:
      serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      serverSocket.bind(("", Settings.SERVER_PORT))
      serverSocket.listen(Settings.SERVER_BACK_LOG)
    except socket.error:
      # Unable to open listening socket.
      isError = True
      if serverSocket:
        serverSocket.close()

    # If all went alright...
    if not isError:
      # While the system is running...
      while PrimaryThread.isRunning:
        # Wait for a connection, or 100 ms.
        inputReady, _, _ = select.select([serverSocket], [], [], 0.1)

        # For all the results the unblocked...
        for readySource in inputReady:
          # Was the source our server getting a connection?
          if readySource == serverSocket:
            # Start a thread to deal with this client
            _CommandClientThread(serverSocket.accept(), self._callback, self._log)
        # end for

      # end while

    # Close server socket.
    serverSocket.close()


# end class

