from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import threading
import urllib.request

import pytest

from latka_jazn.core.loopback_proxy import (
    LOOPBACK_PROXY_BYPASS_HOSTS,
    ensure_loopback_proxy_bypass,
)
from latka_jazn.core.runtime_daemon import http_json


def _items(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def test_loopback_proxy_bypass_preserves_existing_entries_and_case_variants() -> None:
    env = {
        "NO_PROXY": "example.com,LOCALHOST",
        "no_proxy": "internal.test,example.com",
    }

    result = ensure_loopback_proxy_bypass(env)

    assert result["NO_PROXY"] == result["no_proxy"]
    assert env["NO_PROXY"] == env["no_proxy"]
    assert _items(env["NO_PROXY"]) == [
        "example.com",
        "LOCALHOST",
        "internal.test",
        "127.0.0.1",
        "::1",
    ]


def test_loopback_proxy_bypass_is_idempotent() -> None:
    env: dict[str, str] = {}

    first = ensure_loopback_proxy_bypass(env)
    second = ensure_loopback_proxy_bypass(env)

    assert first == second
    assert _items(env["NO_PROXY"]) == list(LOOPBACK_PROXY_BYPASS_HOSTS)


def test_wildcard_no_proxy_is_preserved() -> None:
    env = {"NO_PROXY": "*"}

    result = ensure_loopback_proxy_bypass(env)

    assert result == {"NO_PROXY": "*", "no_proxy": "*"}


def test_runtime_http_json_reaches_loopback_with_dead_proxy_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b'{"ok":true,"transport":"direct-loopback"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for name in (
            "NO_PROXY",
            "no_proxy",
            "HTTP_PROXY",
            "http_proxy",
            "HTTPS_PROXY",
            "https_proxy",
            "ALL_PROXY",
            "all_proxy",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("HTTP_PROXY", "http://10.255.255.1:9")
        ensure_loopback_proxy_bypass(os.environ)

        assert urllib.request.proxy_bypass("127.0.0.1") is True
        result = http_json(
            "GET",
            f"http://127.0.0.1:{server.server_address[1]}/ready",
            timeout=0.2,
        )

        assert result == {"ok": True, "transport": "direct-loopback"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
