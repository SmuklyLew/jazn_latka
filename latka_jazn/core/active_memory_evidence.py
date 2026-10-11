"""Bounded, read-only daemon observations for the operator readiness preflight.

The collector result is INTERNAL: paths and identity claims must not be copied
into public reports. Configured database access is not proof of a real recall.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import shlex
import sqlite3
import subprocess
import time
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core.process_identity import process_fingerprint, process_fingerprint_matches
from latka_jazn.core.runtime_root import resolve_active_runtime_marker_path
from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.memory.database_identity import read_database_identity

SCHEMA = "jazn_active_memory_evidence/v1"
ENDPOINT = "/active-memory-evidence"
CHECKS = ("runtime_root", "version_integrity", "process", "endpoint", "heartbeat",
          "memory_root", "database_identity", "recall", "continuity")
META_KEYS = ("schema_version", "memory_generation", "source_union_sha256",
             "restore_run_id", "parent_database_sha256")


def _check(state: str, issue: str) -> dict[str, str]:
    return {"state": state, "issue": issue}


def _same_path(left: Any, right: Any) -> bool:
    try:
        if not left or not right:
            return False
        a, b = Path(str(left)), Path(str(right))
        return a.is_absolute() and b.is_absolute() and a.resolve() == b.resolve()
    except (OSError, ValueError, RuntimeError):
        return False


def _signature(payload: dict[str, Any], token: str) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hmac.new(token.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _file_state(path: Path) -> tuple[Any, ...]:
    result: list[Any] = []
    for item in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        try:
            stat = item.stat()
            result.append((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))
        except FileNotFoundError:
            result.append(None)
    return tuple(result)


def _database_metadata(path: Path) -> dict[str, str]:
    """A single bounded read transaction; no schema creation or source checkpoint."""
    before = _file_state(path)
    if before[0] is None:
        raise FileNotFoundError
    deadline = time.monotonic() + 1.0
    with closing(connect_runtime_readonly(path, timeout_ms=250)) as con:
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        con.execute("BEGIN")
        rows = con.execute(
            "SELECT key,value FROM unified_memory_meta WHERE key IN ("
            + ",".join("?" for _ in META_KEYS) + ")", META_KEYS,
        ).fetchall()
        metadata = {str(row[0]): str(row[1]) for row in rows}
        identity = read_database_identity(con)
        if identity is not None:
            metadata["database_uuid"] = identity.database_uuid
            metadata["trust_state"] = identity.trust_state
        if any(len(value) > 4096 for value in metadata.values()):
            raise ValueError("metadata_limit")
    if before != _file_state(path):
        raise ValueError("database_changed")
    return metadata


def build_active_memory_payload(
    config: JaznConfig, *, liveness: dict[str, Any], nonce: str, token: str,
) -> dict[str, Any]:
    """Called only by the authenticated daemon handler; no lifecycle writes."""
    if re.fullmatch(r"[a-f0-9]{32}", nonce) is None:
        raise ValueError("invalid_evidence_nonce")
    identity_keys = ("daemon_instance_id", "daemon_pid", "process_fingerprint",
                     "runtime_version", "active_root", "runtime_process_active",
                     "last_heartbeat_at_utc", "heartbeat_interval_seconds")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA, "nonce": nonce,
        "identity": {key: liveness.get(key) for key in identity_keys},
        "memory_observation": "configured_native_database_read_only",
        "memory_root": None, "database_path": None, "database_metadata": {},
        "database_observation": "unverified",
        "recall": _check("unverified", "independent_recall_evidence_missing"),
        "continuity": _check("unverified", "independent_continuity_evidence_missing"),
    }
    try:
        # Reuse gateway discovery, never instantiate a gateway/session or store.
        from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
        memory_root = config.memory_root.resolve()
        database = LivingMemoryGateway._candidate_native_database(memory_root).resolve()
        database.relative_to(memory_root)
        payload["memory_root"] = str(memory_root)
        payload["database_path"] = str(database)
        if config.memory_mode == "off":
            payload["database_observation"] = "memory_disabled"
        else:
            payload["database_metadata"] = _database_metadata(database)
            payload["database_observation"] = "observed"
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        payload["database_observation"] = "unverified"
    payload["proof"] = _signature(payload, token)
    return payload


def _observe_process_command(pid: int, root: Path) -> bool | None:
    """Observe OS command arguments, not marker claims; never return arguments."""
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {int(pid)}').CommandLine"],
                capture_output=True, text=True, timeout=3.0,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            )
            if result.returncode or not result.stdout.strip():
                return None
            args = [value.strip('"') for value in shlex.split(result.stdout.strip(), posix=False)]
        elif os.name == "posix":
            raw = (Path("/proc") / str(pid) / "cmdline").read_bytes()
            args = [part.decode("utf-8", errors="strict") for part in raw.split(b"\0") if part]
        else:
            return None
        if "--daemon-run" not in args or "--root" not in args:
            return False
        at = args.index("--root")
        if at + 1 >= len(args) or not _same_path(args[at + 1], root):
            return False
        return any(_same_path(arg, root / name) for arg in args for name in ("main.py", "run.py"))
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return None


def _heartbeat_verified(identity: dict[str, Any]) -> bool:
    try:
        stamp = datetime.fromisoformat(str(identity["last_heartbeat_at_utc"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False
        age = (datetime.now(timezone.utc) - stamp).total_seconds()
        interval = float(identity["heartbeat_interval_seconds"])
        return (math.isfinite(interval) and 0 < interval <= 60
                and -2 <= age <= min(60, max(15, interval * 3)))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def collect_active_memory_evidence(system_root: Path) -> dict[str, Any]:
    """Collect internal evidence only; never authorize activation or emit contents."""
    from latka_jazn.core import runtime_daemon as daemon
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "checks": {key: _check("unverified", f"{key}_evidence_missing") for key in CHECKS},
        "observed_memory_path": None, "database_metadata": {},
    }
    checks = result["checks"]
    checks["recall"] = _check("unverified", "independent_recall_evidence_missing")
    checks["continuity"] = _check("unverified", "independent_continuity_evidence_missing")
    try:
        root = Path(system_root).expanduser().resolve()
        config = JaznConfig(root=root)
        marker_path = resolve_active_runtime_marker_path(root)
        if not marker_path.is_file() or marker_path.stat().st_size > 2_000_000:
            return result
        marker_bytes = marker_path.read_bytes()
        marker = json.loads(marker_bytes)
        if not isinstance(marker, dict):
            return result
        host = str(marker.get("daemon_host") or daemon.DEFAULT_DAEMON_HOST)
        if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
            checks["endpoint"] = _check("blocked", "endpoint_not_loopback")
            return result
        port = int(marker.get("daemon_port") or daemon.DEFAULT_DAEMON_PORT)
        if not 1 <= port <= 65535:
            return result
        status = daemon.status_daemon(config, host=host, port=port, probe_endpoint=False)
        same_root = status.get("marker_valid") is True and _same_path(status.get("resolved_active_root"), root)
        checks["runtime_root"] = _check("verified" if same_root else "conflict", "runtime_root_bound" if same_root else "runtime_root_mismatch")
        if not same_root:
            return result
        token = daemon.read_daemon_auth_token(root)
        if not token:
            checks["endpoint"] = _check("unverified", "endpoint_authentication_missing")
            return result
        pid = int(status.get("pid") or 0)
        before = process_fingerprint(pid)
        nonce = secrets.token_hex(16)
        response = daemon.http_json("GET", daemon.daemon_url(host, port, ENDPOINT) + "?nonce=" + nonce, timeout=3.0, token=token)
        if not isinstance(response, dict):
            return result
        proof = response.pop("proof", "")
        authenticated = (response.get("schema_version") == SCHEMA and response.get("nonce") == nonce
                         and isinstance(proof, str) and hmac.compare_digest(proof, _signature(response, token)))
        if not authenticated:
            checks["endpoint"] = _check("conflict", "endpoint_authentication_failed")
            return result
        identity = response.get("identity")
        if not isinstance(identity, dict):
            return result
        instance = marker.get("daemon_instance_id")
        bound = bool(instance and identity.get("daemon_instance_id") == instance
                     and identity.get("daemon_pid") == pid and pid > 0
                     and _same_path(identity.get("active_root"), root)
                     and identity.get("runtime_process_active") is True)
        checks["endpoint"] = _check("verified" if bound else "conflict", "authenticated_instance_bound" if bound else "endpoint_instance_mismatch")
        if not bound:
            return result
        version_ok = (status.get("package_integrity_verified") is True and status.get("source_provenance_verified") is True
                      and identity.get("runtime_version") == status.get("runtime_version_full")
                      and identity.get("runtime_version") == marker.get("runtime_version_full", marker.get("runtime_version")))
        checks["version_integrity"] = _check("verified" if version_ok else "conflict", "version_integrity_bound" if version_ok else "version_integrity_mismatch")
        command = _observe_process_command(pid, root)
        after = process_fingerprint(pid)
        matches = [process_fingerprint_matches(left, before) for left in (marker.get("process_fingerprint"), identity.get("process_fingerprint"), after)]
        process_ok = command is True and all(value is True for value in matches)
        process_conflict = command is False or any(value is False for value in matches)
        checks["process"] = _check("verified" if process_ok else "conflict" if process_conflict else "unverified", "process_command_fingerprint_bound" if process_ok else "process_identity_not_verified")
        heartbeat_ok = _heartbeat_verified(identity)
        checks["heartbeat"] = _check("verified" if heartbeat_ok else "unverified", "fresh_instance_heartbeat" if heartbeat_ok else "heartbeat_stale_or_invalid")
        memory_root = response.get("memory_root")
        same_memory = _same_path(memory_root, config.memory_root)
        checks["memory_root"] = _check("verified" if same_memory else "conflict", "memory_root_bound" if same_memory else "host_runtime_memory_root_mismatch")
        # Do not inspect a path claimed by an unbound or incorrectly launched process.
        if not (same_memory and process_ok and version_ok and heartbeat_ok):
            return result
        raw_database = response.get("database_path")
        if not isinstance(raw_database, str) or not Path(raw_database).is_absolute():
            return result
        database = Path(raw_database).resolve()
        database.relative_to(Path(str(memory_root)).resolve())
        from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
        expected_database = LivingMemoryGateway._candidate_native_database(config.memory_root).resolve()
        if database != expected_database or response.get("database_observation") != "observed":
            checks["database_identity"] = _check("unverified", "configured_database_not_observed")
            return result
        local_metadata = _database_metadata(database)
        runtime_metadata = response.get("database_metadata")
        identity_ok = (isinstance(runtime_metadata, dict) and local_metadata == runtime_metadata
                       and bool(local_metadata.get("database_uuid")))
        checks["database_identity"] = _check("verified" if identity_ok else "conflict" if local_metadata != runtime_metadata else "unverified", "database_identity_observation_bound" if identity_ok else "database_identity_unverified")
        # Heartbeats can rewrite the marker normally; only generation identity
        # must stay stable across this non-atomic collection.
        final_marker = json.loads(marker_path.read_bytes())
        if (not isinstance(final_marker, dict) or final_marker.get("daemon_instance_id") != instance
                or final_marker.get("daemon_pid") != pid):
            checks["endpoint"] = _check("conflict", "runtime_generation_changed")
            return result
        result["observed_memory_path"] = str(database)
        result["database_metadata"] = local_metadata
        result["observation_scope"] = "sequential_config_bound_metadata_not_recall"
        return result
    except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error):
        checks["database_identity"] = _check("unverified", "evidence_collection_incomplete")
        return result
