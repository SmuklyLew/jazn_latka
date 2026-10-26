"""Explicit operator/test layouts; no implicit migration of live runtime or MEMORY.

SYSTEM is the verified root containing latka_jazn and tools. Acceptance state
is outside SYSTEM, canonical MEMORY, and every known runtime workspace.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
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
    parent = (Path(base).expanduser() if base is not None
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
    for forbidden in protected:
        resolved = forbidden.resolve()
        if _overlaps(runtime, resolved) or _overlaps(operator, resolved):
            raise ValueError("Izolacja odbioru nachodzi na SYSTEM, MEMORY lub aktywny workspace")
    if _overlaps(runtime, operator):
        raise ValueError("Runtime i stan operatora nie mogą się nakładać")
    validate_operator_path(operator, system, directory=True)
    return AcceptanceLayout(system, runtime, operator, memory)


@contextmanager
def acceptance_environment(system_root: Path) -> Iterator[AcceptanceLayout]:
    """Scoped acceptance overrides; production ENV and daemon remain untouched."""
    # Unique runtime per invocation, durable operator evidence per checkout.
    # Never clear another instance's daemon markers or state on exit.
    layout = resolve_acceptance_layout(system_root, session_id=uuid4().hex)
    overrides: Mapping[str, str] = {
        "JAZN_RUNTIME_WORKSPACE_DIR": str(layout.runtime),
        "JAZN_OPERATOR_STATE_ROOT": str(layout.operator),
        "JAZN_MEMORY_ROOT": str(layout.memory),
        "JAZN_MEMORY_MODE": "off",
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
