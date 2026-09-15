from __future__ import annotations

"""Durable, idempotent host operations for short-lived executor surfaces.

The caller performs only a bounded submit/status interaction.  Long-running
canonical Jaźń commands execute in a detached worker and keep their own durable
operation record under ``workspace_runtime``.  This module deliberately does
not replace lifecycle logic: the worker always re-enters the public ``run.py``
control plane.
"""

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping, Sequence

from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

HOST_OPERATION_SCHEMA_VERSION = schema_version("host_durable_operation")
HOST_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
TERMINAL_OPERATION_STATES = frozenset({"completed", "failed", "spawn_failed", "conflict"})
SUPPORTED_OPERATION_KINDS = frozenset({"daemon-start", "runtime-bootstrap", "supervisor-start"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_operation_id(value: str) -> str:
    candidate = str(value or "").strip()
    if not HOST_OPERATION_ID_RE.fullmatch(candidate):
        raise ValueError("operation_id_contains_unsafe_characters_or_invalid_length")
    return candidate


def host_operations_dir(root: Path) -> Path:
    return workspace_runtime_path(Path(root).expanduser().resolve()) / "host_operations"


def operation_record_path(root: Path, operation_id: str) -> Path:
    return host_operations_dir(root) / f"{normalize_operation_id(operation_id)}.json"


def operation_stdout_path(root: Path, operation_id: str) -> Path:
    return host_operations_dir(root) / f"{normalize_operation_id(operation_id)}.stdout.log"


def operation_stderr_path(root: Path, operation_id: str) -> Path:
    return host_operations_dir(root) / f"{normalize_operation_id(operation_id)}.stderr.log"


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _create_json_exclusive(path: Path, payload: Mapping[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        return True
    except FileExistsError:
        return False


def read_host_operation(root: Path, operation_id: str) -> dict[str, Any] | None:
    path = operation_record_path(root, operation_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _clean_remainder(items: Sequence[str]) -> list[str]:
    result = [str(item) for item in items]
    if result and result[0] == "--":
        result = result[1:]
    return result


def _reject_root_override(args: Sequence[str]) -> None:
    if any(item == "--root" or item.startswith("--root=") for item in args):
        raise ValueError("host_operation_root_override_forbidden")


def _require_option(args: Sequence[str], option: str) -> None:
    if option in args or any(item.startswith(option + "=") for item in args):
        return
    raise ValueError(f"host_operation_required_option_missing:{option}")


def build_host_operation_target_argv(
    root: Path,
    *,
    kind: str,
    remainder: Sequence[str] = (),
    python_executable: str | None = None,
) -> list[str]:
    runtime_root = Path(root).expanduser().resolve()
    run_file = runtime_root / "run.py"
    if not run_file.is_file():
        raise FileNotFoundError(f"canonical run.py not found: {run_file}")
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in SUPPORTED_OPERATION_KINDS:
        raise ValueError(f"unsupported_host_operation_kind:{normalized_kind}")
    extra = _clean_remainder(remainder)
    _reject_root_override(extra)

    if normalized_kind == "daemon-start":
        public_command = "start"
    elif normalized_kind == "runtime-bootstrap":
        public_command = "runtime-bootstrap"
        _require_option(extra, "--parts-dir")
        _require_option(extra, "--destination")
    else:
        public_command = "supervisor-run"

    return [
        str(python_executable or sys.executable),
        "-X",
        "utf8",
        str(run_file),
        public_command,
        "--root",
        str(runtime_root),
        *extra,
    ]


def operation_fingerprint(*, root: Path, kind: str, target_argv: Sequence[str]) -> str:
    payload = {
        "root": str(Path(root).expanduser().resolve()),
        "kind": str(kind),
        "target_argv": [str(item) for item in target_argv],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detached_process_options(*, platform: str | None = None) -> tuple[int, dict[str, Any]]:
    """Return explicit child-detachment options without shell indirection."""

    candidate = str(platform or os.name).lower()
    if candidate in {"nt", "windows", "win32"}:
        flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        return flags, {}
    return 0, {"start_new_session": True}


def _public_snapshot(record: Mapping[str, Any], *, created: bool | None = None) -> dict[str, Any]:
    snapshot = dict(record)
    snapshot.pop("target_argv", None)
    if created is not None:
        snapshot["created"] = bool(created)
        snapshot["idempotent_replay"] = not bool(created)
    snapshot["truth_boundary"] = (
        "accepted/running proves only that the durable host operation was recorded and, when present, its worker was spawned. "
        "It does not prove daemon readiness, active runtime identity, connector readiness, or an accepted visible Jaźń turn."
    )
    return snapshot


def submit_host_operation(
    root: Path,
    *,
    operation_id: str,
    kind: str,
    remainder: Sequence[str] = (),
    python_executable: str | None = None,
) -> dict[str, Any]:
    runtime_root = Path(root).expanduser().resolve()
    normalized_id = normalize_operation_id(operation_id)
    normalized_kind = str(kind or "").strip().lower()
    target_argv = build_host_operation_target_argv(
        runtime_root,
        kind=normalized_kind,
        remainder=remainder,
        python_executable=python_executable,
    )
    fingerprint = operation_fingerprint(root=runtime_root, kind=normalized_kind, target_argv=target_argv)
    record_path = operation_record_path(runtime_root, normalized_id)
    stdout_path = operation_stdout_path(runtime_root, normalized_id)
    stderr_path = operation_stderr_path(runtime_root, normalized_id)
    now = utc_now_iso()
    record: dict[str, Any] = {
        "schema_version": HOST_OPERATION_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION_FULL,
        "operation_id": normalized_id,
        "kind": normalized_kind,
        "operation_fingerprint": fingerprint,
        "status": "accepted",
        "phase": "worker_spawn_pending",
        "accepted": True,
        "created_at_utc": now,
        "updated_at_utc": now,
        "root": str(runtime_root),
        "target_argv": target_argv,
        "worker_pid": None,
        "command_pid": None,
        "returncode": None,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "retry_policy": "reuse_same_operation_id_never_replay_with_new_id_after_ambiguous_transport",
    }
    created = _create_json_exclusive(record_path, record)
    if not created:
        existing = read_host_operation(runtime_root, normalized_id)
        if existing is None:
            return {
                "ok": False,
                "accepted": False,
                "error_code": "host_operation_record_unreadable",
                "operation_id": normalized_id,
            }
        if str(existing.get("operation_fingerprint") or "") != fingerprint:
            return {
                "ok": False,
                "accepted": False,
                "error_code": "host_operation_id_conflict",
                "operation_id": normalized_id,
                "existing_kind": existing.get("kind"),
                "existing_status": existing.get("status"),
            }
        result = _public_snapshot(existing, created=False)
        result["ok"] = str(existing.get("status") or "") not in {"failed", "spawn_failed"}
        return result

    worker_argv = [
        str(python_executable or sys.executable),
        "-X",
        "utf8",
        "-m",
        "latka_jazn.core.host_operations",
        "--worker",
        "--root",
        str(runtime_root),
        "--operation-id",
        normalized_id,
    ]
    creationflags, extra_popen = detached_process_options()
    try:
        with stdout_path.open("ab") as out, stderr_path.open("ab") as err:
            proc = subprocess.Popen(
                worker_argv,
                cwd=str(runtime_root),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                creationflags=creationflags,
                **extra_popen,
            )
    except OSError as exc:
        record.update(
            {
                "status": "spawn_failed",
                "phase": "worker_spawn_failed",
                "updated_at_utc": utc_now_iso(),
                "error_code": "host_operation_worker_spawn_failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        _write_json_atomic(record_path, record)
        result = _public_snapshot(record, created=True)
        result["ok"] = False
        return result

    record.update(
        {
            "status": "accepted",
            "phase": "worker_spawned",
            "worker_pid": int(proc.pid),
            "updated_at_utc": utc_now_iso(),
        }
    )
    _write_json_atomic(record_path, record)
    result = _public_snapshot(record, created=True)
    result.update(
        {
            "ok": True,
            "next_action": "poll_host_operation",
            "status_command": (
                f"python -X utf8 run.py host-op-status --root {json.dumps(str(runtime_root))} "
                f"--operation-id {normalized_id} --json"
            ),
        }
    )
    return result


def host_operation_status(root: Path, *, operation_id: str) -> dict[str, Any]:
    runtime_root = Path(root).expanduser().resolve()
    normalized_id = normalize_operation_id(operation_id)
    record = read_host_operation(runtime_root, normalized_id)
    if record is None:
        return {
            "ok": False,
            "found": False,
            "error_code": "host_operation_not_found",
            "operation_id": normalized_id,
            "schema_version": HOST_OPERATION_SCHEMA_VERSION,
        }
    result = _public_snapshot(record)
    status = str(record.get("status") or "unknown")
    result.update(
        {
            "ok": status == "completed",
            "found": True,
            "terminal": status in TERMINAL_OPERATION_STATES,
            "pending": status not in TERMINAL_OPERATION_STATES,
            "next_action": "inspect_result" if status in TERMINAL_OPERATION_STATES else "poll_host_operation",
        }
    )
    return result


def _worker_update(root: Path, operation_id: str, **changes: Any) -> dict[str, Any]:
    record = read_host_operation(root, operation_id)
    if record is None:
        raise RuntimeError("host_operation_record_missing")
    record.update(changes)
    record["updated_at_utc"] = utc_now_iso()
    _write_json_atomic(operation_record_path(root, operation_id), record)
    return record


def run_host_operation_worker(root: Path, *, operation_id: str) -> int:
    runtime_root = Path(root).expanduser().resolve()
    normalized_id = normalize_operation_id(operation_id)
    record = read_host_operation(runtime_root, normalized_id)
    if record is None:
        return 31
    if str(record.get("status") or "") in TERMINAL_OPERATION_STATES:
        return 0
    target_value = record.get("target_argv")
    if not isinstance(target_value, list) or not target_value:
        _worker_update(
            runtime_root,
            normalized_id,
            status="failed",
            phase="target_validation_failed",
            error_code="host_operation_target_missing",
        )
        return 32
    target_argv = [str(item) for item in target_value]
    expected = operation_fingerprint(
        root=runtime_root,
        kind=str(record.get("kind") or ""),
        target_argv=target_argv,
    )
    if expected != str(record.get("operation_fingerprint") or ""):
        _worker_update(
            runtime_root,
            normalized_id,
            status="failed",
            phase="target_validation_failed",
            error_code="host_operation_fingerprint_mismatch",
        )
        return 33

    stdout_path = operation_stdout_path(runtime_root, normalized_id)
    stderr_path = operation_stderr_path(runtime_root, normalized_id)
    kind = str(record.get("kind") or "")
    creationflags, extra_popen = detached_process_options()
    try:
        with stdout_path.open("ab") as out, stderr_path.open("ab") as err:
            proc = subprocess.Popen(
                target_argv,
                cwd=str(runtime_root),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                creationflags=creationflags,
                **extra_popen,
            )
            _worker_update(
                runtime_root,
                normalized_id,
                status="running",
                phase="target_spawned",
                command_pid=int(proc.pid),
                started_at_utc=utc_now_iso(),
            )
            if kind == "supervisor-start":
                # The supervisor is intentionally the long-lived owner.  The
                # operation worker only proves process creation and then exits.
                try:
                    returncode = proc.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    _worker_update(
                        runtime_root,
                        normalized_id,
                        status="completed",
                        phase="supervisor_spawned",
                        returncode=None,
                        completed_at_utc=utc_now_iso(),
                        supervisor_pid=int(proc.pid),
                    )
                    return 0
                _worker_update(
                    runtime_root,
                    normalized_id,
                    status="failed",
                    phase="supervisor_exited_early",
                    returncode=int(returncode),
                    completed_at_utc=utc_now_iso(),
                    error_code="supervisor_exited_early",
                )
                return int(returncode or 34)
            returncode = proc.wait()
    except OSError as exc:
        _worker_update(
            runtime_root,
            normalized_id,
            status="failed",
            phase="target_spawn_failed",
            error_code="host_operation_target_spawn_failed",
            error=f"{type(exc).__name__}: {exc}",
            completed_at_utc=utc_now_iso(),
        )
        return 35

    _worker_update(
        runtime_root,
        normalized_id,
        status="completed" if int(returncode) == 0 else "failed",
        phase="target_completed" if int(returncode) == 0 else "target_failed",
        returncode=int(returncode),
        completed_at_utc=utc_now_iso(),
        error_code=None if int(returncode) == 0 else "host_operation_target_nonzero_exit",
    )
    return int(returncode)


def _worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--operation-id", required=True)
    return parser


def _main(argv: Sequence[str] | None = None) -> int:
    ns = _worker_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    if not ns.worker:
        return 2
    return run_host_operation_worker(ns.root, operation_id=ns.operation_id)


if __name__ == "__main__":
    raise SystemExit(_main())
