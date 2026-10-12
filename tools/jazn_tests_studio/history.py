"""Bounded, redacted Test Studio run history outside SYSTEM and MEMORY."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time
from typing import Any, Mapping
from uuid import uuid4

from latka_jazn.db.runtime_sqlite import runtime_sqlite_write_guard
from latka_jazn.tools.application_shell.operator_paths import (
    operator_file, validate_operator_path,
)

from .core import UI_STATUS, state_dir

HISTORY_SCHEMA = "jazn_tests_studio_run_history/v1"
HISTORY_LIMIT = 100
HISTORY_MAX_BYTES = 262_144
VALID_OUTCOMES = frozenset({"passed", "failed", "error", "cancelled", "timeout"})


class HistoryFormatError(ValueError):
    """Fail-closed history schema, size, or location violation."""


def _history_path(root: Path) -> Path:
    # The leaf must never be a symlink, even to another file inside operator state.
    raw = state_dir(root) / "run_history.json"
    if raw.is_symlink():
        raise HistoryFormatError("Run history must not be a symbolic link.")
    return operator_file("jazn-tests-studio", root, "run_history.json", per_system=True)


def _empty() -> dict[str, Any]:
    return {"schema": HISTORY_SCHEMA, "runs": []}


def load_run_history(root: Path, *, limit: int = HISTORY_LIMIT) -> dict[str, Any]:
    """Load bounded metadata only, without creating any files or running pytest."""
    if not 0 <= limit <= HISTORY_LIMIT:
        raise ValueError("History limit must be between 0 and 100.")
    path = _history_path(Path(root))
    if not path.exists():
        return _empty()
    if not path.is_file() or path.stat().st_size > HISTORY_MAX_BYTES:
        raise HistoryFormatError("Run history is not a supported regular file.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise HistoryFormatError("Run history contains invalid JSON.") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema", "runs"}:
        raise HistoryFormatError("Unsupported run history envelope.")
    if raw["schema"] != HISTORY_SCHEMA or not isinstance(raw["runs"], list):
        raise HistoryFormatError("Unsupported run history schema.")
    runs: list[dict[str, Any]] = []
    allowed = {
        "id", "finished_at_utc", "scope", "outcome", "ok",
        "duration_seconds", "total", "completed", "counts",
    }
    for row in raw["runs"]:
        if not isinstance(row, dict) or set(row) != allowed:
            raise HistoryFormatError("Unsupported run history entry.")
        if row["scope"] not in {"all", "selected"} or row["outcome"] not in VALID_OUTCOMES:
            raise HistoryFormatError("Invalid run history classification.")
        if not isinstance(row["counts"], dict) or set(row["counts"]) != set(UI_STATUS):
            raise HistoryFormatError("Invalid run history status counts.")
        runs.append(row)
    if len(runs) > HISTORY_LIMIT:
        raise HistoryFormatError("Run history exceeds retention cap.")
    return {"schema": HISTORY_SCHEMA, "runs": runs[-limit:] if limit else []}


def record_run_summary(root: Path, result: Mapping[str, Any], *, scope: str) -> dict[str, Any]:
    """Append a safe test outcome: never record stdout, command, nodeids or paths."""
    if scope not in {"selected", "all"}:
        raise ValueError("Invalid run scope.")
    duration = float(result.get("duration_seconds") or 0)
    if not math.isfinite(duration):
        raise ValueError("Non-finite test duration.")
    outcome = str(result.get("outcome", "error"))
    if outcome not in VALID_OUTCOMES:
        outcome = "error"
    counts = result.get("counts")
    counts = counts if isinstance(counts, dict) else {}
    entry = {
        "id": uuid4().hex,
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": scope,
        "outcome": outcome,
        "ok": bool(result.get("ok", False)),
        "duration_seconds": max(0.0, round(duration, 3)),
        "total": max(0, int(result.get("total") or 0)),
        "completed": max(0, int(result.get("completed") or 0)),
        "counts": {key: max(0, int(counts.get(key, 0))) for key in UI_STATUS},
    }
    root = Path(root)
    path = _history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.with_name(path.name + ".runtime-write.lock").is_symlink():
        raise HistoryFormatError("Run history lock must not be a symbolic link.")
    with runtime_sqlite_write_guard(path, timeout_ms=30_000):
        path = _history_path(root)
        records = load_run_history(root)["runs"]
        payload = json.dumps(
            {"schema": HISTORY_SCHEMA, "runs": [*records, entry][-HISTORY_LIMIT:]},
            ensure_ascii=False, indent=2,
        ) + "\n"
        if len(payload.encode("utf-8")) > HISTORY_MAX_BYTES:
            raise HistoryFormatError("Run history exceeds size cap.")
        temp = path.with_suffix(".tmp")
        if temp.exists() or temp.is_symlink():
            raise HistoryFormatError("Run history staging path is occupied.")
        try:
            with temp.open("xb") as out:
                out.write(payload.encode("utf-8"))
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
    return entry


def export_run_history(root: Path, destination: str | Path) -> Path:
    """Explicit, create-only JSON export outside SYSTEM, MEMORY and runtime state."""
    raw = Path(destination).expanduser()
    if not raw.is_absolute() or ".." in raw.parts or raw.suffix.lower() != ".json":
        raise ValueError("Export requires an absolute .json path without traversal.")
    target = validate_operator_path(raw, Path(root))
    if raw.is_symlink() or target.exists():
        raise FileExistsError("Export destination already exists.")
    if not target.parent.is_dir():
        raise ValueError("Export parent directory must already exist.")
    payload = json.dumps(load_run_history(Path(root)), ensure_ascii=False, indent=2) + "\n"
    with target.open("x", encoding="utf-8") as out:
        out.write(payload)
    return target
