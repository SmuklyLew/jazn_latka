"""Read-only, bounded process/job/finalization telemetry for Jaźń Monitor.

Only a matching live daemon instance is considered an owned runtime process.
No user prompts, model outputs, raw command lines or private MEMORY are emitted.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from typing import Any

from .paths import monitor_workspace

MAX_JOB_JSON = 2 * 1024 * 1024
MAX_PROCESS_JSON = 512 * 1024
MAX_VISIBLE_JOBS = 20
SAFE_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,95}$")


def _safe_code(value: Any) -> str | None:
    return value if isinstance(value, str) and SAFE_CODE.fullmatch(value) else None


def _read_json(path: Path, cap: int) -> dict[str, Any] | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > cap:
            return None
        data = json.loads(path.read_bytes().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _elapsed(start: Any, end: Any = None) -> float | None:
    if not isinstance(start, str):
        return None
    try:
        from_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        to_time = (
            datetime.fromisoformat(end.replace("Z", "+00:00"))
            if isinstance(end, str)
            else datetime.now(timezone.utc)
        )
        if from_time.tzinfo is None or to_time.tzinfo is None:
            return None
        return round(max(0.0, (to_time - from_time).total_seconds()), 2)
    except (TypeError, ValueError, OverflowError):
        return None


def _audit_reasons(root: Path, request_ids: set[str]) -> dict[str, str]:
    """Optional read-only lookup of rejection *codes*, never response contents."""
    if not request_ids:
        return {}
    db = monitor_workspace(root) / "core_state" / "memory_runtime" / "sqlite" / "runtime_write_v1" / "runtime_audit.sqlite3"
    if not db.resolve().is_relative_to(monitor_workspace(root).resolve()) or db.is_symlink() or not db.is_file():
        return {}
    found: dict[str, str] = {}
    try:
        # ro=1 avoids writes to the audit database; keep this query short.
        con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=0.1)
        try:
            rows = con.execute(
                "SELECT payload_json FROM audit_runtime_events "
                "WHERE event_type IN ('runtime_turn_rejected','runtime_turn_failed') "
                "ORDER BY created_at_utc DESC LIMIT 100"
            )
            for (raw,) in rows:
                if not isinstance(raw, str) or len(raw) > 131072:
                    continue
                item = json.loads(raw)
                if not isinstance(item, dict):
                    continue
                rid = item.get("request_id")
                if not isinstance(rid, str) or rid not in request_ids or rid in found:
                    continue
                diag = item.get("turn_diagnostics")
                reason = _safe_code(diag.get("failure_reason_code")) if isinstance(diag, dict) else None
                if reason:
                    found[rid] = reason
                if len(found) >= len(request_ids):
                    break
        finally:
            con.close()
    except (OSError, ValueError, sqlite3.Error):
        return found
    return found


def jobs_snapshot(root: Path | None, marker: dict[str, Any] | None) -> dict[str, Any]:
    """Recovery metadata is not a history of all accepted dialogue turns."""
    unavailable = {"state": "unknown", "counts": None, "items": [],
                   "finalization": {"state": "unknown", "reason_code": None,
                                    "error_code": None, "request_id": None}}
    if root is None or not isinstance(marker, dict):
        return unavailable
    summary = marker.get("daemon_chat_jobs")
    counts = None
    if isinstance(summary, dict):
        keys = ("submitted_total", "completed_total", "failed_non_timeout_total",
                "execution_timeout_total", "host_finalization_rejected_total",
                "host_finalization_expired_total", "cancelled_total", "recovered_total",
                "queue_size", "pending")
        counts = {key: summary.get(key) if type(summary.get(key)) is int
                  and summary[key] >= 0 else None for key in keys}
    data = _read_json(monitor_workspace(root) / "daemon_chat_jobs.json", MAX_JOB_JSON)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        out = dict(unavailable)
        out["counts"] = counts
        out["state"] = "unavailable"
        return out
    terminal = {"completed", "failed", "rejected", "execution_timeout", "cancelled",
                "recovered_after_restart", "host_finalization_rejected", "host_finalization_expired"}
    known = terminal | {"accepted", "pending", "running", "queued",
                        "awaiting_host_finalization", "waiting_for_host_finalization"}
    items: list[dict[str, Any]] = []
    for entry in data["jobs"]:
        if not isinstance(entry, dict):
            continue
        req = entry.get("request_id")
        if not isinstance(req, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", req):
            continue
        status = entry.get("status")
        created = entry.get("created_at_utc")
        completed = entry.get("completed_at_utc")
        items.append({
            "accepted_finalization_at_utc": entry.get("accepted_finalization_at_utc") if status == "completed" else None,
            "last_host_attempt_at_utc": entry.get("last_host_attempt_at_utc"),
            "request_id": req, "state": status if isinstance(status, str) and status in known else "unknown",
            "created_at_utc": created if _date_epoch(created) is not None else None,
            "completed_at_utc": completed if _date_epoch(completed) is not None else None,
            "duration_seconds": _elapsed(entry.get("started_at_utc") or created, completed)
                                if completed or (isinstance(status, str) and status not in terminal) else None,
            "error_code": _safe_code(entry.get("result_error_code")) or _safe_code(entry.get("error")),
            "reason_code": _safe_code(entry.get("host_finalization_reason")),
        })

    def latest(rows: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
        if len(rows) == 1:
            return rows[0]
        dated = [row for row in rows if row.get(field)]
        return max(dated, key=lambda row: (_date_epoch(row[field]) or 0.0, row["request_id"]), default=None)

    admitted = latest(items, "created_at_utc")
    completed_job = latest([row for row in items if row["state"] == "completed"], "completed_at_utc")
    last = latest([row for row in items if row["state"] in terminal], "completed_at_utc")
    accepted_final = latest([row for row in items if _date_epoch(row["accepted_finalization_at_utc"]) is not None],
                            "accepted_finalization_at_utc")
    host_attempt = latest([row for row in items if _date_epoch(row["last_host_attempt_at_utc"]) is not None],
                          "last_host_attempt_at_utc")
    history_counts = dict(Counter(item["state"] for item in items))
    items.sort(key=lambda row: (
        _date_epoch(row["completed_at_utc"] or row["created_at_utc"]) or float("-inf"), row["request_id"]
    ), reverse=True)
    visible = items[:MAX_VISIBLE_JOBS]
    reason_rows = visible + ([last] if last else [])
    reasons = _audit_reasons(root, {row["request_id"] for row in reason_rows
                                   if row["state"] in ("failed", "rejected") and not row["reason_code"]})
    for row in reason_rows:
        row["reason_code"] = row["reason_code"] or reasons.get(row["request_id"])
    finalization = {"state": "unknown", "reason_code": None, "error_code": None,
                    "request_id": None, "accepted_finalization": None, "evidence": "job_status_only"}
    if last is not None:
        finalization.update({key: last[key] for key in ("reason_code", "error_code", "request_id")})
        finalization["state"] = {"failed": "rejected", "completed": "completed_job"}.get(last["state"], last["state"])
    return {"state": "available", "counts": counts, "counts_scope": "current_daemon_instance",
            "history_counts": history_counts, "history_scope": "retained_recovery_records",
            "items": visible, "last_admitted_job": admitted, "last_completed_job": completed_job,
            "last_terminal_job": last, "last_host_attempt": host_attempt,
            "last_accepted_finalization": accepted_final, "finalization": finalization,
            "scope": "daemon_recovery_metadata_only"}


def _windows_process_rows() -> list[dict[str, Any]] | None:
    """WMI probe is bounded; never send raw CommandLine to UI or logs."""
    if os.name != "nt":
        return None
    script = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        "$r=@(Get-CimInstance Win32_Process -Filter "
        "\"Name='python.exe' OR Name='pythonw.exe' OR Name='Jazn-Daemon.exe'\" "
        "| ForEach-Object { $p=Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; "
        "[pscustomobject]@{pid=$_.ProcessId;parent_pid=$_.ParentProcessId;"
        "created=$($_.CreationDate.ToString('o'));"
        "command_line=$_.CommandLine;cpu_seconds=$($p.CPU);"
        "ram_bytes=$($p.WorkingSet64)} }); "
        "@($r) | ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=5, check=False,
            # Polling a GUI observer must not flash a new PowerShell console.
            # CREATE_NO_WINDOW prevents a window, NOT OS process visibility.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if p.returncode != 0 or len(p.stdout) > MAX_PROCESS_JSON:
            return None
        obj = json.loads(p.stdout.decode("utf-8-sig"))
        return [x for x in (obj if isinstance(obj, list) else [obj]) if isinstance(x, dict)]
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        return None


def _date_epoch(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp() if dt.tzinfo else None
    except (ValueError, OverflowError):
        return None


def _linux_process_rows() -> list[dict[str, Any]] | None:
    """Read /proc identity/metrics without ps, subprocesses or executable renames."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        boot = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                    if line.startswith("btime "))
        sysconf = getattr(os, "sysconf")  # POSIX-only; Windows stubs omit it.
        ticks = sysconf("SC_CLK_TCK")
        page_size = sysconf("SC_PAGE_SIZE")
        paths = list(Path("/proc").iterdir())
    except (OSError, ValueError, StopIteration):
        return None
    result = []
    for path in paths:
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            argv = (path / "cmdline").read_bytes()[:32768].decode("utf-8", errors="replace").split("\0")
            if not argv or "python" not in Path(argv[0]).name.lower():
                continue
            result.append({"pid": int(path.name), "parent_pid": int(fields[1]),
                "created": datetime.fromtimestamp(boot + int(fields[19]) / ticks, timezone.utc).isoformat(),
                "command_line": " ".join('"' + arg + '"' for arg in argv if arg),
                "cpu_seconds": (int(fields[11]) + int(fields[12])) / ticks,
                "ram_bytes": int(fields[21]) * page_size})
        except (OSError, ValueError, IndexError, OverflowError):
            continue  # process may exit during the observation
    return result


