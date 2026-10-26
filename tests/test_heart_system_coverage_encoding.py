"""Machine audit JSON remains portable across Windows stdio code pages."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

@pytest.mark.parametrize("encoding", ["cp1250", "utf-8"])
def test_audit_cli_json_has_lossless_unicode_with_legacy_stdio(tmp_path: Path, encoding: str) -> None:
    env = dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING=encoding)
    completed = subprocess.run(
        [sys.executable, "-m", "latka_jazn.mcp.turn_coverage",
         "--expected", str(tmp_path / "missing.json"),
         "--observed", str(tmp_path / "missing-observed.json")],
        capture_output=True, env=env, timeout=15, check=False,
    )
    assert completed.returncode == 2
    # ASCII is a valid UTF-8 subset; JSON decoding must recover exact Polish text.
    report = json.loads(completed.stdout.decode("ascii"))
    assert "Jaźń" in report["truth_boundary"]
    assert report["reason_code"] == "input_unavailable_or_invalid:FileNotFoundError"
    assert report["ok"] is False
    assert report["current_message_toolset_verified"] is False
