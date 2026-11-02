"""Read-only pagination exercises actual files, bounded pages and refused evidence."""
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from tools.jazn_run_studio.tpa_history_paging import read_page
from tools.jazn_run_studio.test_evidence_archive import history_page, history
from tests.test_jss_evidence_archive import archive_store

if TYPE_CHECKING:
    from tools.jazn_run_studio.window import Window


def folders(base, count):
    base.mkdir()
    for number in range(count):
        path = base / f"run-{number:032x}"
        path.mkdir()
        os.utime(path, ns=(1_000_000_000 + number, 1_000_000_000 + number))


def loader(folder):
    return {"run_id": folder.name}, 1


def test_all_237_records_are_reachable_without_duplicates(tmp_path):
    base = tmp_path / "runs"
    folders(base, 237)
    seen, cursor = [], None
    while True:
        page = read_page(base, loader, limit=17, cursor=cursor)
        assert page.total == 237 and len(page.runs) <= 17 and not page.errors
        seen += [run["run_id"] for run in page.runs]
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    assert len(seen) == len(set(seen)) == 237
    assert seen == [f"run-{number:032x}" for number in reversed(range(237))]


def test_page_byte_budget_defers_next_record_instead_of_dropping_it(tmp_path):
    base = tmp_path / "runs"
    folders(base, 9)
    seen, cursor = [], None
    while True:
        page = read_page(base, lambda path: ({"run_id": path.name}, 12 * 1024 * 1024), cursor=cursor)
        assert page.bytes_read <= 64 * 1024 * 1024
        seen += [run["run_id"] for run in page.runs]
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    assert len(seen) == len(set(seen)) == 9


def test_bad_record_does_not_hide_older_records_or_become_pass(tmp_path):
    base = tmp_path / "runs"
    folders(base, 4)
    def load(path):
        if path.name.endswith("3"):
            raise ValueError("Corrupt")
        return loader(path)
    page = read_page(base, load, limit=1)
    assert not page.runs and len(page.errors) == 1 and page.next_cursor
    older = read_page(base, load, cursor=page.next_cursor)
    assert len(older.runs) == 3 and not older.errors


def test_changing_inventory_refuses_stale_cursor(tmp_path):
    base = tmp_path / "runs"
    folders(base, 3)
    page = read_page(base, loader, limit=1)
    (base / ("run-" + "f" * 32)).mkdir()
    with pytest.raises(ValueError, match="zmieniła"):
        read_page(base, loader, cursor=page.next_cursor)


@pytest.mark.parametrize("cursor", ["[]", "null", "{}", "../../private", "x" * 601])
def test_malformed_cursors_refused(tmp_path, cursor):
    with pytest.raises(ValueError, match="kursor"):
        read_page(tmp_path / "absent", loader, cursor=cursor)


def test_cursor_cannot_be_reused_for_other_evidence_root(tmp_path):
    base, other = tmp_path / "one", tmp_path / "two"
    folders(base, 3)
    folders(other, 3)
    page = read_page(base, loader, limit=1)
    with pytest.raises(ValueError, match="kursor"):
        read_page(other, loader, cursor=page.next_cursor)


def test_mutation_during_read_refused_without_returning_partial_success(tmp_path):
    base = tmp_path / "runs"
    folders(base, 2)
    def changing(path):
        (base / ("run-" + "f" * 32)).mkdir(exist_ok=True)
        return loader(path)
    with pytest.raises(ValueError, match="podczas"):
        read_page(base, changing)


def test_discovery_does_not_follow_junctions(tmp_path):
    base, outside = tmp_path / "runs", tmp_path / "foreign"
    folders(base, 1)
    outside.mkdir()
    target = base / ("run-" + "f" * 32)
    try:
        target.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not permit creation of a directory symlink")
    called = []
    def track(path):
        called.append(path)
        return loader(path)
    page = read_page(base, track)
    assert len(page.runs) == 1 and len(page.errors) == 1
    assert target not in called


def populate(store, count):
    definitions = [{"id": "synthetic-case", "title": "Pagination fixture", "expected": "Not executed",
                    "steps": "Fixture only", "category": "test", "executor": "pytest", "mode": "automatic",
                    "files": [], "requirements": [], "limitations": "Synthetic fixture; no operator acceptance"}]
    reports = []
    for _ in range(count):
        reports.append(store.create(("synthetic-case",), "synthetic-python", {}, catalogue=definitions))
    return reports


