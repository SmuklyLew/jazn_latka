"""Local daemon probes must not inherit system HTTP proxy settings."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from latka_jazn.core.runtime_daemon import http_json


def test_health_check_ignores_proxy_for_loopback(monkeypatch) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"ok": True, "active_state": "active_trusted"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setattr("urllib.request.proxy_bypass", lambda _host: False)
        payload = http_json("GET", f"http://127.0.0.1:{server.server_port}/live", timeout=1.5)
        assert payload["ok"] is True
        assert payload["active_state"] == "active_trusted"
    finally:
        server.shutdown()
        worker.join(timeout=3)
        server.server_close()
