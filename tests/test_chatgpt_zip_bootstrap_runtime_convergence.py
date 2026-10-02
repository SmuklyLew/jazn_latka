from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast
import zipfile

import CHATGPT_BOOTSTRAP as bootstrap
from latka_jazn.version import PACKAGE_RELEASE_NAME, PACKAGE_VERSION
from tools.jazn_pack_generator_app.constants import SYSTEM_BOOTSTRAP_REQUIRED_FILES
from tools.jazn_pack_generator_app.manifest import (
    PUBLIC_MCP_HTTP_GATEWAY_MEMBER,
    PUBLIC_MCP_HTTP_TASKS_BRIDGE_MEMBER,
    PUBLIC_MCP_REMOTE_RUNTIME_MEMBER,
    PUBLIC_MCP_TASK_RESUME_MEMBER,
    SECURE_MCP_SERVER_MEMBER,
    build_host_bootstrap_contract,
)
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry


_REQUIRED_BOOTSTRAP_MEMBERS = {
    "run.py": "print('ok')\n",
    "AGENTS.md": "# test\n",
    "latka_jazn/version.py": "PACKAGE_VERSION='test'\n",
    "PACKAGE_INTEGRITY_MANIFEST.json": "{}\n",
    "SOURCE_PROVENANCE.json": "{}\n",
}


def _write_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in _REQUIRED_BOOTSTRAP_MEMBERS.items():
            zf.writestr(name, content)


def _plan(tmp_path: Path) -> PackPlan:
    source_root = tmp_path / "source"
    source_root.mkdir()
    members = tuple(SYSTEM_BOOTSTRAP_REQUIRED_FILES) + (
        SECURE_MCP_SERVER_MEMBER,
        PUBLIC_MCP_HTTP_GATEWAY_MEMBER,
        PUBLIC_MCP_HTTP_TASKS_BRIDGE_MEMBER,
        PUBLIC_MCP_REMOTE_RUNTIME_MEMBER,
        PUBLIC_MCP_TASK_RESUME_MEMBER,
    )
    entries = tuple(
        SourceEntry(
            source=source_root / name,
            archive_path=name,
            size_bytes=1,
            is_dir=False,
        )
        for name in members
    )
    return PackPlan(
        request=PackRequest(
            source_root=source_root,
            output_root=tmp_path / "out",
            content=ContentMode.SYSTEM,
        ),
        package_version=PACKAGE_VERSION,
        package_basename="jazn.system.zip",
        entries=entries,
        excluded=(),
        source_total_size_bytes=len(entries),
    )


