"""Actual Ollama adapter boundary: isolated model circuit and no transport replay."""
from __future__ import annotations

from pathlib import Path
from email.message import Message
from urllib.error import HTTPError
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from latka_jazn.config import JaznConfig
from latka_jazn.core.conversation_channel import apply_model_channel_config
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter


@pytest.mark.parametrize("operator,client,expected", [
    (False, True, False), (False, False, False),
    (True, False, False), (True, True, True),
])
def test_client_cannot_elevate_paid_inference_permission(
    tmp_path: Path, operator: bool, client: bool, expected: bool,
) -> None:
    config = JaznConfig(root=tmp_path, allow_paid_openai_api=operator)
    routed = apply_model_channel_config(config, {"allow_paid_openai_api": client})
    assert routed.allow_paid_openai_api is expected
    assert config.allow_paid_openai_api is operator


def test_ollama_http_failure_opens_shared_model_circuit_without_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    recovered = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(self.path)
            if not recovered.is_set():
                self.send_response(503)
                self.end_headers()
                return
            body = json.dumps({"done": True, "model": "synthetic", "message": {"role": "assistant", "content": "Tak."}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        request = ModelAdapterRequest(prompt="test", metadata={"allow_non_polish": True})
        adapter = LocalLlmAdapter(root=tmp_path, model="synthetic", api_base=base, timeout_seconds=2)
        clock = [100.0]
        monkeypatch.setattr(adapter._transport_breaker, "_clock", lambda: clock[0])
        for _ in range(3):
            result = adapter.generate(request)
            assert result.status == "http_error_503"
            assert result.transport["retry_count"] == 0
            assert not result.generated
        rebuilt = LocalLlmAdapter(root=tmp_path, model="synthetic", api_base=base, timeout_seconds=2)
        assert rebuilt._transport_breaker is adapter._transport_breaker
        blocked = rebuilt.generate(request)
        assert blocked.status == "model_circuit_open"
        assert not blocked.generated
        assert blocked.transport["attempts"][0]["request_dispatched"] is False
        assert calls == ["/api/chat"] * 3
        other = LocalLlmAdapter(root=tmp_path, model="different", api_base=base)
        assert other.describe()["model_transport_circuit"]["state"] == "closed"
        recovered.set()
        clock[0] += 16.0
        result = rebuilt.generate(request)
        assert result.generated
        assert calls == ["/api/chat"] * 4
        assert rebuilt.describe()["model_transport_circuit"]["state"] == "closed"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_non_transient_http_denial_does_not_open_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def denied(request, *, timeout):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 401, "denied", Message(), None)
    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", denied)
    adapter = LocalLlmAdapter(model="synthetic")
    for _ in range(4):
        result = adapter.generate(ModelAdapterRequest(prompt="test"))
        assert result.status == "http_error_401"
    assert len(calls) == 4
    assert adapter.describe()["model_transport_circuit"]["state"] == "closed"
