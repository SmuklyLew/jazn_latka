"""PTY geometry / explicit session ownership regressions; no Jaźń daemon."""
from __future__ import annotations
import os
from pathlib import Path
import pytest
from tools.jazn_run_studio.terminal_session import PtySession, StudioError


def test_resize_before_start_refuses_to_take_over_a_process(tmp_path: Path) -> None:
    s = PtySession(tmp_path)
    with pytest.raises(StudioError):
        s.resize(30, 90)
    with pytest.raises(ValueError):
        s.resize(1, 5)
    assert s.process is None


@pytest.mark.skipif(os.name == "nt", reason="Windows backend optional; manual ConPTY acceptance")
def test_posix_start_and_resize_report_actual_tty_geometry(tmp_path: Path) -> None:
    import termios
    s = PtySession(tmp_path)
    s.start(rows=33, cols=99)
    try:
        assert s.master is not None
        assert termios.tcgetwinsize(s.master) == (33, 99)
        s.resize(42, 111)
        assert termios.tcgetwinsize(s.master) == (42, 111)
    finally:
        s.close()
    with pytest.raises(StudioError):
        s.resize(40, 100)


def test_windows_backend_missing_resize_capability_fails_closed(monkeypatch, tmp_path: Path) -> None:
    import tools.jazn_run_studio.terminal_session as module
    class Owned:
        pass
    s = PtySession(tmp_path)
    s.process = Owned()
    monkeypatch.setattr(module.sys, "platform", "win32")
    with pytest.raises(StudioError, match="nie obsługuje"):
        s.resize(30, 100)


def test_windows_backend_resize_receives_rows_then_cols(monkeypatch, tmp_path: Path) -> None:
    import tools.jazn_run_studio.terminal_session as module
    class Owned:
        def __init__(self) -> None:
            self.dimensions: tuple[int, int] | None = None
        def setwinsize(self, rows: int, cols: int) -> None:
            self.dimensions = rows, cols
    owned = Owned()
    s = PtySession(tmp_path)
    s.process = owned
    monkeypatch.setattr(module.sys, "platform", "win32")
    s.resize(37, 108)
    assert owned.dimensions == (37, 108)
