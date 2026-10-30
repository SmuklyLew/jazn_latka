"""Grounded operator service status; a configured PID or URL never means ready."""
from __future__ import annotations
from typing import Any

def visual_state(service: str, evidence: dict[str, Any]) -> str:
    if not evidence:
        return "unknown"
    if service == "runtime":
        if evidence.get("root_matches") is False or evidence.get("version_matches") is False:
            return "error"
        if evidence.get("root_matches") is not True or evidence.get("version_matches") is not True:
            return "unknown"
        if evidence.get("active_state") == "active_trusted" and all(
            evidence.get(k) is True for k in (
                "endpoint_reachable", "process_identity_confirmed",
                "endpoint_identity_matches", "heartbeat_fresh", "conversation_ready",
            )
        ):
            return "ready"
        if evidence.get("active_state") in {"dead", "stopped", "inactive"}:
            return "stopped"
        return "unknown"
    if evidence.get("ready") is True:
        return "ready"
    if evidence.get("ready") is False:
        return "error"
    if service == "ollama" and evidence.get("endpoint_reachable") is True:
        return "reachable"
    return "unknown"

COLORS = {"ready": "#31B85D", "reachable": "#D8A549", "stopped": "#8F96A2",
          "error": "#E6576A", "unknown": "#8F96A2"}
TITLES = {"ready": "Gotowość potwierdzona", "reachable": "API odpowiada — generacja i Jaźń osobno",
          "stopped": "Zatrzymano — odczyt stanu", "error": "Potwierdzony błąd",
          "unknown": "Brak wystarczających dowodów"}
