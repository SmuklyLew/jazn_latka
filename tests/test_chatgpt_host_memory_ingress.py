from __future__ import annotations

"""Regression contracts for ChatGPT MCP ingress and nonblocking MEMORY core."""

import json
from pathlib import Path

import pytest

from latka_jazn.memory.availability import build_memory_availability_status
from tools.chatgpt_mcp_connection_doctor import classify_endpoint
from tools.jazn_pack_generator_app.manifest import build_memory_attachment_contract
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry

ROOT = Path(__file__).resolve().parents[1]


def test_core_dialogue_survives_missing_autobiographical_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "system"
    root.mkdir()
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("JAZN_MEMORY_MODE", "optional")
    monkeypatch.setenv("JAZN_MEMORY_READINESS_POLICY", "native_unified_required")
    monkeypatch.delenv("JAZN_MEMORY_ROOT", raising=False)

    status = build_memory_availability_status(root)
    assert status.persistent_memory_present is False
    assert status.core_runtime_allowed is True
    assert status.ordinary_dialogue_allowed is True
    assert status.recall_candidate_present is False
    assert status.persistent_memory_enabled is False
    assert status.status == "persistent_memory_absent_optional"


def test_memory_continuity_contract_matches_package_generator(tmp_path: Path) -> None:
    manifest = json.loads((ROOT / "MEMORY_ATTACHMENT_CONTRACT.json").read_text(encoding="utf-8"))
    source_root = tmp_path / "source"
    source_root.mkdir()
    plan = PackPlan(
        request=PackRequest(source_root=source_root, output_root=tmp_path / "out", content=ContentMode.SYSTEM),
        package_version="test",
        package_basename="test.zip",
        entries=(SourceEntry(source=source_root / "run.py", archive_path="run.py", size_bytes=1, is_dir=False),),
        excluded=(),
        source_total_size_bytes=1,
    )
    generated = build_memory_attachment_contract(plan)
    shared = (
        "autobiographical_continuity_requires_verified_memory",
        "core_reasoning_independent_of_persistent_memory_in_optional_mode",
        "memory_missing_core_effect",
        "required_mode_operator_override_can_block_core",
    )
    for key in shared:
        assert manifest[key] == generated[key]
    assert manifest["autobiographical_continuity_requires_verified_memory"] is True
    assert manifest["persistent_memory_required_for_core_runtime"] is False
    assert manifest["recall_without_verified_persistent_memory"] is False
    assert manifest["runtime_attach_joined_zip_required"] is False
    assert manifest["runtime_attach_repack_required"] is False


def test_host_contract_uses_distinct_capability_gates() -> None:
    data = json.loads(
        (ROOT / "latka_jazn/resources/chatgpt_startup_evidence_contract.json").read_text(encoding="utf-8")
    )
    assert len(data["required_current_message_tools"]) == 4
    assert "bounded_single_independent_executor_alternative" in data["pre_post_materialization_capabilities"]["before_unpack"]
    assert "run_canonical_preflight_start_live_status" in data["pre_post_materialization_capabilities"]["after_unpack"]
    assert "materialized_python_grants_mcp_tools" in data["pre_post_materialization_capabilities"]["prohibited_inferences"]
    assert data["memory_continuity_policy"]["missing_memory_blocks_core_reasoning"] is False
    assert "continuity_ready" in data["memory_continuity_policy"]["claims_require"]


def test_plugin_loopback_is_not_web_remote_ready() -> None:
    assert classify_endpoint("http://127.0.0.1:8080/mcp") == "loopback_or_private_endpoint"
    assert classify_endpoint("https://example.com/mcp") == "public_https_endpoint_configured_unverified"
    assert classify_endpoint("https://example.com/mcp?key=secret") == "invalid_mcp_endpoint"


def test_runbook_no_longer_requires_default_memory_zip_join_or_repack() -> None:
    text = (ROOT / "AGENTS.chatgpt.md").read_text(encoding="utf-8")
    assert "bez obowiązkowego joinu ZIP" in text
    assert "Legacy repack v3 jest jawną ścieżką migracji/eksportu" in text
    assert "wymagany bezpieczny repack v3" not in text
    assert "w ordinary `hybrid_adaptive` handoff pozostaje zabroniony".replace("`", "\x60") in text
