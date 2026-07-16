from __future__ import annotations

from pathlib import Path
import os

import py7zr
import pytest

from latka_jazn.memory import raw_archive
from latka_jazn.memory.raw_archive import (
    RawArchiveEntry,
    RawArchiveSafetyPolicy,
    unpack_chat_html_archive,
)


def _write_archive(root: Path, entries: dict[str, bytes]) -> Path:
    source = root / "archive-source"
    source.mkdir(parents=True)
    archive = root / "chat.html.7z"
    with py7zr.SevenZipFile(archive, "w") as handle:
        for index, (arcname, content) in enumerate(entries.items()):
            path = source / f"entry-{index}"
            path.write_bytes(content)
            handle.write(path, arcname=arcname)
    return archive


@pytest.mark.security
def test_safe_archive_is_staged_validated_and_atomically_installed(tmp_path: Path) -> None:
    _write_archive(tmp_path, {"nested/export.html": b"<html>safe</html>"})
    report = unpack_chat_html_archive(tmp_path)
    output = tmp_path / "memory" / "raw" / "chat.html"
    assert report.status == "unpacked", report.error
    assert report.selected_html == "nested/export.html"
    assert output.read_bytes() == b"<html>safe</html>"
    assert not list(output.parent.glob(".chat-html-staging-*"))
    assert not list(output.parent.glob(".chat.html.*.tmp"))


@pytest.mark.security
@pytest.mark.parametrize("malicious", ["../secret.html", "/absolute/chat.html", "C:/Windows/chat.html", "//server/share/chat.html"])
def test_archive_listing_rejects_traversal_and_absolute_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    malicious: str,
) -> None:
    archive = tmp_path / "chat.html.7z"
    archive.write_bytes(b"placeholder")
    monkeypatch.setattr(raw_archive, "py7zr_available", lambda: True)
    monkeypatch.setattr(raw_archive, "_list_py7zr", lambda _path: [
        RawArchiveEntry(malicious, 10, 10, False, True),
    ])
    report = unpack_chat_html_archive(tmp_path)
    assert report.status == "validation_failed"
    assert not (tmp_path / "memory" / "raw" / "chat.html").exists()


@pytest.mark.security
def test_archive_symlink_is_rejected_or_skipped_when_platform_cannot_create_it(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    link = tmp_path / "linked.html"
    source.write_text("<html>source</html>", encoding="utf-8")
    try:
        os.symlink(source, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable on this Windows runner: {exc}")
    archive = tmp_path / "chat.html.7z"
    try:
        with py7zr.SevenZipFile(archive, "w") as handle:
            handle.write(link, arcname="linked.html")
    except OSError as exc:
        pytest.skip(f"py7zr cannot archive symlinks on this runner: {exc}")
    report = unpack_chat_html_archive(tmp_path)
    assert report.status == "validation_failed"
    assert "link" in str(report.error).lower()


def _fake_archive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entries: list[RawArchiveEntry]) -> None:
    (tmp_path / "chat.html.7z").write_bytes(b"x" * 100)
    monkeypatch.setattr(raw_archive, "py7zr_available", lambda: True)
    monkeypatch.setattr(raw_archive, "_list_py7zr", lambda _path: entries)


@pytest.mark.security
def test_archive_rejects_oversized_single_entry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_archive(monkeypatch, tmp_path, [RawArchiveEntry("chat.html", 50, 101, False, True)])
    report = unpack_chat_html_archive(tmp_path, policy=RawArchiveSafetyPolicy(max_file_bytes=100))
    assert report.status == "validation_failed"
    assert "file size" in str(report.error)


@pytest.mark.security
def test_archive_rejects_oversized_total(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_archive(monkeypatch, tmp_path, [
        RawArchiveEntry("chat.html", 50, 70, False, True),
        RawArchiveEntry("note.txt", 50, 70, False, True),
    ])
    report = unpack_chat_html_archive(tmp_path, policy=RawArchiveSafetyPolicy(max_file_bytes=100, max_total_bytes=100))
    assert report.status == "validation_failed"
    assert "total" in str(report.error)


@pytest.mark.security
def test_archive_rejects_bomb_compression_ratio(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_archive(monkeypatch, tmp_path, [RawArchiveEntry("chat.html", 1, 1000, False, True)])
    report = unpack_chat_html_archive(tmp_path, policy=RawArchiveSafetyPolicy(max_compression_ratio=10))
    assert report.status == "validation_failed"
    assert "ratio" in str(report.error)


@pytest.mark.security
def test_archive_rejects_multiple_html_and_no_html(tmp_path: Path) -> None:
    multiple = tmp_path / "multiple"
    multiple.mkdir()
    _write_archive(multiple, {"a.html": b"a", "b.html": b"b"})
    report = unpack_chat_html_archive(multiple)
    assert report.status == "validation_failed"
    assert "exactly one" in str(report.error)

    none = tmp_path / "none"
    none.mkdir()
    _write_archive(none, {"readme.txt": b"no html"})
    report = unpack_chat_html_archive(none)
    assert report.status == "validation_failed"
    assert "no HTML" in str(report.error)


@pytest.mark.security
def test_archive_failure_leaves_no_staging_residue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _fake_archive(monkeypatch, tmp_path, [RawArchiveEntry("../chat.html", 10, 10, False, True)])
    report = unpack_chat_html_archive(tmp_path)
    assert report.status == "validation_failed"
    raw = tmp_path / "memory" / "raw"
    assert not raw.exists() or not list(raw.iterdir())
