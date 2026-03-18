###############################################################################
# Name: metrics_thread.py
# Uses: Prometheus-compatible metrics HTTP endpoint thread.
#
# Serves GET /metrics in Prometheus text format 0.0.4.
# Uses only stdlib — no extra dependencies.
###############################################################################

from http.server import BaseHTTPRequestHandler, HTTPServer

from dune_winder.threads.primary_thread import PrimaryThread
from dune_winder.machine.settings import Settings
from dune_winder.core.metrics_collector import MetricsCollector


class MetricsThread(PrimaryThread):
  # -------------------------------------------------------------------------
  def __init__(self, collector: MetricsCollector, log):
    PrimaryThread.__init__(self, "MetricsThread", log)
    self._collector = collector
    self._httpd = None

  # -------------------------------------------------------------------------
  def body(self):
    collector = self._collector

    class _Handler(BaseHTTPRequestHandler):
      def do_GET(self):
        if self.path != "/metrics":
          self.send_response(404)
          self.end_headers()
          return

        body = collector.render_prometheus().encode("utf-8")
        self.send_response(200)
        self.send_header(
          "Content-Type",
          "text/plain; version=0.0.4; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

      def log_message(self, fmt, *args):  # suppress access log noise
        pass

    self._httpd = HTTPServer(("", Settings.METRICS_PORT), _Handler)
    self._httpd.timeout = 0.1

    try:
      while PrimaryThread.isRunning:
        self._httpd.handle_request()
    finally:
      if self._httpd is not None:
        self._httpd.server_close()
        self._httpd = None

  # -------------------------------------------------------------------------
  def stop(self):
    if self._httpd is not None:
      self._httpd.timeout = 0.0


# end class
