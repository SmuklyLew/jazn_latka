from __future__ import annotations

"""Versioned L0 writer shared by every format adapter."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import sqlite3
import uuid

from .intermediate import PreparedSource, canonical_json
from .l0_evidence import persist_record_metadata
from .schema_l0 import L0_SCHEMA_VERSION, ensure_l0_schema_extensions
from .sqlite_utils import ClosingSQLiteConnection


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UnifiedL0Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30, factory=ClosingSQLiteConnection)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def ensure_schema(self, con: sqlite3.Connection | None = None) -> None:
        owns = con is None
        connection = con or self._connect()
        try:
            ensure_l0_schema_extensions(connection)
            connection.execute("INSERT INTO memory_l0_fts(memory_l0_fts) VALUES('rebuild')")
            connection.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('l0_schema_version',?)",
                (L0_SCHEMA_VERSION,),
            )
            if owns:
                connection.commit()
        finally:
            if owns:
                connection.close()

    def ingest(self, prepared: PreparedSource, *, dry_run: bool = False) -> dict[str, Any]:
        now = utc_now()
        source_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"jazn-l0-source:{prepared.adapter_id}:{prepared.source_sha256}:{prepared.source_member or ''}",
        ))
        counters = {"seen": 0, "inserted": 0, "new_revisions": 0, "linked_existing": 0}
        with self._connect() as con:
            self.ensure_schema(con)
            con.commit()
            con.execute("BEGIN IMMEDIATE")
            previous_source = con.execute(
                "SELECT source_id FROM memory_l0_sources WHERE adapter_id=? AND source_sha256=? AND source_member=?",
                (prepared.adapter_id, prepared.source_sha256, prepared.source_member or ""),
            ).fetchone()
            if previous_source is None:
                con.execute(
                    """INSERT INTO memory_l0_sources(
                       source_id,adapter_id,source_kind,source_sha256,source_name,source_member,
                       first_imported_at_utc,last_seen_at_utc,metadata_json
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        source_id, prepared.adapter_id, prepared.source_kind, prepared.source_sha256,
                        prepared.source_name, prepared.source_member or "", now, now,
                        canonical_json(dict(prepared.metadata)),
                    ),
                )
            else:
                source_id = str(previous_source["source_id"])
                con.execute(
                    "UPDATE memory_l0_sources SET last_seen_at_utc=? WHERE source_id=?",
                    (now, source_id),
                )

            for record in prepared.iter_records():
                counters["seen"] += 1
                current = con.execute(
                    """SELECT record_id,revision,content_sha256 FROM memory_l0_records
                       WHERE logical_key=? AND is_current_revision=1""",
                    (record.logical_key,),
                ).fetchone()
                if current is not None and str(current["content_sha256"]) == record.content_sha256:
                    revision = int(current["revision"])
                    counters["linked_existing"] += 1
                    record_id = str(current["record_id"])
                else:
                    revision = int(current["revision"]) + 1 if current is not None else 1
                    if current is not None:
                        con.execute(
                            "UPDATE memory_l0_records SET is_current_revision=0 WHERE record_id=?",
                            (current["record_id"],),
                        )
                        counters["new_revisions"] += 1
                    else:
                        counters["inserted"] += 1
                    record_id = str(uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"jazn-l0-record:{record.logical_key}:{revision}:{record.content_sha256}",
                    ))
                    provenance = {
                        "adapter_id": prepared.adapter_id,
                        "source_id": source_id,
                        "source_sha256": prepared.source_sha256,
                        "source_name": prepared.source_name,
                        "source_member": prepared.source_member,
                        **dict(record.provenance),
                    }
                    con.execute(
                        """INSERT INTO memory_l0_records(
                           record_id,logical_key,revision,source_id,source_record_id,source_kind,
                           record_kind,title,content,content_sha256,event_time_start,event_time_end,
                           timestamp_status,conversation_id,role,truth_status,importance,raw_json,
                           provenance_json,created_at_utc,is_current_revision
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                        (
                            record_id, record.logical_key, revision, source_id, record.source_record_id,
                            prepared.source_kind, record.record_kind, record.title, record.content,
                            record.content_sha256, record.event_time_start, record.event_time_end,
                            record.timestamp_status, record.conversation_id, record.role,
                            record.truth_status, float(record.importance), canonical_json(dict(record.raw)),
                            canonical_json(provenance), now,
                        ),
                    )
                persist_record_metadata(
                    con,
                    record_id=record_id,
                    source_id=source_id,
                    raw=record.raw,
                    observed_at_utc=now,
                )
                con.execute(
                    """INSERT OR IGNORE INTO memory_l0_occurrences(
                       logical_key,revision,source_id,source_record_id,seen_at_utc
                       ) VALUES(?,?,?,?,?)""",
                    (record.logical_key, revision, source_id, record.source_record_id, now),
                )

            if dry_run:
                con.rollback()
            else:
                con.commit()
        return {
            "ok": True,
            "status": "planned" if dry_run else "imported",
            "adapter_id": prepared.adapter_id,
            "source_kind": prepared.source_kind,
            "source_sha256": prepared.source_sha256,
            "source_name": prepared.source_name,
            "schema_version": L0_SCHEMA_VERSION,
            "visibility_classification": True,
            "attachment_catalog": True,
            **counters,
            "automatic_l2": False,
            "automatic_l3": False,
            "automatic_activation": False,
        }

    def store_embedding(self, record_id: str, model_id: str, vector: bytes, dimensions: int) -> None:
        if dimensions < 1 or not vector:
            raise ValueError("Embedding wymaga dodatniego wymiaru i niepustego wektora.")
        with self._connect() as con:
            self.ensure_schema(con)
            con.execute(
                """INSERT OR REPLACE INTO memory_l0_embeddings(
                   record_id,model_id,dimensions,vector_blob,vector_sha256,created_at_utc
                   ) VALUES(?,?,?,?,?,?)""",
                (
                    record_id, model_id, dimensions, sqlite3.Binary(vector),
                    hashlib.sha256(vector).hexdigest(), utc_now(),
                ),
            )
            con.commit()


__all__ = ["UnifiedL0Store"]
