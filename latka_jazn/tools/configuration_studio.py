"""Fail-closed Configuration Studio profiles for *future* Jaźń launches.

The profile is not the daemon's live configuration. Existing runtime/MEMORY
files are never opened for writing by this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Mapping

from latka_jazn.core.runtime_root import (
    active_runtime_marker_path, legacy_workspace_runtime_path,
    workspace_runtime_path,
)
from latka_jazn.db.runtime_sqlite import runtime_sqlite_write_guard
from latka_jazn.memory.memory_root import resolve_memory_root
from latka_jazn.tools.memory_rebuild_app.project_store import default_project_root
from latka_jazn.tools.memory_rebuild_app.settings import resolve_settings_path
from latka_jazn.nlp.local_resource_paths import polish_nlp_data_root
from latka_jazn.version import PACKAGE_VERSION

SCHEMA = "jazn_configuration_profile/v1"
PROFILE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,47}$")


@dataclass(frozen=True)
class Setting:
    key: str
    title: str
    section: str
    kind: str
    hint: str


SETTINGS: tuple[Setting, ...] = (
    Setting("JAZN_RUNTIME_WORKSPACE_DIR", "Stan operacyjny", "Ścieżki", "directory", "Absolutny katalog stanu poza SYSTEM"),
    Setting("JAZN_MEMORY_ROOT", "Pamięć prywatna", "Ścieżki", "directory", "Oddzielony katalog MEMORY"),
    Setting("LATKA_NLP_DATA_DIR", "Zasoby NLP", "Ścieżki", "directory", "Zewnętrzny katalog modeli"),
    Setting("JAZN_MEMORY_REBUILD_PROJECTS", "Projekty odbudowy", "Ścieżki", "directory", "Katalog projektów, nie katalog pamięci"),
    Setting("JAZN_MEMORY_REBUILD_SETTINGS", "Ustawienia odbudowy", "Ścieżki", "file", "Oddzielny plik JSON ustawień"),
    Setting("JAZN_LEXICAL_RESOURCE_CACHE", "Cache słownikowy", "Ścieżki", "file", "Oddzielna baza SQLite, nigdy MEMORY"),
    Setting("JAZN_MEMORY_MODE", "Tryb MEMORY", "Runtime", "memory_mode", "optional / required / off"),
    Setting("JAZN_LLM_ROUTE", "Routing LLM", "Runtime", "llm_route", "auto / local / chatgpt_bridge / openai_api / none"),
    Setting("JAZN_MODEL_ADAPTER", "Adapter modelu", "Runtime", "adapter", "null / local / chatgpt / terminal / openai_compatible"),
    Setting("JAZN_STARTUP_STATUS_MODE", "Diagnostyka startu", "Runtime", "status_mode", "fast / full"),
    Setting("JAZN_SQLITE_HEALTH_MODE", "Kontrola SQLite", "Runtime", "sqlite_mode", "metadata / full"),
)
SETTING_BY_KEY = {setting.key: setting for setting in SETTINGS}
ENUMS: dict[str, frozenset[str]] = {
    "memory_mode": frozenset({"optional", "required", "off"}),
    "llm_route": frozenset({"auto", "local", "chatgpt_bridge", "openai_api", "none"}),
    "adapter": frozenset({"null", "local", "chatgpt", "terminal", "openai_compatible"}),
    "status_mode": frozenset({"fast", "full"}),
    "sqlite_mode": frozenset({"metadata", "full"}),
}
PATH_SETTINGS = frozenset(x.key for x in SETTINGS if x.kind in {"file", "directory"})


class ConfigValidationError(ValueError):
    """The operator profile is unsafe or inconsistent."""


def system_root(root: str | Path) -> Path:
    source = Path(root).expanduser().resolve()
    if not (source / "main.py").is_file() or not (source / "latka_jazn" / "version.py").is_file():
        raise ConfigValidationError("Nie znaleziono zweryfikowanego SYSTEM (main.py, version.py).")
    return source


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _checked_folder(folder: Path) -> None:
    """Reject symlinks throughout an untrusted profile storage suffix."""
    for part in (folder, *folder.parents):
        if part.is_symlink():
            raise ConfigValidationError("Niedozwolone dowiązanie symboliczne katalogu profili.")


def profile_directory(root: str | Path, *, workspace: Path | None = None) -> Path:
    source = system_root(root)
    target = Path(workspace).expanduser().resolve() if workspace is not None else workspace_runtime_path(source)
    home = target / "configuration_studio" / "profiles"
    if _inside(home.resolve(), source) or _inside(target, resolve_memory_root(source)):
        raise ConfigValidationError("Profile nie mogą znajdować się wewnątrz SYSTEM ani MEMORY.")
    _checked_folder(home)
    return home


def profile_file(root: str | Path, *, name: str = "operator", workspace: Path | None = None) -> Path:
    if not PROFILE_RE.fullmatch(name):
        raise ConfigValidationError("Niedozwolona nazwa profilu.")
    path = profile_directory(root, workspace=workspace) / (name + ".json")
    if path.is_symlink():
        raise ConfigValidationError("Dowiązanie symboliczne profilu jest niedozwolone.")
    return path


def _checked_path(key: str, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ConfigValidationError(f"{key}: wymagana jest ścieżka bezwzględna.")
    return candidate.resolve()


def validate_values(root: str | Path, entries: Mapping[str, str]) -> dict[str, str]:
    """Validate an allowlisted future-process profile without touching MEMORY."""
    source = system_root(root)
    result: dict[str, str] = {}
    for key, raw in entries.items():
        setting = SETTING_BY_KEY.get(key)
        if setting is None:
            raise ConfigValidationError(f"Niedozwolony klucz konfiguracji: {key}")
        if not isinstance(raw, str):
            raise ConfigValidationError(f"{key}: oczekiwano tekstu.")
        value = raw.strip()
        if not value:
            continue
        if len(value) > 4096 or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ConfigValidationError(f"{key}: niedozwolone znaki lub długość.")
        if setting.kind in {"directory", "file"}:
            result[key] = str(_checked_path(key, value))
        elif setting.kind in ENUMS:
            normalized = value.lower()
            if normalized not in ENUMS[setting.kind]:
                raise ConfigValidationError(f"{key}: niedozwolona wartość {value!r}.")
            result[key] = normalized
        else:
            raise ConfigValidationError(f"{key}: nieznany typ wartości.")

    current_workspace = workspace_runtime_path(source)
    workspace = Path(result.get("JAZN_RUNTIME_WORKSPACE_DIR", str(current_workspace))).resolve()
    memory = Path(result.get("JAZN_MEMORY_ROOT", str(resolve_memory_root(source)))).resolve()
    current_memory = resolve_memory_root(source)
    legacy_workspace = legacy_workspace_runtime_path(source)
    for label, path in (("workspace", workspace), ("MEMORY", memory)):
        if _inside(path, source) or _inside(path, legacy_workspace):
            raise ConfigValidationError(f"{label}: niedozwolony katalog w drzewie SYSTEM.")
    if _inside(workspace, memory) or _inside(workspace, current_memory) or workspace == memory:
        raise ConfigValidationError("Workspace nie może znajdować się w MEMORY.")
    if _inside(memory, workspace) and memory != workspace / "memory":
        raise ConfigValidationError("MEMORY w workspace może leżeć tylko w workspace/memory.")
    protected_roots = (memory, current_memory, source, legacy_workspace)
    runtime_internal = (
        workspace / "memory", workspace / "core_state",
        workspace / "daemon", workspace / "supervisor",
        workspace / "conversation_state", workspace / "runtime_sessions",
        workspace / "chatgpt_host_bridge",
        current_workspace / "memory", current_workspace / "core_state",
        current_workspace / "daemon", current_workspace / "supervisor",
    )
    for key in PATH_SETTINGS - {"JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_MEMORY_ROOT"}:
        if key not in result:
            continue
        path = Path(result[key])
        if any(_inside(path, block) for block in (*protected_roots, *runtime_internal)):
            raise ConfigValidationError(f"{key}: kolizja z chronioną pamięcią lub stanem runtime.")
        if key.endswith("_CACHE") and path.suffix.lower() not in {".sqlite", ".sqlite3", ".db"}:
            raise ConfigValidationError(f"{key}: cache musi wskazywać plik SQLite.")
        if key == "JAZN_MEMORY_REBUILD_SETTINGS" and path.suffix.lower() != ".json":
            raise ConfigValidationError(f"{key}: ustawienia muszą być plikiem JSON.")
    if "JAZN_MEMORY_REBUILD_SETTINGS" in result and "JAZN_LEXICAL_RESOURCE_CACHE" in result:
        if result["JAZN_MEMORY_REBUILD_SETTINGS"] == result["JAZN_LEXICAL_RESOURCE_CACHE"]:
            raise ConfigValidationError("Pliki cache i ustawień nie mogą mieć tej samej ścieżki.")
    if "JAZN_MEMORY_REBUILD_PROJECTS" in result:
        projects = Path(result["JAZN_MEMORY_REBUILD_PROJECTS"])
        for key in ("JAZN_LEXICAL_RESOURCE_CACHE", "JAZN_MEMORY_REBUILD_SETTINGS"):
            if key in result and _inside(Path(result[key]), projects):
                raise ConfigValidationError(f"{key}: plik nie może znajdować się w katalogu projektów.")
    return result


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ConfigValidationError(f"Zduplikowany klucz JSON: {key}")
        value[key] = item
    return value


def _parse_profile(root: str | Path, payload: bytes) -> dict[str, str]:
    if len(payload) > 65536:
        raise ConfigValidationError("Profil przekracza dopuszczalny rozmiar.")
    obj = json.loads(payload.decode("utf-8"), object_pairs_hook=_no_duplicates)
    if not isinstance(obj, dict) or set(obj) != {"schema", "values"} or obj["schema"] != SCHEMA:
        raise ConfigValidationError("Nieobsługiwany format profilu.")
    if not isinstance(obj["values"], dict):
        raise ConfigValidationError("Brak poprawnego obiektu values.")
    return validate_values(root, obj["values"])


def profile_snapshot(root: str | Path, *, name: str = "operator",
                     workspace: Path | None = None) -> tuple[dict[str, str], str | None]:
    path = profile_file(root, name=name, workspace=workspace)
    if not path.exists():
        return {}, None
    if not path.is_file() or path.is_symlink():
        raise ConfigValidationError("Niebezpieczny profil.")
    payload = path.read_bytes()
    values = _parse_profile(root, payload)
    return values, sha256(payload).hexdigest()


def read_profile(root: str | Path, *, name: str = "operator", workspace: Path | None = None) -> dict[str, str]:
    return profile_snapshot(root, name=name, workspace=workspace)[0]


def profile_digest(root: str | Path, *, name: str = "operator", workspace: Path | None = None) -> str | None:
    return profile_snapshot(root, name=name, workspace=workspace)[1]


def save_profile(root: str | Path, entries: Mapping[str, str], *, name: str = "operator",
                 workspace: Path | None = None, expected_sha256: str | None = None) -> Path:
    """Serialize CAS, verified rollback copy and atomic profile replacement."""
    values = validate_values(root, entries)
    path = profile_file(root, name=name, workspace=workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    _checked_folder(path.parent)
    try:
        # Reuse Jaźń's cross-platform process and file guard, not a second lock engine.
        with runtime_sqlite_write_guard(path, timeout_ms=30000):
            old_values, current_hash = profile_snapshot(root, name=name, workspace=workspace)
            if current_hash != expected_sha256:
                raise ConfigValidationError("Profil zmieniono na dysku. Wczytaj go ponownie.")
            previous = path.read_bytes() if current_hash is not None else None
            if previous is not None and old_values == values:
                return path
            payload = (json.dumps({"schema": SCHEMA, "values": values},
                                  ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
            backup = path.with_name(f"{name}.previous.json")
            staged = path.with_name(f".{name}.{os.getpid()}.tmp")
            backup_temp = path.with_name(f".{name}.previous.{os.getpid()}.tmp")
            try:
                if previous is not None:
                    if backup.is_symlink():
                        raise ConfigValidationError("Symlink poprzedniego profilu jest niedozwolony.")
                    with backup_temp.open("xb") as out:
                        out.write(previous)
                        out.flush()
                        os.fsync(out.fileno())
                    os.replace(backup_temp, backup)
                with staged.open("xb") as out:
                    out.write(payload)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(staged, path)
            finally:
                staged.unlink(missing_ok=True)
                backup_temp.unlink(missing_ok=True)
    except sqlite3.OperationalError as exc:
        raise ConfigValidationError("Nie uzyskano blokady profilu.") from exc
    return path


def restore_previous_profile(root: str | Path, *, name: str = "operator",
                             workspace: Path | None = None,
                             expected_sha256: str | None = None) -> Path:
    path = profile_file(root, name=name, workspace=workspace)
    backup = path.with_name(f"{name}.previous.json")
    if backup.is_symlink() or not backup.is_file():
        raise ConfigValidationError("Brak bezpiecznej kopii poprzedniego profilu.")
    values = _parse_profile(root, backup.read_bytes())
    return save_profile(root, values, name=name, workspace=workspace, expected_sha256=expected_sha256)


def validated_launch_values(root: str | Path, *, name: str = "operator") -> dict[str, str]:
    """Single-read snapshot for direct consumption by the launcher's PowerShell."""
    source = system_root(root)
    values, digest = profile_snapshot(source, name=name)
    if digest is None:
        raise ConfigValidationError("Nie znaleziono profilu.")
    if any(key in values for key in ("JAZN_MEMORY_ROOT", "JAZN_RUNTIME_WORKSPACE_DIR")):
        # A stale PID/marker is not proof of running daemon. Be conservative:
        # require explicit operator stop/cleanup of conflicting state first.
        workspace = workspace_runtime_path(source)
        if (workspace / "JAZN_ACTIVE_RUNTIME.json").exists():
            raise ConfigValidationError(
                "Istnieje znacznik runtime. Zmiana lokalizacji wymaga weryfikacji i wyłączenia daemona."
            )
    return values


