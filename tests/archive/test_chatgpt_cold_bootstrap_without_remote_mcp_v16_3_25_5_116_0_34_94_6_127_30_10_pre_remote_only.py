"""Cold-start policy: a local SYSTEM ZIP never requires remote MCP tool exposure."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.bootstrap.chatgpt_ingress_policy import (
    ChatGptEntryAction as Action,
    select_chatgpt_entry_action as select,
)
from latka_jazn.version import PACKAGE_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_missing_all_four_mcp_tools_does_not_block_local_zip_probe() -> None:
    assert select(complete_remote_toolset=False) is Action.PROBE_LOCAL_PROCESS
    assert select(
        complete_remote_toolset=False,
        local_process_created=True,
    ) is Action.VERIFY_LOCAL_SYSTEM
    assert select(
        complete_remote_toolset=False,
        local_process_created=True,
        verified_system=True,
    ) is Action.START_OR_RESUME_LOCAL
    assert select(
        complete_remote_toolset=False,
        verified_system=True,
        local_runtime_ready=True,
    ) is Action.USE_LOCAL_RUNTIME


def test_live_remote_wins_but_full_toolset_alone_is_not_readiness() -> None:
    assert select(complete_remote_toolset=True) is Action.CHECK_REMOTE_STATUS
    assert select(
        complete_remote_toolset=True,
        remote_ready=False,
    ) is Action.PROBE_LOCAL_PROCESS
    assert select(
        complete_remote_toolset=True,
        remote_ready=True,
        local_process_created=True,
        verified_system=True,
        local_runtime_ready=True,
    ) is Action.USE_REMOTE_RUNTIME


def test_forged_remote_success_does_not_bypass_current_message_toolset() -> None:
    with pytest.raises(ValueError, match="remote_ready_requires"):
        select(complete_remote_toolset=False, remote_ready=True)


def test_failed_host_spawn_is_not_python_failure_or_fake_runtime() -> None:
    assert select(
        complete_remote_toolset=False, local_process_created=False
    ) is Action.HOST_DIAGNOSTIC
    assert select(
        ingress_mode="remote_only", complete_remote_toolset=False
    ) is Action.HOST_DIAGNOSTIC
    with pytest.raises(ValueError, match="local_ready_requires"):
        select(local_runtime_ready=True, verified_system=False)


def test_cold_start_contract_preserves_tool_visibility_and_no_host_timeout_claim() -> None:
    startup = json.loads(
        (ROOT / "latka_jazn/resources/startup_contract.json").read_text(encoding="utf-8")
    )
    evidence = json.loads(
        (ROOT / "latka_jazn/resources/chatgpt_startup_evidence_contract.json").read_text(encoding="utf-8")
    )
    assert startup["version"] == PACKAGE_VERSION
    assert startup["chatgpt_remote_first"] is True
    assert startup["chatgpt_local_bootstrap_requires_mcp_toolset"] is False
    assert startup["chatgpt_remote_toolset_gate_applies_only_to_remote"] is True
    assert startup["chatgpt_pre_spawn_host_error_proves_runtime_failure"] is False
    assert startup["chatgpt_host_tool_probe_latency_is_runtime_controlled"] is False
    assert evidence["local_bootstrap"]["requires_remote_mcp_tools"] is False
    assert evidence["tool_discovery"]["complete_toolset_required_for_remote_only"] is True
    assert evidence["diagnostics"]["model_identity_requires_host_evidence"] is True


def test_short_loader_is_consistent_with_cold_path() -> None:
    loader = (ROOT / "docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt").read_text(encoding="utf-8")
    assert len(loader) <= 5000
    assert "Dotyczy to WYŁĄCZNIE zdalnego MCP" in loader
    assert "Brak `jazn_*` NIE blokuje lokalnego SYSTEM ZIP" in loader
    assert "czas oczekiwania" in loader.lower()
    assert "action=display_exact" in loader