def process_snapshot(root: Path | None, marker: dict[str, Any] | None,
                     live: dict[str, Any] | None) -> dict[str, Any]:
    """Only verified daemon PID and birth-time-safe descendants are labelled owned."""
    if root is None or not isinstance(marker, dict) or not isinstance(live, dict):
        return {"state": "unknown", "items": [], "scope": "verified_daemon_and_descendants"}
    pid = marker.get("daemon_pid")
    if (type(pid) is not int or pid < 1 or live.get("daemon_pid") != pid
            or marker.get("daemon_instance_id") != live.get("daemon_instance_id")
            or live.get("liveness_ok") is not True or live.get("heartbeat_fresh") is not True):
        return {"state": "unknown", "items": [], "scope": "verified_daemon_and_descendants"}
    rows = _windows_process_rows()
    if rows is None and sys.platform.startswith("linux"):
        rows = _linux_process_rows()
    if rows is None:
        return {"state": "unavailable", "items": [], "scope": "verified_daemon_and_descendants"}
    indexed = {x["pid"]: x for x in rows if type(x.get("pid")) is int}
    daemon = indexed.get(pid)
    if daemon is None:
        return {"state": "error", "items": [], "scope": "verified_daemon_and_descendants"}
    # The daemon command must identify the requested root; PID alone can be reused.
    cmd = str(daemon.get("command_line") or "")
    root_text = str(root.resolve())
    if os.name == "nt":
        cmd = cmd.casefold().replace("/", "\\")
        root_text = root_text.casefold().replace("/", "\\")
    root_text = root_text.rstrip("/\\")
    # Token boundary prevents accidental ownership of similarly prefixed roots
    # (e.g. v12721 vs v12721_copy). No raw argv escapes this function.
    argv_tokens = [token.strip('"').rstrip("\\")
                   for token in re.findall(r'"[^"]+"|\S+', cmd)]
    if root_text not in argv_tokens:
        return {"state": "error", "items": [], "scope": "verified_daemon_and_descendants"}
    owned = {pid}
    for _ in range(4):
        for item in rows:
            parent = item.get("parent_pid")
            child_id = item.get("pid")
            if type(parent) is not int or type(child_id) is not int or parent not in owned:
                continue
            parent_time, child_time = _date_epoch(indexed[parent].get("created")), _date_epoch(item.get("created"))
            if parent_time is None or child_time is None or child_time < parent_time:
                continue
            owned.add(child_id)
    now = datetime.now(timezone.utc).timestamp()
    result = []
    for process_id in sorted(owned):
        item = indexed.get(process_id)
        if item is None:
            continue
        when = _date_epoch(item.get("created"))
        cpu = item.get("cpu_seconds")
        ram = item.get("ram_bytes")
        result.append({
            "name": "Jaźń — Daemon" if process_id == pid else "Jaźń — Worker",
            "pid": process_id,
            "parent_pid": item.get("parent_pid"),
            "cpu_seconds": round(float(cpu), 2) if isinstance(cpu, (float, int)) else None,
            "ram_mb": round(float(ram) / (1024 * 1024), 1) if isinstance(ram, (float, int)) else None,
            "uptime_seconds": int(max(0, now - when)) if when is not None else None,
            "evidence": "verified_instance" if process_id == pid else "verified_parent_chain",
        })
    return {"state": "available", "items": result, "scope": "verified_daemon_and_descendants",
            "cpu_measure": "cumulative_cpu_seconds"}
