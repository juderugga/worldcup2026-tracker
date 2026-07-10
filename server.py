#!/usr/bin/env python3
"""
FIFA World Cup 2026 Tracker - Local Server (Python edition)
-----------------------------------------------------------
A zero-dependency replacement for proxy.js. Uses only the Python 3
standard library, so it runs on a stock Ubuntu install with no
`npm install` and no Node.js required.

Three jobs:
  1. Serves worldcup2026.html at http://localhost:3001/
  2. Serves matchdata.json at /local-data (scores, scorers, stats)
  3. Forwards /api/* to football-data.org for live scores

HOW TO RUN:
    python3 server.py

Then open http://localhost:3001/ in your browser.
Press Ctrl+C to stop.
"""

import http.server
import json
import os
import socketserver
import urllib.request
import urllib.error

HERE      = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(HERE, "matchdata.json")
HTML_FILE = os.path.join(HERE, "worldcup2026.html")

PORT      = 3001
API_TOKEN = "9d424744f5934fbc9ec3b8a4cae44749"
API_HOST  = "api.football-data.org"
API_BASE  = "/v4"


class Handler(http.server.BaseHTTPRequestHandler):
    # quieter logging
    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Auth-Token")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self._send_json(404, {"error": os.path.basename(path) + " not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        # The tracker page itself
        if path in ("/", "/index.html", "/worldcup2026.html"):
            self._send_file(HTML_FILE, "text/html; charset=utf-8")
            return

        # Local match data
        if path == "/local-data":
            self._send_file(DATA_FILE, "application/json")
            return

        # Favicon / app icon
        if path in ("/icon.svg", "/favicon.ico", "/favicon.svg"):
            self._send_file(os.path.join(HERE, "icon.svg"), "image/svg+xml")
            return

        # Health check
        if path == "/health":
            self._send_json(200, {"status": "ok", "message": "WC2026 server running"})
            return

        # Forward /api/* to football-data.org
        if path.startswith("/api"):
            self._forward()
            return

        self._send_json(404, {"error": "Not found. Use /api/... or /local-data"})

    def _forward(self):
        forward_path = API_BASE + self.path[len("/api"):]
        url = "https://" + API_HOST + forward_path
        req = urllib.request.Request(url, headers={
            "X-Auth-Token": API_TOKEN,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
                code = resp.getcode()
        except urllib.error.HTTPError as e:
            body = e.read()
            code = e.code
        except Exception as e:  # noqa: BLE001
            self._send_json(502, {"error": "Proxy error: " + str(e)})
            return
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(body)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    try:
        httpd = Server(("127.0.0.1", PORT), Handler)
    except OSError as e:
        print("\n  \u2717 Could not start on port %d: %s" % (PORT, e))
        print("  Another copy may already be running.\n")
        raise SystemExit(1)

    print("")
    print("  \u26bd  FIFA World Cup 2026 Server (Python)")
    print("  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
    print("  Open: http://localhost:%d/" % PORT)
    print("  Press Ctrl+C to stop.")
    print("")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopping. Goodbye!")
        httpd.shutdown()


if __name__ == "__main__":
    main()
