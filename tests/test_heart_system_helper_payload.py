"""Reject malformed operation requests without poisoning Studio job state."""
from __future__ import annotations

from pathlib import Path
import pytest
from tools.jazn_run_studio.core import Controller, StudioError


@pytest.fixture
def controller(tmp_path: Path) -> Controller:
    (tmp_path / "latka_jazn").mkdir()
    (tmp_path / "latka_jazn/version.py").touch()
    (tmp_path / "main.py").touch()
    (tmp_path / "run.py").touch()
    return Controller(tmp_path)


@pytest.mark.parametrize("invalid", [
    {"unsupported": object()},
    {"nonfinite": float("nan")},
    {"oversize": "x" * 65536},
])
def test_helper_rejects_invalid_payload_before_reservation(controller: Controller, invalid: dict) -> None:
    """Invalid JSON inputs must not reserve a ghost operator job."""
    with pytest.raises(StudioError):
        controller.studio_helper("execute", "tests", invalid)
    assert "helper:execute:tests" not in controller.jobs


def test_helper_accepts_valid_payload_after_rejection(controller: Controller, monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid input can start immediately after a rejected helper request."""
    launched: list[object] = []
    monkeypatch.setattr(controller, "_launch", lambda job, argv, timeout: launched.append(job))
    with pytest.raises(StudioError):
        controller.studio_helper("execute", "tests", {"invalid": object()})
    job = controller.studio_helper("execute", "tests", {"path": "safe", "enabled": True})
    assert launched == [job]
    assert job.input_data == b'{"path": "safe", "enabled": true}'
    assert job.state == "starting"
    job.done.set()
