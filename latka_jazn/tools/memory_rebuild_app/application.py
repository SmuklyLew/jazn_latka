from __future__ import annotations

"""Single Memory Rebuild v4 application service used by every host surface."""

from pathlib import Path
from typing import Any, Mapping
import subprocess

from latka_jazn.version import PACKAGE_VERSION_FULL

from .protocol_engine import ProtocolEngine
from .settings import MemoryRebuildSettings
from .test_spec import TEST_PROTOCOL_ORDER


def resolve_base_commit(root: str | Path) -> str:
    repository = Path(root).expanduser().resolve()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise RuntimeError(f"cannot resolve Memory Rebuild base commit: {exc}") from exc
    commit = completed.stdout.strip()
    if len(commit) != 40:
        raise RuntimeError("git rev-parse HEAD returned an invalid commit")
    return commit


class MemoryRebuildApplicationService:
    """Composition root for ProtocolEngine in CLI, Studio and tests."""

    def __init__(
        self,
        output_root: str | Path,
        *,
        tool_root: str | Path,
        settings: MemoryRebuildSettings | None = None,
        base_commit: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self.output_root = Path(output_root).expanduser().resolve()
        self.tool_root = Path(tool_root).expanduser().resolve()
        self.engine = ProtocolEngine(
            self.output_root,
            settings=settings,
            system_version=PACKAGE_VERSION_FULL,
            base_commit=base_commit or resolve_base_commit(self.tool_root),
            run_id=run_id,
        )

    def run_protocol(self, profile: str, **kwargs: Any) -> dict[str, Any]:
        selected = profile.strip().lower()
        if selected not in TEST_PROTOCOL_ORDER:
            raise ValueError(f"unknown Memory Rebuild protocol: {profile}")
        runner = getattr(self.engine, f"run_{selected}")
        result = dict(runner(**kwargs))
        result["run_manifest"] = self.engine.seal_manifest()
        return result

    def validate_protocol(
        self,
        profile: str,
        artifact: str | Path | Mapping[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.engine.validate(profile, artifact, **kwargs)


__all__ = ["MemoryRebuildApplicationService", "resolve_base_commit"]
