"""Configuration Studio: validated, operator-scoped launch profiles.

Profiles are deliberately NOT live Jaźń runtime configuration: they are applied
only to a new child process by the explicit Windows launcher. Never edit
SYSTEM, MEMORY, daemon marker, secrets or operating-system environment here.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from latka_jazn.core.runtime_root import (
    active_runtime_marker_path, legacy_workspace_runtime_path, workspace_runtime_path,
)
from latka_jazn.memory.memory_root import resolve_memory_root
from latka_jazn.version import PACKAGE_VERSION

SCHEMA = "jazn_configuration_profile/v1"
PROFILE_FILENAME = "operator.json"
PROFILE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")


@dataclass(frozen=True)
class Setting:
    key: str
    title: str
    section: str
    kind: str
    hint: str


SETTINGS: tuple[Setting, ...] = (
    Setting("JAZN_RUNTIME_WORKSPACE_DIR", "Stan operacyjny", "Ścieżki", "directory", "Bezwzględny katalog poza SYSTEM i MEMORY"),
    Setting("JAZN_MEMORY_ROOT", "Pamięć prywatna", "Ścieżki", "directory", "Bezwzględny katalog pamięci poza kodem SYSTEM"),
    Setting("LATKA_NLP_DATA_DIR", "Modele językowe NLP", "Ścieżki", "directory", "Bezwzględny katalog zasobów opcjonalnych"),
    Setting("JAZN_MEMORY_REBUILD_PROJECTS", "Projekty odbudowy", "Ścieżki", "directory", "Prywatny katalog projektów Studio Pamięci"),
    Setting("JAZN_MEMORY_REBUILD_SETTINGS", "Ustawienia odbudowy", "Ścieżki", "file", "Ścieżka do pliku JSON"),
    Setting("JAZN_LEXICAL_RESOURCE_CACHE", "Cache słownikowy", "Ścieżki", "file", "Ścieżka SQLite cache"),
    Setting("JAZN_MEMORY_MODE", "Tryb MEMORY", "Runtime", "memory_mode", "optional / required / off"),
    Setting("JAZN_LLM_ROUTE", "Routing LLM", "Runtime", "llm_route", "auto / local / chatgpt_bridge / openai_api / none"),
    Setting("JAZN_MODEL_ADAPTER", "Adapter modelu", "Runtime", "adapter", "null / local / chatgpt / terminal / openai_compatible"),
    Setting("JAZN_STARTUP_STATUS_MODE", "Diagnostyka startu", "Runtime", "status_mode", "fast / full"),
    Setting("JAZN_SQLITE_HEALTH_MODE", "Kontrola SQLite", "Runtime", "sqlite_mode", "metadata / full"),
)
SETTING_BY_KEY = {setting.key: setting for setting in SETTINGS}
ENUMS = {
    "memory_mode": frozenset({"optional", "required", "off"}),
    "llm_route": frozenset({"auto", "local", "chatgpt_bridge", "openai_api", "none"}),
    "adapter": frozenset({"null", "local", "chatgpt", "terminal", "openai_compatible"}),
    "status_mode": frozenset({"fast", "full"}),
    "sqlite_mode": frozenset({"metadata", "full"}),
}


class ConfigValidationError(ValueError):
    """Profile cannot be accepted safely."""


def system_root(root: str | Path) -> Path:
    path = Path(root).expanduser().resolve()
    if not (path / "main.py").is_file() or not (path / "latka_jazn" / "version.py").is_file():
        raise ConfigValidationError("Wskaż istniejący SYSTEM z main.py i latka_jazn/version.py.")
    return path


def profile_directory(root: str | Path, *, workspace: Path | None = None) -> Path:
    source = system_root(root)
    target = Path(workspace).expanduser().resolve() if workspace is not None else workspace_runtime_path(source)
    if target == source or source in target.parents:
        raise ConfigValidationError("Profile nie mogą być zapisywane wewnątrz katalogu SYSTEM.")
    return target / "configuration_studio" / "profiles"


def profile_file(root: str | Path, *, name: str = "operator", workspace: Path | None = None) -> Path:
    if not PROFILE_RE.fullmatch(name):
        raise ConfigValidationError("Niedozwolona nazwa profilu.")
    return profile_directory(root, workspace=workspace) / (name + ".json")


def _inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def validate_values(root: str | Path, entries: Mapping[str, str]) -> dict[str, str]:
    """Strict allowlist; do not accept secrets, hidden extra keys or relative paths."""
    source = system_root(root)
    result: dict[str, str] = {}
    for key, value in entries.items():
        setting = SETTING_BY_KEY.get(key)
        if setting is None:
            raise ConfigValidationError(f"Niedozwolony klucz konfiguracji: {key}")
        if not isinstance(value, str):
            raise ConfigValidationError(f"{key}: wymagana wartość tekstowa.")
        value = value.strip()
        if not value:
            continue
        if len(value) > 4096 or any(ch in value for ch in "\r\n\x00"):
            raise ConfigValidationError(f"{key}: niedozwolone znaki lub długość.")
        if setting.kind in {"directory", "file"}:
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                raise ConfigValidationError(f"{key}: wymagana ścieżka bezwzględna.")
            resolved = candidate.resolve()
            if _inside(resolved, source) or _inside(resolved, legacy_workspace_runtime_path(source)):
                raise ConfigValidationError(f"{key}: ścieżka w SYSTEM/starym runtime jest zabroniona.")
            result[key] = str(resolved)
        elif setting.kind in ENUMS:
            lowered = value.lower()
            if lowered not in ENUMS[setting.kind]:
                raise ConfigValidationError(f"{key}: niedozwolona wartość '{value}'.")
            result[key] = lowered
        else:
            raise ConfigValidationError(f"{key}: nieznany typ ustawienia.")
    workspace = Path(result.get("JAZN_RUNTIME_WORKSPACE_DIR") or workspace_runtime_path(source)).resolve()
    memory = result.get("JAZN_MEMORY_ROOT")
    if memory and (_inside(Path(memory), workspace) and Path(memory) != workspace / "memory"):
        raise ConfigValidationError("MEMORY wewnątrz workspace ma używać tylko katalogu workspace/memory.")
    if memory and (_inside(workspace, Path(memory)) or Path(memory) == workspace):
        raise ConfigValidationError("Workspace nie może być częścią MEMORY.")
    return result


def read_profile(root: str | Path, *, name: str = "operator", workspace: Path | None = None) -> dict[str, str]:
    path = profile_file(root, name=name, workspace=workspace)
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ConfigValidationError("Profil nie jest bezpiecznym plikiem JSON.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA or not isinstance(raw.get("values"), dict):
        raise ConfigValidationError("Nieobsługiwany format profilu.")
    return validate_values(root, raw["values"])


def save_profile(root: str | Path, entries: Mapping[str, str], *, name: str = "operator",
                 workspace: Path | None = None, expected_sha256: str | None = None) -> Path:
    """Backup + atomic replace; no live runtime files are touched."""
    values = validate_values(root, entries)
    path = profile_file(root, name=name, workspace=workspace)
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink() or path.is_symlink():
        raise ConfigValidationError("Dowiązanie symboliczne w katalogu profili jest zabronione.")
    previous = path.read_bytes() if path.exists() else None
    existing_hash = sha256(previous).hexdigest() if previous is not None else None
    if existing_hash != expected_sha256:
        raise ConfigValidationError("Profil został zmieniony na dysku; odczytaj go ponownie.")
    if previous is not None:
        read_profile(root, name=name, workspace=workspace)  # fail closed on corrupt existing profile
    payload = json.dumps({"schema": SCHEMA, "values": values}, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temp = folder / f".{name}.{os.getpid()}.tmp"
    backup = folder / f"{name}.previous.json"
    try:
        with temp.open("x", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if previous is not None:
            # Keep the previous approved configuration for manual rollback.
            previous_tmp = folder / f".{name}.previous.{os.getpid()}.tmp"
            try:
                with previous_tmp.open("xb") as stream:
                    stream.write(previous)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(previous_tmp, backup)
            finally:
                previous_tmp.unlink(missing_ok=True)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def profile_digest(root: str | Path, *, name: str = "operator", workspace: Path | None = None) -> str | None:
    path = profile_file(root, name=name, workspace=workspace)
    return sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def inspect_system(root: str | Path) -> list[dict[str, str]]:
    """Read-only snapshot: existence does NOT imply active daemon or accepted MEMORY."""
    source = system_root(root)
    workspace = workspace_runtime_path(source)
    memory = resolve_memory_root(source)
    locations = (
        ("SYSTEM", source, "Kod programu"),
        ("WORKSPACE", workspace, "Stan procesów i sesji"),
        ("MEMORY", memory, "Dane prywatnej pamięci"),
        ("CORE_STATE", workspace / "core_state", "Operacyjne SQLite bez pamięci prywatnej"),
        ("MARKER", active_runtime_marker_path(source), "Znacznik, nie dowód aktywności"),
        ("DAEMON_PID", workspace / "jazn_daemon.pid", "PID, nie dowód aktywności"),
        ("DAEMON_LOG", workspace / "daemon" / "process_events.jsonl", "Historia zdarzeń"),
        ("SESSION_STATE", workspace / "runtime_session_state.json", "Ostatni checkpoint sesji"),
        ("PROFILES", profile_directory(source), "Profile dla przyszłych uruchomień"),
        ("STUDIO_MEMORY", Path.home() / ".jazn" / "memory_rebuild_projects", "Projekty odbudowy"),
        ("NLP_MODELS", source / "latka_jazn" / "local_resources" / "nlp", "Opcjonalne zasoby NLP"),
    )
    return [{"name": key, "path": str(path), "exists": str(path.exists()).lower(), "note": note}
            for key, path, note in locations]


def describe_profile(root: str | Path, *, name: str = "operator", workspace: Path | None = None) -> dict[str, Any]:
    source = system_root(root)
    path = profile_file(source, name=name, workspace=workspace)
    return {"schema": SCHEMA, "system_root": str(source), "profile_path": str(path),
            "profile_sha256": profile_digest(source, name=name, workspace=workspace),
            "values": read_profile(source, name=name, workspace=workspace),
            "version": PACKAGE_VERSION, "applied_to_running_daemon": False}
