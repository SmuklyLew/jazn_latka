"""Bounded operator projection of canonical status, without private paths."""
from __future__ import annotations
from typing import Any


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value[:160] if isinstance(value, str) and value else "nie sprawdzono"


def _verified(value: Any) -> str:
    return "zweryfikowane" if value is True else "błąd weryfikacji" if value is False else "niezweryfikowane"


def status_summary(data: dict[str, Any]) -> dict[str, str]:
    """Availability/configuration never certifies recall, generation or a turn."""
    daemon = _object(data.get("daemon"))
    startup = _object(data.get("startup"))
    manifest = _object(daemon.get("package_integrity_verification"))
    memory = _object(data.get("memory_availability"))
    adapter = _object(startup.get("model_adapter_status"))
    proofs = (daemon.get("package_integrity_verified"), manifest.get("ok"))
    integrity = (True if all(v is True for v in proofs) else
                 False if any(v is False for v in proofs) else None)
    memory_state = {
        "disabled_by_policy": "wyłączona przez konfigurację",
        "available": "dostępna technicznie",
        "missing_optional": "brak opcjonalnej pamięci",
        "missing_required": "brak wymaganej pamięci",
    }.get(str(memory.get("status")), "stan techniczny niezweryfikowany")
    mode = memory.get("mode")
    if isinstance(mode, str) and mode in {"off", "optional", "required"}:
        memory_state += " (" + str(mode) + ")"
    adapter_name = _text(adapter.get("selected_backend_adapter") or adapter.get("adapter_id"))
    if adapter_name in {"null", "null_model_adapter"}:
        model = "null_model_adapter — brak backendu generacyjnego"
    else:
        model = adapter_name + " / " + _text(adapter.get("model_name")) + "; generacja niezweryfikowana"
    return {
        "version": _text(data.get("runtime_version")),
        "integrity": _verified(integrity),
        "provenance": _verified(daemon.get("source_provenance_verified")),
        "memory": memory_state + "; recall i ciągłość wymagają osobnego potwierdzenia",
        "model": model,
    }
