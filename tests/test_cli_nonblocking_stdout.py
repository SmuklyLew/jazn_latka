"""Regressions for large host diagnostics on non-blocking stdout pipes."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys

from latka_jazn.cli import _emit


def test_emit_to_in_memory_stream_preserves_json_and_text(monkeypatch) -> None:
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    _emit({"ż": "ółw"}, as_json=True)
    assert json.loads(stream.getvalue()) == {"ż": "ółw"}
    stream.seek(0)
    stream.truncate(0)
    _emit("raw text", as_json=False)
    assert stream.getvalue() == "raw text\n"


def test_large_json_survives_nonblocking_host_stdout_pipe() -> None:
    # Reproduces the host signature: O_NONBLOCK stdout + >64KiB JSON.
    script = (
        "import os, sys\n"
        "from latka_jazn.cli import _emit\n"
        "os.set_blocking(sys.stdout.fileno(), False)\n"
        "_emit({'message': 'x' * 200000}, as_json=True)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    assert json.loads(completed.stdout)["message"] == "x" * 200000
