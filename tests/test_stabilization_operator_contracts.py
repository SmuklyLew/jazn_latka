"""Synthetic, isolated operator checks; never start an existing daemon."""
import json
import os
import sys
from pathlib import Path
import pytest

from latka_jazn import cli
from latka_jazn.model_adapters.base import ModelAdapterRequest
from latka_jazn.model_adapters.local_llm_adapter import LocalLlmAdapter
from tools.jazn_monitor.paths import monitor_workspace
from tools.jazn_monitor.generation import last_ollama_generation
from tools.jazn_monitor import telemetry, probe


@pytest.mark.parametrize("separator", [[], ["--"]])
@pytest.mark.parametrize("command,flag", [("start", "--daemon-start"), ("stop", "--daemon-stop")])
def test_lifecycle_port_is_preserved_without_starting_process(tmp_path, separator, command, flag):
    calls = []
    result = cli.main([command, "--root", str(tmp_path), *separator, "--daemon-port", "18785"],
                      legacy_handler=lambda args: calls.append(args) or 0)
    assert result == 0
    assert calls == [[flag, "--root", str(tmp_path), "--daemon-port", "18785"]]


@pytest.mark.parametrize("suffix", ["", "/", "/api", "/api/"])
def test_ollama_native_api_base_normalization(suffix, monkeypatch):
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return json.dumps({"done": True, "model": "real-model", "message": {"role": "assistant", "content": "To jest odpowiedź po polsku."}}).encode()
    def open_request(req, **kwargs):
        calls.append((req, kwargs))
        return Response()
    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", open_request)
    result = LocalLlmAdapter(model="requested", api_base="http://127.0.0.1:11434"+suffix).generate(
        ModelAdapterRequest(prompt="Test", system_context={}, metadata={"allow_non_polish": True}))
    assert result.generated
    assert result.model == "real-model"
    assert calls[0][0].full_url == "http://127.0.0.1:11434/api/chat"
    assert json.loads(calls[0][0].data)["stream"] is False
    assert calls[0][1]["timeout"] == 45.0


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_rejected(timeout):
    with pytest.raises(ValueError, match="positive_finite"):
        LocalLlmAdapter(model="test", timeout_seconds=timeout)


@pytest.mark.parametrize("extra,code", [({"error": "PRIVATE"}, "ollama_chat_provider_error"),
                                       ({"message": {"role": "user", "content": "PRIVATE"}}, "ollama_chat_role_invalid")])
def test_ollama_error_and_wrong_role_never_generate(extra, code, monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return json.dumps({"done": True, "message": {"content": "Test"}, **extra}).encode()
    monkeypatch.setattr("latka_jazn.model_adapters.local_llm_adapter.urlopen", lambda *_a, **_k: Response())
    result = LocalLlmAdapter(model="test").generate(ModelAdapterRequest(prompt="Test", system_context={}))
    assert not result.generated
    assert result.transport["error_code"] == code
    assert "PRIVATE" not in json.dumps(result.transport)


def test_two_roots_jobs_and_ledger_are_isolated_and_readonly(tmp_path):
    for name in ("first", "second"):
        root = tmp_path / name
        root.mkdir()
        (root / "local_resources").mkdir()
        workspace = monitor_workspace(root)
        workspace.mkdir(parents=True)
        jobs = workspace / "daemon_chat_jobs.json"
        jobs.write_text(json.dumps({"jobs": [{"request_id": name, "status": "completed"}]}))
        ledger = workspace / "core_state/memory_runtime/layered/source_origin_ledger_current_line.jsonl"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"schema_version": "source_origin_ledger/v1", "model_provider": "ollama",
            "model_candidate_generated": True, "model_candidate_validated": True,
            "model": name, "user_text": "PRIVATE", "turn_id": name})+"\n")
        before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
        result = telemetry.jobs_snapshot(root, {})
        assert result["finalization"]["state"] == "completed_job"
        assert result["finalization"]["accepted_finalization"] is None
        assert result["items"][0]["request_id"] == name
        generation = last_ollama_generation(root)
        assert generation["model"] == name
        assert generation["accepted_finalization"] is None
        assert "PRIVATE" not in json.dumps(generation)
        assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_selected_ports_do_not_accept_other_instance(tmp_path, monkeypatch):
    roots = [tmp_path / name for name in ("one", "two")]
    for i, root in enumerate(roots):
        root.mkdir()
        (root / "run.py").touch()
        marker = monitor_workspace(root) / "JAZN_ACTIVE_RUNTIME.json"
        marker.parent.mkdir(parents=True)
        marker.write_text(json.dumps({"daemon_pid": 100+i, "daemon_instance_id": str(i)}))
    def http(port, endpoint, timeout=1.5):
        i = 0 if port == 18785 else 1
        return {"daemon_pid": 100+i, "daemon_instance_id": str(i), "active_root": str(roots[i]),
                "liveness_ok": True, "heartbeat_fresh": True} if endpoint == "/live" else None
    monkeypatch.setattr(probe, "_http_json", http)
    monkeypatch.setattr(probe, "process_snapshot", lambda *_: {})
    assert probe.snapshot(roots[0], daemon_port=18785)["services"]["Daemon Jaźni"]["state"] == "ready"
    assert probe.snapshot(roots[0], daemon_port=18786)["services"]["Daemon Jaźni"]["state"] == "error"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="native Linux /proc only")
def test_native_linux_process_read_has_current_python():
    rows = telemetry._linux_process_rows()
    assert rows is not None
    current = next(row for row in rows if row["pid"] == os.getpid())
    assert current["parent_pid"] == os.getppid()
    assert current["ram_bytes"] > 0
    assert current["cpu_seconds"] >= 0


def test_bad_workspace_stops_observation_without_network(tmp_path, monkeypatch):
    (tmp_path / "run.py").touch()
    (tmp_path / "local_resources").mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path.parent))
    monkeypatch.setattr(probe, "_http_json", lambda *_a, **_k: pytest.fail("network after invalid path"))
    assert probe.snapshot(tmp_path)["services"]["Daemon Jaźni"]["state"] == "error"


def test_source_ledger_keeps_actual_model_and_observer_does_not_read_private_memory(tmp_path, monkeypatch):
    from latka_jazn.core.source_origin_ledger import SourceOriginLedger
    monkeypatch.setenv("JAZN_MEMORY_MODE", "off")
    ledger = SourceOriginLedger(tmp_path)
    entry = ledger.build_entry(turn_id="turn", user_text="synthetic", response_text="synthetic",
        route="local", detected_intent="test", model_response={"provider": "ollama", "model": "actual",
        "generated": True}, validator_result={"accepted": True})
    ledger.append(entry)
    result = last_ollama_generation(tmp_path)
    assert result["model"] == "actual"
    assert result["candidate_validated"] is True
    assert result["accepted_finalization"] is None


def test_qt_standalone_title_does_not_repeat_display_name(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PySide6.QtWidgets")
    from tools.jazn_monitor.window import MonitorWindow
    app = widgets.QApplication.instance() or widgets.QApplication([])
    app.setApplicationDisplayName("Jaźń Monitor")
    window = MonitorWindow(None, 8787, 11434, smoke=True)
    assert window.windowTitle() == "Tylko odczyt"
    window.close()
