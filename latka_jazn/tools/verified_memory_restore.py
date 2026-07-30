from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Iterable, Sequence
from urllib.parse import quote
import uuid
import zlib


SCHEMA_VERSION = "jazn_verified_memory_restore/v1"
L2_DRAFT_SCHEMA = "jazn_verified_memory_restore_l2_draft/v1"
L2_MANIFEST_SCHEMA = "jazn_verified_memory_restore_l2_manifest/v1"
TRUTH_BOUNDARY = (
    "Narzędzie odtwarza źródłowe archiwum runtime i przygotowuje kontrolowane L1/L2/L3. "
    "Test 04, integralność SQLite, wake-state ani obecność danych nie dowodzą aktywnej Jaźni. "
    "L2 wymaga ręcznej decyzji dla każdego kandydata. L3 wymaga dokładnego SHA manifestu "
    "i jawnego zatwierdzającego. Daemon może zostać uruchomiony dopiero po końcowym doctor."
)
REQUIRED_TEST04_DATABASES = {
    "archive_chats": "archive_chats.sqlite3",
    "journal": "journal.sqlite3",
    "memory_jazn": "memory_jazn.sqlite3",
    "experience": "experience.sqlite3",
    "import_catalog": "import_catalog.sqlite3",
}
TEST04_REQUIRED_PASSES = (
    "structural_integrity",
    "source_completeness",
    "same_target_idempotence",
    "fresh_rebuild_reproducibility",
    "test03_reconciliation",
    "recall",
    "multi_turn_review",
)
DEFAULT_HARD_LIMIT_BYTES = 480 * 1024 * 1024


class VerifiedMemoryRestoreError(RuntimeError):
    """Kontrolowany błąd ścieżki przywracania pamięci."""


@dataclass(slots=True)
class PhaseReport:
    schema_version: str
    status: str
    phase: str
    root: str
    run_dir: str | None
    details: dict[str, Any]
    errors: list[str]
    truth_boundary: str = TRUTH_BOUNDARY

    @property
    def ok(self) -> bool:
        return self.status in {
            "validated",
            "staged",
            "ready_for_l2_review",
            "l2_manifest_sealed",
            "l2_applied_l3_manifest_ready",
            "active_trusted",
        }

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ok": self.ok}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_text(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{uuid.uuid4().hex}")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    return path


def _atomic_json(path: Path, value: Any) -> Path:
    return _atomic_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerifiedMemoryRestoreError(f"Nie można odczytać JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VerifiedMemoryRestoreError(f"JSON nie jest obiektem: {path}")
    return payload


def _utc_from_epoch(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        text = str(value).strip()
        return text or None


def _sqlite_health(path: Path, *, full: bool = True, hash_file: bool = True) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ok": False,
            "path": str(path),
            "exists": False,
            "integrity_check": None,
            "foreign_key_error_count": None,
            "sha256": None,
            "errors": ["database_missing"],
        }
    errors: list[str] = []
    integrity: str | None = None
    foreign_rows: list[tuple[Any, ...]] = []
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=30.0)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            pragma = "integrity_check" if full else "quick_check"
            integrity = str(connection.execute(f"PRAGMA {pragma}").fetchone()[0])
            foreign_rows = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        finally:
            connection.close()
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return {
        "ok": not errors and integrity == "ok" and not foreign_rows,
        "path": str(path),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "integrity_check": integrity,
        "foreign_key_error_count": len(foreign_rows),
        "foreign_key_errors": foreign_rows[:50],
        "sha256": _sha256_file(path) if hash_file and path.is_file() else None,
        "errors": errors,
    }


def _database_paths(test04_root: Path) -> dict[str, Path]:
    sqlite_root = test04_root / "memory" / "sqlite"
    return {
        role: sqlite_root / filename
        for role, filename in REQUIRED_TEST04_DATABASES.items()
    }


def validate_test04_summary(summary_path: Path) -> dict[str, Any]:
    summary = _load_json(summary_path)
    if summary.get("schema_version") != "jazn_memory_sqlite_test04/v1":
        raise VerifiedMemoryRestoreError(
            f"Nieobsługiwany schemat raportu Testu 04: {summary.get('schema_version')!r}"
        )
    final = summary.get("final")
    if not isinstance(final, dict):
        raise VerifiedMemoryRestoreError("Raport Testu 04 nie zawiera obiektu final.")
    failed = {
        field: final.get(field)
        for field in TEST04_REQUIRED_PASSES
        if final.get(field) != "passed"
    }
    html_status = final.get("html_import_dry_run", "not_applicable")
    if html_status not in {"passed", "not_applicable"}:
        failed["html_import_dry_run"] = html_status
    if int(summary.get("error_count") or 0) != 0:
        failed["error_count"] = summary.get("error_count")
    if summary.get("system_activation_performed") is not False:
        failed["system_activation_performed"] = summary.get("system_activation_performed")
    if final.get("system_activation_ready") is not False:
        failed["system_activation_ready"] = final.get("system_activation_ready")
    if failed:
        raise VerifiedMemoryRestoreError(
            "Test 04 nie spełnia kontraktu wejściowego: " + _canonical_json(failed)
        )
    return {
        "ok": True,
        "path": str(summary_path),
        "sha256": _sha256_file(summary_path),
        "final": final,
        "error_count": 0,
        "system_activation_performed": False,
    }


def validate_test04_databases(test04_root: Path) -> dict[str, Any]:
    paths = _database_paths(test04_root)
    reports = {role: _sqlite_health(path, full=True) for role, path in paths.items()}
    failures = {role: report for role, report in reports.items() if not report["ok"]}
    if failures:
        raise VerifiedMemoryRestoreError(
            "Walidacja baz Testu 04 nie przeszła: "
            + _canonical_json({role: report.get("errors") or report for role, report in failures.items()})
        )

    archive_path = paths["archive_chats"]
    journal_path = paths["journal"]
    with sqlite3.connect(f"file:{archive_path.resolve().as_posix()}?mode=ro", uri=True) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        required = {"import_sources", "conversations", "nodes", "conversation_occurrences"}
        missing = sorted(required - tables)
        if missing:
            raise VerifiedMemoryRestoreError(f"archive_chats.sqlite3 nie ma tabel: {missing}")
        counts = {
            "sources": int(connection.execute("SELECT COUNT(*) FROM import_sources").fetchone()[0]),
            "conversations": int(connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]),
            "nodes": int(connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]),
        }
    with sqlite3.connect(f"file:{journal_path.resolve().as_posix()}?mode=ro", uri=True) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")
        }
        if "journal_entries" not in tables:
            raise VerifiedMemoryRestoreError("journal.sqlite3 nie ma tabeli journal_entries.")
        counts["journal_entries"] = int(
            connection.execute("SELECT COUNT(*) FROM journal_entries WHERE status='active'").fetchone()[0]
        )
    if counts["sources"] <= 0 or counts["conversations"] <= 0 or counts["nodes"] <= 0:
        raise VerifiedMemoryRestoreError(f"Test 04 ma puste wymagane dane: {counts}")
    if counts["journal_entries"] <= 0:
        raise VerifiedMemoryRestoreError("Test 04 nie zawiera aktywnych wpisów dziennika.")
    return {
        "ok": True,
        "root": str(test04_root),
        "databases": reports,
        "counts": counts,
    }


