"""Local, ignored, non-secret config stored in the SYSTEM root."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path, PureWindowsPath
import re
import tempfile
from typing import Any, Mapping, MutableMapping
from urllib.parse import urlsplit

NAME = "jazn_system_config.json"
SCHEMA = "jazn_system_config/v1"
MAX_BYTES = 32768
ALLOWED = frozenset({
    "JAZN_RUNTIME_WORKSPACE_DIR", "JAZN_MEMORY_ROOT", "JAZN_MEMORY_TIER_DB",
    "LATKA_NLP_DATA_DIR", "JAZN_MEMORY_REBUILD_PROJECTS",
    "JAZN_MEMORY_REBUILD_SETTINGS", "JAZN_LEXICAL_RESOURCE_CACHE",
    "JAZN_MEMORY_MODE", "JAZN_LLM_ROUTE", "JAZN_MODEL_ADAPTER",
    "JAZN_STARTUP_STATUS_MODE", "JAZN_SQLITE_HEALTH_MODE",
})
ENUMS = {
    "JAZN_MEMORY_MODE": {"optional", "required", "off"},
    "JAZN_LLM_ROUTE": {"auto", "local", "chatgpt_bridge", "openai_api", "none"},
    "JAZN_MODEL_ADAPTER": {"null", "local", "chatgpt", "terminal", "openai_compatible"},
    "JAZN_STARTUP_STATUS_MODE": {"fast", "full"},
    "JAZN_SQLITE_HEALTH_MODE": {"metadata", "full"},
}
STUDIO_FIELDS = frozenset({"python", "model", "daemon_url"})


class SystemConfigError(ValueError):
    """Do not embed raw config data or secrets in errors."""


@dataclass(frozen=True)
class SystemConfig:
    values: dict[str, str] = field(default_factory=dict)
    studio: dict[str, str] = field(default_factory=dict)
    digest: str | None = None


def config_path(root: str | Path) -> Path:
    path = Path(root).resolve() / NAME
    if path.is_symlink() or path.is_junction():
        raise SystemConfigError("Dowiązanie konfiguracji SYSTEM jest niedozwolone")
    return path


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SystemConfigError("Powtórzony klucz JSON")
        result[key] = value
    return result


def _validate(root: Path, values: Mapping[str, str], studio: Mapping[str, str]) -> SystemConfig:
    if set(values) - ALLOWED or set(studio) - STUDIO_FIELDS:
        raise SystemConfigError("Nieznany klucz lub sekret w konfiguracji SYSTEM")
    for key, val in [*values.items(), *studio.items()]:
        if not isinstance(val, str) or not val or len(val) > 2048 or any(ch in val for ch in "\0\r\n"):
            raise SystemConfigError("Nieprawidłowy tekst konfiguracji")
        if key in ENUMS and val not in ENUMS[key]:
            raise SystemConfigError("Nieprawidłowa wartość enum")
        if key == "JAZN_MEMORY_TIER_DB":
            portable = val.replace("\\", "/")
            segments = portable.split("/")
            if (PureWindowsPath(portable).anchor or portable.startswith("/") or ":" in portable
                    or any(part in {"", ".", ".."} for part in segments)
                    or segments[0].lower() == "memory"
                    or not portable.lower().endswith((".sqlite", ".sqlite3", ".db"))):
                raise SystemConfigError("Baza MEMORY wymaga bezpiecznej ścieżki względnej")
        elif key in ALLOWED and key not in ENUMS:
            if key == "JAZN_RUNTIME_WORKSPACE_DIR" and val.startswith(("$ROOT/", "$" + "{ROOT}/")):
                tail = val.split("/", 1)[1]
                if not tail or any(part in {"", ".", ".."} for part in tail.split("/")) or ":" in tail:
                    raise SystemConfigError("Niebezpieczna ścieżka workspace")
            elif not Path(val).is_absolute():
                raise SystemConfigError("Wymagana absolutna ścieżka konfiguracji")
    def resolve_workspace(value: str) -> Path:
        if value.startswith(("$ROOT/", "$" + "{ROOT}/")):
            return (root / value.split("/", 1)[1]).resolve()
        return Path(value).resolve()
    workspace = (resolve_workspace(values["JAZN_RUNTIME_WORKSPACE_DIR"])
                 if "JAZN_RUNTIME_WORKSPACE_DIR" in values else None)
    memory = (Path(values["JAZN_MEMORY_ROOT"]).resolve()
              if "JAZN_MEMORY_ROOT" in values else None)
    if workspace is not None and workspace.is_relative_to(root) and workspace != root / "workspace_runtime":
        raise SystemConfigError("Workspace nie może leżeć w drzewie SYSTEM")
    if memory is not None and memory.is_relative_to(root) and memory != root / "memory":
        raise SystemConfigError("MEMORY nie może leżeć w drzewie kodu SYSTEM")
    if workspace is not None and memory is not None:
        if workspace.is_relative_to(memory) or memory.is_relative_to(workspace):
            raise SystemConfigError("Workspace i MEMORY nie mogą się nakładać")
    if "python" in studio and not Path(studio["python"]).is_absolute():
        raise SystemConfigError("Ścieżka interpretera musi być absolutna")
    if "model" in studio and not re.fullmatch(r"[\w./:@-]{1,200}", studio["model"]):
        raise SystemConfigError("Nieprawidłowa nazwa modelu")
    if "daemon_url" in studio:
        try:
            url = urlsplit(studio["daemon_url"])
            port = url.port
        except ValueError as exc:
            raise SystemConfigError("Nieprawidłowy adres daemona") from exc
        if (url.scheme != "http" or url.hostname != "127.0.0.1" or port is None
                or not (1 <= port <= 65535) or url.username or url.password
                or url.path not in {"", "/"} or url.query or url.fragment):
            raise SystemConfigError("Daemon musi wskazywać http://127.0.0.1:PORT")
    return SystemConfig(dict(values), dict(studio))


def read_system_config(root: str | Path) -> SystemConfig:
    path = config_path(root)
    if not path.exists():
        return SystemConfig()
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise SystemConfigError("Zły typ lub rozmiar konfiguracji SYSTEM")
    payload = path.read_bytes()
    try:
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SystemConfigError("Nieprawidłowy JSON konfiguracji SYSTEM") from exc
    if (not isinstance(data, dict) or set(data) != {"schema_version", "values", "studio"}
            or data.get("schema_version") != SCHEMA
            or not isinstance(data.get("values"), dict)
            or not isinstance(data.get("studio"), dict)):
        raise SystemConfigError("Nieznany schemat konfiguracji SYSTEM")
    checked = _validate(Path(root).resolve(), data["values"], data["studio"])
    return SystemConfig(checked.values, checked.studio, sha256(payload).hexdigest())


def apply_system_config(root: str | Path, environment: MutableMapping[str, str]) -> dict[str, str]:
    """CLI flags > explicit ENV > root file > runtime defaults."""
    config = read_system_config(root)
    provenance: dict[str, str] = {}
    for key, val in config.values.items():
        if key in environment:
            provenance[key] = "explicit_env"
        else:
            environment[key] = val
            provenance[key] = "system_file"
    return provenance


def write_system_config(root: str | Path, values: Mapping[str, str], studio: Mapping[str, str],
                        *, expected_digest: str | None) -> SystemConfig:
    path = config_path(root)
    current = read_system_config(root)
    if current.digest != expected_digest:
        raise SystemConfigError("Konflikt równoczesnego zapisu konfiguracji")
    checked = _validate(Path(root).resolve(), values, studio)
    content = (json.dumps({"schema_version": SCHEMA, "values": checked.values, "studio": checked.studio},
                          ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(content) > MAX_BYTES:
        raise SystemConfigError("Konfiguracja przekracza limit")
    backup = path.with_name("jazn_system_config.previous.json")
    if backup.is_symlink() or backup.is_junction():
        raise SystemConfigError("Niebezpieczny backup konfiguracji")
    stage: str | None = None
    prev_stage: str | None = None
    try:
        if current.digest is not None:
            fd, prev_stage = tempfile.mkstemp(dir=path.parent, prefix=".jazn-prev-", suffix=".tmp")
            with os.fdopen(fd, "wb") as handle:
                handle.write(path.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(prev_stage, backup)
            prev_stage = None
        fd, stage = tempfile.mkstemp(dir=path.parent, prefix=".jazn-config-", suffix=".tmp")
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(stage, path)
        stage = None
    finally:
        if stage:
            Path(stage).unlink(missing_ok=True)
        if prev_stage:
            Path(prev_stage).unlink(missing_ok=True)
    return SystemConfig(checked.values, checked.studio, sha256(content).hexdigest())


def migrate_operator_profile(
    root: str | Path, *, expected_sha256: str | None = None,
) -> SystemConfig:
    """Migrate a verified operator snapshot, never a newer profile by accident.

    Cooperating profile writers use the same per-profile cross-process guard.
    Legacy callers may omit expected_sha256; interactive Qt supplies its
    operator-approved digest. No live daemon or MEMORY state is modified.
    """
    import sqlite3

    from latka_jazn.db.runtime_sqlite import runtime_sqlite_write_guard
    from latka_jazn.tools.configuration_studio import profile_file, profile_snapshot

    profile_path = profile_file(root)
    if not profile_path.is_file():
        raise SystemConfigError("Brak profilu operator.json")
    try:
        with runtime_sqlite_write_guard(profile_path, timeout_ms=30000):
            current = read_system_config(root)
            operator_values, digest = profile_snapshot(root)
            if digest is None:
                raise SystemConfigError("Brak profilu operator.json")
            if expected_sha256 is not None and digest != expected_sha256:
                raise SystemConfigError(
                    "Profil operatora zmieniono po potwierdzeniu. Wczytaj go ponownie."
                )
            if any(key in current.values and current.values[key] != val
                   for key, val in operator_values.items()):
                raise SystemConfigError("Konflikt profilu operatora z konfiguracją SYSTEM")
            merged = {**current.values, **operator_values}
            # Verify once more just before committing to catch noncooperating
            # file replacements between the first read and the write.
            _, latest_digest = profile_snapshot(root)
            if latest_digest != digest:
                raise SystemConfigError(
                    "Profil operatora zmieniono podczas migracji. Wczytaj go ponownie."
                )
            if merged == current.values:
                return current
            return write_system_config(
                root, merged, current.studio, expected_digest=current.digest,
            )
    except sqlite3.OperationalError as exc:
        raise SystemConfigError("Nie uzyskano blokady profilu operatora.") from exc
