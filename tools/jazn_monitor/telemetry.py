"""Read-only, bounded process/job/finalization telemetry for Jaźń Monitor.

Only a matching live daemon instance is considered an owned runtime process.
No user prompts, model outputs, raw command lines or private MEMORY are emitted.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from typing import Any

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
    db = root / "workspace_runtime" / "core_state" / "memory_runtime" / "sqlite" / "runtime_write_v1" / "runtime_audit.sqlite3"
    if db.is_symlink() or not db.is_file():
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
                "execution_timeout_total", "pending")
        counts = {key: summary.get(key) if type(summary.get(key)) is int
                  and summary[key] >= 0 else None for key in keys}
    data = _read_json(root / "workspace_runtime" / "daemon_chat_jobs.json", MAX_JOB_JSON)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        out = dict(unavailable)
        out["counts"] = counts
        out["state"] = "unavailable"
        return out
    raw_jobs = data["jobs"][-MAX_VISIBLE_JOBS:]
    items = []
    for entry in raw_jobs:
        if not isinstance(entry, dict):
            continue
        state = entry.get("status") if entry.get("status") in (
            "pending", "running", "completed", "failed", "cancelled", "rejected"
        ) else "unknown"
        req = entry.get("request_id")
        if not isinstance(req, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", req):
            continue
        items.append({
            "request_id": req,
            "state": state,
            "duration_seconds": _elapsed(entry.get("started_at_utc") or entry.get("created_at_utc"),
                                         entry.get("completed_at_utc")),
            "error_code": _safe_code(entry.get("result_error_code"))
                          or _safe_code(entry.get("error")),
            "reason_code": None,
            "created_at_utc": entry.get("created_at_utc") if isinstance(entry.get("created_at_utc"), str) else None,
        })
    rejected_ids = {item["request_id"] for item in items if item["state"] in ("failed", "rejected")}
    reasons = _audit_reasons(root, rejected_ids)
    for item in items:
        item["reason_code"] = reasons.get(item["request_id"])
    last = (summary.get("last_terminal_job")
            if isinstance(summary, dict) and isinstance(summary.get("last_terminal_job"), dict)
            else None)
    last = last or (data["jobs"][-1] if data["jobs"] and isinstance(data["jobs"][-1], dict) else None)
    finalization: dict[str, Any] = {"state": "unknown", "reason_code": None,
                                    "error_code": None, "request_id": None}
    if isinstance(last, dict):
        status = last.get("job_status", last.get("status"))
        last_id = last.get("request_id")
        if isinstance(last_id, str) and re.fullmatch(r"[a-zA-Z0-9-]{1,64}", last_id):
            finalization["request_id"] = last_id
            finalization["error_code"] = _safe_code(last.get("error_code")) or _safe_code(last.get("result_error_code"))
            finalization["reason_code"] = reasons.get(last_id)
        if status in ("failed", "rejected", "cancelled"):
            finalization["state"] = "rejected"
        elif status == "completed":
            finalization["state"] = "completed_job"
        elif status in ("pending", "running"):
            finalization["state"] = "pending"
    return {"state": "available", "counts": counts, "items": items, "finalization": finalization,
            "scope": "daemon_recovery_metadata_only"}


def _windows_process_rows() -> list[dict[str, Any]] | None:
    """WMI probe is bounded; never send raw CommandLine to UI or logs."""
    if os.name != "nt":
        return None
    script = (
        "$ErrorActionPreference='Stop'; "
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
    if rows is None:
        return {"state": "unavailable", "items": [], "scope": "verified_daemon_and_descendants"}
    indexed = {x["pid"]: x for x in rows if type(x.get("pid")) is int}
    daemon = indexed.get(pid)
    if daemon is None:
        return {"state": "error", "items": [], "scope": "verified_daemon_and_descendants"}
    # The daemon command must identify the requested root; PID alone can be reused.
    cmd = str(daemon.get("command_line") or "").casefold().replace("/", "\\")
    root_text = str(root.resolve()).casefold().replace("/", "\\")
    if root_text not in cmd:
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