ARCHIVE_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE archive_conversations(
  conversation_uid TEXT PRIMARY KEY,
  source_uid TEXT,
  conversation_index INTEGER NOT NULL,
  source_conversation_id TEXT,
  title TEXT,
  create_time TEXT,
  update_time TEXT,
  source_format TEXT NOT NULL,
  current_node TEXT,
  visible_node_count INTEGER NOT NULL,
  source_node_count INTEGER NOT NULL,
  message_count INTEGER NOT NULL,
  occurrence_count INTEGER NOT NULL
);
CREATE TABLE archive_conversation_occurrences(
  occurrence_uid TEXT PRIMARY KEY,
  conversation_uid TEXT NOT NULL,
  source_uid TEXT NOT NULL,
  relation_to_active TEXT,
  source_locator TEXT,
  observed_at_utc TEXT,
  FOREIGN KEY(conversation_uid) REFERENCES archive_conversations(conversation_uid)
);
CREATE TABLE content_blobs(
  content_hash TEXT PRIMARY KEY,
  normalized_hash TEXT NOT NULL,
  text TEXT NOT NULL,
  char_count INTEGER NOT NULL,
  byte_count INTEGER NOT NULL,
  first_occurrence_uid TEXT,
  first_source_uid TEXT,
  created_at_utc TEXT
);
CREATE TABLE archive_messages(
  message_uid TEXT PRIMARY KEY,
  conversation_uid TEXT NOT NULL,
  source_message_id TEXT,
  node_id TEXT,
  parent_node_id TEXT,
  role TEXT,
  author_label TEXT,
  model_slug TEXT,
  default_model_slug TEXT,
  content_type TEXT,
  create_time TEXT,
  is_visible_path INTEGER NOT NULL,
  visible_index INTEGER,
  content_hash TEXT NOT NULL,
  content_shard_id TEXT NOT NULL,
  normalized_hash TEXT NOT NULL,
  logical_hash TEXT NOT NULL,
  text_length INTEGER NOT NULL,
  first_source_uid TEXT,
  first_occurrence_uid TEXT,
  occurrence_count INTEGER NOT NULL,
  FOREIGN KEY(conversation_uid) REFERENCES archive_conversations(conversation_uid),
  FOREIGN KEY(content_hash) REFERENCES content_blobs(content_hash)
);
CREATE INDEX idx_archive_messages_conversation
  ON archive_messages(conversation_uid,is_visible_path,visible_index,message_uid);
CREATE INDEX idx_archive_messages_role ON archive_messages(role,create_time);
CREATE TABLE archive_message_occurrences(
  occurrence_uid TEXT PRIMARY KEY,
  message_uid TEXT NOT NULL,
  conversation_uid TEXT NOT NULL,
  source_uid TEXT NOT NULL,
  source_conversation_id TEXT,
  source_message_id TEXT,
  node_id TEXT,
  parent_node_id TEXT,
  conversation_index INTEGER NOT NULL,
  message_index INTEGER NOT NULL,
  source_order INTEGER NOT NULL,
  is_visible_path INTEGER NOT NULL,
  visible_index INTEGER,
  source_locator TEXT,
  occurrence_hash TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  FOREIGN KEY(message_uid) REFERENCES archive_messages(message_uid),
  FOREIGN KEY(conversation_uid) REFERENCES archive_conversations(conversation_uid),
  FOREIGN KEY(content_hash) REFERENCES content_blobs(content_hash)
);
CREATE INDEX idx_archive_occurrences_source
  ON archive_message_occurrences(source_uid,conversation_index,message_index);
"""

STAGING_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE staging_memory_entries(
  staging_uid TEXT PRIMARY KEY,
  archive_message_uid TEXT NOT NULL,
  archive_occurrence_uid TEXT NOT NULL,
  conversation_uid TEXT NOT NULL,
  source_uid TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  role TEXT,
  title TEXT,
  create_time TEXT,
  memory_namespace TEXT NOT NULL,
  privacy_scope TEXT NOT NULL,
  identity_confidence REAL NOT NULL,
  review_status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL
);
CREATE INDEX idx_staging_conversation ON staging_memory_entries(conversation_uid,create_time);
"""

FTS_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE fts_docs(
  rowid INTEGER PRIMARY KEY AUTOINCREMENT,
  fts_doc_uid TEXT NOT NULL UNIQUE,
  archive_message_uid TEXT NOT NULL,
  archive_occurrence_uid TEXT NOT NULL,
  staging_uid TEXT NOT NULL,
  conversation_uid TEXT NOT NULL,
  source_uid TEXT NOT NULL,
  role TEXT,
  title TEXT,
  create_time TEXT,
  content_hash TEXT NOT NULL
);
CREATE VIRTUAL TABLE message_fts USING fts5(
  text,
  content='',
  tokenize='unicode61 remove_diacritics 2'
);
"""

MANIFEST_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE manifest_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE archive_sources(
  source_uid TEXT PRIMARY KEY,
  path TEXT,
  source_name TEXT,
  sha256 TEXT,
  size_bytes INTEGER,
  imported_at_utc TEXT,
  parser_version TEXT,
  source_kind TEXT
);
CREATE TABLE shard_files(
  shard_id TEXT PRIMARY KEY,
  family TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  relative_path TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL,
  size_mib REAL NOT NULL,
  sha256 TEXT NOT NULL,
  integrity_check TEXT NOT NULL,
  foreign_key_error_count INTEGER NOT NULL,
  hard_limit_bytes INTEGER NOT NULL,
  over_limit INTEGER NOT NULL,
  created_at_utc TEXT NOT NULL
);
CREATE TABLE conversation_locations(
  conversation_uid TEXT PRIMARY KEY,
  shard_id TEXT NOT NULL
);
CREATE TABLE conversation_occurrence_locations(
  occurrence_uid TEXT PRIMARY KEY,
  conversation_uid TEXT NOT NULL,
  source_uid TEXT NOT NULL,
  shard_id TEXT NOT NULL
);
CREATE TABLE message_locations(
  message_uid TEXT PRIMARY KEY,
  shard_id TEXT NOT NULL
);
CREATE TABLE occurrence_locations(
  occurrence_uid TEXT PRIMARY KEY,
  shard_id TEXT NOT NULL
);
CREATE TABLE content_locations(
  content_hash TEXT PRIMARY KEY,
  shard_id TEXT NOT NULL
);
CREATE TABLE staging_locations(
  staging_uid TEXT PRIMARY KEY,
  shard_id TEXT NOT NULL
);
CREATE TABLE fts_locations(
  fts_doc_uid TEXT PRIMARY KEY,
  shard_id TEXT NOT NULL
);
"""


