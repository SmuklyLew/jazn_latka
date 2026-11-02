"""Evidence-based service presentation; never equate configuration with readiness."""
from __future__ import annotations

from typing import Any


def visual_state(service: str, evidence: dict[str, Any]) -> str:
    """Return ready/reachable/stopped/error/unknown from *observed* capabilities.

    An optional service that is not configured or not started is not necessarily
    broken. A reachable Ollama API is not proof of model generation; a reachable
    tunnel is not proof of authenticated MCP or a completed Jaźń turn.
    """
    if not evidence:
        return "unknown"

    if service == "runtime":
        if evidence.get("root_matches") is False or evidence.get("version_matches") is False:
            return "error"
        if evidence.get("active_state") in {"dead", "stopped", "inactive"}:
            return "stopped"
        if evidence.get("root_matches") is not True or evidence.get("version_matches") is not True:
            return "unknown"
        if evidence.get("active_state") == "active_trusted" and all(
            evidence.get(key) is True for key in (
                "endpoint_reachable", "process_identity_confirmed",
                "endpoint_identity_matches", "heartbeat_fresh", "conversation_ready",
            )
        ):
            return "ready"
        return "unknown"

    if evidence.get("status") in {"error", "failed"} or evidence.get("error") or evidence.get("failure_reason"):
        return "error"

    if service == "ollama":
        if evidence.get("endpoint_reachable") is True:
            if (evidence.get("selected_model_present") is True
                    and evidence.get("generation_verified") is True):
                return "ready"
            return "reachable"
        if evidence.get("ready") is False:
            return "error"
        return "unknown"

    if service == "memory":
        if (evidence.get("full_autobiographical_recall_ready") is True
                and evidence.get("continuity_ready") is True):
            return "ready"
        if evidence.get("memory_search_ready") is True or evidence.get("ready") is True:
            return "reachable"
        return "unknown"

    if service == "cloudflare":
        if (evidence.get("ready") is True
                and evidence.get("authenticated_mcp_ready") is True
                and evidence.get("runtime_ready") is True):
            return "ready"
        if evidence.get("ready") is True or evidence.get("endpoint_reachable") is True:
            return "reachable"
        return "unknown"

    if service == "supervisor":
        if evidence.get("ready") is True:
            return "ready"
        if evidence.get("active") is False:
            return "stopped"
        return "unknown"

    if service == "gateway":
        if evidence.get("ready") is True:
            return "ready"
        if evidence.get("endpoint_reachable") is True:
            return "reachable"
        return "unknown"

    if evidence.get("ready") is True:
        return "ready"
    return "unknown"


COLORS = {
    "ready": "#31B85D",
    "reachable": "#D8A549",
    "stopped": "#8F96A2",
    "error": "#E6576A",
    "unknown": "#8F96A2",
}
TITLES = {
    "ready": "Gotowość danej zdolności potwierdzona",
    "reachable": "Dostępna technicznie; pełna gotowość wymaga osobnych dowodów",
    "stopped": "Nieaktywne lub zatrzymane",
    "error": "Potwierdzony błąd",
    "unknown": "Brak wystarczających dowodów; odśwież stan",
}
