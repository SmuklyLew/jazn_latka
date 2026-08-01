from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any

from latka_jazn.core.version_source import VERSION_MODULE_RELATIVE_PATH


PACKAGE_DIR_NAME = "latka_jazn"
START_FILE_NAMES = ("run.py", "main.py")
WORKSPACE_RUNTIME_DIR_NAME = "workspace_runtime"
ACTIVE_RUNTIME_MARKER_NAME = "JAZN_ACTIVE_RUNTIME.json"


class RuntimeRootNotFoundError(RuntimeError):
    """Raised when no structurally valid runtime root can be found."""


def runtime_root_missing_markers(root: Path) -> tuple[str, ...]:
    candidate = Path(root).expanduser().resolve()
    missing: list[str] = []
    if not candidate.is_dir():
        missing.append("runtime_root_directory")
        return tuple(missing)
    if not (candidate / VERSION_MODULE_RELATIVE_PATH).is_file():
        missing.append(VERSION_MODULE_RELATIVE_PATH.as_posix())
    if not (candidate / PACKAGE_DIR_NAME).is_dir():
        missing.append(f"{PACKAGE_DIR_NAME}/")
    if not any((candidate / name).is_file() for name in START_FILE_NAMES):
        missing.append("main.py|run.py")
    return tuple(missing)


def is_runtime_root(root: Path) -> bool:
    return not runtime_root_missing_markers(root)


def find_start_file(root: Path) -> Path | None:
    candidate = Path(root).expanduser().resolve()
    for name in START_FILE_NAMES:
        path = candidate / name
        if path.is_file():
            return path
    return None


def find_runtime_root(start: Path | None = None) -> Path:
    origin = Path.cwd() if start is None else Path(start)
    origin = origin.expanduser().resolve()
    candidate = origin.parent if origin.is_file() else origin
    for current in (candidate, *candidate.parents):
        if is_runtime_root(current):
            return current
    raise RuntimeRootNotFoundError(
        f"runtime root not found from {origin}; required: "
        f"{VERSION_MODULE_RELATIVE_PATH.as_posix()}, {PACKAGE_DIR_NAME}/, and main.py or run.py"
    )


def workspace_runtime_path(
    root: Path,
    configured: str | Path | None = None,
) -> Path:
    """Resolve mutable runtime state independently from the code installation.

    A verified package may be mounted read-only by a host.  In that case the
    operator can set ``JAZN_RUNTIME_WORKSPACE_DIR`` to an absolute writable
    directory.  Relative values intentionally remain relative to ``active_root``
    for backward compatibility.
    """

    runtime_root = Path(root).expanduser().resolve()
    raw = configured
    if raw is None:
        raw = os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR", WORKSPACE_RUNTIME_DIR_NAME)
    candidate = Path(str(raw or WORKSPACE_RUNTIME_DIR_NAME).strip() or WORKSPACE_RUNTIME_DIR_NAME).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (runtime_root / candidate).resolve()


def runtime_state_path(root: Path, configured: str | Path) -> Path:
    """Resolve legacy ``workspace_runtime/...`` state through the writable root."""

    runtime_root = Path(root).expanduser().resolve()
    candidate = Path(configured).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    parts = candidate.parts
    if parts and parts[0].casefold() == WORKSPACE_RUNTIME_DIR_NAME.casefold():
        base = workspace_runtime_path(runtime_root)
        target = base.joinpath(*parts[1:]).resolve()
    else:
        base = runtime_root
        target = (runtime_root / candidate).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"runtime state path escapes its configured root: {configured}") from exc
    return target


def active_runtime_marker_path(root: Path) -> Path:
    return workspace_runtime_path(root) / ACTIVE_RUNTIME_MARKER_NAME


def resolve_active_runtime_marker_path(root: Path, marker_path: Path | None = None) -> Path:
    runtime_root = Path(root).expanduser().resolve()
    if marker_path is None:
        return active_runtime_marker_path(runtime_root)
    configured = Path(marker_path).expanduser()
    return configured.resolve() if configured.is_absolute() else (runtime_root / configured).resolve()


@dataclass(frozen=True, slots=True)
class ActiveRuntimeRootResolution:
    requested_root: Path
    root: Path
    marker_path: Path
    marker_found: bool
    marker_valid: bool
    source: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("requested_root", "root", "marker_path"):
            data[key] = str(data[key])
        return data


def resolve_active_runtime_root(
    runtime_root: Path,
    *,
    marker_path: Path | None = None,
) -> ActiveRuntimeRootResolution:
    requested_root = Path(runtime_root).expanduser().resolve()
    marker = resolve_active_runtime_marker_path(requested_root, marker_path)
    if not marker.is_file():
        return ActiveRuntimeRootResolution(
            requested_root=requested_root,
            root=requested_root,
            marker_path=marker,
            marker_found=False,
            marker_valid=False,
            source="runtime_root",
            error="active_marker_missing",
        )
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ActiveRuntimeRootResolution(
            requested_root=requested_root,
            root=requested_root,
            marker_path=marker,
            marker_found=True,
            marker_valid=False,
            source="runtime_root_after_rejected_marker",
            error=f"active_marker_invalid_json:{type(exc).__name__}",
        )

    raw_active_root = payload.get("active_root") if isinstance(payload, dict) else None
    if not isinstance(raw_active_root, str) or not raw_active_root.strip():
        return ActiveRuntimeRootResolution(
            requested_root=requested_root,
            root=requested_root,
            marker_path=marker,
            marker_found=True,
            marker_valid=False,
            source="runtime_root_after_rejected_marker",
            error="marker_active_root_empty",
        )

    candidate = Path(raw_active_root.strip()).expanduser()
    if not candidate.is_absolute():
        return ActiveRuntimeRootResolution(
            requested_root=requested_root,
            root=requested_root,
            marker_path=marker,
            marker_found=True,
            marker_valid=False,
            source="runtime_root_after_rejected_marker",
            error="marker_active_root_not_absolute",
        )
    candidate = candidate.resolve()
    missing = runtime_root_missing_markers(candidate)
    if missing:
        return ActiveRuntimeRootResolution(
            requested_root=requested_root,
            root=requested_root,
            marker_path=marker,
            marker_found=True,
            marker_valid=False,
            source="runtime_root_after_rejected_marker",
            error="marker_active_root_invalid:" + ",".join(missing),
        )
    return ActiveRuntimeRootResolution(
        requested_root=requested_root,
        root=candidate,
        marker_path=marker,
        marker_found=True,
        marker_valid=True,
        source="active_marker",
    )
