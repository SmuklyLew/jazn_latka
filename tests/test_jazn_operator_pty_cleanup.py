"""Owned PTY has an actual controlling tty and is reaped; daemon untouched."""
from __future__ import annotations
import os
from pathlib import Path
import time
import pytest
from tools.jazn_run_studio.terminal_session import PtySession, StudioError


@pytest.mark.skipif(os.name == "nt", reason="Windows pywinpty needs physical operator acceptance")
def test_controlling_terminal_and_reap(tmp_path: Path) -> None:
    s = PtySession(tmp_path)
    s.start()
    owned = s.process
    assert owned is not None and owned.poll() is None
    try:
        s.write("tty -s && echo JSS_TTY_OK\n")
        output = ""
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and "JSS_TTY_OK" not in output:
            output += "".join(s.read_available())
            time.sleep(.05)
        assert "JSS_TTY_OK" in output
    finally:
        s.close()
    assert owned.poll() is not None
    assert s.process is None
    s.close()  # Idempotent; only owner subprocess affected.


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group only")
def test_terminates_foreground_child_and_reaps(tmp_path: Path) -> None:
    s = PtySession(tmp_path)
    s.start()
    child = s.process
    assert child is not None
    try:
        s.write("sleep 30\n")
        time.sleep(.2)
    finally:
        s.close()
    assert child.poll() is not None


def test_stop_without_spawn_is_idempotent(tmp_path: Path) -> None:
    s = PtySession(tmp_path)
    s.close()
    s.close()
    assert s.process is None
