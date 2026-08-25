from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator
import sqlite3

from ..intermediate import IntermediateRecord, PreparedSource, sha256_file
from ..settings import MemoryRebuildSettings
from ..source_detection import SourceProbe
from ..sqlite_utils import ClosingSQLiteConnection
from .common import iso_from_epoch


TABLE_SPECS: dict[str, dict[str, tuple[str, ...] | str]] = {
    "nodes": {
        "content": ("text",), "title": (), "key": ("message_id", "node_id"),
        "event": ("create_time",), "kind": "conversation_message",
    },
    "journal_entries": {
        "content": ("content", "summary"), "title": ("title",), "key": ("identity_key", "entry_id"),
        "event": ("event_time_start",), "kind": "journal_entry",
    },
    "experiences": {
        "content": ("summary",), "title": ("title",), "key": ("identity_key", "experience_id"),
        "event": ("updated_at_utc", "created_at_utc"), "kind": "experience",
    },
    "memory_records": {
        "content": ("content",), "title": (), "key": ("memory_id",),
        "event": ("updated_at_utc", "created_at_utc"), "kind": "active_memory_snapshot",
    },
    "runtime_memory_records_l0": {
        "content": ("content",), "title": (), "key": ("source_record_key", "record_id"),
        "event": ("event_time", "imported_at_utc"), "kind": "runtime_l0_record",
    },
}


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _first(row: sqlite3.Row, names: tuple[str, ...]) -> Any:
    keys = set(row.keys())
    for name in names:
        if name in keys and row[name] not in (None, ""):
            return row[name]
    return None


def _records(path: Path) -> Iterator[IntermediateRecord]:
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30, factory=ClosingSQLiteConnection) as con:
        con.row_factory = sqlite3.Row
        tables = {
            str(row[0]) for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        for table, spec in TABLE_SPECS.items():
            if table not in tables:
                continue
            for ordinal, row in enumerate(con.execute(f"SELECT * FROM {_quote(table)}"), start=1):
                content = str(_first(row, spec["content"]) or "").strip()  # type: ignore[arg-type]
                if not content:
                    continue
                key = str(_first(row, spec["key"]) or ordinal).strip()  # type: ignore[arg-type]
                event_raw = _first(row, spec["event"])  # type: ignore[arg-type]
                event = iso_from_epoch(event_raw)
                title = str(_first(row, spec["title"]) or "").strip()  # type: ignore[arg-type]
                raw = {name: row[name] for name in row.keys()}
                conversation_id = str(row["conversation_id"]) if "conversation_id" in row.keys() else None
                role = str(row["role"]) if "role" in row.keys() and row["role"] else None
                truth = str(row["truth_status"]) if "truth_status" in row.keys() else "source_recorded"
                yield IntermediateRecord(
                    logical_key=f"legacy:{table}:{key}",
                    source_record_id=key,
                    record_kind=str(spec["kind"]),
                    title=title,
                    content=content,
                    event_time_start=event,
                    event_time_end=event,
                    timestamp_status="source_recorded" if event else "missing",
                    conversation_id=conversation_id,
                    role=role,
                    truth_status=truth,
                    importance=0.5,
                    raw=raw,
                    provenance={"legacy_table": table, "legacy_key": key},
                )


class LegacySqliteAdapter:
    adapter_id = "legacy-sqlite/v16.1"

    def supports(self, path: Path, probe: SourceProbe) -> bool:
        return probe.kind == "legacy_sqlite" and path.suffix.casefold() in {".sqlite", ".sqlite3", ".db"}

    def prepare(
        self, path: Path, probe: SourceProbe, settings: MemoryRebuildSettings,
    ) -> PreparedSource:
        del probe, settings
        return PreparedSource(
            adapter_id=self.adapter_id,
            source_kind="legacy_sqlite",
            source_sha256=sha256_file(path),
            source_name=path.name,
            source_member=None,
            metadata={"mode": "read_only_legacy_projection"},
            record_factory=lambda: _records(path),
            native_projection="legacy_sqlite",
        )


__all__ = ["LegacySqliteAdapter", "TABLE_SPECS"]
