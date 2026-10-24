"""Versioned local acceptance tests: no fake execution or Git side effects."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.jazn_run_studio import local_acceptance as a


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    system = tmp_path / "source"
    system.mkdir()
    (system / "latka_jazn").mkdir()
    (system / "latka_jazn/version.py").write_text(
        'PACKAGE_VERSION = "1.0.0"\nDISTRIBUTION_VERSION = PACKAGE_VERSION\n'
        'PACKAGE_RELEASE_NAME = "local-test"\n', encoding="utf-8"
    )
    op = tmp_path / "operator"
    monkeypatch.setenv("JAZN_OPERATOR_STATE_ROOT", str(op))
    return system, op


def test_manual_results_are_outside_system_memory_and_workspace(roots):
    system, op = roots
    path = a.result_path(system)
    assert op in path.parents
    assert system not in path.parents
    assert len(a.catalog(system, a.load(system)[0])) >= 10
    assert not path.exists()


def test_save_archive_and_version_reopens_test(roots):
    system, op = roots
    data, digest = a.load(system)
    assert a.outcome(data, "chat-reconnect", a.scope_version(system)) is None
    digest = a.save_result(system, digest, "chat-reconnect", "failed", "Transport returned 1", "report-01")
    data, old = a.load(system)
    assert old == digest
    assert a.outcome(data, "chat-reconnect", a.scope_version(system))["status"] == "failed"
    with pytest.raises(ValueError, match="PASS"):
        a.archive_result(system, digest, "chat-reconnect")
    digest = a.save_result(system, digest, "chat-reconnect", "passed", "Two accepted turns", "report-02")
    digest = a.archive_result(system, digest, "chat-reconnect")
    data, _ = a.load(system)
    assert len(data["archive"]) == 1
    assert a.outcome(data, "chat-reconnect", a.scope_version(system))["archived"]
    with pytest.raises(ValueError, match="archiwum"):
        a.save_result(system, digest, "chat-reconnect", "failed", "Regression", "new")
    (system / "latka_jazn/version.py").write_text(
        'PACKAGE_VERSION = "1.0.1"\nDISTRIBUTION_VERSION = PACKAGE_VERSION\n'
        'PACKAGE_RELEASE_NAME = "local-test"\n', encoding="utf-8"
    )
    assert a.outcome(data, "chat-reconnect", a.scope_version(system)) is None
    assert len(list(op.rglob("*.backup-*"))) >= 1


def test_cas_and_secret_rejection(roots):
    system, _ = roots
    _, digest = a.load(system)
    fresh = a.save_result(system, digest, "gui-daemon", "blocked", "Brak 8879", "")
    with pytest.raises(ValueError, match="Odśwież"):
        a.save_result(system, digest, "gui-daemon", "passed", "all ok", "evidence")
    with pytest.raises(ValueError, match="sekret"):
        a.save_result(system, fresh, "gui-daemon", "passed", "token=my-secret-value", "evidence")


def test_custom_case_is_local_and_read_only_until_operator_marks_it(roots):
    system, _ = roots
    _, old = a.load(system)
    new = a.add_custom(system, old, "Nowy test Windows", "Otwórz Qt", "Okno działa")
    state, digest = a.load(system)
    assert new == digest
    custom = next(t for t in a.catalog(system, state) if t["title"] == "Nowy test Windows")
    assert custom["id"].startswith("local-")
    assert a.outcome(state, custom["id"], a.scope_version(system)) is None
    with pytest.raises(ValueError, match="Wypełnij"):
        a.add_custom(system, digest, "incomplete", "", "")


def test_corrupt_or_symlinked_state_fails_closed(roots):
    system, op = roots
    path = a.result_path(system)
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        a.load(system)


def test_qt_acceptance_page_renders_without_live_runtime(roots, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from tools.jazn_run_studio.local_acceptance_view import LocalAcceptancePanel
    system, _ = roots
    app = QApplication.instance() or QApplication([])
    panel = LocalAcceptancePanel(system)
    assert panel.table.rowCount() >= 10
    assert "DO WYKONANIA" in panel.table.item(0, 3).text()
    panel.state.setCurrentIndex(1)
    panel.note.setPlainText("Nie udało się uruchomić")
    panel.evidence.setText("operator-log-01")
    panel.save()
    assert panel.table.item(0, 3).text() == "FAILED"
    panel.close()
    app.processEvents()
