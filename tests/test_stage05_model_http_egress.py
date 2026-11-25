"""Stage 05: actual loopback HTTP redirects and local egress authority."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from latka_jazn.model_adapters import model_http_transport as transport
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter
from latka_jazn.model_adapters.openai_compatible_local_adapter import OpenAICompatibleLocalAdapter


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("local", [False, True])
def test_inference_http_does_not_follow_redirect(
    status: int, method: str, local: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def reply(self) -> None:
            paths.append(self.path)
            if self.command == "POST":
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(status if self.path == "/initial" else 200)
            self.send_header("Location", "/unexpected")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = reply
        do_POST = reply

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("NO_PROXY", "127.0.0.1")
        monkeypatch.setenv("no_proxy", "127.0.0.1")
        req = Request(
            f"http://127.0.0.1:{server.server_port}/initial",
            data=b"synthetic" if method == "POST" else None, method=method,
            headers={"Authorization": "Bearer synthetic-never-forward"},
        )
        opener = transport.open_local_model_request if local else transport.open_model_request
        with pytest.raises(HTTPError) as caught:
            opener(req, timeout=2.0)
        assert caught.value.code == status
        caught.value.close()
        assert paths == ["/initial"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("url", [
    "https://example.invalid/v1", "http://192.0.2.1:11434/api/chat",
    "http://localhost.example.invalid/api/chat", "http://127.0.0.1@example.invalid/api/chat",
    "http://user:secret@127.0.0.1/api/chat", "http://127.0.0.1:99999/api/chat",
    "http://127.0.0.1/api/chat?target=external", "http://127.0.0.1/api/chat#external",
])
def test_local_transport_refuses_unapproved_destination_before_open(
    url: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "build_opener", lambda *_a: pytest.fail("network must not be reached"))
    with pytest.raises(URLError, match="local_model_destination_not_authorized"):
        transport.open_local_model_request(Request(url, method="POST", data=b"synthetic"), timeout=2)


def test_local_adapters_cannot_bypass_egress_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "build_opener", lambda *_a: pytest.fail("network must not be reached"))
    endpoint = "https://example.invalid"
    native = LocalLlmAdapter(model="synthetic", api_base=endpoint)
    compatible = OpenAICompatibleLocalAdapter(model="synthetic", api_base=endpoint + "/v1")
    assert not native.probe()["probe_ok"]
    assert not native.generate(ModelAdapterRequest(prompt="synthetic")).generated
    assert not compatible.generate(ModelAdapterRequest(prompt="synthetic")).generated


def test_loopback_inference_ignores_proxy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("NO_PROXY", "")
        req = Request(f"http://127.0.0.1:{server.server_port}/")
        with transport.open_local_model_request(req, timeout=2.0) as response:
            assert response.read() == b"OK"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
