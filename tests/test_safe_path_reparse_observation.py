from pathlib import Path
from types import SimpleNamespace
import stat
import pytest
from latka_jazn.tools.safe_paths import _is_reparse_point

@pytest.mark.parametrize("mode,attributes,expected", [
    (stat.S_IFLNK, 0, True),
    (stat.S_IFDIR, 0x400, True),
    (stat.S_IFREG, 0x400, True),
    (stat.S_IFDIR, 0, False),
    (stat.S_IFREG, 0, False),
])
def test_nonfollowing_metadata_preserves_posix_and_windows_reparse_detection(monkeypatch, mode, attributes, expected):
    monkeypatch.setattr(Path, "lstat", lambda self: SimpleNamespace(st_mode=mode, st_file_attributes=attributes))
    assert _is_reparse_point(Path("candidate")) is expected


def test_missing_path_cannot_be_reported_as_reparse_point(tmp_path):
    assert _is_reparse_point(tmp_path / "missing") is False
