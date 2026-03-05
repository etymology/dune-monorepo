###############################################################################
# Name: WebServerInterface.py
# Uses: Web interface to remote system.
# Date: 2016-04-29
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import urllib.request
import urllib.error
import json
import re

from http.server import HTTPServer
from http.server import SimpleHTTPRequestHandler
from dune_winder.library.remote_session import RemoteSession
from dune_winder.library.json import dumps as jsonDumps


class WebServerInterface(SimpleHTTPRequestHandler):
  # $$$FUTURE - If we decide to use authentication, this must change.
  BYPASS_AUTHENTICATION = True

  commandRegistry = None
  log = None

  # ---------------------------------------------------------------------
  @staticmethod
  def _cookieData(headers):
    cookies = {}
    if "Cookie" in headers:
      cookieData = headers["Cookie"]
      cookieData = cookieData.split("; ")
      for cookie in cookieData:
        if "=" in cookie:
          cookieName, cookieValue = cookie.split("=", 1)
          cookies[cookieName] = cookieValue
    return cookies

  # ---------------------------------------------------------------------
  @staticmethod
  def _setupSession(headers, clientAddress):
    cookies = WebServerInterface._cookieData(headers)

    # Get session identification.
    sessionId = None
    if "sessionId" in cookies:
      sessionId = cookies["sessionId"]

    # Find or create session.
    session = RemoteSession.sessionSetup(sessionId)
    sessionId = session.getId()
    cookies["sessionId"] = sessionId

    # If the client address is a loop-back (i.e. the local machine) then
    # it by default is authenticated.
    if (
      re.search(r"127\.[0-9]+\.[0-9]+\.[0-9]+", clientAddress)
      or WebServerInterface.BYPASS_AUTHENTICATION
    ):
      session.setAuthenticated(True)

    # Check to see if session is authenticated.
    isAuthenticated = session.getAuthenticated()
    return session, cookies, isAuthenticated

  # ---------------------------------------------------------------------
  @staticmethod
  def _statusCodeFromError(error):
    if not error or "code" not in error:
      return 500

    code = str(error["code"])
    if code in ("BAD_REQUEST", "VALIDATION_ERROR"):
      return 400
    if code == "UNAUTHORIZED":
      return 401
    if code == "UNKNOWN_COMMAND":
      return 404
    if code == "INTERNAL_ERROR":
      return 500
    return 400

  # ---------------------------------------------------------------------
  def _sendJsonResponse(self, responseBody, cookies, statusCode=200):
    self.send_response(statusCode)

    for cookieName in cookies:
      cookieValue = str(cookies[cookieName])
      cookieData = cookieName + "=" + cookieValue
      self.send_header("Set-Cookie", cookieData)

    self.send_header("Content-type", "application/json")
    self.end_headers()
    self.wfile.write(jsonDumps(responseBody).encode("utf-8"))

  # ---------------------------------------------------------------------
  def log_message(self, *_):
    """
    Empty function to disable log messages.
    """
    pass

  # ---------------------------------------------------------------------
  def do_GET(self):
    """
    Callback for an HTTP GET request.
    Intercepts /camera_image to proxy the camera's FTP image as HTTP so that
    the browser can load it (browsers no longer support ftp:// in <img> tags).
    All other paths are handled by SimpleHTTPRequestHandler as static files.
    """
    if self.path.split("?")[0] == "/camera_image":
      try:
        if WebServerInterface.commandRegistry is None:
          raise RuntimeError("Command registry is not configured.")

        commandResult = WebServerInterface.commandRegistry.execute(
          "process.get_camera_image_url", {}, isAuthenticated=True
        )
        if not commandResult.get("ok", False):
          raise RuntimeError("Camera URL command failed.")

        camera_url = commandResult.get("data")
        with urllib.request.urlopen(camera_url, timeout=3) as response:
          data = response.read()
        self.send_response(200)
        self.send_header("Content-Type", "image/bmp")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)
      except Exception:
        self.send_response(503)
        self.end_headers()
      return
    super().do_GET()

  # ---------------------------------------------------------------------
  def do_POST(self):
    """
    Callback for an HTTP POST request.
    This will process all requests for data.
    """

    # Get post data length.
    length = int(self.headers.get("content-length", "0"))

    clientAddress = self.client_address[0]
    _session, cookies, isAuthenticated = WebServerInterface._setupSession(
      self.headers, clientAddress
    )

    path = self.path.split("?")[0]
    if path not in ("/api/v2/command", "/api/v2/batch"):
      response = {
        "ok": False,
        "data": None,
        "error": {"code": "BAD_REQUEST", "message": "Unsupported POST path."},
      }
      self._sendJsonResponse(response, cookies, statusCode=404)
      return

    payload = None
    if length > 0:
      try:
        body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(body)
      except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None

    if payload is None:
      response = {
        "ok": False,
        "data": None,
        "error": {"code": "BAD_REQUEST", "message": "Invalid JSON request body."},
      }
    elif WebServerInterface.commandRegistry is None:
      response = {
        "ok": False,
        "data": None,
        "error": {
          "code": "INTERNAL_ERROR",
          "message": "Command registry is not configured.",
        },
      }
    elif path == "/api/v2/command":
      response = WebServerInterface.commandRegistry.executeRequest(
        payload, isAuthenticated=isAuthenticated
      )
    else:
      response = WebServerInterface.commandRegistry.executeBatchRequest(
        payload, isAuthenticated=isAuthenticated
      )

    statusCode = 200
    if not response.get("ok"):
      statusCode = WebServerInterface._statusCodeFromError(response.get("error"))

    self._sendJsonResponse(response, cookies, statusCode=statusCode)


# end class

if __name__ == "__main__":
  server_address = ("", 80)
  httpd = HTTPServer(server_address, WebServerInterface)

  print("Starting httpd...")
  while True:
    httpd.handle_request()
