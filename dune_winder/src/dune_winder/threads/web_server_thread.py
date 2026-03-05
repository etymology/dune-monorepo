###############################################################################
# Name: WebServerThread.py
# Uses: Web based user interface server thread.
# Date: 2016-05-02
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
from http.server import HTTPServer
from socketserver import ThreadingMixIn
import os

from dune_winder.threads.primary_thread import PrimaryThread
from dune_winder.machine.settings import Settings
from dune_winder.library.web_server_interface import WebServerInterface


class WebServerThread(PrimaryThread):
  # ---------------------------------------------------------------------
  def __init__(self, log, commandRegistry):
    """
    Constructor.

    Args:
      log: Logger instance.
      commandRegistry: API command registry.
    """

    os.chdir(Settings.WEB_DIRECTORY)

    PrimaryThread.__init__(self, "WebServerThread", log)
    self._commandRegistry = commandRegistry
    self._log = log
    self._httpd = None

  # ---------------------------------------------------------------------
  def body(self):
    """
    Body of thread. Accepts client connections and swans threads to deal with client requests.
    """

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
      """Handle requests in a separate thread."""

      pass

    WebServerInterface.commandRegistry = self._commandRegistry
    WebServerInterface.log = self._log
    server_address = ("", Settings.WEB_SERVER_PORT)
    self._httpd = ThreadedHTTPServer(server_address, WebServerInterface)
    self._httpd.timeout = 0.1

    try:
      while PrimaryThread.isRunning:
        self._httpd.handle_request()
    finally:
      if self._httpd is not None:
        self._httpd.server_close()
        self._httpd = None

  # ---------------------------------------------------------------------
  def stop(self):
    """
    Send a dummy request to server to cause connection to close.
    """
    # The HTTP server polls with a short timeout, so shutdown does not need
    # a synthetic loopback request.
    if self._httpd is not None:
      self._httpd.timeout = 0.0


# end class
