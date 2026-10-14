from __future__ import annotations

import io
import json
import os
import threading
from pathlib import Path

import pytest

from latka_jazn.bridge.secure_host_runtime_gateway import GatewayError
from latka_jazn.core.chat_command_contract import write_chat_bridge_payload
from latka_jazn.core.host_stdout_transport import HostOutputBackpressureError, write_host_frame
from latka_jazn.core.chatgpt_host_pending_store import read_committed_host_request
from latka_jazn.memory.availability import build_memory_availability_status, runtime_memory_storage_root
from latka_jazn.memory.memory_root import resolve_memory_root
from latka_jazn.mcp.tools import jazn_resume_visible_reply
from test_finalization_crash_atomicity import _request, _finalize


def _nonblocking_pipe():
    read_fd, write_fd = os.pipe()
    try:
        os.set_blocking(write_fd, False)
    except (OSError, NotImplementedError, AttributeError):
        os.close(read_fd)
        os.close(write_fd)
        pytest.skip("non-blocking host pipe is not supported by this host")
    return read_fd, write_fd


def test_stdout_nonblocking_pipe_writes_one_complete_utf8_frame():
    read_fd, write_fd = _nonblocking_pipe()
    text = json.dumps({"message": "Żółw 🐾" * 100_000}, ensure_ascii=False) + "\n"
    collected = bytearray()
    def reader():
        while True:
            chunk = os.read(read_fd, 4096)
            if not chunk:
                return
            collected.extend(chunk)
    worker = threading.Thread(target=reader, daemon=True)
    worker.start()
    try:
        with os.fdopen(write_fd, "w", encoding="utf-8") as stream:
            write_host_frame(stream, text, timeout_seconds=5)
    finally:
        worker.join(timeout=5)
        os.close(read_fd)
    assert not worker.is_alive()
    assert collected.decode("utf-8") == text
    assert json.loads(collected.decode("utf-8")) == json.loads(text)


def test_host_pipe_backpressure_timeout_is_explicit_and_bounded():
    read_fd, write_fd = _nonblocking_pipe()
    try:
        with os.fdopen(write_fd, "w", encoding="utf-8") as stream:
            with pytest.raises(HostOutputBackpressureError, match="host_stdout_backpressure_timeout"):
                write_host_frame(stream, "x" * 1_000_000, timeout_seconds=0.02)
    finally:
        os.close(read_fd)


def test_in_memory_chatgpt_frame_remains_one_json_line():
    stream = io.StringIO()
    write_chat_bridge_payload(stream, {"ok": True, "tekst": "Łatka 🐾"})
    assert json.loads(stream.getvalue()) == {"ok": True, "tekst": "Łatka 🐾"}
    assert stream.getvalue().endswith("\n")
    assert stream.getvalue().count("\n") == 1


def test_runtime_artifacts_cannot_forge_persistent_memory(tmp_path: Path, monkeypatch):
    root = tmp_path / "system"
    root.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    memory_root = root / "memory"
    (memory_root / "sqlite" / "runtime_write_v1").mkdir(parents=True)
    (memory_root / "sqlite" / "runtime_write_v1" / "runtime_memory.sqlite3").write_bytes(b"not private recall")
    (memory_root / "layered").mkdir()
    (memory_root / "layered" / "log.txt").write_text("runtime artifact", encoding="utf-8")
    assert resolve_memory_root(root) == memory_root.resolve()
    availability = build_memory_availability_status(root)
    assert availability.status == "persistent_memory_absent_optional"
    assert availability.persistent_memory_enabled is False
    assert runtime_memory_storage_root(root) == (workspace / "core_state" / "memory_runtime").resolve()


def test_resume_reads_durable_final_only_with_matching_lineage(tmp_path: Path):
    reply = _request(tmp_path)
    finalized, errors = _finalize(tmp_path, reply)
    assert not errors and finalized is not None
    record = read_committed_host_request(tmp_path, turn_id=reply["turn_id"])
    request_id = str(record["binding"].get("daemon_request_id") or reply["turn_id"])
    contract_hash = str(record["request_contract_hash"])
    calls = []
    class Unavailable:
        def result(self, req):
            calls.append(req)
            raise GatewayError("daemon_unavailable:TransportTimeoutError")
    params = {"root": tmp_path, "gateway": Unavailable(), "daemon_request_id": request_id,
              "turn_id": reply["turn_id"], "host_request_contract_hash": contract_hash}
    recovered = jazn_resume_visible_reply.run(**params)
    assert recovered["isError"] is False
    assert recovered["structuredContent"]["action"] == "display_exact"
    assert recovered["structuredContent"]["final_visible_text"] == finalized["final_visible_text"]
    assert recovered["structuredContent"]["durable_commit_verified"] is True
    assert recovered["structuredContent"]["must_not_resubmit_user_message"] is True
    assert calls == [request_id]
    rejected = jazn_resume_visible_reply.run(**{**params, "host_request_contract_hash": "0" * 64})
    assert rejected["isError"] is True
    assert rejected["structuredContent"]["action"] == "host_diagnostic"
    assert "lineage_mismatch" in rejected["structuredContent"]["reason"]
    without_lineage = jazn_resume_visible_reply.run(**{**params, "host_request_contract_hash": None})
    assert without_lineage["structuredContent"]["action"] == "poll_runtime"


def test_resume_fails_closed_for_tampered_accepted_text(tmp_path: Path):
    reply = _request(tmp_path)
    finalized, errors = _finalize(tmp_path, reply)
    assert finalized is not None and not errors
    record = read_committed_host_request(tmp_path, turn_id=reply["turn_id"])
    path = next(tmp_path.rglob("consumed/*.json"))
    altered = json.loads(path.read_text(encoding="utf-8"))
    altered["final_visible_capture"]["final_visible_text"] += " Modyfikacja"
    path.write_text(json.dumps(altered), encoding="utf-8")
    class Unavailable:
        def result(self, req):
            raise GatewayError("daemon_unavailable:TransportTimeoutError")
    result = jazn_resume_visible_reply.run(root=tmp_path, gateway=Unavailable(),
        daemon_request_id=str(record["binding"].get("daemon_request_id") or reply["turn_id"]),
        turn_id=reply["turn_id"], host_request_contract_hash=record["request_contract_hash"])
    assert result["isError"] is True
    assert result["structuredContent"]["action"] == "host_diagnostic"
    assert "capture_binding_mismatch" in result["structuredContent"]["reason"]


def test_gateway_auth_failure_never_recovers_local_committed_capture(tmp_path: Path):
    reply = _request(tmp_path)
    finalized, errors = _finalize(tmp_path, reply)
    assert finalized is not None and not errors
    record = read_committed_host_request(tmp_path, turn_id=reply["turn_id"])
    class AuthRejected:
        def result(self, req):
            raise GatewayError("gateway_auth_rejected")
    result = jazn_resume_visible_reply.run(root=tmp_path, gateway=AuthRejected(),
        daemon_request_id=str(record["binding"].get("daemon_request_id") or reply["turn_id"]),
        turn_id=reply["turn_id"], host_request_contract_hash=record["request_contract_hash"])
    assert result["isError"] is True
    assert result["structuredContent"]["action"] == "host_diagnostic"
    assert "gateway_auth_rejected" in result["structuredContent"]["reason"]
