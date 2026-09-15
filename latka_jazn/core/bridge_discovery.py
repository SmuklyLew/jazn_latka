from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from latka_jazn.bridge_secure_gateway import SecureGatewayPolicy
from latka_jazn.config import JaznConfig
from latka_jazn.core.host_tool_capabilities import build_host_tool_capability_snapshot
from latka_jazn.core.runtime_daemon import DEFAULT_DAEMON_HOST, DEFAULT_DAEMON_PORT, status_daemon
from latka_jazn.core.runtime_root import active_runtime_marker_path
from latka_jazn.mcp.secure_tunnel import build_secure_mcp_tunnel_plan, tunnel_client_executable_status
from latka_jazn.version import schema_version
from latka_jazn.core.conversation_entrypoint_contract import (
    AUTO_ROUTE_PRIORITY,
    conversation_entrypoint_contract,
)


OLLAMA_TRUTH_BOUNDARY = (
    "Ollama jest lokalnym backendem językowym przez natywne API /api/tags i /api/chat. "
    "Nie wymaga OPENAI_API_KEY i nie jest źródłem tożsamości, pamięci, stanu ani prawdy runtime Jaźni. "
    "Widoczna odpowiedź przechodzi przez istniejący runtime, walidację i prawdomówny fallback."
)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def discover_runtime_bridges(
    config: JaznConfig,
    *,
    host: str = DEFAULT_DAEMON_HOST,
    port: int = DEFAULT_DAEMON_PORT,
) -> dict[str, Any]:
    root = Path(config.root).resolve()
    marker_path = active_runtime_marker_path(root)
    marker = _read_json(marker_path)
    daemon = status_daemon(config, host=host, port=port, probe_endpoint=False)
    conversation = conversation_entrypoint_contract("--chat").to_dict()
    chatgpt = conversation_entrypoint_contract("--chat-gpt").to_dict()
    host_tool_capabilities = build_host_tool_capability_snapshot()
    secure_tunnel_plan = build_secure_mcp_tunnel_plan(root).to_dict()
    tunnel_client = tunnel_client_executable_status()
    return {
        "schema_version": schema_version("runtime_bridge_discovery"),
        "active_root": str(root),
        "marker_path": str(marker_path),
        "marker_found": marker is not None,
        "marker": marker or {},
        "daemon_status": daemon,
        "host_tool_capabilities": host_tool_capabilities,
        "conversation": {
            **conversation,
            "command": "python -X utf8 run.py chat --session-id <id>",
            "one_shot_command": 'python -X utf8 run.py chat -- "Cześć Łatko"',
            "backend_selection": "auto",
            "route_priority": list(AUTO_ROUTE_PRIORITY),
            "meaning": (
                "kanoniczne uniwersalne wejście do rozmowy; runtime wybiera dostępny backend językowy, "
                "ale pozostaje właścicielem sesji, tury, pamięci, narzędzi i finalizacji"
            ),
        },
        "local_chat": {
            "command": "python -X utf8 run.py chat --session-id <id>",
            "compatibility_command": "python main.py --chat --session-id <id>",
            "compatibility_alias_of": "conversation",
            "meaning": (
                "terminalna prezentacja kanonicznego run.py chat; nazwa local_chat jest zachowana "
                "wyłącznie dla zgodności starszych konsumentów discovery"
            ),
        },
        "chatgpt_bridge": {
            **chatgpt,
            "command": "python -X utf8 run.py chat-gpt --session-id <id>",
            "canonical_command": "run.py chat-gpt",
            "legacy_aliases": ["--chat-gpt-final-only", "--chat-gpt --final-only"],
            "transport": "persistent_stdio_jsonl",
            "transport_selection": "capability_negotiated",
            "fallback_transport": "daemon_bound_transactional_turns",
            "remote_transport": "openai_secure_mcp_tunnel_when_host_connector_available",
            "remote_failover_policy": "managed_tunnel_ready_plus_explicit_host_connector_capability",
            "per_message_cli_required": False,
            "per_message_cli_allowed_when_host_cannot_retain_stdio": True,
            "persistent_stdio_required": False,
            "nonstreaming_turn_command": (
                'python -X utf8 run.py chat-gpt --session-id <stable-session-id> '
                '--daemon-request-id <unique-turn-request-id> -- "<exact-user-message>"'
            ),
            "nonstreaming_resume_command": (
                "python -X utf8 run.py chat-gpt --session-id <stable-session-id> "
                "--daemon-result <same-request-id>"
            ),
            "request_id_preallocated_before_process_spawn": True,
            "ambiguous_transport_policy": "poll_same_request_id_never_local_replay",
            "local_turn_fallback_after_verified_daemon_submit": False,
            "persistent_bridge_process_required_when_host_supports_it": True,
            "persistent_bridge_process_required_when_host_cannot_retain_it": False,
            "daemon_transactional_resume_supported": True,
            "pipe_lifetime_is_identity": False,
            "accepted_visible_turn_required": True,
            "visible_turn_readiness": "accepted_final_visible_text_only",
            "requires_api_key": False,
            "uses_openai_api": False,
            "host_tool_capability_discovery": {
                "snapshot_status": host_tool_capabilities.get("status"),
                "manifest_present": host_tool_capabilities.get("manifest_present"),
                "manifest_source": host_tool_capabilities.get("manifest_source"),
                "verified_tools": list(host_tool_capabilities.get("verified_tools") or []),
                "advertised_tools": list(host_tool_capabilities.get("advertised_tools") or []),
                "capability_confirmation_required_for_tools": list(
                    host_tool_capabilities.get("capability_confirmation_required_for_tools") or []
                ),
                "probe_policy": "automatic_probe_read_only_only; mutating/private probes forbidden",
                "manifest_env": [
                    "JAZN_HOST_TOOL_CAPABILITIES_JSON",
                    "JAZN_HOST_TOOL_CAPABILITIES_FILE",
                ],
            },
            "meaning": (
                "kanoniczny most hosta ChatGPT: persistent stdin/JSONL jest preferowany, gdy host potrafi "
                "utrzymać proces; w przeciwnym razie trwały daemon utrzymuje logical session/turn lineage. "
                "Jeżeli host ma jawnie skonfigurowany i zweryfikowany OpenAI Secure MCP Tunnel oraz connector/app "
                "capability, ten sam runtime może być osiągany zdalnie bez tworzenia procesu przez bieżącą powierzchnię "
                "czatu. Żywotność pipe'a ani tunelu nie jest źródłem tożsamości ani dowodem gotowej odpowiedzi; "
                "widoczna może być tylko zaakceptowana final_visible_text. Tryb nie wykonuje żądania OpenAI model API."
            ),
        },
        "openai_bridge": {
            "command": "python main.py --chat-open-ai --session-id <id>",
            "aliases": ["--chat-openai"],
            "requires_api_key": True,
            "env": "OPENAI_API_KEY",
            "meaning": "ten sam runtime Jaźni + OpenAI Responses API jako model_adapter językowy",
        },
        "ollama_bridge": {
            "command": "python -X utf8 run.py chat-ollama --session-id <id>",
            "compatibility_command": "python main.py --chat-ollama --session-id <id>",
            "aliases": ["--ollama", "--local-llm"],
            "requires_api_key": False,
            "env": ["JAZN_OLLAMA_MODEL", "JAZN_OLLAMA_BASE_URL"],
            "probe_endpoint": "/api/tags",
            "chat_endpoint": "/api/chat",
            "meaning": "ten sam runtime Jaźni + lokalny model Ollama jako wymienna warstwa językowa; publiczne wejście operatorskie prowadzi przez run.py",
            "truth_boundary": OLLAMA_TRUTH_BOUNDARY,
        },
        "daemon": {
            "start": "python -X utf8 run.py start",
            "status": "python -X utf8 run.py status --json",
            "stop": "python -X utf8 run.py stop",
            "active_state_contract": "active_trusted / active_degraded / inactive",
        },
        "secure_gateway_scaffold": SecureGatewayPolicy().to_dict(),
        "secure_mcp": {
            "status": "implemented_secure_tunnel_managed_runtime_target",
            "server_command": secure_tunnel_plan["stdio_mcp_command"],
            "local_transport": "stdio",
            "remote_transport": "openai_secure_mcp_tunnel",
            "tunnel_client": tunnel_client,
            "tunnel_plan": secure_tunnel_plan,
            "preferred_supervision": secure_tunnel_plan["preferred_supervision"],
            "managed_connect_argv": secure_tunnel_plan["managed_connect_argv"],
            "managed_status_argv": secure_tunnel_plan["managed_status_argv"],
            "managed_stop_argv": secure_tunnel_plan["managed_stop_argv"],
            "managed_readiness_fields": ["process_running", "healthy", "ready"],
            "managed_tunnel_readiness_is_host_route_readiness": False,
            "host_connector_capability_required": True,
            "remote_failover_classifier": "classify_remote_runtime_failover",
            "remote_runtime_route_evidence": "all_managed_readiness_fields_true_plus_host_connector_capability",
            "public_ingress_enabled": False,
            "package_contains_tunnel_target": True,
            "external_tunnel_control_plane_bundled": False,
            "requires_auth": True,
            "finalization_gate": "host_visible_finalization",
            "audit_and_idempotency": True,
            "identity_owner": "jazn_persistent_runtime",
            "memory_owner": "jazn_persistent_runtime",
            "turn_owner": "jazn_persistent_runtime",
            "truth_boundary": (
                "Secure MCP Tunnel is an authenticated transport to the local runtime; it is not identity, memory, "
                "turn authority or proof that a visible reply was accepted. Managed tunnel readiness alone does not "
                "prove that the current ChatGPT surface exposes the corresponding connector/app capability. The SYSTEM "
                "package contains the local stdio target but does not bundle/authenticate OpenAI's external tunnel control plane."
            ),
        },
        "truth_boundary": (
            "GitHub i ZIP są źródłem kodu/snapshotu. Aktywna Jaźń wymaga żywego procesu, świeżego heartbeat i zgodnego active_root. "
            "Host-tool discovery i Secure MCP Tunnel są osobnymi kontraktami capability i nie dowodzą runtime readiness ani accepted visible turn."
        ),
    }