def inspect_system(root: str | Path) -> list[dict[str, str]]:
    """Effective, read-only locations; existence is not daemon readiness."""
    source = system_root(root)
    workspace = workspace_runtime_path(source)
    memory = resolve_memory_root(source)
    nlp = polish_nlp_data_root(source)
    locations = (
        ("SYSTEM", source, "Kod SYSTEM"),
        ("WORKSPACE", workspace, "Stan procesów"),
        ("MEMORY", memory, "Prywatna pamięć"),
        ("CORE_STATE", workspace / "core_state", "Operacyjne SQLite"),
        ("MARKER", active_runtime_marker_path(source), "Znacznik, nie dowód aktywności"),
        ("DAEMON_PID", workspace / "jazn_daemon.pid", "PID, nie dowód aktywności"),
        ("DAEMON_LOG", workspace / "daemon" / "process_events.jsonl", "Historia zdarzeń"),
        ("SESSION_STATE", workspace / "runtime_session_state.json", "Checkpoint sesji"),
        ("PROFILES", profile_directory(source), "Profile przyszłych uruchomień"),
        ("STUDIO_MEMORY", default_project_root(), "Projekty odbudowy"),
        ("STUDIO_SETTINGS", resolve_settings_path(None, tool_root=source), "Ustawienia odbudowy"),
        ("NLP_MODELS", nlp, "Zasoby NLP"),
    )
    return [{"name": key, "path": str(path), "exists": str(path.exists()).lower(), "note": note}
            for key, path, note in locations]


def describe_profile(root: str | Path, *, name: str = "operator", workspace: Path | None = None) -> dict[str, Any]:
    source = system_root(root)
    path = profile_file(source, name=name, workspace=workspace)
    values, digest = profile_snapshot(source, name=name, workspace=workspace)
    return {"schema": SCHEMA, "system_root": str(source), "profile_path": str(path),
            "profile_sha256": digest, "values": values,
            "version": PACKAGE_VERSION, "applied_to_running_daemon": False}