class RuntimeArchiveConverter:
    """Convert the active Memory Rebuild snapshot into the current runtime archive layout."""

    def __init__(self, test04_root: Path, output_root: Path) -> None:
        self.test04_root = test04_root.expanduser().resolve()
        self.output_root = output_root.expanduser().resolve()
        self.source_archive = _database_paths(self.test04_root)["archive_chats"]
        self.source_journal = _database_paths(self.test04_root)["journal"]
        self.archive_dir = self.output_root / "memory" / "sqlite" / "conversation_archive_v1"
        self.fts_dir = self.output_root / "memory" / "sqlite" / "conversation_fts_v1"
        self.staging_dir = self.output_root / "memory" / "sqlite" / "staging_v1"
        self.raw_dir = self.output_root / "memory" / "raw"
        self.archive_path = self.archive_dir / "conversation_archive_0001.sqlite3"
        self.manifest_path = self.archive_dir / "conversation_archive_manifest.sqlite3"
        self.fts_path = self.fts_dir / "conversation_fts_0001.sqlite3"
        self.staging_path = self.staging_dir / "staging_memory_0001.sqlite3"
        self.journal_path = self.raw_dir / "dziennik.json"

    @staticmethod
    def _stable_id(prefix: str, *parts: Any) -> str:
        raw = "|".join([prefix, *(str(part or "") for part in parts)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalized_hash(text: str) -> str:
        normalized = " ".join(text.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _payload(row: sqlite3.Row) -> dict[str, Any]:
        codec = str(row["payload_codec"] or "")
        blob = bytes(row["payload_blob"])
        if codec == "zlib-json-v1":
            raw = zlib.decompress(blob)
        elif codec in {"json", "json-v1", "plain-json"}:
            raw = blob
        else:
            raise VerifiedMemoryRestoreError(
                f"Nieobsługiwany payload_codec dla {row['conversation_id']}: {codec}"
            )
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise VerifiedMemoryRestoreError(
                f"Payload rozmowy nie jest obiektem: {row['conversation_id']}"
            )
        return payload

    def build(self) -> dict[str, Any]:
        validate_test04_databases(self.test04_root)
        if self.output_root.exists() and any(self.output_root.iterdir()):
            raise VerifiedMemoryRestoreError(
                f"Katalog staging musi być pusty: {self.output_root}"
            )
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.fts_dir.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

        from latka_jazn.tools.chat_export_reader import build_conversation_graph

        source = sqlite3.connect(
            f"file:{self.source_archive.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=30.0,
        )
        source.row_factory = sqlite3.Row
        archive = sqlite3.connect(self.archive_path)
        archive.row_factory = sqlite3.Row
        staging = sqlite3.connect(self.staging_path)
        fts = sqlite3.connect(self.fts_path)
        counts = {
            "sources": 0,
            "conversations": 0,
            "conversation_occurrences": 0,
            "messages": 0,
            "message_occurrences": 0,
            "content_blobs": 0,
            "staging": 0,
            "fts": 0,
            "fts_nul_replacements": 0,
        }
        source_rows: list[dict[str, Any]] = []
        manifest_rows: dict[str, list[tuple[Any, ...]]] = {
            "conversation_locations": [],
            "conversation_occurrence_locations": [],
            "message_locations": [],
            "occurrence_locations": [],
            "content_locations": [],
            "staging_locations": [],
            "fts_locations": [],
        }
        try:
            source.execute("PRAGMA query_only=ON")
            archive.executescript(ARCHIVE_SCHEMA)
            staging.executescript(STAGING_SCHEMA)
            fts.executescript(FTS_SCHEMA)
            archive.execute("PRAGMA synchronous=FULL")
            staging.execute("PRAGMA synchronous=FULL")
            fts.execute("PRAGMA synchronous=FULL")

            source_rows = [
                dict(row)
                for row in source.execute(
                    """SELECT import_id,sha256,source_name,source_path,size_bytes,
                              COALESCE(completed_at_utc,started_at_utc) AS imported_at_utc,
                              status
                         FROM import_sources
                        WHERE status='completed'
                        ORDER BY started_at_utc,import_id"""
                )
            ]
            source_order = {
                str(row["import_id"]): index
                for index, row in enumerate(source_rows, start=1)
            }
            counts["sources"] = len(source_rows)
            if not source_rows:
                raise VerifiedMemoryRestoreError("archive_chats.sqlite3 nie ma ukończonych źródeł.")

            node_source_rows = source.execute(
                """SELECT conversation_id,node_id,first_seen_import_id,last_seen_import_id,
                          role,create_time,timestamp_status,content_type,message_id,parent_node_id,
                          on_current_path,structural_ordinal
                     FROM nodes"""
            ).fetchall()
            node_sources = {
                (str(row["conversation_id"]), str(row["node_id"])): dict(row)
                for row in node_source_rows
            }
            occurrence_by_conversation: dict[str, list[dict[str, Any]]] = {}
            for row in source.execute(
                """SELECT conversation_id,import_id,relation_to_active,observed_at_utc
                     FROM conversation_occurrences
                    ORDER BY conversation_id,observed_at_utc,import_id"""
            ):
                occurrence_by_conversation.setdefault(
                    str(row["conversation_id"]), []
                ).append(dict(row))

            conversations = source.execute(
                """SELECT conversation_id,title,create_time,update_time,current_node_id,
                          payload_codec,payload_blob,node_count,message_count,
                          first_seen_import_id,last_seen_import_id
                     FROM conversations
                    ORDER BY COALESCE(create_time,0),conversation_id"""
            )
            for conversation_index, row in enumerate(conversations, start=1):
                payload = self._payload(row)
                graph = build_conversation_graph(payload)
                conversation_uid = str(row["conversation_id"])
                if graph.conversation_id != conversation_uid:
                    raise VerifiedMemoryRestoreError(
                        f"Niezgodne ID rozmowy: DB={conversation_uid}, payload={graph.conversation_id}"
                    )
                source_uid = str(row["first_seen_import_id"] or row["last_seen_import_id"] or "")
                if source_uid not in source_order:
                    source_uid = str(source_rows[0]["import_id"])
                occurrence_rows = occurrence_by_conversation.get(conversation_uid) or [
                    {
                        "import_id": source_uid,
                        "relation_to_active": "active_snapshot",
                        "observed_at_utc": _now(),
                    }
                ]
                visible_index_by_node = {
                    node_id: index
                    for index, node_id in enumerate(graph.current_path, start=1)
                }
                message_nodes = [
                    node for node in graph.nodes
                    if node.message_id and node.text.strip()
                ]
                archive.execute(
                    """INSERT INTO archive_conversations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        conversation_uid,
                        source_uid,
                        conversation_index,
                        conversation_uid,
                        graph.title,
                        _utc_from_epoch(graph.create_time),
                        _utc_from_epoch(graph.update_time),
                        "memory_rebuild_active_snapshot/v24",
                        graph.current_node_id,
                        len(graph.current_path),
                        graph.node_count,
                        len(message_nodes),
                        len(occurrence_rows),
                    ),
                )
                counts["conversations"] += 1
                manifest_rows["conversation_locations"].append(
                    (conversation_uid, "archive_0001")
                )

                for conv_occurrence in occurrence_rows:
                    conv_source_uid = str(conv_occurrence.get("import_id") or source_uid)
                    conv_occurrence_uid = self._stable_id(
                        "conversation-occurrence", conversation_uid, conv_source_uid
                    )
                    source_info = next(
                        (
                            item for item in source_rows
                            if str(item["import_id"]) == conv_source_uid
                        ),
                        None,
                    )
                    source_path = str((source_info or {}).get("source_path") or "")
                    locator = (
                        f"{source_path}#conversation={quote(conversation_uid)}"
                        if source_path
                        else f"archive_chats.sqlite3#conversation={quote(conversation_uid)}"
                    )
                    archive.execute(
                        """INSERT INTO archive_conversation_occurrences
                           VALUES(?,?,?,?,?,?)""",
                        (
                            conv_occurrence_uid,
                            conversation_uid,
                            conv_source_uid,
                            conv_occurrence.get("relation_to_active"),
                            locator,
                            conv_occurrence.get("observed_at_utc"),
                        ),
                    )
                    manifest_rows["conversation_occurrence_locations"].append(
                        (
                            conv_occurrence_uid,
                            conversation_uid,
                            conv_source_uid,
                            "archive_0001",
                        )
                    )
                    counts["conversation_occurrences"] += 1

                for message_index, node in enumerate(message_nodes, start=1):
                    meta = node_sources.get((conversation_uid, node.node_id), {})
                    message_source_uid = str(
                        meta.get("first_seen_import_id")
                        or meta.get("last_seen_import_id")
                        or source_uid
                    )
                    if message_source_uid not in source_order:
                        message_source_uid = source_uid
                    text = node.text
                    content_hash = node.text_sha256 or _sha256_text(text)
                    normalized_hash = self._normalized_hash(text)
                    logical_hash = self._stable_id(
                        "logical-message",
                        conversation_uid,
                        node.role,
                        normalized_hash,
                    )
                    message_uid = self._stable_id(
                        "archive-message",
                        conversation_uid,
                        node.node_id,
                        node.message_id,
                        content_hash,
                    )
                    occurrence_uid = self._stable_id(
                        "archive-occurrence",
                        message_uid,
                        message_source_uid,
                        node.node_id,
                    )
                    staging_uid = self._stable_id("staging", occurrence_uid)
                    fts_doc_uid = self._stable_id("fts", staging_uid)
                    visible_index = visible_index_by_node.get(node.node_id)
                    is_visible = int(bool(node.on_current_path))
                    source_info = next(
                        (
                            item for item in source_rows
                            if str(item["import_id"]) == message_source_uid
                        ),
                        None,
                    )
                    source_path = str((source_info or {}).get("source_path") or "")
                    source_locator = (
                        f"{source_path}#conversation={quote(conversation_uid)}&node={quote(node.node_id)}"
                        if source_path
                        else (
                            "archive_chats.sqlite3"
                            f"#conversation={quote(conversation_uid)}&node={quote(node.node_id)}"
                        )
                    )
                    if archive.execute(
                        "SELECT 1 FROM content_blobs WHERE content_hash=?",
                        (content_hash,),
                    ).fetchone() is None:
                        archive.execute(
                            """INSERT INTO content_blobs VALUES(?,?,?,?,?,?,?,?)""",
                            (
                                content_hash,
                                normalized_hash,
                                text,
                                len(text),
                                len(text.encode("utf-8")),
                                occurrence_uid,
                                message_source_uid,
                                _now(),
                            ),
                        )
                        manifest_rows["content_locations"].append(
                            (content_hash, "archive_0001")
                        )
                        counts["content_blobs"] += 1
                    archive.execute(
                        """INSERT INTO archive_messages VALUES(
                           ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            message_uid,
                            conversation_uid,
                            node.message_id,
                            node.node_id,
                            node.parent_node_id,
                            node.role,
                            node.role,
                            None,
                            None,
                            node.content_type,
                            _utc_from_epoch(node.create_time),
                            is_visible,
                            visible_index,
                            content_hash,
                            "archive_0001",
                            normalized_hash,
                            logical_hash,
                            len(text),
                            message_source_uid,
                            occurrence_uid,
                            1,
                        ),
                    )
                    archive.execute(
                        """INSERT INTO archive_message_occurrences VALUES(
                           ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            occurrence_uid,
                            message_uid,
                            conversation_uid,
                            message_source_uid,
                            conversation_uid,
                            node.message_id,
                            node.node_id,
                            node.parent_node_id,
                            conversation_index,
                            message_index,
                            int(source_order.get(message_source_uid, 1)),
                            is_visible,
                            visible_index,
                            source_locator,
                            self._stable_id(
                                "occurrence-hash",
                                occurrence_uid,
                                source_locator,
                                content_hash,
                            ),
                            content_hash,
                        ),
                    )
                    staging.execute(
                        """INSERT INTO staging_memory_entries VALUES(
                           ?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            staging_uid,
                            message_uid,
                            occurrence_uid,
                            conversation_uid,
                            message_source_uid,
                            content_hash,
                            node.role,
                            graph.title,
                            _utc_from_epoch(node.create_time),
                            "source_archive",
                            "personal",
                            0.0,
                            "unreviewed",
                            _now(),
                        ),
                    )
                    fts_text = text.replace("\x00", "\uFFFD")
                    if fts_text != text:
                        counts["fts_nul_replacements"] += 1
                    cursor = fts.execute(
                        """INSERT INTO fts_docs(
                           fts_doc_uid,archive_message_uid,archive_occurrence_uid,
                           staging_uid,conversation_uid,source_uid,role,title,
                           create_time,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            fts_doc_uid,
                            message_uid,
                            occurrence_uid,
                            staging_uid,
                            conversation_uid,
                            message_source_uid,
                            node.role,
                            graph.title,
                            _utc_from_epoch(node.create_time),
                            content_hash,
                        ),
                    )
                    fts.execute(
                        "INSERT INTO message_fts(rowid,text) VALUES(?,?)",
                        (cursor.lastrowid, fts_text),
                    )
                    manifest_rows["message_locations"].append(
                        (message_uid, "archive_0001")
                    )
                    manifest_rows["occurrence_locations"].append(
                        (occurrence_uid, "archive_0001")
                    )
                    manifest_rows["staging_locations"].append(
                        (staging_uid, "staging_0001")
                    )
                    manifest_rows["fts_locations"].append(
                        (fts_doc_uid, "fts_0001")
                    )
                    counts["messages"] += 1
                    counts["message_occurrences"] += 1
                    counts["staging"] += 1
                    counts["fts"] += 1

            archive.commit()
            staging.commit()
            fts.commit()
            archive.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            staging.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            fts.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            fts.close()
            staging.close()
            archive.close()
            source.close()

        self._export_journal()
        self._build_manifest(source_rows, manifest_rows, counts)

        files = [
            self.archive_path,
            self.staging_path,
            self.fts_path,
            self.manifest_path,
        ]
        validation = {path.name: _sqlite_health(path, full=True) for path in files}
        failed = {name: item for name, item in validation.items() if not item["ok"]}
        if failed:
            raise VerifiedMemoryRestoreError(
                "Walidacja przekonwertowanego archiwum nie przeszła: "
                + _canonical_json(failed)
            )

        from latka_jazn.memory.conversation_archive import ConversationArchiveStore

        status = ConversationArchiveStore(self.output_root).status(health_mode="deep").to_dict()
        if not status.get("ready_for_search"):
            raise VerifiedMemoryRestoreError(
                "Przekonwertowane archiwum nie jest gotowe do wyszukiwania: "
                + _canonical_json(status.get("issues"))
            )
        return {
            "ok": True,
            "source_archive": str(self.source_archive),
            "source_archive_sha256": _sha256_file(self.source_archive),
            "output_root": str(self.output_root),
            "paths": {
                "manifest": str(self.manifest_path),
                "archive": str(self.archive_path),
                "staging": str(self.staging_path),
                "fts": str(self.fts_path),
                "journal": str(self.journal_path),
            },
            "counts": counts,
            "validation": validation,
            "conversation_archive_status": status,
            "truth_boundary": (
                "Konwersja zachowuje aktywny kanoniczny snapshot rozmów z Memory Rebuild. "
                "Pełne źródłowe ZIP-y i katalog importów pozostają L0; konwersja nie promuje "
                "wiadomości do L2 ani L3."
            ),
        }

    def _export_journal(self) -> None:
        source = sqlite3.connect(
            f"file:{self.source_journal.resolve().as_posix()}?mode=ro",
            uri=True,
        )
        source.row_factory = sqlite3.Row
        entries: list[dict[str, Any]] = []
        try:
            for row in source.execute(
                """SELECT entry_id,source_record_id,title,summary,content,raw_json,
                          truth_status,importance,event_time_start,event_time_end,
                          timestamp_status,revision
                     FROM journal_entries
                    WHERE status='active'
                    ORDER BY COALESCE(event_time_start,updated_at_utc),entry_id"""
            ):
                try:
                    raw = json.loads(str(row["raw_json"] or "{}"))
                except json.JSONDecodeError:
                    raw = {}
                if not isinstance(raw, dict):
                    raw = {}
                if not raw:
                    raw = {
                        "id": row["source_record_id"] or row["entry_id"],
                        "tytuł": row["title"],
                        "treść": row["content"],
                        "podsumowanie": row["summary"],
                        "timestamp": row["event_time_start"],
                        "truth_status": row["truth_status"],
                    }
                raw.setdefault(
                    "_verified_restore_provenance",
                    {
                        "source_database": str(self.source_journal),
                        "entry_id": row["entry_id"],
                        "revision": int(row["revision"]),
                        "truth_status": row["truth_status"],
                        "timestamp_status": row["timestamp_status"],
                    },
                )
                entries.append(raw)
        finally:
            source.close()
        if not entries:
            raise VerifiedMemoryRestoreError("Brak aktywnych wpisów dziennika do recovery.")
        _atomic_json(
            self.journal_path,
            {
                "entries": entries,
                "_derived_from": {
                    "source_database": str(self.source_journal),
                    "source_sha256": _sha256_file(self.source_journal),
                    "generated_at_utc": _now(),
                    "truth_boundary": (
                        "To jest pochodna kopia L0 dla recovery. Oryginalny journal.sqlite3 "
                        "pozostaje źródłem dowodowym."
                    ),
                },
            },
        )

    def _build_manifest(
        self,
        source_rows: list[dict[str, Any]],
        location_rows: dict[str, list[tuple[Any, ...]]],
        counts: dict[str, int],
    ) -> None:
        manifest = sqlite3.connect(self.manifest_path)
        try:
            manifest.executescript(MANIFEST_SCHEMA)
            manifest.execute("PRAGMA synchronous=FULL")
            meta = {
                "schema_version": "conversation_archive_manifest/v1",
                "hard_limit_bytes": str(DEFAULT_HARD_LIMIT_BYTES),
                "created_at_utc": _now(),
                "source_database": str(self.source_archive),
                "source_database_sha256": _sha256_file(self.source_archive),
                "truth_boundary": TRUTH_BOUNDARY,
            }
            manifest.executemany(
                "INSERT INTO manifest_meta(key,value) VALUES(?,?)",
                sorted(meta.items()),
            )
            for row in source_rows:
                manifest.execute(
                    "INSERT INTO archive_sources VALUES(?,?,?,?,?,?,?,?)",
                    (
                        row["import_id"],
                        row["source_path"],
                        row["source_name"],
                        row["sha256"],
                        row["size_bytes"],
                        row["imported_at_utc"],
                        SCHEMA_VERSION,
                        "memory_rebuild_import",
                    ),
                )

            file_specs = (
                (
                    "archive_0001",
                    "archive",
                    1,
                    self.archive_path,
                    counts["messages"],
                ),
                (
                    "staging_0001",
                    "staging",
                    1,
                    self.staging_path,
                    counts["staging"],
                ),
                (
                    "fts_0001",
                    "fts",
                    1,
                    self.fts_path,
                    counts["fts"],
                ),
            )
            for shard_id, family, ordinal, path, row_count in file_specs:
                health = _sqlite_health(path, full=True)
                if not health["ok"]:
                    raise VerifiedMemoryRestoreError(
                        f"Shard {shard_id} nie przeszedł walidacji."
                    )
                size = int(path.stat().st_size)
                over_limit = int(size > DEFAULT_HARD_LIMIT_BYTES)
                if over_limit:
                    raise VerifiedMemoryRestoreError(
                        f"Shard {path.name} przekracza limit {DEFAULT_HARD_LIMIT_BYTES} bajtów."
                    )
                manifest.execute(
                    "INSERT INTO shard_files VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        shard_id,
                        family,
                        ordinal,
                        path.name,
                        int(row_count),
                        size,
                        round(size / 1024 / 1024, 6),
                        health["sha256"],
                        "ok",
                        0,
                        DEFAULT_HARD_LIMIT_BYTES,
                        over_limit,
                        _now(),
                    ),
                )

            manifest.executemany(
                "INSERT INTO conversation_locations VALUES(?,?)",
                location_rows["conversation_locations"],
            )
            manifest.executemany(
                "INSERT INTO conversation_occurrence_locations VALUES(?,?,?,?)",
                location_rows["conversation_occurrence_locations"],
            )
            manifest.executemany(
                "INSERT INTO message_locations VALUES(?,?)",
                location_rows["message_locations"],
            )
            manifest.executemany(
                "INSERT INTO occurrence_locations VALUES(?,?)",
                location_rows["occurrence_locations"],
            )
            manifest.executemany(
                "INSERT INTO content_locations VALUES(?,?)",
                location_rows["content_locations"],
            )
            manifest.executemany(
                "INSERT INTO staging_locations VALUES(?,?)",
                location_rows["staging_locations"],
            )
            manifest.executemany(
                "INSERT INTO fts_locations VALUES(?,?)",
                location_rows["fts_locations"],
            )
            manifest.commit()
        finally:
            manifest.close()


def _copy_with_sidecars(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(source) + suffix)
        if sidecar.is_file():
            shutil.copy2(sidecar, Path(str(destination) + suffix))


def _backup_runtime_memory(root: Path, backup_root: Path) -> dict[str, Any]:
    backup_root.mkdir(parents=True, exist_ok=True)
    relative_paths = (
        Path("memory/sqlite/conversation_archive_v1"),
        Path("memory/sqlite/conversation_fts_v1"),
        Path("memory/sqlite/staging_v1"),
        Path("memory/sqlite/recovery_current"),
        Path("memory/sqlite/runtime_write_v1"),
        Path("memory/sqlite/runtime_write_v2"),
        Path("memory/raw/dziennik.json"),
    )
    copied: list[str] = []
    for relative in relative_paths:
        source = root / relative
        destination = backup_root / relative
        if source.is_dir():
            shutil.copytree(source, destination, copy_function=shutil.copy2)
            copied.append(str(relative))
        elif source.is_file():
            _copy_with_sidecars(source, destination)
            copied.append(str(relative))
    _atomic_json(
        backup_root / "backup_manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "created_at_utc": _now(),
            "root": str(root),
            "copied": copied,
            "truth_boundary": "Backup jest punktem przywracania, nie aktywną pamięcią.",
        },
    )
    return {"ok": True, "root": str(backup_root), "copied": copied}


def _restore_runtime_memory(root: Path, backup_root: Path) -> None:
    manifest = _load_json(backup_root / "backup_manifest.json")
    for raw_relative in manifest.get("copied") or []:
        relative = Path(str(raw_relative))
        destination = root / relative
        source = backup_root / relative
        if destination.is_dir():
            shutil.rmtree(destination)
        elif destination.exists():
            destination.unlink()
        if source.is_dir():
            shutil.copytree(source, destination, copy_function=shutil.copy2)
        elif source.is_file():
            _copy_with_sidecars(source, destination)


def _publish_staged_archive(staged_root: Path, runtime_root: Path) -> dict[str, Any]:
    mappings = (
        (
            staged_root / "memory/sqlite/conversation_archive_v1",
            runtime_root / "memory/sqlite/conversation_archive_v1",
        ),
        (
            staged_root / "memory/sqlite/conversation_fts_v1",
            runtime_root / "memory/sqlite/conversation_fts_v1",
        ),
        (
            staged_root / "memory/sqlite/staging_v1",
            runtime_root / "memory/sqlite/staging_v1",
        ),
    )
    for source, _ in mappings:
        if not source.is_dir():
            raise VerifiedMemoryRestoreError(f"Brak staged katalogu: {source}")
    for source, destination in mappings:
        temporary = destination.with_name(destination.name + f".incoming-{uuid.uuid4().hex}")
        if temporary.exists():
            shutil.rmtree(temporary)
        temporary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, temporary, copy_function=shutil.copy2)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(temporary, destination)
    staged_journal = staged_root / "memory/raw/dziennik.json"
    runtime_journal = runtime_root / "memory/raw/dziennik.json"
    if not staged_journal.is_file():
        raise VerifiedMemoryRestoreError(f"Brak staged dziennika: {staged_journal}")
    _atomic_text(runtime_journal, staged_journal.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "archive": str(runtime_root / "memory/sqlite/conversation_archive_v1"),
        "fts": str(runtime_root / "memory/sqlite/conversation_fts_v1"),
        "staging": str(runtime_root / "memory/sqlite/staging_v1"),
        "journal": str(runtime_journal),
    }


def _run_json(root: Path, arguments: Sequence[str], *, timeout: float = 600.0) -> dict[str, Any]:
    command = [sys.executable, "-X", "utf8", str(root / "run.py"), *arguments]
    completed = subprocess.run(
        command,
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    payload: dict[str, Any] | None = None
    for index in range(len(lines)):
        candidate = "\n".join(lines[index:])
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payload = parsed
            break
    if payload is None:
        raise VerifiedMemoryRestoreError(
            f"Komenda nie zwróciła JSON (exit={completed.returncode}): {' '.join(command)}; "
            f"stderr={completed.stderr[-2000:]}"
        )
    payload["_exit_code"] = completed.returncode
    payload["_stderr_tail"] = completed.stderr[-2000:]
    if completed.returncode != 0:
        raise VerifiedMemoryRestoreError(
            f"Komenda zakończyła się kodem {completed.returncode}: {' '.join(command)}"
        )
    return payload


def _run_plain(root: Path, arguments: Sequence[str], *, timeout: float = 600.0) -> dict[str, Any]:
    command = [sys.executable, "-X", "utf8", str(root / "run.py"), *arguments]
    completed = subprocess.run(
        command,
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _stop_daemon(root: Path) -> dict[str, Any]:
    result = _run_plain(root, ["stop"], timeout=180.0)
    if result["exit_code"] not in {0, 1}:
        raise VerifiedMemoryRestoreError(
            f"Nie udało się zatrzymać daemona: {result['stderr'][-1200:]}"
        )
    return result


def build_l2_review_draft(root: Path, *, limit: int) -> dict[str, Any]:
    from latka_jazn.memory.memory_recovery_pipeline import MemoryRecoveryPipeline

    pipeline = MemoryRecoveryPipeline(root)
    rows = pipeline._candidate_rows(limit=max(1, int(limit)))
    candidates = []
    for row in rows:
        content = str(row["content_excerpt"] or "")
        candidates.append(
            {
                "item_id": str(row["item_id"]),
                "source_table": str(row["source_table"]),
                "source_row_id": str(row["source_row_id"]),
                "memory_type": str(row["memory_type"]),
                "memory_namespace": str(row["memory_namespace"] or "recovered_memory"),
                "truth_status": str(row["truth_status"] or ""),
                "confidence": float(row["confidence"] or 0.0),
                "importance": float(row["importance"] or 0.0),
                "source_sha256": str(row["source_sha256"] or "") or None,
                "conversation_id": str(row["conversation_id"] or "") or None,
                "source_timestamp": str(row["source_timestamp"] or "") or None,
                "grounding": str(row["grounding"] or ""),
                "content_excerpt": content,
                "content_excerpt_sha256": _sha256_text(content),
                "decision": "pending_review",
                "review_note": "",
            }
        )
    return {
        "schema_version": L2_DRAFT_SCHEMA,
        "created_at_utc": _now(),
        "root": str(root),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "review_instructions": {
            "allowed_decisions": ["approved", "rejected"],
            "all_candidates_require_decision": True,
            "do_not_change": [
                "item_id",
                "source_table",
                "source_row_id",
                "content_excerpt",
                "content_excerpt_sha256",
                "source_sha256",
            ],
            "truth_boundary": (
                "Zatwierdzenie L2 oznacza zgodę na krótkoterminowy rekord z TTL. "
                "Nie jest promocją L3."
            ),
        },
        "automatic_l2": False,
        "automatic_l3": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def seal_l2_review(
    draft_path: Path,
    *,
    reviewed_by: str,
    output_path: Path,
) -> dict[str, Any]:
    if not reviewed_by.strip():
        raise VerifiedMemoryRestoreError("reviewed_by jest wymagane.")
    draft = _load_json(draft_path)
    if draft.get("schema_version") != L2_DRAFT_SCHEMA:
        raise VerifiedMemoryRestoreError("Nieobsługiwany schemat draftu L2.")
    candidates = draft.get("candidates")
    if not isinstance(candidates, list):
        raise VerifiedMemoryRestoreError("Draft L2 nie ma listy candidates.")
    invalid = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            invalid.append({"index": index, "reason": "not_object"})
            continue
        decision = candidate.get("decision")
        if decision not in {"approved", "rejected"}:
            invalid.append(
                {
                    "index": index,
                    "item_id": candidate.get("item_id"),
                    "reason": "decision_must_be_approved_or_rejected",
                }
            )
        excerpt = str(candidate.get("content_excerpt") or "")
        if candidate.get("content_excerpt_sha256") != _sha256_text(excerpt):
            invalid.append(
                {
                    "index": index,
                    "item_id": candidate.get("item_id"),
                    "reason": "content_excerpt_sha256_mismatch",
                }
            )
    if invalid:
        raise VerifiedMemoryRestoreError(
            "Ręczny przegląd L2 jest niekompletny lub zmieniono dane źródłowe: "
            + _canonical_json(invalid[:50])
        )
    manifest = {
        "schema_version": L2_MANIFEST_SCHEMA,
        "created_at_utc": _now(),
        "reviewed_by": reviewed_by.strip(),
        "source_draft_path": str(draft_path.resolve()),
        "source_draft_sha256": _sha256_file(draft_path),
        "candidate_count": len(candidates),
        "approved_count": sum(
            1 for candidate in candidates if candidate.get("decision") == "approved"
        ),
        "rejected_count": sum(
            1 for candidate in candidates if candidate.get("decision") == "rejected"
        ),
        "candidates": candidates,
        "automatic_commit_allowed": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }
    manifest_sha = _sha256_text(_canonical_json(manifest))
    manifest["manifest_sha256"] = manifest_sha
    _atomic_json(output_path, manifest)
    return {**manifest, "path": str(output_path.resolve())}


def _verify_l2_manifest(
    manifest_path: Path,
    *,
    expected_sha256: str,
    reviewed_by: str,
) -> dict[str, Any]:
    payload = _load_json(manifest_path)
    if payload.get("schema_version") != L2_MANIFEST_SCHEMA:
        raise VerifiedMemoryRestoreError("Nieobsługiwany schemat manifestu L2.")
    stored = str(payload.pop("manifest_sha256", ""))
    actual = _sha256_text(_canonical_json(payload))
    if stored != actual or expected_sha256 != actual:
        raise VerifiedMemoryRestoreError(
            f"Niezgodny SHA manifestu L2: expected={expected_sha256}, stored={stored}, actual={actual}"
        )
    if str(payload.get("reviewed_by") or "").strip() != reviewed_by.strip():
        raise VerifiedMemoryRestoreError("reviewed_by nie zgadza się z manifestem L2.")
    payload["manifest_sha256"] = actual
    return payload


def apply_l2_review(
    root: Path,
    *,
    manifest_path: Path,
    expected_sha256: str,
    reviewed_by: str,
    l3_limit: int,
) -> dict[str, Any]:
    from latka_jazn.config import JaznConfig
    from latka_jazn.memory.memory_recovery_pipeline import (
        MemoryRecoveryPipeline,
        _kind,
        _truth,
    )
    from latka_jazn.memory.memory_tier_store import MemoryTierStore
    from latka_jazn.memory.memory_tiers import ShortTermMemoryPolicy

    manifest = _verify_l2_manifest(
        manifest_path,
        expected_sha256=expected_sha256,
        reviewed_by=reviewed_by,
    )
    approved = [
        item
        for item in manifest.get("candidates") or []
        if isinstance(item, dict) and item.get("decision") == "approved"
    ]
    config = JaznConfig(root=root)
    pipeline = MemoryRecoveryPipeline(root)
    sidecar = sqlite3.connect(
        f"file:{config.normalization_sidecar_db_path.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    sidecar.row_factory = sqlite3.Row
    policy = ShortTermMemoryPolicy()
    written = skipped = 0
    memory_ids: list[str] = []
    try:
        with MemoryTierStore(config.memory_tier_db_path) as store:
            for item in approved:
                row = sidecar.execute(
                    "SELECT * FROM normalized_memory_items WHERE item_id=?",
                    (str(item.get("item_id") or ""),),
                ).fetchone()
                if row is None:
                    raise VerifiedMemoryRestoreError(
                        f"Kandydat L2 zniknął z sidecara: {item.get('item_id')}"
                    )
                content = str(row["content_excerpt"] or "")
                if item.get("content_excerpt_sha256") != _sha256_text(content):
                    raise VerifiedMemoryRestoreError(
                        f"Treść kandydata L2 zmieniła się: {item.get('item_id')}"
                    )
                evidence = pipeline._evidence(row)
                truth = _truth(str(row["truth_status"] or ""))
                if truth.value not in {"source_recorded", "user_confirmed"}:
                    skipped += 1
                    continue
                record = policy.create(
                    kind=_kind(str(row["memory_type"])),
                    content=content,
                    domain=str(row["memory_namespace"] or "recovered_memory"),
                    mode="verified_memory_restore_manual_l2",
                    truth_status=truth,
                    confidence=float(row["confidence"] or 0.0),
                    importance=float(row["importance"] or 0.0),
                    evidence=(evidence,),
                    created_at_utc=datetime.now(timezone.utc),
                    tags=(
                        "verified_memory_restore",
                        "manual_l2_review",
                        str(row["memory_type"]),
                        f"reviewed_by:{reviewed_by.strip()}",
                    ),
                )
                record = replace(
                    record,
                    reinforcement_count=1,
                    last_reinforced_at_utc=datetime.now(timezone.utc),
                    reinforcement_evidence_keys=(evidence.evidence_key,),
                )
                store.save_record(record)
                written += 1
                memory_ids.append(record.memory_id)
    finally:
        sidecar.close()

    l3_manifest = pipeline.build_l3_manifest(limit=max(0, int(l3_limit)))
    return {
        "status": "l2_applied_l3_manifest_ready",
        "manifest_sha256": expected_sha256,
        "reviewed_by": reviewed_by,
        "approved": len(approved),
        "written": written,
        "skipped": skipped,
        "memory_ids": memory_ids,
        "memory_tier_database": str(config.memory_tier_db_path),
        "l3_manifest": l3_manifest,
        "automatic_l3": False,
        "truth_boundary": TRUTH_BOUNDARY,
    }


def prepare(
    root: Path,
    *,
    test04_root: Path,
    test04_summary: Path,
    publish: bool,
    stop_daemon: bool,
    l2_limit: int,
    report_path: Path | None,
) -> PhaseReport:
    root = root.expanduser().resolve()
    test04_root = test04_root.expanduser().resolve()
    test04_summary = test04_summary.expanduser().resolve()
    if not (root / "run.py").is_file():
        raise VerifiedMemoryRestoreError(f"Brak run.py pod rootem: {root}")
    run_dir = root / "workspace_runtime" / "verified_memory_restore" / _run_id()
    staged_root = run_dir / "staged_runtime"
    backup_root = run_dir / "backup_before_publish"
    run_dir.mkdir(parents=True, exist_ok=False)
    summary_report = validate_test04_summary(test04_summary)
    database_report = validate_test04_databases(test04_root)
    conversion = RuntimeArchiveConverter(test04_root, staged_root).build()

    details: dict[str, Any] = {
        "test04_summary": summary_report,
        "test04_databases": database_report,
        "conversion": conversion,
        "publish_requested": publish,
    }
    status = "staged"
    errors: list[str] = []
    if publish:
        backup = _backup_runtime_memory(root, backup_root)
        details["backup"] = backup
        try:
            if stop_daemon:
                details["daemon_stop"] = _stop_daemon(root)
            else:
                status_snapshot = _run_json(
                    root,
                    ["status", "--snapshot", "--json"],
                    timeout=180.0,
                )
                details["status_before_publish"] = status_snapshot
                text = _canonical_json(status_snapshot).lower()
                if "active_trusted" in text or '"daemon_active":true' in text:
                    raise VerifiedMemoryRestoreError(
                        "Daemon wygląda na aktywny. Użyj --stop-daemon albo zatrzymaj go ręcznie."
                    )
            details["publication"] = _publish_staged_archive(staged_root, root)

            from latka_jazn.memory.memory_recovery_pipeline import MemoryRecoveryPipeline
            from latka_jazn.tools.memory_validation import validate_large_memory

            pipeline = MemoryRecoveryPipeline(root)
            recovery = pipeline.run(
                force_recovery=True,
                normalize_limit=None,
                prepare_l2=False,
                build_l3_manifest=False,
            ).to_dict()
            details["recovery"] = recovery
            if not recovery.get("ok"):
                raise VerifiedMemoryRestoreError(
                    "Recovery/normalizacja/wake-state nie zakończyły się powodzeniem: "
                    + _canonical_json(recovery.get("errors"))
                )

            validation = validate_large_memory(
                root,
                full=True,
                include_all_sqlite=True,
                max_errors=100,
                table_counts=False,
                hash_files=False,
                output=run_dir / "memory_validation_after_prepare.json",
            )
            details["memory_validation"] = validation
            if not validation.get("ok"):
                raise VerifiedMemoryRestoreError(
                    "Pełna walidacja pamięci po recovery nie przeszła."
                )

            l2_draft = build_l2_review_draft(root, limit=l2_limit)
            l2_draft_path = run_dir / "l2_review_draft.json"
            _atomic_json(l2_draft_path, l2_draft)
            details["l2_review_draft"] = {
                "path": str(l2_draft_path),
                "sha256": _sha256_file(l2_draft_path),
                "candidate_count": l2_draft["candidate_count"],
            }
            status = "ready_for_l2_review"
        except BaseException:
            _restore_runtime_memory(root, backup_root)
            raise

    report = PhaseReport(
        schema_version=SCHEMA_VERSION,
        status=status,
        phase="prepare",
        root=str(root),
        run_dir=str(run_dir),
        details=details,
        errors=errors,
    )
    _atomic_json(run_dir / "prepare_report.json", report.to_dict())
    if report_path is not None:
        _atomic_json(report_path.expanduser().resolve(), report.to_dict())
    return report


def activate(
    root: Path,
    *,
    l3_manifest_path: Path,
    expected_sha256: str,
    approved_by: str,
    start_daemon: bool,
    report_path: Path | None,
) -> PhaseReport:
    root = root.expanduser().resolve()
    if not approved_by.strip():
        raise VerifiedMemoryRestoreError("approved_by jest wymagane.")
    if not start_daemon:
        raise VerifiedMemoryRestoreError(
            "Aktywacja wymaga jawnego --start-daemon."
        )
    from latka_jazn.memory.memory_recovery_pipeline import MemoryRecoveryPipeline
    from latka_jazn.tools.memory_validation import validate_large_memory

    pipeline = MemoryRecoveryPipeline(root)
    canonical_l3 = pipeline.manifest_path.resolve()
    supplied_l3 = l3_manifest_path.expanduser().resolve()
    if supplied_l3 != canonical_l3:
        raise VerifiedMemoryRestoreError(
            f"Manifest L3 musi być kanoniczny: {canonical_l3}"
        )
    apply_report = pipeline.apply_l3_manifest(
        expected_sha256=expected_sha256,
        approved_by=approved_by,
    )
    if apply_report.get("status") not in {"ready", "completed_with_warnings"}:
        raise VerifiedMemoryRestoreError(
            "Nie udało się zastosować manifestu L3: " + _canonical_json(apply_report)
        )
    if apply_report.get("errors"):
        raise VerifiedMemoryRestoreError(
            "Manifest L3 zakończył się błędami: "
            + _canonical_json(apply_report.get("errors"))
        )

    validation = validate_large_memory(
        root,
        full=True,
        include_all_sqlite=True,
        max_errors=100,
        table_counts=True,
        hash_files=True,
        output=root
        / "workspace_runtime"
        / "memory_validation"
        / "before_activation.json",
    )
    if not validation.get("ok"):
        raise VerifiedMemoryRestoreError(
            "Końcowa walidacja pamięci przed doctor nie przeszła."
        )

    doctor = _run_json(root, ["doctor", "--json"], timeout=600.0)
    if not doctor.get("ok"):
        raise VerifiedMemoryRestoreError("Końcowy doctor nie jest zielony.")
    if doctor.get("activation_prerequisites_ready") is False:
        raise VerifiedMemoryRestoreError(
            "Doctor zgłasza activation_prerequisites_ready=false."
        )

    start = _run_plain(root, ["start"], timeout=300.0)
    if start["exit_code"] != 0:
        raise VerifiedMemoryRestoreError(
            f"Start daemona nie powiódł się: {start['stderr'][-2000:]}"
        )
    status = _run_json(root, ["status", "--json"], timeout=300.0)
    status_text = _canonical_json(status).lower()
    active_trusted = (
        "active_trusted" in status_text
        or (
            bool(status.get("ok"))
            and (
                status.get("active") is True
                or status.get("daemon_active") is True
                or status.get("runtime_active") is True
            )
        )
    )
    if not active_trusted:
        raise VerifiedMemoryRestoreError(
            "Status po starcie nie potwierdził active_trusted."
        )

    run_dir = root / "workspace_runtime" / "verified_memory_restore" / _run_id()
    run_dir.mkdir(parents=True, exist_ok=False)
    report = PhaseReport(
        schema_version=SCHEMA_VERSION,
        status="active_trusted",
        phase="activate",
        root=str(root),
        run_dir=str(run_dir),
        details={
            "l3_apply": apply_report,
            "memory_validation": validation,
            "doctor": doctor,
            "start": start,
            "status": status,
            "approved_by": approved_by,
            "l3_manifest_sha256": expected_sha256,
        },
        errors=[],
    )
    _atomic_json(run_dir / "activation_report.json", report.to_dict())
    if report_path is not None:
        _atomic_json(report_path.expanduser().resolve(), report.to_dict())
    return report


def _emit(payload: Any, *, as_json: bool) -> None:
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    if as_json or not isinstance(payload, str):
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verified-memory-restore",
        description=(
            "Memory Rebuild/Test04 -> current runtime archive -> recovery -> "
            "wake-state -> manual L2 -> explicit L3 -> doctor-gated activation"
        ),
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    child = sub.add_parser("validate-test04", allow_abbrev=False)
    child.add_argument("--test04-root", type=Path, required=True)
    child.add_argument("--test04-summary", type=Path, required=True)
    child.add_argument("--json", action="store_true", dest="as_json")

    child = sub.add_parser("prepare", allow_abbrev=False)
    child.add_argument("--root", type=Path, required=True)
    child.add_argument("--test04-root", type=Path, required=True)
    child.add_argument("--test04-summary", type=Path, required=True)
    child.add_argument("--publish", action="store_true")
    child.add_argument("--stop-daemon", action="store_true")
    child.add_argument("--l2-limit", type=int, default=120)
    child.add_argument("--report", type=Path)
    child.add_argument("--json", action="store_true", dest="as_json")

    child = sub.add_parser("seal-l2", allow_abbrev=False)
    child.add_argument("--draft", type=Path, required=True)
    child.add_argument("--reviewed-by", required=True)
    child.add_argument("--output", type=Path, required=True)
    child.add_argument("--json", action="store_true", dest="as_json")

    child = sub.add_parser("apply-l2", allow_abbrev=False)
    child.add_argument("--root", type=Path, required=True)
    child.add_argument("--manifest", type=Path, required=True)
    child.add_argument("--expected-sha256", required=True)
    child.add_argument("--reviewed-by", required=True)
    child.add_argument("--l3-limit", type=int, default=25)
    child.add_argument("--report", type=Path)
    child.add_argument("--json", action="store_true", dest="as_json")

    child = sub.add_parser("activate", allow_abbrev=False)
    child.add_argument("--root", type=Path, required=True)
    child.add_argument("--l3-manifest", type=Path, required=True)
    child.add_argument("--expected-sha256", required=True)
    child.add_argument("--approved-by", required=True)
    child.add_argument("--start-daemon", action="store_true")
    child.add_argument("--report", type=Path)
    child.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-test04":
            payload = {
                "schema_version": SCHEMA_VERSION,
                "status": "validated",
                "summary": validate_test04_summary(args.test04_summary.resolve()),
                "databases": validate_test04_databases(args.test04_root.resolve()),
                "truth_boundary": TRUTH_BOUNDARY,
            }
        elif args.command == "prepare":
            payload = prepare(
                args.root,
                test04_root=args.test04_root,
                test04_summary=args.test04_summary,
                publish=bool(args.publish),
                stop_daemon=bool(args.stop_daemon),
                l2_limit=max(1, int(args.l2_limit)),
                report_path=args.report,
            )
        elif args.command == "seal-l2":
            payload = seal_l2_review(
                args.draft.resolve(),
                reviewed_by=args.reviewed_by,
                output_path=args.output.resolve(),
            )
        elif args.command == "apply-l2":
            payload = apply_l2_review(
                args.root.resolve(),
                manifest_path=args.manifest.resolve(),
                expected_sha256=args.expected_sha256,
                reviewed_by=args.reviewed_by,
                l3_limit=max(0, int(args.l3_limit)),
            )
            if args.report:
                _atomic_json(args.report.resolve(), payload)
        elif args.command == "activate":
            payload = activate(
                args.root,
                l3_manifest_path=args.l3_manifest,
                expected_sha256=args.expected_sha256,
                approved_by=args.approved_by,
                start_daemon=bool(args.start_daemon),
                report_path=args.report,
            )
        else:
            raise VerifiedMemoryRestoreError(f"Nieznana komenda: {args.command}")
        _emit(payload, as_json=bool(args.as_json))
        if hasattr(payload, "ok"):
            return 0 if bool(payload.ok) else 1
        return 0 if payload.get("status") not in {"failed", "error"} else 1
    except VerifiedMemoryRestoreError as exc:
        error = {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "truth_boundary": TRUTH_BOUNDARY,
        }
        _emit(error, as_json=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
