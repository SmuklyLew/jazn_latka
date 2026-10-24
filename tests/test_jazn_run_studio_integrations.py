"""Positive and failure contracts for real Studio integration boundaries."""
from __future__ import annotations

from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio import external, probes, studio_worker
from tools.jazn_run_studio.core import Controller, Settings, StudioError, discovery
from tools.jazn_run_studio.chat import ChatClient


@pytest.fixture
def core(tmp_path: Path) -> Controller:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text("# synthetic SYSTEM", encoding="utf-8")
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    return Controller(tmp_path, Settings(model="local-test"))


def test_frozen_child_environment_restores_system_libraries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path), str(tmp_path / "Qt"), str(tmp_path.parent / "outside")]))
    monkeypatch.setenv("LD_LIBRARY_PATH", str(tmp_path))
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/original")
    monkeypatch.setenv("QT_PLUGIN_PATH", str(tmp_path))
    env = external.environment()
    assert env["PATH"] == str(tmp_path.parent / "outside")
    assert env["LD_LIBRARY_PATH"] == "/original"
    assert "QT_PLUGIN_PATH" not in env
    assert os.environ["QT_PLUGIN_PATH"] == str(tmp_path)


def test_external_program_uses_actual_exit_and_output(tmp_path: Path) -> None:
    result = external.run([sys.executable, "-c", "print('external-ok'); raise SystemExit(6)"], cwd=tmp_path)
    assert result.returncode == 6
    assert result.stdout.strip() == b"external-ok"


def test_frozen_discovery_allows_setting_interpreter_later(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("JAZN_STUDIO_PYTHON", raising=False)
    assert discovery(Settings())["python"] is None


@pytest.mark.parametrize("url", ["http://example.com", "http://127.0.0.1:22", "https://u:p@x.workers.dev", "https://x.workers.dev/?token=secret"])
def test_probes_reject_unapproved_destinations(url: str) -> None:
    with pytest.raises(ValueError):
        probes.read_json(url)


def test_ollama_models_are_not_a_generation_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "read_json", lambda _url: (200, {"models": [{"name": "local-test"}]}))
    result = probes.ollama("local-test")
    assert result["selected_model_present"] is True
    assert result["generation_verified"] is False
    assert result["accepted_visible_turn"] is False
    monkeypatch.setattr(probes, "read_json", lambda _url: (200, {"models": [7]}))
    with pytest.raises(ValueError):
        probes.ollama()


def test_probe_failure_is_not_reported_as_service_ready(core: Controller, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_model: str):
        raise OSError("simulated unavailable endpoint")
    monkeypatch.setattr(probes, "ollama", fail)
    job = core.probe("ollama")
    assert job.done.wait(5)
    assert job.state == "failed" and job.error == "OSError"


def test_schema_preserves_canonical_required_and_repeated_arguments() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    child = parser.add_subparsers(dest="op").add_parser("check")
    child.add_argument("--source", required=True, action="append")
    schema = studio_worker.commands(parser)[0]
    assert studio_worker.argv_for(schema, {"0": "a path", "1": ["one", "two"]}) == ["--project", "a path", "check", "--source", "one", "--source", "two"]
    with pytest.raises(ValueError):
        studio_worker.argv_for(schema, {})
    with pytest.raises(ValueError):
        studio_worker.argv_for(schema, {"invented": "x"})


def test_studio_schemas_come_from_original_parsers() -> None:
    import importlib
    for module, factory in studio_worker.MODULES.values():
        parser = getattr(importlib.import_module(module), factory)()
        schema = studio_worker.commands(parser)
        assert schema and all(item["path"] for item in schema)


def test_chat_checkpoints_identity_before_sending_and_blocks_replay(core: Controller, monkeypatch: pytest.MonkeyPatch) -> None:
    client = ChatClient(core)
    pipe = io.BytesIO()
    proc = SimpleNamespace(stdin=pipe, poll=lambda: None)
    monkeypatch.setattr(client, "job", SimpleNamespace(proc=proc))
    request = client.send("Dokładny tekst")
    persisted = json.loads(client.checkpoint.read_bytes())
    frame = json.loads(pipe.getvalue())
    assert persisted["request_id"] == frame["request_id"] == request
    assert frame["session_id"] == client.session_id
    assert frame["message"] == "Dokładny tekst"
    with pytest.raises(StudioError):
        client.send("Nie wolno powtórzyć")
    recovered = ChatClient(core)
    assert recovered.pending == request and recovered.session_id == client.session_id
    assert "Dokładny tekst" not in client.checkpoint.read_text(encoding="utf-8")


def test_poll_never_resubmits_user_text(core: Controller, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.jazn_run_studio.chat as chat
    client = ChatClient(core)
    client.pending = "pending-request"
    calls = []
    def run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, b'{"request_id":"pending-request","done":false}', b"")
    monkeypatch.setattr(chat, "run", run)
    monkeypatch.setattr(client, "receive", lambda _payload: None)
    client.resume()
    assert core.jobs["chat:resume"].done.wait(5)
    assert calls[0][-2:] == ["--daemon-result", "pending-request"]
    assert client.pending == "pending-request"


def test_local_final_validator_checks_integrity_binding_and_lineage() -> None:
    from tools.jazn_run_studio.validation_worker import validate
    text = "🕒 2026-10-22 16:00:00\n🙂 Łatka\n\nZweryfikowana wypowiedź."
    payload = {"request_id": "r", "turn_id": "t", "trace_id": "x", "ok": True,
        "answer_ok": True, "execution_state": "final_visible_answer", "host_finalization_pending": False,
        "final_visible_text": text, "final_visible_integrity": {"valid": True, "consensus": True,
        "text_sha256": sha256(text.encode()).hexdigest()}, "runtime_truth_gate": {"ok": True, "normal_response_allowed": True},
        "final_response_contract": {"author_source": "jazn_runtime"}}
    assert validate(payload, "r")["text"] == text
    assert validate(payload, "wrong")["accepted"] is False
    payload["final_visible_text"] = "Unaccepted candidate"
    assert validate(payload, "r")["accepted"] is False


def test_public_jsonl_bridge_preserves_preallocated_request_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from latka_jazn.core import chat_command_contract as bridge
    from latka_jazn.config import JaznConfig
    observed = {}
    class Session:
        def __init__(self, *_args, **_kwargs):
            self.state = SimpleNamespace(session_id="session")
        def process_user_text(self, text, **kwargs):
            observed.update(kwargs)
            observed["message"] = text
            return {"ok": False}
        def close(self):
            pass
    monkeypatch.setattr(bridge, "DaemonConversationSession", Session)
    monkeypatch.setattr(bridge, "apply_ollama_cli_settings", lambda config: config)
    monkeypatch.setattr(bridge, "write_chat_bridge_payload", lambda *_args, **_kwargs: None)
    data = json.dumps({"message": "Cześć.", "session_id": "s", "request_id": "stable-request"})
    assert bridge.run_jsonl_chat_bridge(config=JaznConfig(root=tmp_path), session_id="s", no_carryover=False,
        command="--chat-ollama", daemon_bound=True, stdin=io.StringIO(data + "\n"), stdout=io.StringIO()) == 0
    assert observed["request_id"] == "stable-request"
    assert observed["message"] == "Cześć."


def test_integrated_python_studio_executes_original_detect_host_command() -> None:
    root = Path(__file__).resolve().parents[1]
    core = Controller(root)
    job = core.studio_helper("execute", "python", {"path": ["detect-host"], "values": {}})
    assert job.done.wait(30)
    assert job.state == "succeeded" and job.returncode == 0
    assert '"host"' in "\n".join(core.logs[job.key])
