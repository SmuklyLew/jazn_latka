"""Closed report indexes, not deferred directory mtimes, order stored evidence."""
import os

import pytest

from tools.jazn_run_studio.tpa_history_paging import read_page


def inventory(base):
    base.mkdir()
    for number in range(4):
        folder = base / f"run-{number:032x}"
        folder.mkdir()
        path = folder / "report.json"
        path.write_text("{}", encoding="utf-8")
        os.utime(path, ns=(1000 + number, 1000 + number))


def test_directory_mtime_changes_do_not_invalidate_committed_index_pages(tmp_path):
    base = tmp_path / "runs"
    inventory(base)
    def load(folder):
        # Explicitly reproduce NTFS publishing a delayed directory mtime.
        os.utime(folder, ns=(2000, 2000))
        return {"id": folder.name}, 2
    first = read_page(base, load, limit=2, index_file="report.json")
    assert first.next_cursor and len(first.runs) == 2 and not first.errors
    second = read_page(base, load, cursor=first.next_cursor, index_file="report.json")
    assert second.next_cursor is None and not second.errors
    assert [run["id"] for run in first.runs + second.runs] == [f"run-{number:032x}" for number in reversed(range(4))]


def test_changed_report_index_requires_refresh(tmp_path):
    base = tmp_path / "runs"
    inventory(base)
    first = read_page(base, lambda folder: ({"id": folder.name}, 2), limit=2, index_file="report.json")
    (base / f"run-{0:032x}" / "report.json").write_text('{"new":"revision"}', encoding="utf-8")
    with pytest.raises(ValueError, match="zmieniła"):
        read_page(base, lambda folder: ({"id": folder.name}, 2), cursor=first.next_cursor, index_file="report.json")


def test_cursor_is_bound_to_discovery_index_policy(tmp_path):
    base = tmp_path / "runs"
    inventory(base)
    first = read_page(base, lambda folder: ({"id": folder.name}, 2), limit=2, index_file="report.json")
    with pytest.raises(ValueError, match="kursor"):
        read_page(base, lambda folder: ({"id": folder.name}, 2), cursor=first.next_cursor)
