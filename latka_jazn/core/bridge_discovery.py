from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from latka_jazn.bridge_secure_gateway import SecureGatewayPolicy
from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon import DEFAULT_DAEMON_HOST, DEFAULT_DAEMON_PORT, status_daemon
from latka_jazn.core.runtime_root import active_runtime_marker_path
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
    return {
        "schema_version": schema_version("runtime_bridge_discovery"),
        "active_root": str(root),
        "marker_path": str(marker_path),
        "marker_found": marker is not None,
        "marker": marker or {},
        "daemon_status": daemon,
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
            "meaning": (
                "kanoniczny most hosta ChatGPT: persistent stdin/JSONL jest preferowany, gdy host potrafi "
                "utrzymać proces; w przeciwnym razie trwały daemon utrzymuje logical session/turn lineage, "
                "a host wznawia ten sam request_id i finalizuje phase-2 bez replayu wiadomości. Żywotność pipe'a "
                "nie jest źródłem tożsamości ani dowodem gotowej odpowiedzi; widoczna może być tylko zaakceptowana "
                "final_visible_text. Tryb nie wykonuje żądania OpenAI API."
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
            "status": "implemented_private_stdio_server",
            "server_command": "python -X utf8 -m latka_jazn.mcp.server",
            "tunnel_transport": "optional_outbound_secure_mcp_tunnel",
            "public_ingress_enabled": False,
            "requires_auth": True,
            "finalization_gate": "host_visible_finalization",
            "audit_and_idempotency": True,
            "truth_boundary": "MCP is a transport to the local runtime; it is not identity, memory, or proof that the daemon is active.",
        },
        "truth_boundary": (
            "GitHub i ZIP są źródłem kodu/snapshotu. Aktywna Jaźń wymaga żywego procesu, świeżego heartbeat i zgodnego active_root."
        ),
    }
