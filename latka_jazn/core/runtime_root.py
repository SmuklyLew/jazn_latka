from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Iterator

from latka_jazn.core.version_source import VERSION_MODULE_RELATIVE_PATH


PACKAGE_DIR_NAME = "latka_jazn"
START_FILE_NAMES = ("run.py", "main.py")
WORKSPACE_RUNTIME_DIR_NAME = "workspace_runtime"
ACTIVE_RUNTIME_MARKER_NAME = "JAZN_ACTIVE_RUNTIME.json"
WORKSPACE_MIGRATION_LOG_NAME = "runtime_workspace_migrations.jsonl"
WORKSPACE_LOCK_DIR_NAME = ".locks"


class RuntimeRootNotFoundError(RuntimeError):
    """Raised when no structurally valid runtime root can be found."""


class RuntimeWorkspaceBusyError(RuntimeError):
    """Raised when a short-lived canonical workspace transition is already running."""


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


def default_runtime_workspace_path(root: Path) -> Path:
    """Return the one host-level mutable workspace shared by sibling runtime versions.

    Runtime code may live in versioned directories, but the active marker, daemon PID,
    checkpoints and other mutable host state must not be versioned with that code.
    When a runtime is already materialized directly under ``workspace_runtime`` (the
    ChatGPT host layout), the parent itself is the canonical workspace. Otherwise the
    canonical workspace is a sibling of the active runtime root.
    """

    runtime_root = Path(root).expanduser().resolve()
    parent = runtime_root.parent
    if parent.name.casefold() == WORKSPACE_RUNTIME_DIR_NAME.casefold():
        return parent.resolve()
    if parent.name.casefold() in {"runtime_roots", "runtime-roots"}:
        return (parent.parent / WORKSPACE_RUNTIME_DIR_NAME).resolve()
    return (parent / WORKSPACE_RUNTIME_DIR_NAME).resolve()


def legacy_workspace_runtime_path(root: Path) -> Path:
    """Historical per-version workspace path kept only for one-way migration."""

    return (Path(root).expanduser().resolve() / WORKSPACE_RUNTIME_DIR_NAME).resolve()


def workspace_runtime_path(
    root: Path,
    configured: str | Path | None = None,
) -> Path:
    """Resolve the single mutable host workspace independently from code versions.

    ``JAZN_RUNTIME_WORKSPACE_DIR`` remains the explicit operator override. Absolute
    overrides are used directly; relative overrides remain relative to ``active_root``
    for compatibility. Without an override the workspace is host-level, outside the
    versioned runtime root, so upgrades replace only code while preserving live state.
    """

    runtime_root = Path(root).expanduser().resolve()
    raw: str | Path | None = configured
    configured_text = str(raw or "").strip()
    if not configured_text or configured_text.casefold() == WORKSPACE_RUNTIME_DIR_NAME.casefold():
        env_raw = os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR")
        raw = env_raw if env_raw and env_raw.strip() else None
    if raw is None or not str(raw).strip():
        return default_runtime_workspace_path(runtime_root)
    candidate = Path(str(raw).strip()).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (runtime_root / candidate).resolve()


def runtime_state_path(root: Path, configured: str | Path) -> Path:
    """Resolve legacy ``workspace_runtime/...`` names through the canonical workspace."""

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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _files_equivalent(left: Path, right: Path) -> bool:
    try:
        return left.stat().st_size == right.stat().st_size and _sha256_file(left) == _sha256_file(right)
    except OSError:
        return False


