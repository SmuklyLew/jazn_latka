"""Portable frozen-snapshot safety and Windows stat/fstat regression.

Only synthetic files and metadata are used. No PRIVATE MEMORY is opened.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import time
from types import SimpleNamespace
from typing import cast

import pytest

from latka_jazn.tools.memory_rebuild_app.p1_provenance_chain import (
    _same_source_stamp,
    _stable_digest,
    _stamp,
)


def _metadata(*, ctime_ns: int = 123) -> os.stat_result:
    return cast(os.stat_result, SimpleNamespace(
        st_dev=15, st_ino=41, st_size=7, st_mtime_ns=999,
        st_ctime_ns=ctime_ns, st_birthtime_ns=123,
    ))


@pytest.mark.skipif(os.name != "nt", reason="Windows-only stat/fstat ctime semantics")
def test_windows_path_stat_and_fstat_agree_on_birthtime_not_ctime() -> None:
    # On Windows Python 3.12+, path stat exposes creation time in st_ctime,
    # while fstat may expose metadata-change time for the very same file.
    path_metadata = _metadata(ctime_ns=123)
    fd_metadata = _metadata(ctime_ns=456)
    assert _stamp(path_metadata) == _stamp(fd_metadata)


@pytest.mark.skipif(os.name != "nt", reason="Windows-only stat/fstat ctime semantics")
def test_windows_metadata_change_remains_detectable_within_a_single_api() -> None:
    assert not _same_source_stamp(_metadata(ctime_ns=123), _metadata(ctime_ns=456))
    assert _same_source_stamp(_metadata(ctime_ns=123), _metadata(ctime_ns=123))


def test_frozen_file_digest_matches_sha256_on_supported_platforms(tmp_path: Path) -> None:
    snapshot = tmp_path / "synthetic_snapshot.sqlite3"
    snapshot.write_bytes(b"test-only frozen content")
    result = _stable_digest(snapshot, max_bytes=1024, deadline=time.monotonic() + 30)
    assert result == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_sidecar_rejects_snapshot_even_with_valid_bytes(tmp_path: Path) -> None:
    snapshot = tmp_path / "synthetic_snapshot.sqlite3"
    snapshot.write_bytes(b"test-only frozen content")
    Path(str(snapshot) + "-wal").write_bytes(b"synthetic sidecar")
    with pytest.raises(ValueError, match="artifact_not_frozen"):
        _stable_digest(snapshot, max_bytes=1024, deadline=time.monotonic() + 30)


def test_size_limit_blocks_digest_on_supported_platforms(tmp_path: Path) -> None:
    snapshot = tmp_path / "synthetic_snapshot.sqlite3"
    snapshot.write_bytes(b"more than one byte")
    with pytest.raises(ValueError, match="artifact_size_limit"):
        _stable_digest(snapshot, max_bytes=1, deadline=time.monotonic() + 30)
