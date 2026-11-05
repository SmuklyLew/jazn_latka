"""Live TPA probes and runtime configuration must use the same isolated API."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import threading

import pytest

from tools.jazn_run_studio import probes, tpa_live


@pytest.fixture
def api():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path)
            payload = json.dumps({"models": [{"name": "synthetic:latest"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
        assert not thread.is_alive()


def test_selected_test_endpoint_is_probed_without_default_port_fallback(api, tmp_path):
    base, calls = api
    assert probes.ollama("synthetic:latest", api_base=base)["selected_model_present"] is True
    folder = tmp_path / "live"
    folder.mkdir()
    result = tpa_live.exercise(tmp_path / "SYSTEM", folder, "ollama-two-turns",
                               sys.executable, "missing:latest", api_base=base)
    assert result["status"] == "BLOCKED"
    assert result["evidence"]["selected_model_present"] is False
    assert result["evidence"]["cleanup"]["ok"] is True
    assert not any(folder.iterdir())
    assert calls == ["/api/tags", "/api/tags"]


@pytest.mark.parametrize("base", [
    "https://127.0.0.1:11534", "http://localhost:11534", "http://192.0.2.1:11534",
    "http://user:secret@127.0.0.1:11534", "http://127.0.0.1:11534/api",
    "http://127.0.0.1:11534/?token=secret", "http://127.0.0.1:11534/#fragment",
    "http://127.0.0.1", "http://127.0.0.1:80", "http://127.0.0.1:99999",
])
def test_invalid_endpoint_is_rejected_before_transport(base, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Invalid endpoint must not reach transport")
    monkeypatch.setattr(probes, "read_json", forbidden)
    with pytest.raises(ValueError):
        probes.ollama("synthetic:latest", api_base=base)


def test_live_cli_passes_explicit_endpoint_to_existing_executor(tmp_path, monkeypatch):
    monkeypatch.setattr(tpa_live, "validate_staging", lambda *_a, **_kw: tmp_path)
    observed = []
    def exercise(*_args, **kwargs):
        observed.append(kwargs)
        return {"status": "BLOCKED", "reason": "Synthetic executor, no daemon"}
    monkeypatch.setattr(tpa_live, "exercise", exercise)
    monkeypatch.setattr(sys, "argv", [
        "tpa_live", "--root", str(tmp_path), "--folder", str(tmp_path),
        "--run-id", "synthetic-run", "--case", "ollama-two-turns",
        "--ollama-api-base", "http://127.0.0.1:11534",
    ])
    assert tpa_live.main() == 1
    assert observed == [{"api_base": "http://127.0.0.1:11534"}]


def test_runtime_environment_preserves_preflight_endpoint(tmp_path, monkeypatch):
    from latka_jazn.tools import release_staging
    folder = tmp_path / "live"
    folder.mkdir()
    observed = []
    monkeypatch.setattr(tpa_live, "ollama", lambda _model, **kwargs:
                        observed.append(kwargs["api_base"]) or {"selected_model_present": True})
    monkeypatch.setattr(release_staging, "create_system_smoke_staging", lambda _root, stage: stage.mkdir())
    monkeypatch.setattr(tpa_live.os, "environ", {})
    def controller(*_args, **_kwargs):
        assert tpa_live.os.environ["JAZN_OLLAMA_BASE_URL"] == observed[0]
        raise RuntimeError("Stop before any runtime process is created")
    monkeypatch.setattr(tpa_live, "Controller", controller)
    with pytest.raises(RuntimeError, match="Stop before"):
        tpa_live.exercise(tmp_path / "SYSTEM", folder, "ollama-two-turns", sys.executable,
                          "synthetic:latest", api_base="http://127.0.0.1:11534/")
    assert observed == ["http://127.0.0.1:11534"]
