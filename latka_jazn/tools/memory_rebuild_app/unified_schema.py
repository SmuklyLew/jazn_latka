from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
import hashlib
import json
import sqlite3

UNIFIED_SCHEMA_VERSION = "jazn_unified_memory/v3.0"
COMPATIBLE_UNIFIED_SCHEMA_VERSIONS = (
    "jazn_unified_memory/v2.4",
    "jazn_unified_memory/v2.5",
    UNIFIED_SCHEMA_VERSION,
)
CANONICAL_DATABASE_NAME = "memory_jazn.sqlite3"
LEGACY_DATABASE_NAMES = (
    "archive_chats.sqlite3",
    "journal.sqlite3",
    "experience.sqlite3",
    "memory_jazn.sqlite3",
    "import_catalog.sqlite3",
)

EXTRA_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS unified_memory_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_revisions(
  revision_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  snapshot_json TEXT NOT NULL,
  changed_fields_json TEXT NOT NULL,
  edited_at_utc TEXT NOT NULL,
  edited_by TEXT NOT NULL,
  reason TEXT NOT NULL,
  UNIQUE(candidate_id,revision),
  FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS candidate_evidence(
  candidate_id TEXT NOT NULL,
  evidence_key TEXT NOT NULL,
  source_database TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  source_sha256 TEXT,
  excerpt TEXT,
  context_before TEXT,
  context_after TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  created_at_utc TEXT NOT NULL,
  PRIMARY KEY(candidate_id,evidence_key),
  FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS candidate_links(
  link_id TEXT PRIMARY KEY,
  source_candidate_id TEXT NOT NULL,
  target_candidate_id TEXT NOT NULL,
  relation TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL,
  created_by TEXT NOT NULL,
  UNIQUE(source_candidate_id,target_candidate_id,relation),
  FOREIGN KEY(source_candidate_id) REFERENCES candidates(candidate_id),
  FOREIGN KEY(target_candidate_id) REFERENCES candidates(candidate_id)
);
CREATE TABLE IF NOT EXISTS unified_export_runs(
  run_id TEXT PRIMARY KEY,
  operation TEXT NOT NULL,
  source_manifest_sha256 TEXT,
  target_path TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  completed_at_utc TEXT,
  report_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS unified_migration_conflicts(
  conflict_id TEXT PRIMARY KEY,
  source_database_name TEXT NOT NULL,
  table_name TEXT NOT NULL,
  key_json TEXT NOT NULL,
  target_sha256 TEXT,
  incoming_sha256 TEXT NOT NULL,
  revision_relation TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('unresolved','resolved_target_canonical','resolved_duplicate')),
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unified_migration_conflicts_status
  ON unified_migration_conflicts(status,table_name);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_records_fts USING fts5(
  memory_id UNINDEXED,
  content,
  domain,
  kind,
  content='memory_records',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS memory_records_fts_insert AFTER INSERT ON memory_records BEGIN
  INSERT INTO memory_records_fts(rowid,memory_id,content,domain,kind)
  VALUES(new.rowid,new.memory_id,new.content,new.domain,new.kind);
END;
CREATE TRIGGER IF NOT EXISTS memory_records_fts_delete AFTER DELETE ON memory_records BEGIN
  INSERT INTO memory_records_fts(memory_records_fts,rowid,memory_id,content,domain,kind)
  VALUES('delete',old.rowid,old.memory_id,old.content,old.domain,old.kind);
END;
CREATE TRIGGER IF NOT EXISTS memory_records_fts_update AFTER UPDATE OF memory_id,content,domain,kind ON memory_records BEGIN
  INSERT INTO memory_records_fts(memory_records_fts,rowid,memory_id,content,domain,kind)
  VALUES('delete',old.rowid,old.memory_id,old.content,old.domain,old.kind);
  INSERT INTO memory_records_fts(rowid,memory_id,content,domain,kind)
  VALUES(new.rowid,new.memory_id,new.content,new.domain,new.kind);
END;
CREATE INDEX IF NOT EXISTS idx_candidates_review_order
  ON candidates(status,importance DESC,confidence DESC,created_at_utc);
CREATE INDEX IF NOT EXISTS idx_candidate_revisions_candidate
  ON candidate_revisions(candidate_id,revision DESC);
"""

COPY_ORDER = (
    "archive_meta", "import_sources", "import_source_aliases", "conversations",
    "conversation_occurrences", "conversation_revisions", "nodes", "fts_docs",
    "assets", "message_assets", "import_conflicts",
    "journal_meta", "journal_sources", "journal_entries", "journal_entry_sources",
    "journal_revisions", "journal_fts_docs",
    "experience_meta", "candidates", "experiences", "experience_domains",
    "experience_sources", "experience_fts_docs",
    "memory_store_meta", "memory_records", "memory_evidence", "working_memory_index",
    "short_term_memory_index", "promotion_requests", "promotion_decisions",
    "promotion_ledger", "long_term_memory_index", "memory_outbox", "session_checkpoints",
    "catalog_meta", "sources", "source_occurrences", "operations", "links", "verifications",
    "unified_memory_meta", "candidate_revisions", "candidate_evidence", "candidate_links",
    "unified_export_runs", "unified_migration_conflicts",
)

EDITABLE_CANDIDATE_FIELDS = {
    "title", "summary", "truth_status", "confidence", "importance", "domains_json",
    "score_json", "status", "reviewed_at_utc", "reviewed_by", "review_reason",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def candidate_snapshot(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    for key in ("domains_json", "score_json"):
        try:
            raw = item.get(key)
            default = "[]" if key == "domains_json" else "{}"
            item[key[:-5]] = json.loads(str(raw if raw not in (None, "") else default))
        except json.JSONDecodeError:
            item[key[:-5]] = [] if key == "domains_json" else {}
    return item


@dataclass(slots=True, frozen=True)
class UnifiedImportResult:
    source: str
    kind: str
    status: str
    report: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "kind": self.kind, "status": self.status, "report": self.report}


__all__ = [
    "CANONICAL_DATABASE_NAME", "COMPATIBLE_UNIFIED_SCHEMA_VERSIONS", "COPY_ORDER", "EDITABLE_CANDIDATE_FIELDS", "EXTRA_SCHEMA",
    "LEGACY_DATABASE_NAMES", "UNIFIED_SCHEMA_VERSION", "UnifiedImportResult",
    "candidate_snapshot", "json_text", "quote", "sha_text", "utc_now",
]
