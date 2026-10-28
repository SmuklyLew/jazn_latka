"""Bounded, operator-facing explanations for Studio failure codes.

No raw URLs, token values, subprocess command lines or untrusted output are
included in the UI guidance. Runtime and MEMORY readiness remain independent.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.error import URLError
import errno
import socket


@dataclass(frozen=True)
class Guidance:
    title: str
    remedy: str
    module: str


def probe_failure_code(exc: BaseException) -> str:
    """Classify a transport failure without storing its raw, potentially private reason."""
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError) or (
            isinstance(reason, OSError) and reason.errno in {
                errno.ECONNREFUSED, getattr(errno, "WSAECONNREFUSED", 10061), 10061,
            }
        ):
            return "connection_refused"
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "connection_timeout"
        if isinstance(reason, OSError) and reason.errno in {
            errno.ETIMEDOUT, 10060,
        }:
            return "connection_timeout"
        return "transport_unreachable"
    if isinstance(exc, TimeoutError):
        return "connection_timeout"
    return type(exc).__name__


def explain_failure(key: str, error: str) -> Guidance:
    error = str(error or "unknown")
    if key.startswith("probe:ollama"):
        if error in {"URLError", "transport_unreachable", "connection_refused", "connection_timeout"}:
            return Guidance(
                "Ollama nie odpowiada na lokalnym API",
                "Sprawdź, czy Ollama działa i czy http://127.0.0.1:11434/api/tags "
                "jest osiągalne. Potem wybierz istniejący model i ponów test; "
                "nie pobieraj modelu automatycznie.",
                "Ollama",
            )
        if error in {"ollama_models_empty", "selected_model_missing"}:
            return Guidance(
                "Model nie jest dostępny w lokalnej Ollama",
                "Wykryj listę modeli w Czat lokalny. Sprawdź OLLAMA_MODELS i "
                "kontekst użytkownika procesu; ponów test generacji.",
                "Ollama",
            )
        if error == "ollama_generation_unverified":
            return Guidance(
                "Generacja modelu nie została potwierdzona",
                "Sprawdź wybrany model, obciążenie pamięci oraz wynik próby "
                "/api/chat. To nie jest jeszcze zaakceptowana odpowiedź Jaźni.",
                "Ollama",
            )
    if key.startswith("probe:gateway") or key.startswith("service:gateway"):
        return Guidance(
            "Lokalna brama MCP nie jest gotowa",
            "Sprawdź interpreter MCP i brakujące zależności (mcp, uvicorn, "
            "starlette, pydantic), a potem port i lokalne /readyz. "
            "Nie wystawiaj --loopback-dev przez publiczny tunel.",
            "MCP",
        )
    if key in {"status", "start", "stop", "restart"}:
        return Guidance(
            "Operacja runtime nie została potwierdzona",
            "Sprawdź w Pulpicie katalog i wersję aktywnego daemona. "
            "Uruchomiony master nie jest instancją bieżącego Worktree. "
            "Nie zatrzymuj ani nie przejmuj obcego daemona; sprawdź "
            "kanoniczny status i szczegóły zadania.",
            "Runtime",
        )
    return Guidance(
        "Operacja nie została ukończona",
        "Otwórz Output / Logi, wybierz źródło zadania i sprawdź ostatni "
        "zredagowany komunikat. Nie uruchamiaj ponownie operacji mutującej "
        "bez sprawdzenia jej stanu.",
        "Diagnostyka",
    )
