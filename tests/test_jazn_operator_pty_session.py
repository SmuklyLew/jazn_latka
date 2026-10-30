"""Owned PTY checks, no interaction with Jaźń runtime."""
from __future__ import annotations
import os
from pathlib import Path
import time
import pytest
from tools.jazn_run_studio.terminal_session import PtySession, safe_env

def test_env_redacts_runtime_credentials(tmp_path: Path):
    env = safe_env(tmp_path, {"PATH": "/usr/bin", "JAZN_MCP_OAUTH_CLIENT_SECRET": "secret", "JAZN_ROOT": "old"})
    assert env["JAZN_ROOT"] == str(tmp_path)
    assert "JAZN_MCP_OAUTH_CLIENT_SECRET" not in env

def test_terminal_is_not_autostarted(tmp_path: Path):
    session = PtySession(tmp_path)
    assert session.process is None
    session.close()
    assert session.read_available() == []

@pytest.mark.skipif(os.name == "nt", reason="Windows ConPTY acceptance needs optional pywinpty")
def test_posix_session_runs_only_owned_shell(tmp_path: Path):
    session = PtySession(tmp_path)
    session.start()
    try:
        session.write("printf 'JAZN_OPERATOR_PTY_OK\\n'\n")
        output = ""
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and "JAZN_OPERATOR_PTY_OK" not in output:
            output += "".join(session.read_available())
            time.sleep(0.05)
        assert "JAZN_OPERATOR_PTY_OK" in output
    finally:
        session.close()
