"""The explicit Ollama probe must never manufacture an accepted Jaźń turn."""
from __future__ import annotations

import json

import pytest

from tools.jazn_run_studio import probes


def test_missing_model_does_not_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "ollama", lambda _model: {
        "service": "ollama", "endpoint_reachable": True, "models": [],
        "selected_model_present": False, "generation_verified": False,
    })
    monkeypatch.setattr(probes, "build_opener", lambda *_args: (_ for _ in ()).throw(AssertionError("Unexpected POST")))
    result = probes.ollama_generation("gemma3:latest")
    assert result["generation_verified"] is False
    assert result["reason"] == "model_not_visible"


def test_explicit_probe_requires_done_and_nonempty_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "ollama", lambda model: {
        "service": "ollama", "endpoint_reachable": True, "models": [model],
        "selected_model_present": True, "generation_verified": False,
    })
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return b'{"done":true,"message":{"content":"OK"}}'

    class Opener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            return Response()

    monkeypatch.setattr(probes, "build_opener", lambda *_args: Opener())
    result = probes.ollama_generation("gemma3:latest")
    assert result["generation_verified"] is True
    assert result["accepted_visible_turn"] is False
    assert "content" not in result
    request, timeout = calls[0]
    assert timeout <= 60
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    body = json.loads(request.data)
    assert body["stream"] is False and body["model"] == "gemma3:latest"
    assert body["options"]["num_predict"] == 12


def test_invalid_model_rejected_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "ollama", lambda _model: (_ for _ in ()).throw(AssertionError("Unexpected GET")))
    with pytest.raises(ValueError):
        probes.ollama_generation("../foo?admin=true")