def _move_file_preserving_state(source: Path, destination: Path) -> str:
    """Move a state file, falling back to copy+fsync across filesystems."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, destination)
        return "replace"
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    tmp = destination.with_name(f".{destination.name}.{os.getpid()}.migrate.tmp")
    try:
        with source.open("rb") as src, tmp.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(source, tmp, follow_symlinks=False)
        os.replace(tmp, destination)
        source.unlink()
        return "copy_fsync_replace"
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_root_label(root: Path) -> str:
    value = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in root.name)
    return value or "runtime"


@contextmanager
def runtime_workspace_transition_lock(
    root: Path,
    name: str,
    *,
    stale_after_seconds: float = 60.0,
) -> Iterator[Path]:
    """Serialize short marker/migration transitions with an atomic exclusive file."""

    workspace = workspace_runtime_path(root)
    lock_dir = workspace / WORKSPACE_LOCK_DIR_NAME
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{name}.lock"
    for _attempt in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            try:
                age = max(0.0, time.time() - lock_path.stat().st_mtime)
            except OSError:
                age = 0.0
            if age > float(stale_after_seconds):
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    pass
            raise RuntimeWorkspaceBusyError(f"runtime workspace transition busy: {lock_path}") from exc
        else:
            try:
                payload = {
                    "schema_version": "runtime_workspace_transition_lock/v1",
                    "name": name,
                    "pid": os.getpid(),
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "runtime_root": str(Path(root).resolve()),
                }
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                yield lock_path
            finally:
                try:
                    lock_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return
    raise RuntimeWorkspaceBusyError(f"runtime workspace transition busy: {lock_path}")


def migrate_legacy_runtime_workspace(
    root: Path,
    *,
    destination: Path | None = None,
) -> dict[str, Any]:
    """Move historical ``<runtime>/workspace_runtime`` state to the host workspace.

    Existing canonical files win. Byte-identical legacy duplicates are removed;
    divergent legacy files are preserved under ``legacy_workspace_imports`` instead
    of overwriting current host state. Symlinks fail closed and remain untouched.
    """

    runtime_root = Path(root).expanduser().resolve()
    source = legacy_workspace_runtime_path(runtime_root)
    target = Path(destination).expanduser().resolve() if destination else workspace_runtime_path(runtime_root)
    report: dict[str, Any] = {
        "schema_version": "runtime_workspace_migration/v1",
        "runtime_root": str(runtime_root),
        "legacy_workspace": str(source),
        "canonical_workspace": str(target),
        "moved": [],
        "deduplicated": [],
        "archived_conflicts": [],
        "blocked": [],
        "ok": True,
        "status": "not_needed",
    }
    if source == target:
        report["status"] = "already_canonical"
        return report
    target.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        report["status"] = "legacy_workspace_absent"
        return report
    if source.is_symlink() or not source.is_dir():
        report["ok"] = False
        report["status"] = "blocked"
        report["blocked"].append({"path": str(source), "reason": "legacy_workspace_not_plain_directory"})
        return report

    with runtime_workspace_transition_lock(runtime_root, "workspace-migration"):
        for path in sorted(source.rglob("*")):
            if not path.is_file() and not path.is_symlink():
                continue
            rel = path.relative_to(source)
            if path.is_symlink():
                report["blocked"].append({"path": rel.as_posix(), "reason": "symlink_not_migrated"})
                continue
            canonical = target / rel
            if not canonical.exists():
                method = _move_file_preserving_state(path, canonical)
                report["moved"].append({"path": rel.as_posix(), "method": method})
                continue
            if canonical.is_file() and _files_equivalent(path, canonical):
                path.unlink()
                report["deduplicated"].append(rel.as_posix())
                continue
            digest = _sha256_file(path)[:12]
            archived = target / "legacy_workspace_imports" / _safe_root_label(runtime_root) / rel
            if archived.exists():
                archived = archived.with_name(f"{archived.name}.{digest}.legacy")
            method = _move_file_preserving_state(path, archived)
            report["archived_conflicts"].append(
                {"path": rel.as_posix(), "archived_to": str(archived), "method": method}
            )

        for directory in sorted((p for p in source.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            source.rmdir()
        except OSError:
            pass

        report["ok"] = not report["blocked"]
        report["status"] = "migrated" if report["ok"] else "partially_migrated_blocked_entries"
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        log_path = target / WORKSPACE_MIGRATION_LOG_NAME
        with log_path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return report


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
