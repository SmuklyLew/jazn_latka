"""Regression checks for Studio structured diagnostics and readiness."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from latka_jazn.tools.jazn_studio import core


def test_studio_console_progress_keeps_doctor_json(monkeypatch, tmp_path: Path) -> None:
    """Progress on stdout must not hide the trailing canonical doctor payload."""
    output = '✔ 100% Manifest i kontrakty\n✔ 100% Gotowość\n{\n  "installation_ok": true,\n  "live_runtime_ready": false\n}\n'

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(core.subprocess, "run", fake_run)
    result = core._invoke(["python", "run.py", "doctor", "--json"], cwd=tmp_path)
    assert result["ok"] is True
    assert result["result"]["installation_ok"] is True
    assert result["result"]["live_runtime_ready"] is False
    assert "stdout_tail" not in result["result"]


def test_studio_readyz_http_200_is_not_readiness(monkeypatch) -> None:
    """HTTP liveness is distinct from a negative runtime readiness payload."""
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self, amount):
            return b'{"status":"degraded","ready":false,"gateway_live":true}'

    monkeypatch.setattr(core, "urlopen", lambda request, timeout: Response())
    result = core.probe_http("http://127.0.0.1:8080/readyz")
    assert result["http_status"] == 200
    assert result["http_ok"] is True
    assert result["ok"] is False
    assert result["status"]["ready"] is False
    assert core.probe_http("http://127.0.0.1:8080/healthz")["ok"] is True
