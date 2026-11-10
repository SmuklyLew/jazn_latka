"""A failed Windows redirector must not recursively re-launch the same venv."""
from __future__ import annotations

from pathlib import Path

import pytest

from latka_jazn.dependencies import environment, private_python


def test_handoff_guard_prevents_recursive_reexec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE", "1")
    monkeypatch.setattr(private_python, "private_python_status", lambda _root: {
        "present": True, "ready": True, "current": False,
        "python_executable": "private-python", "state": "ready",
    })
    monkeypatch.setattr(environment, "dependency_activation_status",
                        lambda _root: pytest.fail("wrong interpreter selected"))
    report = environment.prepare_entrypoint_environment(tmp_path, auto_install=False)
    assert report["ok"] is False
    assert report["state"] == "private_python_handoff_not_established"
    assert report["reexec_python"] is None


def test_studio_launcher_rejects_repeated_handoff_before_reexec() -> None:
    text = (Path(__file__).resolve().parents[1] / "run_studio.py").read_text(encoding="utf-8")
    assert 'os.environ.get("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE") == "1"' in text
    assert '"Jaźń: private_python_handoff_not_established"' in text
    assert text.index('private_python_handoff_not_established') < text.index('handoff_to_managed_python')
