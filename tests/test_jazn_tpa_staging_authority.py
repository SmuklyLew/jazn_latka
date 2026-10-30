"""Run capabilities admit canonical local acceptance without admitting live data."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest

from tools.jazn_run_studio.tpa_paths import TOKEN_ENV, issue_staging, validate_staging
from tools.jazn_run_studio.tpa_reports import RunStore


@pytest.fixture
def owned(tmp_path, monkeypatch):
    root = tmp_path / "SYSTEM"
    (root / ".settings").mkdir(parents=True)
    (root / "latka_jazn").mkdir()
    (root / "latka_jazn/version.py").write_text('PACKAGE_VERSION="1.2.3"\n', encoding="utf-8")
    monkeypatch.delenv("JAZN_OPERATOR_STATE_ROOT", raising=False)
    monkeypatch.setenv("JAZN_STUDIO_ACCEPTANCE_PROFILE", "isolated")
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(root / ".settings_local/acceptance/operator"))
    store = RunStore(root)
    report = store.create(("gui-daemon", "chat-resume"), sys.executable, {})
    folder, token = issue_staging(root, store.folder(report["run_id"]), "gui-daemon")
    return root, store, report, folder, token


def test_local_acceptance_is_fresh_single_use_and_cleanup_can_resume(owned):
    root, _, report, folder, token = owned
    assert folder.is_relative_to(root / ".settings_local/acceptance/operator")
    assert validate_staging(root, folder, report["run_id"], "gui-daemon", token) == folder
    with pytest.raises(FileExistsError):
        validate_staging(root, folder, report["run_id"], "gui-daemon", token)
    assert validate_staging(root, folder, report["run_id"], "gui-daemon", token, cleaning=True) == folder


@pytest.mark.parametrize("mutation", ["token", "run", "case", "root", "stale", "future", "nonempty", "traversal"])
def test_refuses_foreign_stale_or_nonfresh_staging(owned, mutation):
    root, _, report, folder, token = owned
    run_id, case = report["run_id"], "gui-daemon"
    if mutation == "token":
        token = "foreign"
    elif mutation == "run":
        run_id = "run-" + "0" * 32
    elif mutation == "case":
        case = "chat-resume"
    elif mutation == "root":
        root = root.parent / "other-system"
    elif mutation in {"stale", "future"}:
        claim = folder.parent / (folder.name + ".claim.json")
        payload = json.loads(claim.read_text())
        payload["created"] = time.time() + (60 if mutation == "future" else -1000)
        claim.write_text(json.dumps(payload))
    elif mutation == "nonempty":
        (folder / "user-staging.txt").write_text("preserve")
    elif mutation == "traversal":
        folder = folder / ".." / folder.name
    with pytest.raises(ValueError):
        validate_staging(root, folder, run_id, case, token)


@pytest.mark.parametrize("name", ["", "memory", "workspace_runtime", ".settings_local/acceptance/runtime"])
def test_protected_paths_are_never_authorized(owned, name):
    root, _, report, _, token = owned
    with pytest.raises(ValueError):
        validate_staging(root, root / name, report["run_id"], "gui-daemon", token)


def test_junction_is_rejected_even_when_target_stays_in_acceptance(owned):
    root, _, report, folder, token = owned
    target = folder.parent / "other"
    target.mkdir()
    folder.rmdir()  # Only the freshly created empty synthetic test directory.
    if os.name == "nt":
        result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(folder), str(target)], capture_output=True)
        assert result.returncode == 0, result.stderr
    else:
        folder.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="Dowiązanie"):
        validate_staging(root, folder, report["run_id"], "gui-daemon", token)


def test_real_child_arguments_enter_live_mode_without_model_or_memory_mutation(owned):
    root, store, report, _, _ = owned
    folder, token = issue_staging(root, store.folder(report["run_id"]), "chat-resume")
    private = root / "memory"
    private.mkdir()
    sentinel = private / "sentinel.txt"
    sentinel.write_bytes(b"private synthetic sentinel")
    env = dict(os.environ, **{TOKEN_ENV: token})
    proc = subprocess.run([sys.executable, "-X", "utf8", "-m", "tools.jazn_run_studio.tpa_live",
                           "--root", str(root), "--folder", str(folder), "--run-id", report["run_id"],
                           "--case", "chat-resume"], env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "BLOCKED"
    assert "model Ollama" in payload["reason"]
    assert "sandbox" not in payload.get("evidence", {})
    assert not (folder / "owner.json").exists()
    assert sentinel.read_bytes() == b"private synthetic sentinel"


@pytest.mark.parametrize("sandbox", [False, True])
def test_entrypoint_dispatch_and_structured_validation_failure(owned, monkeypatch, capsys, sandbox):
    from tools.jazn_run_studio import tpa_live
    root, _, report, folder, token = owned
    calls = []
    monkeypatch.setenv(TOKEN_ENV, token)
    monkeypatch.setattr(tpa_live, "exercise", lambda *args: calls.append("live") or {"status": "PASS"})
    monkeypatch.setattr(tpa_live, "sandbox", lambda *args: calls.append("sandbox") or {"status": "PASS"})
    argv = ["tpa_live", "--root", str(root), "--folder", str(folder), "--run-id", report["run_id"], "--case", "gui-daemon"]
    monkeypatch.setattr(sys, "argv", argv + (["--sandbox"] if sandbox else []))
    assert tpa_live.main() == 0
    assert calls == (["sandbox"] if sandbox else ["live"])
    capsys.readouterr()
    assert tpa_live.main() == 1  # Refuse a replay of the already consumed claim.
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "BLOCKED" and failed["pre_start_rejected"] is True
    assert "walidacji" in failed["reason"]
    assert calls == (["sandbox"] if sandbox else ["live"])


@pytest.mark.parametrize("saved_id, observed_id, expected", [("owned", "owned", True), ("owned", "foreign", False), (None, "foreign", False)])
def test_cleanup_only_stops_the_recorded_verified_instance(owned, monkeypatch, saved_id, observed_id, expected):
    from tools.jazn_run_studio import tpa_live
    for key in ("JAZN_MEMORY_ROOT", "JAZN_MEMORY_MODE", "JAZN_OPERATOR_STATE_ROOT", "JAZN_STUDIO_ACCEPTANCE_PROFILE"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    root, _, _, folder, _ = owned
    (folder / "SYSTEM").mkdir()
    (folder / "owner.json").write_text(json.dumps({"root": str((folder / "SYSTEM").resolve()),
                                                 "url": "http://127.0.0.1:43123", "instance_id": saved_id}))
    actions = []
    events = queue.Queue()
    identity = {k: True for k in ("root_matches", "process_identity_confirmed", "endpoint_identity_matches", "version_matches", "heartbeat_fresh")}
    identity["instance_id"] = observed_id
    events.put(("status", "evidence", identity))
    def action(key):
        actions.append(key)
        return SimpleNamespace(done=SimpleNamespace(wait=lambda _: True), state="succeeded", error="")
    monkeypatch.setattr(tpa_live, "Controller", lambda *args: SimpleNamespace(start_action=action, critical_events=events, events=queue.Queue(), close=lambda: None))
    result = tpa_live.cleanup(folder, sys.executable)
    assert result["ok"] is expected
    assert actions == (["status", "stop"] if expected else ["status"])


def test_cleanup_before_start_does_not_create_a_controller(owned, monkeypatch):
    from tools.jazn_run_studio import tpa_live
    monkeypatch.setattr(tpa_live, "Controller", lambda *args: pytest.fail("No process to inspect or stop"))
    assert tpa_live.cleanup(owned[3], sys.executable) == {"ok": True, "reason": "daemon_not_started"}


@pytest.mark.parametrize("mode", ["live", "sandbox"])
def test_qt_queue_passes_run_authority_and_correct_mode(owned, monkeypatch, mode):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication
    from tools.jazn_run_studio.tpa_engine import TPARunner
    app = QCoreApplication.instance() or QCoreApplication([])
    root, store, _, _, _ = owned
    runner = TPARunner(root, sys.executable)
    runner.report = store.create(("gui-daemon",), sys.executable, {})
    runner.active, runner.execution = True, mode
    runner.probe = {"ok": True, "imports": {"PySide6": {"ok": True}}}
    runner.availability = {"gui-daemon": {"ready": True}}
    temporary = tempfile.TemporaryDirectory()
    with temporary:
        runner.temp = temporary
        captured = []
        monkeypatch.setattr(runner.process, "start", lambda python, args: captured.append((python, args)))
        runner._next()
        runner.timer.stop()
        assert runner.report is not None
        assert len(captured) == 1
        args = captured[0][1]
        assert ("--sandbox" in args) is (mode == "sandbox")
        assert args[args.index("--run-id") + 1] == runner.report["run_id"]
        token = runner.process.processEnvironment().value(TOKEN_ENV)
        assert token and token not in " ".join(runner.report["results"][0]["command"])
        assert validate_staging(root, runner.live_folder, runner.report["run_id"], "gui-daemon", token) == runner.live_folder
        runner.active = False
        runner.temp = None
    del app


def test_summary_separates_execution_pass_from_full_acceptance(owned):
    from tools.jazn_run_studio.tpa_reports import summary
    report = owned[2]
    report["results"][0]["status"] = "PASS"
    result = summary(report)
    assert result["dziala"] == []
    assert result["zaliczony_zakres_bez_pelnego_odbioru"] == [report["results"][0]["title"]]
    assert result["full_gate_counts"] == {"NOT_RUN": 2}


@pytest.mark.parametrize("pre_start", [True, False])
def test_qt_result_preserves_original_refusal_with_or_without_cleanup_failure(owned, monkeypatch, pre_start):
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QCoreApplication, QProcess
    from tools.jazn_run_studio.tpa_engine import TPARunner
    app = QCoreApplication.instance() or QCoreApplication([])
    root, store, _, _, _ = owned
    runner = TPARunner(root, sys.executable)
    runner.report = store.create(("gui-daemon",), sys.executable, {})
    runner.active, runner.phase, runner.index = True, "live", 0
    runner.started, runner.log_name = time.monotonic(), "gui-daemon.log"
    runner.live_result = {"status": "BLOCKED", "reason": "Pierwotna odmowa walidacji", "pre_start_rejected": pre_start}
    monkeypatch.setattr(runner.process, "start", lambda *args: pytest.fail("Pre-start rejection must not spawn cleanup"))
    if pre_start:
        runner._finished(1, QProcess.ExitStatus.NormalExit)
    else:
        runner.live_exit_code, runner.cleanup_result = 1, {"ok": False}
        runner._live_done(1)
    assert runner.report is not None
    saved = store.load(runner.report["run_id"])["results"][0]
    assert saved["reason"].startswith("Pierwotna odmowa walidacji")
    assert saved["status"] == "BLOCKED" and saved["full_gate"] == "NOT_RUN"
    assert ("sprzątnięcia" in saved["reason"]) is (not pre_start)
    runner.active = False
    del app
