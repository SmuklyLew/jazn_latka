"""Invalid argument refusal uses the canonical writer and durability barrier."""
import pytest
pytest.importorskip("PySide6")
from tools.jazn_run_studio.tpa_engine import TPARunner
from tests.test_jazn_tpa_execution_qt import system, wait_until
from tests.test_jss_tpa_async_persistence_qt import hold_first_save


@pytest.mark.parametrize("cancel", [False, True])
def test_invalid_interpreter_keeps_gui_uncommitted_until_snapshot_ack(system, monkeypatch, cancel):
    root, _ = system
    runner = TPARunner(root, "")
    entered, release, _ = hold_first_save(runner, monkeypatch, final=True)
    completed, starts = [], []
    runner.completed.connect(completed.append)
    monkeypatch.setattr(runner.process, "start", lambda *_args: starts.append(1))
    runner.start_selection(("gui-daemon",))
    try:
        wait_until(entered.is_set)
        assert runner.report is not None
        folder = runner.store.folder(runner.report["run_id"])
        assert (folder / "manifest.json").is_file()
        assert runner.report["results"][0]["status"] == "QUEUED"
        assert not list(folder.glob("snapshot-*.json"))
        assert runner.report["finished_utc"] is None
        assert runner.active and runner.persistence_pending and not completed
        if cancel:
            runner.stop()
    finally:
        release.set()
        wait_until(lambda: not runner.active)
    assert not starts and len(completed) == 1
    saved = runner.store.load(runner.report["run_id"])
    assert saved["results"][0]["status"] == ("CANCELLED" if cancel else "BLOCKED")
    assert saved["environment"]["probe_executed"] is False
    assert saved["finished_utc"] and saved["results"][0]["full_gate"] == "NOT_RUN"


def test_invalid_interpreter_write_failure_never_claims_durable_refusal(system, monkeypatch):
    root, _ = system
    runner = TPARunner(root, "relative-python.exe")
    starts, completed = [], []
    monkeypatch.setattr(runner.process, "start", lambda *_args: starts.append(1))
    def fail(_report):
        raise OSError("Synthetic disk refusal")
    monkeypatch.setattr(runner.store, "save", fail)
    runner.completed.connect(completed.append)
    runner.start_selection(("gui-daemon",))
    wait_until(lambda: not runner.active)
    assert runner.report is not None
    assert not starts and len(completed) == 1
    assert runner.report["persistence_error"]
    assert runner.report["results"][0]["status"] == "CANCELLED"
    assert not list(runner.store.folder(runner.report["run_id"]).glob("snapshot-*.json"))


def test_blocked_ui_state_always_has_matching_committed_disk_state(system, monkeypatch):
    root, _ = system
    runner = TPARunner(root, str(root / "absent-python.exe"))
    observations = []
    def observe():
        if runner.report and runner.report["results"][0]["status"] == "BLOCKED":
            saved = runner.store.load(runner.report["run_id"])
            observations.append(saved["results"][0]["status"])
    runner.changed.connect(observe)
    runner.start_selection(("gui-daemon",))
    wait_until(lambda: not runner.active)
    assert observations and set(observations) == {"BLOCKED"}
