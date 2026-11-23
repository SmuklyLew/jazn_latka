"""Bounded historical generation evidence from operational state, never private MEMORY."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import monitor_workspace

MAX_LEDGER_TAIL = 256 * 1024


def last_ollama_generation(root: Path | None) -> dict[str, Any]:
    unknown: dict[str, Any] = {"state": "unknown", "source": "SourceOriginLedger",
                               "scope": "operational_core_state_only",
                               "accepted_finalization": None}
    if root is None:
        return unknown
    base = monitor_workspace(root)
    path = base / "core_state/memory_runtime/layered/source_origin_ledger_current_line.jsonl"
    if not path.resolve().is_relative_to(base.resolve()):
        return unknown
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            offset = max(0, size - MAX_LEDGER_TAIL)
            stream.seek(offset)
            lines = stream.read(MAX_LEDGER_TAIL).splitlines()
        if offset:
            lines = lines[1:]  # discard possibly partial first record
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(entry, dict) or entry.get("schema_version") != "source_origin_ledger/v1":
                continue
            if entry.get("model_provider") != "ollama":
                continue
            if entry.get("model_candidate_generated") is not True:
                continue
            # Explicit allowlist: no prompt, answer, source excerpts or raw errors.
            out = dict(unknown)
            out.update({"state": "recorded_generation", "historical": True,
                        "candidate_validated": entry.get("model_candidate_validated") is True})
            for key in ("turn_id", "trace_id", "created_at_utc", "model_adapter_id", "model_endpoint_used", "model"):
                value = entry.get(key)
                if isinstance(value, str) and len(value) <= 200 and not any(ord(c) < 32 for c in value):
                    out[key] = value
            return out
    except (OSError, ValueError):
        pass
    return unknown
