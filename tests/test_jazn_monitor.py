"""Read-only monitor regressions; no daemon or model is started."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jazn_monitor import probe
from jazn_monitor import main


def root_with_marker(tmp_path: Path) -> Path:
    (tmp_path / "run.py").write_text("# test only\n", encoding="utf-8")
    path = tmp_path / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "daemon_instance_id": "one", "daemon_pid": 2220,
    }), encoding="utf-8")
    return tmp_path


def live(root: Path) -> dict:
    return {
        "daemon_instance_id": "one", "daemon_pid": 2220,
        "active_root": str(root), "heartbeat_fresh": True, "liveness_ok": True,
    }


def test_unknown_without_root_and_zero_side_effects(monkeypatch):
    monkeypatch.setattr(probe, "_http_json", lambda port, endpoint, timeout=1.5: None)
    result = probe.snapshot(None)
    assert result["observation_only"] is True
    assert all(value["state"] == "unknown" for value in result["services"].values())


def test_instance_readiness_and_model_reachability_are_separate(monkeypatch, tmp_path):
    root = root_with_marker(tmp_path)
    endpoints = {
        "/live": live(root),
        "/ready": {"daemon_instance_id": "one", "readiness_ok": True,
                   "runtime_write_ready": True, "persistent_memory_enabled": False},
        "/api/tags": {"models": [{"name": "gemma3:latest"}]},
    }
    monkeypatch.setattr(probe, "_http_json", lambda port, endpoint, timeout=1.5: endpoints.get(endpoint))
    states = probe.snapshot(root)["services"]
    assert states["Daemon Jaźni"]["state"] == "ready"
    assert states["Runtime Core"]["state"] == "ready"
    assert states["Ollama"]["state"] == "reachable"
    assert states["MEMORY"]["state"] == "disabled"
    assert states["JSS"]["state"] == "unknown"
    endpoints["/live"]["heartbeat_fresh"] = False
    degraded = probe.snapshot(root)["services"]
    assert degraded["Daemon Jaźni"]["state"] == "reachable"
    assert degraded["Runtime Core"]["state"] == "unknown"


@pytest.mark.parametrize("kind", ["instance", "root", "pid"])
def test_instance_mismatch_fail_closed(monkeypatch, tmp_path, kind):
    root = root_with_marker(tmp_path)
    value = live(root)
    if kind == "instance":
        value["daemon_instance_id"] = "unexpected"
    elif kind == "root":
        value["active_root"] = str(tmp_path / "other")
    else:
        value["daemon_pid"] = 3333
    monkeypatch.setattr(probe, "_http_json", lambda port, endpoint, timeout=1.5:
                        value if endpoint == "/live" else None)
    states = probe.snapshot(root)["services"]
    assert states["Daemon Jaźni"]["state"] == "error"
    assert states["Runtime Core"]["state"] == "unknown"


def test_unavailable_daemon_is_not_false_ready(monkeypatch, tmp_path):
    root = root_with_marker(tmp_path)
    monkeypatch.setattr(probe, "_http_json", lambda port, endpoint, timeout=1.5: None)
    assert probe.snapshot(root)["services"]["Daemon Jaźni"]["state"] == "unknown"


@pytest.mark.parametrize("content", [b"{broken", b"x" * (probe.MAX_JSON + 1)], ids=["invalid-json", "oversized-json"])
def test_untrusted_marker_rejected(monkeypatch, tmp_path, content):
    root = root_with_marker(tmp_path)
    marker = root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_bytes(content)
    monkeypatch.setattr(probe, "_http_json", lambda port, endpoint, timeout=1.5: live(root))
    assert probe.snapshot(root)["services"]["Daemon Jaźni"]["state"] == "unknown"


def test_http_allowlist_and_port_rejection():
    assert probe._http_json(0, "/live") is None
    assert probe._http_json(8787, "/private") is None
    assert probe._http_json(65536, "/ready") is None
    with pytest.raises(SystemExit) as error:
        main(["--daemon-port", "0", "--probe-json"])
    assert error.value.code == 2


def test_json_mode_does_not_require_gui(monkeypatch, capsys):
    monkeypatch.setattr(probe, "_http_json", lambda port, endpoint, timeout=1.5: None)
    assert main(["--probe-json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["schema_version"] == "jazn_monitor_snapshot/v1"
    assert data["observation_only"] is True


def test_readiness_requires_runtime_write_and_chat_worker(monkeypatch, tmp_path):
    root = root_with_marker(tmp_path)
    current = {
        "/live": live(root),
        "/ready": {"daemon_instance_id": "one", "readiness_ok": False,
                   "runtime_write_ready": True, "readiness_reasons": ["chat_worker_not_ready"]},
    }
    monkeypatch.setattr(probe, "_http_json", lambda p, e, timeout=1.5: current.get(e))
    states = probe.snapshot(root)["services"]
    assert states["Daemon Jaźni"]["state"] == "ready"
    assert states["Runtime Core"]["state"] == "reachable"
    current["/ready"]["readiness_ok"] = True
    current["/ready"]["runtime_write_ready"] = False
    assert probe.snapshot(root)["services"]["Runtime Core"]["state"] == "unknown"
