"""Qt evidence boundaries, stale-result rejection and public command routing."""
from pathlib import Path
import json
import sys

import pytest

pytest.importorskip("PySide6")
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from tools.jazn_run_studio.core import Controller, Settings
from tools.jazn_run_studio.memory_view import evidence_rows
from tools.jazn_run_studio.window import Window


@pytest.fixture
def window(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    (tmp_path / "latka_jazn").mkdir()
    for file in ("latka_jazn/version.py", "main.py", "run.py"):
        (tmp_path / file).touch()
    window = Window(Controller(tmp_path, Settings()), smoke=True)
    window.show()
    yield window
    window.close()
    app.processEvents()


def test_memory_page_fits_minimum_viewport(window: Window) -> None:
    window.resize(860, 580)
    window.nav.setCurrentRow(5)
    QTest.qWait(150)
    page = window.pages.currentWidget()
    assert isinstance(page, QScrollArea)
    assert page.horizontalScrollBar().maximum() == 0
    assert window.memory_panel.tabs.count() == 3


def test_selecting_another_project_discards_delayed_result(window: Window) -> None:
    panel = window.memory_panel
    panel.pending["layout"] = 1.0
    panel.project.setText("another.memory-rebuild.json")
    panel.receive("memory:p1:layout", {"started": 1.0, "report": {"ok": True, "result": {}}})
    assert panel.tables["layout"].rowCount() == 0


def test_older_observation_cannot_replace_newer_request(window: Window) -> None:
    panel = window.memory_panel
    panel.pending["readiness"] = 2.0
    panel.receive("memory:p1:readiness", {"started": 1.0, "report": {"ok": True, "result": {}}})
    assert panel.tables["readiness"].rowCount() == 0


def test_failed_job_cannot_leave_memory_observation_running(window: Window) -> None:
    panel = window.memory_panel
    panel.pending["layout"] = 1.0
    panel.receive_state("memory:p1:layout", {"started": 1.0, "state": "failed", "error": "timeout"})
    item = panel.tables["layout"].item(0, 1)
    assert item is not None and item.text() == "blocked"
    assert "w toku" not in panel.timestamps["layout"].text()


def test_verified_runtime_and_claims_do_not_promote_recall_or_activation() -> None:
    rows = evidence_rows("readiness", {"runtime_ready": True,
        "checks": {"recall": {"state": "verified"}, "continuity": {"state": "verified"}},
        "memory_recall_ready": None, "memory_continuity_ready": None,
        "activation_authorized": False, "activation_preflight_passed": False})
    states = {name: state for name, state, _ in rows}
    assert states["Gotowość bieżącego runtime"] == "verified"
    assert states["Rzeczywisty recall"] == states["Ciągłość pamięci"] == "unverified"
    assert states["Autoryzacja aktywacji"] == states["Pozytywny preflight aktywacji"] == "unverified"


def test_equal_records_do_not_certify_claimed_lineage() -> None:
    rows = evidence_rows("comparison", {"comparisons": {"target_vs_host": {
        "state": "equal", "fingerprint_equal": True,
        "lineage": {"state": "matching_claims", "verification_state": "unverified"}}}})
    states = {name: state for name, state, _ in rows}
    assert states["target_vs_host: zgodność zawartości"] == "verified"
    assert states["target_vs_host: deklarowana lineage"] == "unverified"
    assert states["Niezależnie zweryfikowana proweniencja"] == "unverified"


def test_controller_routes_memory_through_public_launcher(window: Window, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    monkeypatch.setattr(window.core, "_launch", lambda *args: calls.append(args))
    job = window.core.inspect_memory("readiness")
    assert calls[0][1][3] == str(window.core.root / "run.py")
    assert calls[0][1][4:7] == ["memory-inspection", "--root", str(window.core.root)]
    assert "--operation" in calls[0][1]
    job.done.set()


def test_completed_report_displays_codes_in_its_own_tab(window: Window) -> None:
    panel = window.memory_panel
    panel.pending["readiness"] = 1.0
    panel.receive("memory:p1:readiness", {"started": 1.0,
        "report": {"ok": True, "result": {"runtime_ready": False}}})
    assert panel.tables["readiness"].rowCount() > 10
    assert panel.tables["comparison"].rowCount() == 0
    assert "ukończona" in panel.timestamps["readiness"].text()


def test_real_qt_readiness_roundtrip_and_redacted_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(tmp_path / "synthetic-memory"))
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "synthetic-workspace"))
    app = QApplication.instance() or QApplication([])
    core = Controller(Path(__file__).resolve().parents[1], Settings(python=sys.executable))
    window = Window(core, smoke=True)
    try:
        window.memory_panel.start("readiness")
        job = core.jobs["memory:p1:readiness"]
        for _ in range(200):
            QTest.qWait(50)
            if job.done.is_set() and window.memory_panel.tables["readiness"].rowCount():
                break
        assert job.state == "succeeded", job.snapshot()
        assert window.memory_panel.tables["readiness"].rowCount() > 10
        report = core.report()
        assert report["memory_observations"]["readiness"]["report"]["result"]["runtime_ready"] is False
        target = tmp_path / "report.json"
        core.export_report(target)
        exported = json.loads(target.read_text(encoding="utf-8"))
        assert exported["memory_observations"]["readiness"]["report"]["activation_authorized"] is False
        assert str(tmp_path) not in target.read_text(encoding="utf-8")
    finally:
        window.close()
        app.processEvents()