def test_archive_and_legacy_store_can_reach_every_real_run_after_100(archive_store):
    reports = populate(archive_store, 104)
    expected = {report["run_id"] for report in reports}
    for get_page in (lambda cursor: history_page(archive_store.base, cursor=cursor),
                     lambda cursor: archive_store.history_page(cursor=cursor)):
        first = get_page(None)
        assert len(first.runs) == 100 and first.total == 104 and first.next_cursor
        second = get_page(first.next_cursor)
        assert len(second.runs) == 4 and second.next_cursor is None
        runs = first.runs + second.runs
        actual = {run.get("run_id", run.get("summary", {}).get("run_id")) for run in runs}
        assert actual == expected
        assert not first.errors and not second.errors
    _, notices = history(archive_store.base)
    assert len(notices) == 1 and "next_cursor" in notices[0]


def test_actual_verified_snapshots_above_64mib_remain_reachable(archive_store):
    reports = populate(archive_store, 6)
    for report in reports:
        folder = archive_store.folder(report["run_id"])
        # Exercise aggregate snapshot size with ordinary text-log lines. The
        # separately preserved unbroken-word redaction diagnostic is not a
        # storage-pagination result.
        (folder / "large.txt").write_bytes(b"fixture log row\n" * ((12 * 1024 * 1024) // 16))
        report["artifacts"] = ["large.txt"]
        archive_store.save(report)
    first = history_page(archive_store.base)
    assert first.bytes_read <= 64 * 1024 * 1024 and first.next_cursor
    second = history_page(archive_store.base, cursor=first.next_cursor)
    assert second.next_cursor is None and not first.errors and not second.errors
    assert len({run["summary"]["run_id"] for run in first.runs + second.runs}) == 6
    assert sum(page.bytes_read for page in (first, second)) > 64 * 1024 * 1024
    assert all(run["results"][0]["execution_status"] == "QUEUED" for run in first.runs + second.runs)


def test_qt_navigation_loads_older_run_pages_without_growing_loaded_history(archive_store):
    import time
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from tools.jazn_run_studio.test_history_view import TestHistoryPanel
    reports = populate(archive_store, 104)
    app = QApplication.instance() or QApplication([])
    widget = TestHistoryPanel(archive_store.root)
    def drain():
        deadline = time.monotonic() + 10
        while widget.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert widget.worker is None
    try:
        widget.refresh()
        drain()
        first = {run["summary"]["run_id"] for run in widget.runs}
        assert len(first) == 100 and widget.next_runs_button.isEnabled()
        widget.next_runs_button.click()
        drain()
        second = {run["summary"]["run_id"] for run in widget.runs}
        assert len(second) == 4 and not widget.next_runs_button.isEnabled()
        assert first.isdisjoint(second)
        assert first | second == {report["run_id"] for report in reports}
        widget.previous_runs_button.click()
        drain()
        assert {run["summary"]["run_id"] for run in widget.runs} == first
        assert not widget.previous_runs_button.isEnabled()
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_operator_history_uses_background_store_pages_and_reports_failure(archive_store, monkeypatch):
    import threading
    import time
    from types import SimpleNamespace
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget
    from tools.jazn_run_studio.operator_workspace import OperatorWorkspace
    reports = populate(archive_store, 4)
    app = QApplication.instance() or QApplication([])
    class Host(QMainWindow):
        def __init__(self):
            super().__init__()
            self.core = SimpleNamespace(lock=threading.RLock(), jobs={})
            self.local_acceptance_panel = SimpleNamespace(runner=SimpleNamespace(store=archive_store))
    host = Host()
    workspace = OperatorWorkspace.__new__(OperatorWorkspace)
    workspace.host = cast("Window", host)  # History-only host fixture, without runtime startup.
    workspace.tabs = QTabWidget(host)
    workspace._history()
    original = archive_store.history_page
    thread_ids = []
    def load(*, cursor=None):
        thread_ids.append(threading.get_ident())
        return original(limit=2, cursor=cursor)
    monkeypatch.setattr(archive_store, "history_page", load)
    def drain():
        deadline = time.monotonic() + 10
        while workspace.history_io.pending and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert not workspace.history_io.pending
    def displayed_ids():
        result = set()
        for index in range(workspace.history_tree.topLevelItemCount()):
            item = workspace.history_tree.topLevelItem(index)
            assert item is not None
            result.add(item.text(0))
        return result
    try:
        workspace.refresh_history()
        drain()
        first = displayed_ids()
        assert len(first) == 2 and workspace.history_older.isEnabled()
        workspace.history_older.click()
        drain()
        second = displayed_ids()
        assert first.isdisjoint(second)
        assert first | second == {"TPA: " + report["run_id"] for report in reports}
        assert thread_ids and all(value != threading.get_ident() for value in thread_ids)
        def failed(**kwargs):
            raise OSError("Synthetic disk refusal")
        monkeypatch.setattr(archive_store, "history_page", failed)
        workspace.refresh_history()
        drain()
        assert "OSError" in workspace.history_summary.text()
        assert not workspace.history_older.isEnabled()
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
