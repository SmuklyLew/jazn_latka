"""Explicit operator/test layouts; no implicit migration of live runtime or MEMORY.

SYSTEM is the verified root containing latka_jazn and tools. Acceptance state
is outside SYSTEM, canonical MEMORY, and every known runtime workspace.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from hashlib import sha256
import os
import re
from uuid import uuid4
from pathlib import Path
from typing import Iterator, Mapping

from latka_jazn.core.runtime_root import default_runtime_workspace_path, workspace_runtime_path
from latka_jazn.tools.application_shell.operator_paths import validate_operator_path


@dataclass(frozen=True)
class AcceptanceLayout:
    system: Path
    runtime: Path
    operator: Path
    memory: Path


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def resolve_acceptance_layout(system_root: Path, *, base: Path | None = None,
                              session_id: str | None = None) -> AcceptanceLayout:
    """Compute and validate paths only; never move existing data or start services."""
    system = Path(system_root).expanduser().resolve()
    identity = sha256(os.path.normcase(str(system)).encode("utf-8")).hexdigest()[:20]
    from latka_jazn.core.local_settings_layout import (
        local_settings_enabled, resolve_local_settings_layout,
    )
    local_layout = (resolve_local_settings_layout(system)
                    if base is None and local_settings_enabled(system)
                    else None)
    parent = (Path(base).expanduser() if base is not None
              else local_layout.acceptance if local_layout is not None
              else Path.home() / ".jazn" / "acceptance" / identity).resolve()
    if session_id is not None and not re.fullmatch(r"[0-9a-f]{32}", session_id):
        raise ValueError("Nieprawidłowy identyfikator testowej sesji runtime")
    runtime = (parent / "runtime" / session_id).resolve() if session_id else (parent / "runtime").resolve()
    operator = (parent / "operator").resolve()
    memory = (runtime / "memory").resolve()
    protected = {
        system,
        system / "memory",
        system.parent / "memory",
        default_runtime_workspace_path(system),
        workspace_runtime_path(system),
        system.parent / "workspace_runtime",
    }
    configured_memory = os.environ.get("JAZN_MEMORY_ROOT", "").strip()
    if configured_memory:
        candidate = Path(configured_memory).expanduser()
        protected.add(candidate.resolve() if candidate.is_absolute()
                      else (workspace_runtime_path(system) / candidate).resolve())
    # A narrowly owned .settings_local/acceptance path is allowed within
    # SYSTEM; MEMORY and workspace paths remain forbidden.
    if local_layout is not None and parent == local_layout.acceptance:
        protected.discard(system)
    for forbidden in protected:
        resolved = forbidden.resolve()
        if _overlaps(runtime, resolved) or _overlaps(operator, resolved):
            raise ValueError("Izolacja odbioru nachodzi na SYSTEM, MEMORY lub aktywny workspace")
    if _overlaps(runtime, operator):
        raise ValueError("Runtime i stan operatora nie mogą się nakładać")
    if local_layout is not None:
        from latka_jazn.core.local_settings_layout import (
            verify_local_descendant,
        )
        for candidate in (parent, runtime, operator, memory):
            verify_local_descendant(candidate, local_layout)

    validate_operator_path(
        operator, system, directory=True,
        allow_acceptance_operator=local_layout is not None,
    )
    return AcceptanceLayout(system, runtime, operator, memory)


def _owned_session_id(system_root: Path) -> str:
    """Create or recover a version-bound acceptance session, never a daemon."""
    from latka_jazn.version import PACKAGE_VERSION_FULL

    initial = resolve_acceptance_layout(system_root)
    operator = initial.operator
    operator.mkdir(parents=True, exist_ok=True)
    profile = operator / "acceptance_profile.json"
    if profile.is_symlink() or profile.is_junction():
        raise ValueError("Profil odbioru nie może być dowiązaniem")
    system = str(initial.system)
    payload = {
        "schema_version": "jazn_acceptance_profile/v1",
        "system_root": system,
        "runtime_version": PACKAGE_VERSION_FULL,
        "session_id": uuid4().hex,
    }
    # Exclusive creation gives concurrent GUI processes the same session ID.
    # No live daemon state is touched or inferred from this record.
    try:
        with profile.open("x", encoding="utf-8") as writer:
            json.dump(payload, writer, ensure_ascii=False, sort_keys=True)
            writer.flush()
            os.fsync(writer.fileno())
    except FileExistsError:
        pass
    if not profile.is_file() or profile.stat().st_size > 4096:
        raise ValueError("Brak poprawnego profilu odbioru")
    try:
        saved = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Uszkodzony profil odbioru; brak automatycznej migracji") from exc
    if (not isinstance(saved, dict)
            or saved.get("schema_version") != payload["schema_version"]
            or saved.get("system_root") != system
            or saved.get("runtime_version") != PACKAGE_VERSION_FULL
            or not isinstance(saved.get("session_id"), str)
            or re.fullmatch(r"[0-9a-f]{32}", saved["session_id"]) is None):
        raise ValueError("Niezgodny ROOT, wersja lub session_id profilu odbioru")
    return saved["session_id"]


def validate_resumed_daemon(layout: AcceptanceLayout, daemon_url: str) -> None:
    """Read-only identity gate when reusing a session with a daemon marker."""
    marker = layout.runtime / "JAZN_ACTIVE_RUNTIME.json"
    if not marker.exists() and not marker.is_symlink():
        return
    if marker.is_symlink() or marker.is_junction():
        raise ValueError("Niezaufany marker testowego daemona")
    from urllib.parse import urlsplit
    from latka_jazn.config import JaznConfig
    from latka_jazn.core.runtime_daemon import status_daemon
    url = urlsplit(daemon_url)
    if url.scheme != "http" or url.hostname != "127.0.0.1" or url.port is None:
        raise ValueError("Nieprawidłowy adres testowego daemona")
    status = status_daemon(JaznConfig(root=layout.system), host="127.0.0.1", port=url.port)
    if (status.get("active_state") != "active_trusted"
            or status.get("process_identity_confirmed") is not True
            or status.get("endpoint_identity_matches") is not True
            or status.get("endpoint_heartbeat_fresh") is not True
            or status.get("package_integrity_verified") is not True
            or status.get("source_provenance_verified") is not True):
        raise ValueError(
            "Odmowa wznowienia: marker istnieje, lecz ROOT/PID/instancja/heartbeat "
            "lub integralność nie zostały potwierdzone. Wykonaj diagnostykę operatora."
        )


@contextmanager
def acceptance_environment(system_root: Path) -> Iterator[AcceptanceLayout]:
    """Scoped acceptance overrides; production ENV and daemon remain untouched."""
    # Persistent, version-bound profile. No process is ever adopted by path alone.
    layout = resolve_acceptance_layout(system_root, session_id=_owned_session_id(system_root))
    overrides: Mapping[str, str] = {
        "JAZN_RUNTIME_WORKSPACE_DIR": str(layout.runtime),
        "JAZN_OPERATOR_STATE_ROOT": str(layout.operator),
        "JAZN_MEMORY_ROOT": str(layout.memory),
        "JAZN_MEMORY_MODE": "off",
        "JAZN_STUDIO_ACCEPTANCE_PROFILE": "isolated",
        "JAZN_MEMORY_TIER_DB": "acceptance_disabled.sqlite3",
        "JAZN_MEMORY_REBUILD_PROJECTS": str(layout.runtime / "rebuild_projects"),
        "JAZN_MEMORY_REBUILD_SETTINGS": str(layout.runtime / "rebuild_settings.json"),
    }
    removed_secrets = ("JAZN_MEMORY_CLOUD_TOKEN", "JAZN_MEMORY_WRITER_LEASE_TOKEN",
                       "JAZN_MCP_OAUTH_CLIENT_SECRET", "TUNNEL_TOKEN")
    before = {name: os.environ.get(name) for name in (*overrides, *removed_secrets)}
    try:
        os.environ.update(overrides)
        for name in removed_secrets:
            os.environ.pop(name, None)
        yield layout
    finally:
        for name, old in before.items():
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
