"""Regression: finite fractional uptime never strands the JSS status worker."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import pytest

from tools.jazn_run_studio.core import Controller, Settings, StudioError


@pytest.fixture
def controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "system"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'PACKAGE_VERSION = "1.0.0"\nPACKAGE_RELEASE_NAME = "test"\n', encoding="utf-8"
    )
    (root / "main.py").write_text("# test\n", encoding="utf-8")
    (root / "run.py").write_text("# test\n", encoding="utf-8")
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "operator_workspace"))
    instance = Controller(root, Settings(daemon_url="http://127.0.0.1:8791"))
    yield instance
    instance.close()


def test_diagnostic_accepts_finite_fractional_seconds(controller: Controller) -> None:
    controller.emit("status", "daemon_diagnostic", {
        "schema_version": "jazn_studio_daemon_diagnostic/v1",
        "uptime_seconds": 434.312069, "pid": 2552, "heartbeat_fresh": True,
    })
    line = controller.logs["status"][-1]
    data = json.loads(line.removeprefix("JSS_DAEMON_DIAGNOSTIC "))
    assert data["uptime_seconds"] == 434.312069
    assert data["pid"] == 2552


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, [], {}, 1 + 2j])
def test_diagnostic_rejects_nonfinite_and_non_scalar_values(
    controller: Controller, invalid: object,
) -> None:
    with pytest.raises(StudioError, match="Nieprawidłowy format"):
        controller.emit("status", "daemon_diagnostic", {"uptime_seconds": invalid})
    assert not controller.logs.get("status")


def test_real_status_subprocess_reaches_terminal_event_with_float_uptime(
    controller: Controller, monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "root": str(controller.root),
        "runtime_version_full": "1.0.0-test",
        "daemon": {
            "pid": 2552, "daemon_instance_id": "isolated-test",
            "active_state": "active_trusted", "endpoint_reachable": True,
            "process_identity_confirmed": True, "endpoint_identity_matches": True,
            "endpoint_heartbeat_fresh": True,
            "ping": {"runtime_version": "1.0.0-test", "uptime_seconds": 434.312069},
        },
        "capability_matrix": {"conversation_ready": True},
    }
    script = "import json; print(" + repr(json.dumps(payload)) + ")"
    monkeypatch.setattr(
        controller, "command", lambda _key: [sys.executable, "-X", "utf8", "-c", script]
    )
    job = controller.start_action("status")
    assert job.done.wait(15), "A valid uptime must not strand studio-status"
    assert job.state == "succeeded", job.error
    diagnosis = next(line for line in controller.logs["status"] if
                     line.startswith("JSS_DAEMON_DIAGNOSTIC "))
    assert json.loads(diagnosis.split(" ", 1)[1])["uptime_seconds"] == 434.312069
    terminal = [(key, kind, value) for key, kind, value in list(controller.events.queue)
                if key == "status" and kind == "state"]
    assert terminal and terminal[-1][2]["state"] == "succeeded"