def test_bootstrap_emits_post_materialization_activation_contract(tmp_path: Path) -> None:
    archive = tmp_path / "system.zip"
    destination = tmp_path / "active"
    _write_zip(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    payload = bootstrap.bootstrap_system_zip(
        zip_path=archive,
        destination=destination,
        expected_sha256=digest,
        expected_size_bytes=archive.stat().st_size,
    )

    activation = cast(dict[str, Any], payload["activation_contract"])
    local = cast(dict[str, Any], activation["local"])
    chatgpt_host = cast(dict[str, Any], activation["chatgpt_host"])
    remote = cast(dict[str, Any], activation["remote"])
    assert activation["schema_version"] == "chatgpt_post_materialization_activation/v1"
    assert activation["active_root_candidate"] == str(destination.resolve())
    assert activation["control_plane"] == "main.py"
    assert local["same_interpreter_preflight_supported"] is True
    assert local["preflight_requires_child_process"] is False
    assert local["package_can_create_host_executor"] is False
    assert local["runtime_start_entrypoint"] == "main.py start"
    assert local["runtime_status_entrypoint"] == "main.py status --snapshot --json"
    assert local["public_launcher_start_entrypoint"] == "run.py start"
    assert local["public_launcher_status_entrypoint"] == "run.py status --snapshot --json"
    assert local["activation_success_requires_verified_status"] is True
    assert chatgpt_host["control_plane_entrypoint"] == "main.py"
    assert chatgpt_host["persistent_bridge_entrypoint"] == "main.py chat-gpt --session-id <stable-session-id>"
    assert chatgpt_host["persistent_bridge_command"] == (
        "python -X utf8 main.py chat-gpt --session-id <stable-session-id>"
    )
    assert chatgpt_host["transport"] == "persistent_stdio_jsonl"
    assert chatgpt_host["fallback_transport"] == "daemon_bound_transactional_turns"
    assert chatgpt_host["uses_openai_api"] is False
    assert chatgpt_host["openai_api_key_required"] is False
    assert chatgpt_host["model_cli_argument_required"] is False
    assert chatgpt_host["model_binding"] == "chatgpt_host_selected_model"
    assert chatgpt_host["display_action_required"] == "display_exact"
    assert remote["preferred_transport"] == "public_streamable_http"
    assert remote["endpoint_path"] == "/mcp"
    assert remote["status_tool"] == "jazn_status"
    assert remote["turn_tool"] == "jazn_generate_visible_reply"


def test_same_interpreter_preflight_reuses_current_python_without_subprocess(tmp_path: Path) -> None:
    root = tmp_path / "active"
    root.mkdir()
    (root / "main.py").write_text("# marker\n", encoding="utf-8")
    (root / "run.py").write_text(
        "import json, sys\n"
        "assert sys.argv[1:] == ['host-preflight', '--json']\n"
        "print(json.dumps({'ok': True, 'gate_passed': True, 'execution_route': 'local_executor'}))\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )

    result = bootstrap.run_materialized_host_preflight_in_process(root)
    preflight = cast(dict[str, Any], result["preflight"])

    assert result["attempted"] is True
    assert result["mode"] == "same_interpreter_no_child_process"
    assert result["exit_code"] == 0
    assert result["ok"] is True
    assert result["gate_passed"] is True
    assert preflight["execution_route"] == "local_executor"


def test_pack_manifest_advertises_activation_without_claiming_host_capability(tmp_path: Path) -> None:
    contract = build_host_bootstrap_contract(_plan(tmp_path))

    assert contract["post_materialization_same_interpreter_preflight_supported"] is True
    assert contract["post_materialization_preflight_requires_child_process"] is False
    assert contract["post_materialization_preflight_flag"] == "--post-materialization-preflight"
    assert contract["post_materialization_preflight_entrypoint"] == "main.py host-preflight --json"
    assert contract["post_materialization_start_entrypoint"] == "main.py start"
    assert contract["post_materialization_status_entrypoint"] == "main.py status --snapshot --json"
    assert contract["post_materialization_public_launcher_start_entrypoint"] == "run.py start"
    assert contract["post_materialization_public_launcher_status_entrypoint"] == "run.py status --snapshot --json"
    assert contract["post_materialization_activation_sequence"][-1] == (
        "main.py chat-gpt --session-id <stable-session-id>"
    )
    assert contract["post_materialization_chatgpt_bridge_entrypoint"] == (
        "main.py chat-gpt --session-id <stable-session-id>"
    )
    assert contract["post_materialization_chatgpt_bridge_command"] == (
        "python -X utf8 main.py chat-gpt --session-id <stable-session-id>"
    )
    assert contract["post_materialization_chatgpt_transport"] == "persistent_stdio_jsonl"
    assert contract["post_materialization_chatgpt_fallback_transport"] == "daemon_bound_transactional_turns"
    assert contract["post_materialization_chatgpt_uses_openai_api"] is False
    assert contract["post_materialization_chatgpt_openai_api_key_required"] is False
    assert contract["post_materialization_chatgpt_model_cli_argument_required"] is False
    assert contract["post_materialization_chatgpt_model_binding"] == "chatgpt_host_selected_model"
    assert contract["post_materialization_chatgpt_visible_action_required"] == "display_exact"
    assert contract["post_materialization_activation_requires_verified_status"] is True
    assert contract["public_streamable_http_endpoint_path"] == "/mcp"
    assert contract["public_streamable_http_status_tool"] == "jazn_status"
    assert contract["public_streamable_http_turn_tool"] == "jazn_generate_visible_reply"
    assert contract["preferred_remote_runtime_transport"] == "public_streamable_http"
    assert contract["package_can_create_host_executor"] is False
    assert contract["remote_runtime_route_ready_from_package_alone"] is False


def test_release_identity_tracks_chatgpt_host_runtime_convergence() -> None:
    assert PACKAGE_VERSION == "16.3.25.5.97"
    assert PACKAGE_RELEASE_NAME == "chatgpt-host-runtime-convergence"
