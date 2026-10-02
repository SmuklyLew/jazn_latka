from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import CHATGPT_BOOTSTRAP as bootstrap
from tools.jazn_pack_generator_app.constants import SYSTEM_BOOTSTRAP_REQUIRED_FILES
from tools.jazn_pack_generator_app.manifest import build_host_bootstrap_contract
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry


def _plan(tmp_path: Path) -> PackPlan:
    source_root = tmp_path / "source"
    source_root.mkdir()
    entries = tuple(
        SourceEntry(
            source=source_root / name,
            archive_path=name,
            size_bytes=1,
            is_dir=False,
        )
        for name in SYSTEM_BOOTSTRAP_REQUIRED_FILES
    )
    return PackPlan(
        request=PackRequest(
            source_root=source_root,
            output_root=tmp_path / "out",
            content=ContentMode.SYSTEM,
        ),
        package_version="test",
        package_basename="jazn.system.zip",
        entries=entries,
        excluded=(),
        source_total_size_bytes=len(entries),
    )


def test_post_materialization_contract_exposes_exact_chatgpt_control_plane_launch(
    tmp_path: Path,
) -> None:
    activation = bootstrap.build_post_materialization_activation_contract(tmp_path / "active")
    local = cast(dict[str, Any], activation["local"])
    bridge = cast(dict[str, Any], local["chatgpt_bridge"])

    assert bridge["schema_version"] == "chatgpt_local_launch/v1"
    assert bridge["canonical_mode"] == "chat-gpt"
    assert bridge["language_model_channel"] == "chatgpt_host"
    assert bridge["model_cli_argument_required"] is False
    assert bridge["paid_openai_api_required"] is False
    assert bridge["openai_api_key_required"] is False
    assert bridge["requires_host_process_execution"] is True
    assert bridge["package_can_create_host_executor"] is False
    assert bridge["persistent_stdio_preferred"] is True
    assert bridge["one_process_multiple_turns_preferred"] is True
    assert bridge["session_id_must_be_stable"] is True
    assert bridge["control_plane_argv"] == [
        "<python>",
        "-X",
        "utf8",
        "main.py",
        "chat-gpt",
        "--session-id",
        "<stable-session-id>",
    ]
    assert bridge["public_starter_argv"] == [
        "<python>",
        "-X",
        "utf8",
        "run.py",
        "chat-gpt",
        "--session-id",
        "<stable-session-id>",
    ]


def test_post_materialization_nonstreaming_contract_forbids_turn_replay(tmp_path: Path) -> None:
    activation = bootstrap.build_post_materialization_activation_contract(tmp_path / "active")
    bridge = cast(dict[str, Any], cast(dict[str, Any], activation["local"])["chatgpt_bridge"])
    fallback = cast(dict[str, Any], bridge["nonstreaming_turn_contract"])
    acceptance = cast(dict[str, Any], bridge["visible_reply_acceptance"])

    assert fallback["transport"] == "daemon_bound_transactional_turns"
    assert fallback["preallocate_request_id_before_process_spawn"] is True
    assert fallback["message_replay_allowed"] is False
    assert fallback["resume_argv_suffix"] == ["--daemon-result", "<same-request-id>"]
    assert acceptance == {
        "required_action": "display_exact",
        "valid_lineage_required": True,
        "message_envelope_required": True,
        "accepted_finalization_required": True,
    }


def test_system_package_manifest_carries_same_chatgpt_launch_truth(tmp_path: Path) -> None:
    contract = build_host_bootstrap_contract(_plan(tmp_path))

    assert contract["post_materialization_control_plane_start_entrypoint"] == "main.py start"
    assert (
        contract["post_materialization_chatgpt_bridge_entrypoint"]
        == "main.py chat-gpt --session-id <stable-session-id>"
    )
    assert contract["post_materialization_chatgpt_bridge_control_plane_argv"] == [
        "<python>",
        "-X",
        "utf8",
        "main.py",
        "chat-gpt",
        "--session-id",
        "<stable-session-id>",
    ]
    assert contract["post_materialization_chatgpt_language_model_channel"] == "chatgpt_host"
    assert contract["post_materialization_chatgpt_model_cli_argument_required"] is False
    assert contract["post_materialization_chatgpt_paid_openai_api_required"] is False
    assert contract["post_materialization_chatgpt_openai_api_key_required"] is False
    assert contract["post_materialization_chatgpt_requires_host_process_execution"] is True
    assert contract["post_materialization_chatgpt_request_id_preallocated_before_process_spawn"] is True
    assert contract["post_materialization_chatgpt_message_replay_allowed"] is False
    assert contract["post_materialization_chatgpt_visible_reply_requires"] == [
        "action=display_exact",
        "valid_lineage",
        "valid_MessageEnvelope",
        "accepted_finalization",
    ]
