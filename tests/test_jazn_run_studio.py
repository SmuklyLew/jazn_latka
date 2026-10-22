"""Operator foundation: real child processes, isolated roots, no live private data."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

import pytest

from tools.jazn_run_studio.core import (
    ACTIONS, Controller, Redactor, Settings, StudioError, daemon_evidence,
    load_settings, save_settings,
)


@pytest.fixture
def system(tmp_path: Path) -> Path:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").write_text('PACKAGE_VERSION="test"', encoding="utf-8")
    (tmp_path / "main.py").write_text("# synthetic isolated control plane", encoding="utf-8")
    (tmp_path / "run.py").write_text("print('synthetic diagnostic')", encoding="utf-8")
    return tmp_path


def test_controller_requires_a_system_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Controller(tmp_path)


def test_runtime_commands_delegate_to_public_launcher(system: Path) -> None:
    core = Controller(system)
    for action in ACTIONS:
        assert core.command(action.key) == [sys.executable, "-X", "utf8", str(system / "run.py"), *action.args]
    with pytest.raises(StudioError):
        core.command("status; echo unsafe")


@pytest.mark.parametrize("invalid", [
    {"token": "private"}, {"theme": "invented"}, {"accent": "red;"},
    {"python": "relative.exe"}, {"model": "--help"}, {"tunnel_id": "--token=secret"},
    {"model": "foo\nbar"}, {"theme": 3},
])
def test_settings_reject_invalid_values(invalid: dict) -> None:
    with pytest.raises(StudioError):
        Settings.validate(invalid)


def test_settings_save_reload_and_detect_stale_edits(system: Path) -> None:
    settings, digest = load_settings(system)
    assert digest is None
    saved = save_settings(system, settings, None)
    assert load_settings(system) == (settings, saved)
    with pytest.raises(StudioError):
        save_settings(system, Settings(theme="dark"), None)
    save_settings(system, Settings(theme="purple"), saved)
    assert load_settings(system)[0].theme == "purple"


def test_redactor_hides_known_and_structured_secrets() -> None:
    redactor = Redactor({"JAZN_DAEMON_TOKEN": "short", "PATH": "visible"})
    text = redactor.text('short Authorization: Bearer opaque-value api_key="abc" password=x https://user:pass@host/')
    for value in ("short", "opaque-value", '"abc"', "password=x", "user:pass"):
        assert value not in text
    assert "visible" == redactor.text("visible")


def test_port_and_pid_do_not_establish_identity_or_dialogue() -> None:
    result = daemon_evidence({"daemon": {"pid": 42, "endpoint_reachable": True}})
    assert result["endpoint_reachable"] is True
    assert result["process_identity_confirmed"] is False
    assert result["conversation_ready"] is False
    assert result["accepted_visible_turn"] is False


def test_successful_and_failed_real_child_processes(system: Path) -> None:
    core = Controller(system)
    good = core.start_action("version")
    assert good.done.wait(10)
    assert good.state == "succeeded"
    assert good.returncode == 0
    assert "synthetic diagnostic" in "\n".join(core.logs["version"])
    (system / "run.py").write_text("raise SystemExit(7)", encoding="utf-8")
    bad = core.start_action("version")
    assert bad.done.wait(10)
    assert bad.state == "failed"
    assert bad.returncode == 7


def test_missing_executable_is_a_failed_job(system: Path) -> None:
    core = Controller(system)
    job = core._reserve("missing")
    core._launch(job, [str(system / "missing-executable")], 1)
    assert job.done.wait(5)
    assert job.state == "failed"
    assert job.pid is None


def test_timeout_terminates_only_the_owned_child(system: Path) -> None:
    core = Controller(system)
    job = core._reserve("timeout-test")
    core._launch(job, [sys.executable, "-c", "import time; time.sleep(60)"], 1)
    assert job.done.wait(10)
    assert job.state == "failed"
    assert job.error == "timeout"
    assert job.proc is not None and job.proc.poll() is not None


def test_owned_stop_and_duplicate_job_protection(system: Path) -> None:
    core = Controller(system)
    job = core._reserve("service:test")
    core._launch(job, [sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"], None)
    deadline = time.monotonic() + 5
    while job.proc is None and time.monotonic() < deadline:
        time.sleep(0.01)
    with pytest.raises(StudioError):
        core._reserve("service:test")
    with pytest.raises(StudioError):
        core.stop_owned("service:foreign")
    core.stop_owned("service:test")
    assert job.done.wait(10)
    assert job.state == "stopped"
    with pytest.raises(StudioError):
        core.stop_owned("service:test")


def test_only_one_lifecycle_operation_may_be_reserved(system: Path) -> None:
    core = Controller(system)
    core._reserve("start")
    with pytest.raises(StudioError):
        core._reserve("restart")
    core.close()
    with pytest.raises(StudioError):
        core._reserve("version")


def test_invalid_status_cannot_succeed(system: Path) -> None:
    core = Controller(system)
    job = core.start_action("status")
    assert job.done.wait(10)
    assert job.state == "failed" and job.error == "invalid_status_json"


def test_batch_stops_at_first_failed_step(system: Path) -> None:
    (system / "run.py").write_text("import sys; raise SystemExit(4 if '--version' in sys.argv else 0)", encoding="utf-8")
    core = Controller(system)
    job = core.run_batch(("version", "preflight"))
    assert job.done.wait(10)
    assert job.state == "failed"
    assert "preflight" not in core.jobs
    with pytest.raises(StudioError):
        core.run_batch(("start",))


def test_report_is_sanitized_and_never_overwrites(system: Path, tmp_path: Path) -> None:
    core = Controller(system)
    core.redactor = Redactor({"TOKEN": "do-not-export"})
    core.emit("test", "log", 'TOKEN="do-not-export"')
    report = tmp_path / "report.json"
    core.export_report(report)
    assert "do-not-export" not in report.read_text(encoding="utf-8")
    assert json.loads(report.read_text(encoding="utf-8"))["logs"]["test"]
    with pytest.raises(FileExistsError):
        core.export_report(report)


def test_raw_stdout_is_cleared_after_completion(system: Path) -> None:
    core = Controller(system)
    core.redactor = Redactor({"TOKEN": "split-sensitive-value"})
    (system / "run.py").write_text("print('split-sensitive-value')", encoding="utf-8")
    job = core.start_action("version")
    assert job.done.wait(10)
    assert not job.output
    assert "split-sensitive-value" not in json.dumps(core.report())


def test_gui_navigation_theme_and_event_loop_remain_responsive(system: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6")
    if os.name != "nt" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from tools.jazn_run_studio.window import Window
    app = QApplication.instance() or QApplication([])
    core = Controller(system)
    window = Window(core, smoke=True)
    window.show()
    observed: list[bool] = []
    def verify() -> None:
        for index in range(window.pages.count()):
            window.nav.setCurrentRow(index)
            assert window.pages.currentIndex() == index
        for theme in ("system", "light", "dark", "purple", "custom"):
            core.settings = Settings(theme=theme)
            window.apply_theme()
        observed.append(True)
        window.close()
    QTimer.singleShot(50, verify)
    QTimer.singleShot(5000, app.quit)
    app.exec()
    assert observed == [True]
    assert core.closed is True


def test_optional_qt_dependency_uses_canonical_profile() -> None:
    from latka_jazn.dependencies.common import resolve_profile_requirements
    root = Path(__file__).resolve().parents[1]
    assert resolve_profile_requirements(root, ["run-studio"]) == ["PySide6-Essentials>=6.12,<6.13"]


@pytest.mark.skipif(os.name != "nt", reason="Windows loader PATH contract")
def test_windows_build_does_not_scan_foreign_dll_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.jazn_run_studio import build
    observed: dict = {}
    def run(argv: list[str], **kwargs):
        observed.update(kwargs)
        return type("Result", (), {"returncode": 0})()
    monkeypatch.setenv("PATH", "Z:\\foreign-tools\\bin")
    monkeypatch.setattr(sys, "argv", ["build.py", "--output", str(tmp_path / "new-build")])
    monkeypatch.setattr(build.subprocess, "run", run)
    assert build.main() == 0
    assert "foreign-tools" not in observed["env"]["PATH"]
    assert "System32" in observed["env"]["PATH"]
    assert observed["shell"] is False
