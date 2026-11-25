"""Real loopback transport: no Ollama prompt before fresh local model metadata."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import pytest

from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter
from latka_jazn.model_adapters.openai_compatible_local_adapter import OpenAICompatibleLocalAdapter


@pytest.mark.parametrize("kind", ["native", "compatible", "compatible_probe"])
@pytest.mark.parametrize("damage", ["none", "remote_model", "remote_host", "missing", "conflict", "invalid_digest", "malformed", "redirect"])
def test_ollama_metadata_before_inference(kind: str, damage: str) -> None:
    calls: list[tuple[str, str, bytes]] = []
    local: dict[str, Any] = {"name": "alias:latest", "model": "alias:latest",
                             "size": 123456, "digest": "a" * 64}
    models = [local]
    if damage in {"remote_model", "remote_host"}:
        local[damage] = "upstream"
    elif damage == "missing":
        models = []
    elif damage == "conflict":
        models.append({**local, "remote_host": "upstream"})
    elif damage == "invalid_digest":
        local["digest"] = ""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            calls.append(("GET", self.path, b""))
            if damage == "redirect":
                self.send_response(302)
                self.send_header("Location", "/unexpected")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.reply(b"invalid-json" if damage == "malformed" else json.dumps({"models": models}).encode())

        def do_POST(self) -> None:
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append(("POST", self.path, data))
            self.reply(json.dumps({"model": "alias:latest", "done": True,
                                   "message": {"role": "assistant", "content": "To jest odpowiedź po polsku."},
                                   "output_text": "To jest odpowiedź po polsku."}).encode())

        def reply(self, data: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        request = ModelAdapterRequest(prompt="synthetic-prompt")
        if kind == "native":
            result = LocalLlmAdapter(model="alias", api_base=base).generate(request)
            accepted = result.generated
        else:
            adapter = OpenAICompatibleLocalAdapter(provider="ollama", model="alias", api_base=base + "/v1")
            if kind == "compatible_probe":
                accepted = adapter.probe().probe_state == "probed_ok"
            else:
                accepted = adapter.generate(request).generated
        assert calls[0] == ("GET", "/api/tags", b"")
        if damage == "none":
            assert accepted
            assert len(calls) == 2
            assert calls[1][0] == "POST"
        else:
            assert not accepted
            assert calls == [("GET", "/api/tags", b"")]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
