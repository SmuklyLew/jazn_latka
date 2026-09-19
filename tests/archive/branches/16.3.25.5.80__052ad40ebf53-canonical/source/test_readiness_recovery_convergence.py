from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from latka_jazn.bootstrap.recovery_convergence import converge_recovery_result
from latka_jazn.cli_commands.diagnostics_convergence import apply_status_convergence


def _base_status() -> dict[str, Any]:
    return {
        "ok": True,
        "process_ok": True,
        "runtime_core_ready": False,
        "fully_ready": False,
        "runtime_write_ready": True,
        "runtime_write_ready_source": "fault_injection_fixture",
        "transactional_memory": {
            "ready": False,
            "exists": False,
            "status": "missing",
        },
        "daemon": {
            "active_state": "active_trusted",
            "endpoint_reachable": True,
            "pid_alive": True,
            "heartbeat_fresh": True,
        },
        "startup": {"raw_memory_status": {"status": "legacy_wrong_path"}},
        "capability_readiness": {},
        "system_readiness_profile": {
            "profile": "interactive_live_voice",
            "capabilities": {
                "runtime_core": {
                    "classification": "required",
                    "ready": False,
                    "status": "not_ready",
                },
                "live_voice": {
                    "classification": "degraded_allowed",
                    "ready": False,
                    "status": "not_tested",
                },
            },
        },
    }


def test_system_only_status_is_core_ready_without_transactional_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)

    status = apply_status_convergence(_base_status(), root=root)

    assert status["runtime_core_ready"] is True
    assert status["fully_ready"] is True
    assert status["operational_state"] == "active_ready_system_only"
    assert status["transactional_memory_required_for_core_runtime"] is False
    assert status["memory_availability"]["persistent_memory_enabled"] is False
    assert status["startup"]["raw_memory_status"]["status"] == "raw_missing"
    assert status["startup"]["raw_memory_status"]["memory_root"] == str(
        (workspace / "memory").resolve()
    )
    assert "transactional_memory_not_ready" not in status["operational_reasons"]
    assert "persistent_memory_optional_absent" in status["operational_degradations"]


def test_required_memory_mode_blocks_core_without_starting_fake_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "required")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)

    status = apply_status_convergence(_base_status(), root=root)

    assert status["runtime_core_ready"] is False
    assert status["operational_state"] == "active_required_memory_missing"
    assert "persistent_memory_required_missing" in status["operational_reasons"]


class FakeRecoveryModule:
    DEFAULT_CHATGPT_ROOT = Path("/tmp/not-used")
    DEFAULT_DAEMON_HOST = "127.0.0.1"
    DEFAULT_DAEMON_PORT = 8787
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 1.0
    DEFAULT_START_TIMEOUT_SECONDS = 2.0

    def __init__(self) -> None:
        self.started = 0
        self.marker_written = 0

    def runtime_preflight(self, root: Path) -> Any:
        return SimpleNamespace(structure_ok=True, manifest_ok=True, provenance_ok=True)

    def write_active_runtime_marker(self, root: Path, *, action: str) -> dict[str, Any]:
        self.marker_written += 1
        return {"ok": True, "active_root": str(root), "action": action}

    def start_daemon(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.started += 1
        return {"ok": True}

    def status_daemon(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"active_state": "active_trusted"}


def _recovery_result(root: Path) -> Any:
    return SimpleNamespace(
        ok=False,
        state="auto_memory_failed",
        active_root=str(root),
        report={
            "effective_profile": "system",
            "preflight_after": {
                "structure_ok": True,
                "manifest_ok": True,
                "provenance_ok": True,
            },
        },
        pending=False,
        exit_code=11,
        truth_boundary="legacy",
    )


def test_optional_memory_attach_failure_degrades_but_starts_verified_system(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    module = FakeRecoveryModule()
    result = _recovery_result(root)

    converged = converge_recovery_result(
        module,  # type: ignore[arg-type]
        result,
        destination=root,
        start_runtime_daemon=True,
        daemon_host="127.0.0.1",
        daemon_port=8787,
        heartbeat_interval=1.0,
        startup_timeout=2.0,
    )

    assert converged.ok is True
    assert converged.state == "active_memory_degraded"
    assert converged.exit_code == 0
    assert module.marker_written == 1
    assert module.started == 1
    assert converged.report["memory_degradation"]["blocking_core_runtime"] is False
    assert converged.report["memory_degradation"]["recall_allowed"] is False


def test_required_memory_missing_stays_fail_closed_before_daemon_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "required")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)
    module = FakeRecoveryModule()
    result = _recovery_result(root)

    converged = converge_recovery_result(
        module,  # type: ignore[arg-type]
        result,
        destination=root,
        start_runtime_daemon=True,
        daemon_host="127.0.0.1",
        daemon_port=8787,
        heartbeat_interval=1.0,
        startup_timeout=2.0,
    )

    assert converged.ok is False
    assert converged.state == "required_memory_missing"
    assert module.marker_written == 0
    assert module.started == 0


def test_package_import_paths_remain_importable() -> None:
    # Regression guard for the compatibility installers in package __init__.
    import latka_jazn.bootstrap.contract_loader  # noqa: F401
    import latka_jazn.cli_commands.audit  # noqa: F401
    from latka_jazn.bootstrap import chatgpt_recovery
    from latka_jazn.cli_commands import diagnostics

    assert getattr(chatgpt_recovery, "_optional_memory_recovery_convergence_installed") is True
    assert getattr(diagnostics, "_optional_memory_diagnostics_convergence_installed") is True
