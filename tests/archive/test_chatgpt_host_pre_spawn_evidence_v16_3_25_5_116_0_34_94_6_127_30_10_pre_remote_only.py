from __future__ import annotations

"""Host transport evidence must never masquerade as SYSTEM/runtime evidence."""

import json

import pytest

from latka_jazn.bootstrap.chatgpt_ingress_capability import (
    main,
    negotiate_chatgpt_ingress,
)


@pytest.mark.parametrize("error", [
    "ClientError",
    "InvalidArgumentError",
    "TransportTimeoutError",
    "StreamingExecNotEnabledContainerError",
])
def test_pre_spawn_error_keeps_package_unknown(error: str) -> None:
    report = negotiate_chatgpt_ingress(
        phase="before_unpack",
        callable_tool_names=[],
        current_message_toolset_observed=True,
        local_process_created=False,
        host_executor_pre_spawn_error=error,
    )
    assert report["execution_route"] == "host_diagnostic"
    assert report["remote_runtime_available"] is False
    assert report["host_executor_pre_spawn_failure_type"] == error
    assert report["host_executor_pre_spawn_failure_kind"] == "host_executor_unavailable"
    assert report["failed_executor_filesystem_state"] == "unknown"
    assert report["failed_executor_package_state"] == "unknown"
    assert report["local_runtime_ready"] is False
    assert report["accepted_visible_turn"] is False
    assert "connect_or_select_verified_remote_jazn_mcp" in report["host_recovery_hint"]


def test_independent_executor_can_recover_after_primary_pre_spawn_error() -> None:
    report = negotiate_chatgpt_ingress(
        phase="after_unpack",
        callable_tool_names=[],
        current_message_toolset_observed=True,
        local_process_created=True,
        system_operator_verified=True,
        host_executor_pre_spawn_error="ClientError",
    )
    assert report["execution_route"] == "local_bootstrap"
    assert report["next_action"] == "run_canonical_preflight_start_and_live_status"
    assert report["failed_executor_filesystem_state"] == "unknown"
    assert report["local_executor_process_created"] is True
    assert report["accepted_visible_turn"] is False


def test_no_error_evidence_does_not_fabricate_failure() -> None:
    report = negotiate_chatgpt_ingress(phase="before_unpack")
    assert report["host_executor_pre_spawn_failure_type"] is None
    assert report["host_executor_pre_spawn_failure_kind"] is None
    assert report["failed_executor_filesystem_state"] is None


def test_unrecognized_exception_is_rejected_without_echoing_private_text(
    tmp_path, capsys,
) -> None:
    evidence = tmp_path / "host.json"
    evidence.write_text(json.dumps({
        "host_executor_pre_spawn_error": "SecretError: token=DO_NOT_ECHO",
        "local_process_created": False,
    }), encoding="utf-8")
    assert main(["--phase", "before_unpack", "--evidence-file", str(evidence)]) == 2
    printed = capsys.readouterr().out
    assert "DO_NOT_ECHO" not in printed
    assert json.loads(printed)["reason_code"] == "invalid_host_capability_evidence"
