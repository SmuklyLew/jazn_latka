from __future__ import annotations

"""Executable host evidence gates; no live MCP service or private MEMORY needed."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from latka_jazn.bootstrap.chatgpt_ingress_capability import main, negotiate_chatgpt_ingress
from latka_jazn.mcp.chatgpt_toolset import REQUIRED_CHATGPT_TURN_TOOLS
from latka_jazn.mcp.remote_runtime import REGISTERED_MCP_STATUS_SCHEMA
from latka_jazn.memory.availability import build_memory_availability_status
from latka_jazn.version import PACKAGE_VERSION_FULL

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)


def _status(stamp: datetime = NOW) -> dict[str, object]:
    return {
        "evidence_schema": REGISTERED_MCP_STATUS_SCHEMA,
        "tool_name": "jazn_status",
        "registered_transport": "registered_mcp_app",
        "protocol_version": "2025-11-25",
        "ok": True,
        "ready": True,
        "gateway_live": True,
        "daemon_reachable": True,
        "package_version": PACKAGE_VERSION_FULL,
        "runtime_version": PACKAGE_VERSION_FULL,
        "runtime_instance_id": "daemon-test-a",
        "observed_at_utc": stamp.isoformat(),
        "runtime_heartbeat_at_utc": stamp.isoformat(),
    }


def _evaluate(**overrides: object) -> dict[str, object]:
    options: dict[str, object] = {
        "phase": "before_unpack",
        "callable_tool_names": REQUIRED_CHATGPT_TURN_TOOLS,
        "current_message_toolset_observed": True,
        "status_invoked_in_current_message": True,
        "status_payload": _status(),
        "now_utc": NOW,
    }
    options.update(overrides)
    return negotiate_chatgpt_ingress(**options)  # type: ignore[arg-type]


def test_before_unpack_uses_verified_current_message_remote_runtime() -> None:
    status = _evaluate()
    assert status["execution_route"] == "remote_runtime"
    assert status["remote_runtime_available"] is True
    assert status["local_runtime_ready"] is False
    assert status["accepted_visible_turn"] is False
    assert status["memory_required_for_core_ingress"] is False


def test_plugin_only_or_copied_status_never_makes_remote_ready() -> None:
    for options in (
        {"current_message_toolset_observed": False},
        {"status_invoked_in_current_message": False},
        {"status_payload": None},
        {"callable_tool_names": ["jazn_status"]},
    ):
        status = _evaluate(**options)
        assert status["execution_route"] == "host_diagnostic"
        assert status["remote_runtime_available"] is False


def test_stale_status_can_fall_back_to_real_local_process() -> None:
    status = _evaluate(
        status_payload=_status(NOW - timedelta(minutes=20)),
        local_process_created=True,
    )
    assert status["execution_route"] == "local_bootstrap"
    assert status["remote_runtime_available"] is False
    assert status["next_action"] == "discover_verify_and_materialize_system_operator"


def test_after_unpack_does_not_create_host_tools_or_grant_finalization() -> None:
    status = _evaluate(
        phase="after_unpack",
        callable_tool_names=[],
        status_invoked_in_current_message=False,
        status_payload=None,
        local_process_created=None,
        system_operator_verified=True,
    )
    assert status["execution_route"] == "host_diagnostic"
    assert status["materialized_operator_verified"] is True
    assert status["remote_runtime_available"] is False
    assert status["local_runtime_ready"] is False


def test_after_unpack_verified_operator_requires_live_runtime_preflight() -> None:
    status = _evaluate(
        phase="after_unpack",
        callable_tool_names=[],
        status_invoked_in_current_message=False,
        status_payload=None,
        local_process_created=True,
        system_operator_verified=True,
    )
    assert status["execution_route"] == "local_bootstrap"
    assert status["next_action"] == "run_canonical_preflight_start_and_live_status"
    assert status["accepted_visible_turn"] is False


def test_wrong_status_version_does_not_promote_remote_route() -> None:
    status_payload = _status()
    status_payload["runtime_version"] = "wrong-package"
    report = _evaluate(status_payload=status_payload)
    assert report["remote_runtime_available"] is False
    assert report["remote_reason_code"] == "registered_mcp_runtime_version_mismatch"


def test_unknown_phase_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported_chatgpt_ingress_phase"):
        _evaluate(phase="unknown")


def test_unreadable_optional_memory_file_never_blocks_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "system"
    memory = root / "memory"
    memory.mkdir(parents=True)
    path = memory / "MEMORY_PACKAGE_MANIFEST.json"
    path.write_text("pretend-file", encoding="utf-8")

    original_stat = Path.stat
    calls = 0

    def fail_second_stat(p: Path, *args: object, **kwargs: object):
        nonlocal calls
        if p == path:
            calls += 1
            if calls > 1:
                raise PermissionError("private memory cannot be inspected")
        return original_stat(p, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_second_stat)
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.setenv("JAZN_MEMORY_ROOT", str(memory))
    status = build_memory_availability_status(root)
    assert status.persistent_memory_present is False
    assert status.core_runtime_allowed is True
    assert status.recall_candidate_present is False
    assert status.ordinary_dialogue_allowed is True


def test_operator_cli_can_classify_local_bootstrap_without_private_memory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = tmp_path / "host-evidence.json"
    evidence.write_text(json.dumps({
        "callable_tool_names": [],
        "current_message_toolset_observed": True,
        "local_process_created": True,
        "system_operator_verified": True,
    }), encoding="utf-8")
    assert main(["--phase", "after_unpack", "--evidence-file", str(evidence)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["execution_route"] == "local_bootstrap"
    assert output["next_action"] == "run_canonical_preflight_start_and_live_status"
    assert output["accepted_visible_turn"] is False


def test_operator_cli_redacts_untrusted_host_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = tmp_path / "host-evidence.json"
    evidence.write_text(json.dumps({
        "callable_tool_names": ["jazn_status"],
        "current_message_toolset_observed": True,
        "status_payload": {"evidence_schema": "made-up", "secret": "DO_NOT_LEAK"},
    }), encoding="utf-8")
    assert main(["--phase", "before_unpack", "--evidence-file", str(evidence)]) == 2
    output = capsys.readouterr().out
    assert "DO_NOT_LEAK" not in output
    assert json.loads(output)["remote_reason_code"] == "unsupported_status_schema"
