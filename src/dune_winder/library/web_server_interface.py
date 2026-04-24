###############################################################################
# Name: WebServerInterface.py
# Uses: Web interface to remote system.
# Date: 2016-04-29
# Author(s):
#   Andrew Que <aque@bb7.com>
###############################################################################
import json

from http.server import HTTPServer
from http.server import SimpleHTTPRequestHandler
from dune_winder.library.json import dumps as jsonDumps


class WebServerInterface(SimpleHTTPRequestHandler):
  commandRegistry = None
  log = None

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
    All paths are handled by SimpleHTTPRequestHandler as static files.
    """
    super().do_GET()

  # ---------------------------------------------------------------------
  def do_POST(self):
    """
    Callback for an HTTP POST request.
    This will process all requests for data.
    """

    # Get post data length.
    length = int(self.headers.get("content-length", "0"))

    path = self.path.split("?")[0]
    if path not in ("/api/v2/command", "/api/v2/batch"):
      response = {
        "ok": False,
        "data": None,
        "error": {"code": "BAD_REQUEST", "message": "Unsupported POST path."},
      }
      self._sendJsonResponse(response, {}, statusCode=404)
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
      response = WebServerInterface.commandRegistry.executeRequest(payload)
    else:
      response = WebServerInterface.commandRegistry.executeBatchRequest(payload)

    statusCode = 200
    if not response.get("ok"):
      statusCode = WebServerInterface._statusCodeFromError(response.get("error"))

    self._sendJsonResponse(response, {}, statusCode=statusCode)


# end class

if __name__ == "__main__":
  server_address = ("", 80)
  httpd = HTTPServer(server_address, WebServerInterface)

  print("Starting httpd...")
  while True:
    httpd.handle_request()


