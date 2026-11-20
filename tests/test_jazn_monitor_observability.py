"""No network and no daemon start: deterministic monitor evidence regressions."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from tools.jazn_monitor import autostart, probe, telemetry


def _root(tmp_path: Path) -> Path:
    (tmp_path / "run.py").write_text("# fixture\n", encoding="utf-8")
    (tmp_path / "jazn_monitor.py").write_text("# fixture\n", encoding="utf-8")
    return tmp_path


def _marker(root: Path) -> dict:
    return {
        "daemon_pid": 1357, "daemon_instance_id": "instance-fixture",
        "daemon_chat_jobs": {
            "submitted_total": 3, "completed_total": 2,
            "failed_non_timeout_total": 1, "execution_timeout_total": 0,
            "pending": 0,
            "last_terminal_job": {"request_id": "failed-req", "job_status": "failed",
                                  "error_code": "runtime_turn_not_accepted"},
        },
    }


def _live(root: Path) -> dict:
    return {
        "daemon_pid": 1357, "daemon_instance_id": "instance-fixture",
        "active_root": str(root), "heartbeat_fresh": True, "liveness_ok": True,
    }


def test_windows_process_probe_does_not_flash_powershell_console(monkeypatch):
    # Cross-platform, no real OS process is spawned. Windows' CREATE_NO_WINDOW
    # must be forwarded to the short-lived, read-only WMI probe.
    observed = []
    monkeypatch.setattr(telemetry, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(telemetry.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

    def fake_run(args, **kwargs):
        observed.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"[]")

    monkeypatch.setattr(telemetry.subprocess, "run", fake_run)
    assert telemetry._windows_process_rows() == []
    assert len(observed) == 1
    cmd, kwargs = observed[0]
    assert cmd[0] == "powershell.exe"
    assert kwargs["creationflags"] & 0x08000000
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == 5


def test_process_owner_and_descendants_are_strictly_verified(tmp_path, monkeypatch):
    root = _root(tmp_path)
    start = datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc).isoformat()
    child = datetime(2026, 11, 20, 14, 1, tzinfo=timezone.utc).isoformat()
    monkeypatch.setattr(telemetry, "_windows_process_rows", lambda: [
        {"pid": 1357, "parent_pid": 111, "created": start,
         "command_line": f'python main.py --root "{root}" --daemon-run',
         "cpu_seconds": 3.5, "ram_bytes": 104857600},
        {"pid": 2468, "parent_pid": 1357, "created": child,
         "command_line": "python worker.py", "cpu_seconds": 1, "ram_bytes": 10485760},
        {"pid": 3333, "parent_pid": 1357,
         "created": "2026-11-19T14:00:00+00:00",
         "command_line": "python unrelated.py", "cpu_seconds": 0, "ram_bytes": 5},
        {"pid": 4444, "parent_pid": 999, "created": child,
         "command_line": "python unrelated.py", "cpu_seconds": 0, "ram_bytes": 5},
    ])
    result = telemetry.process_snapshot(root, _marker(root), _live(root))
    assert result["state"] == "available"
    assert [p["pid"] for p in result["items"]] == [1357, 2468]
    assert result["items"][0]["name"] == "Jaźń — Daemon"
    assert result["items"][0]["ram_mb"] == 100
    assert result["items"][1]["evidence"] == "verified_parent_chain"
    assert result["cpu_measure"] == "cumulative_cpu_seconds"
    assert "command_line" not in json.dumps(result)


def test_similarly_prefixed_root_does_not_count_as_owned_daemon(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(telemetry, "_windows_process_rows", lambda: [{
        "pid": 1357, "parent_pid": 111,
        "command_line": f'python main.py --root "{root}_other" --daemon-run',
        "created": "2026-11-20T14:00:00+00:00",
    }])
    result = telemetry.process_snapshot(root, _marker(root), _live(root))
    assert result["state"] == "error"
    assert result["items"] == []


def test_process_mismatch_or_unavailable_is_not_claimed_ready(tmp_path, monkeypatch):
    root = _root(tmp_path)
    monkeypatch.setattr(telemetry, "_windows_process_rows", lambda: None)
    assert telemetry.process_snapshot(root, _marker(root), _live(root))["state"] == "unavailable"
    wrong = _live(root)
    wrong["daemon_instance_id"] = "another"
    assert telemetry.process_snapshot(root, _marker(root), wrong)["state"] == "unknown"


def test_job_diagnostics_are_codes_only_not_private_text(tmp_path, monkeypatch):
    root = _root(tmp_path)
    store = root / "workspace_runtime" / "daemon_chat_jobs.json"
    store.parent.mkdir(parents=True)
    store.write_text(json.dumps({
        "jobs": [{"request_id": "failed-req", "status": "failed",
                  "created_at_utc": "2026-11-20T14:00:00+00:00",
                  "completed_at_utc": "2026-11-20T14:00:20+00:00",
                  "error": "runtime_turn_not_accepted",
                  "user_text": "PRIVATE-DONT-SHOW",
                  "model_response": "ANOTHER-PRIVATE-VALUE"}]
    }), encoding="utf-8")
    monkeypatch.setattr(telemetry, "_audit_reasons",
                        lambda path, ids: {"failed-req": "classified_non_dynamic_response"})
    result = telemetry.jobs_snapshot(root, _marker(root))
    assert result["state"] == "available"
    assert result["counts"]["submitted_total"] == 3
    assert result["items"][0]["duration_seconds"] == 20
    assert result["finalization"]["state"] == "rejected"
    assert result["finalization"]["reason_code"] == "classified_non_dynamic_response"
    serialized = json.dumps(result)
    assert "PRIVATE-DONT-SHOW" not in serialized
    assert "ANOTHER-PRIVATE-VALUE" not in serialized


def test_jobs_fail_closed_on_invalid_json_and_no_live_root(tmp_path):
    root = _root(tmp_path)
    path = root / "workspace_runtime" / "daemon_chat_jobs.json"
    path.parent.mkdir(parents=True)
    path.write_text("{bad-json", encoding="utf-8")
    assert telemetry.jobs_snapshot(root, _marker(root))["state"] == "unavailable"
    assert telemetry.jobs_snapshot(root, None)["state"] == "unknown"


def test_probe_preserves_services_and_adds_observability(tmp_path, monkeypatch):
    root = _root(tmp_path)
    marker = root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps(_marker(root)), encoding="utf-8")
    endpoints = {
        "/live": _live(root),
        "/ready": {"daemon_instance_id": "instance-fixture",
                   "readiness_ok": True, "runtime_write_ready": True},
        "/api/tags": {"models": [{"name": "gemma3:latest"}]},
    }
    monkeypatch.setattr(probe, "_http_json", lambda port, endpoint, timeout=1.5: endpoints.get(endpoint))
    monkeypatch.setattr(probe, "process_snapshot", lambda r, m, l:
                        {"state": "available", "items": [{"name": "Jaźń — Daemon", "pid": 1357}]})
    monkeypatch.setattr(probe, "jobs_snapshot", lambda r, m: {
        "state": "available", "items": [],
        "counts": None, "finalization": {"state": "unknown"}})
    result = probe.snapshot(root)
    assert result["services"]["Daemon Jaźni"]["state"] == "ready"
    assert result["services"]["Runtime Core"]["state"] == "ready"
    assert result["processes"]["items"][0]["pid"] == 1357
    assert result["finalization"]["state"] == "unknown"
    endpoints["/ready"] = None
    assert probe.snapshot(root)["services"]["Runtime Core"]["state"] == "unavailable"


def test_no_auto_gui_for_ci_noninteractive_or_operator_off(tmp_path):
    root = _root(tmp_path)
    called = []
    spawn = lambda *args, **kwargs: called.append((args, kwargs))
    for env, interactive in (({"CI": "true"}, True), ({}, False),
                             ({"JAZN_MONITOR_AUTOSTART": "off"}, True)):
        result = autostart.may_autostart_monitor(
            root, daemon_host="127.0.0.1", daemon_port=8787,
            env=env, interactive=interactive, gui_available=True, spawn=spawn,
            platform="nt",
        )
        assert result["state"] in ("disabled", "skipped")
    assert called == []


def test_interactive_auto_gui_is_not_runtime_owner(tmp_path):
    root = _root(tmp_path)
    observed = []

    class Spawned:
        pid = 9870

    def spawn(argv, **options):
        observed.append((argv, options))
        return Spawned()

    result = autostart.may_autostart_monitor(
        root, daemon_host="127.0.0.1", daemon_port=8787,
        env={}, interactive=True, gui_available=True, spawn=spawn, platform="nt",
    )
    assert result["state"] == "spawned"
    assert result["pid"] == 9870
    assert result["visible_window_verified"] is False
    command, options = observed[0]
    assert command[-4:] == ["--root", str(root), "--daemon-port", "8787"]
    assert options["cwd"] == str(root)
    assert all(term not in " ".join(command) for term in ("--daemon-run", "stop", "restart"))
