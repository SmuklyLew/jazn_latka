from __future__ import annotations

import sqlite3

L0_SCHEMA_VERSION = "memory_rebuild_l0/v4"

L0_SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS memory_l0_sources(
  source_id TEXT PRIMARY KEY,
  adapter_id TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_member TEXT NOT NULL DEFAULT '',
  first_imported_at_utc TEXT NOT NULL,
  last_seen_at_utc TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(adapter_id,source_sha256,source_member)
);
CREATE TABLE IF NOT EXISTS memory_l0_records(
  record_id TEXT PRIMARY KEY,
  logical_key TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision>=1),
  source_id TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  record_kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  event_time_start TEXT,
  event_time_end TEXT,
  timestamp_status TEXT NOT NULL,
  conversation_id TEXT,
  role TEXT,
  visibility TEXT NOT NULL DEFAULT 'visible',
  memory_eligible INTEGER NOT NULL DEFAULT 1 CHECK(memory_eligible IN (0,1)),
  truth_status TEXT NOT NULL,
  importance REAL NOT NULL CHECK(importance BETWEEN 0.0 AND 1.0),
  raw_json TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  is_current_revision INTEGER NOT NULL CHECK(is_current_revision IN (0,1)),
  UNIQUE(logical_key,revision),
  FOREIGN KEY(source_id) REFERENCES memory_l0_sources(source_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_l0_one_current_revision
  ON memory_l0_records(logical_key) WHERE is_current_revision=1;
CREATE INDEX IF NOT EXISTS idx_memory_l0_temporal
  ON memory_l0_records(is_current_revision,event_time_start,event_time_end);
CREATE INDEX IF NOT EXISTS idx_memory_l0_source_kind
  ON memory_l0_records(source_kind,record_kind,is_current_revision);
CREATE INDEX IF NOT EXISTS idx_memory_l0_recall_eligible
  ON memory_l0_records(is_current_revision,memory_eligible,role);
CREATE TABLE IF NOT EXISTS memory_l0_occurrences(
  logical_key TEXT NOT NULL,
  revision INTEGER NOT NULL,
  source_id TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  seen_at_utc TEXT NOT NULL,
  PRIMARY KEY(logical_key,revision,source_id,source_record_id),
  FOREIGN KEY(logical_key,revision) REFERENCES memory_l0_records(logical_key,revision),
  FOREIGN KEY(source_id) REFERENCES memory_l0_sources(source_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_l0_fts USING fts5(
  record_id UNINDEXED,
  title,
  content,
  record_kind,
  content='memory_l0_records',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS memory_l0_fts_insert AFTER INSERT ON memory_l0_records BEGIN
  INSERT INTO memory_l0_fts(rowid,record_id,title,content,record_kind)
  VALUES(new.rowid,new.record_id,new.title,new.content,new.record_kind);
END;
CREATE TRIGGER IF NOT EXISTS memory_l0_fts_delete AFTER DELETE ON memory_l0_records BEGIN
  INSERT INTO memory_l0_fts(memory_l0_fts,rowid,record_id,title,content,record_kind)
  VALUES('delete',old.rowid,old.record_id,old.title,old.content,old.record_kind);
END;
CREATE TRIGGER IF NOT EXISTS memory_l0_fts_update
AFTER UPDATE OF record_id,title,content,record_kind ON memory_l0_records BEGIN
  INSERT INTO memory_l0_fts(memory_l0_fts,rowid,record_id,title,content,record_kind)
  VALUES('delete',old.rowid,old.record_id,old.title,old.content,old.record_kind);
  INSERT INTO memory_l0_fts(rowid,record_id,title,content,record_kind)
  VALUES(new.rowid,new.record_id,new.title,new.content,new.record_kind);
END;
CREATE TABLE IF NOT EXISTS memory_l0_embeddings(
  record_id TEXT NOT NULL,
  model_id TEXT NOT NULL,
  dimensions INTEGER NOT NULL CHECK(dimensions>0),
  vector_blob BLOB NOT NULL,
  vector_sha256 TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  PRIMARY KEY(record_id,model_id),
  FOREIGN KEY(record_id) REFERENCES memory_l0_records(record_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS memory_l0_assets(
  asset_pointer TEXT PRIMARY KEY,
  original_filename TEXT,
  content_type TEXT,
  mime_type TEXT,
  availability_status TEXT NOT NULL DEFAULT 'referenced_only',
  file_sha256 TEXT,
  first_seen_source_id TEXT NOT NULL,
  last_seen_source_id TEXT NOT NULL,
  first_seen_at_utc TEXT NOT NULL,
  last_seen_at_utc TEXT NOT NULL,
  FOREIGN KEY(first_seen_source_id) REFERENCES memory_l0_sources(source_id),
  FOREIGN KEY(last_seen_source_id) REFERENCES memory_l0_sources(source_id)
);
CREATE TABLE IF NOT EXISTS memory_l0_record_assets(
  record_id TEXT NOT NULL,
  asset_pointer TEXT NOT NULL,
  PRIMARY KEY(record_id,asset_pointer),
  FOREIGN KEY(record_id) REFERENCES memory_l0_records(record_id) ON DELETE CASCADE,
  FOREIGN KEY(asset_pointer) REFERENCES memory_l0_assets(asset_pointer)
);
CREATE TABLE IF NOT EXISTS memory_l0_conversations(
  variant_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK(revision>=1),
  source_id TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  create_time REAL,
  update_time REAL,
  current_node_id TEXT,
  raw_tree_sha256 TEXT NOT NULL,
  semantic_tree_sha256 TEXT NOT NULL,
  node_count INTEGER NOT NULL,
  message_count INTEGER NOT NULL,
  branch_point_count INTEGER NOT NULL,
  payload_codec TEXT NOT NULL,
  payload_blob BLOB NOT NULL,
  payload_size_uncompressed INTEGER NOT NULL,
  created_at_utc TEXT NOT NULL,
  is_current_revision INTEGER NOT NULL CHECK(is_current_revision IN (0,1)),
  UNIQUE(conversation_id,revision),
  UNIQUE(conversation_id,semantic_tree_sha256,source_id),
  FOREIGN KEY(source_id) REFERENCES memory_l0_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_memory_l0_conversation_current
  ON memory_l0_conversations(conversation_id,is_current_revision,revision);
CREATE TABLE IF NOT EXISTS memory_l0_imports(
  import_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  imported_at_utc TEXT NOT NULL,
  mode TEXT NOT NULL,
  selector_json TEXT NOT NULL,
  control_json TEXT NOT NULL DEFAULT '{}',
  conversation_count INTEGER NOT NULL,
  truth_boundary TEXT NOT NULL,
  FOREIGN KEY(source_id) REFERENCES memory_l0_sources(source_id)
);
CREATE TABLE IF NOT EXISTS memory_activation_guard(
  guard_id INTEGER PRIMARY KEY CHECK(guard_id=1),
  automatic_l2 INTEGER NOT NULL CHECK(automatic_l2=0),
  automatic_l3 INTEGER NOT NULL CHECK(automatic_l3=0),
  automatic_activation INTEGER NOT NULL CHECK(automatic_activation=0),
  private_replacement_allowed INTEGER NOT NULL CHECK(private_replacement_allowed IN (0,1)),
  benchmark_report_sha256 TEXT,
  approved_by TEXT,
  approved_at_utc TEXT,
  reason TEXT NOT NULL
);
INSERT OR IGNORE INTO memory_activation_guard(
  guard_id,automatic_l2,automatic_l3,automatic_activation,private_replacement_allowed,reason
) VALUES(1,0,0,0,0,'fail_closed_until_real_recall_and_provenance_benchmark_passes');
CREATE VIEW IF NOT EXISTS memory_l0_current AS
  SELECT * FROM memory_l0_records WHERE is_current_revision=1;
CREATE VIEW IF NOT EXISTS music_analysis_current AS
  SELECT * FROM memory_l0_records
  WHERE is_current_revision=1 AND source_kind='music_analysis';
"""

def ensure_l0_schema_extensions(con: sqlite3.Connection) -> None:
    """Migrate an existing L0 database to the native v4 evidence boundary."""

    con.executescript(L0_SCHEMA_SQL)
    columns = {str(row[1]) for row in con.execute("PRAGMA table_info(memory_l0_records)")}
    if "visibility" not in columns:
        con.execute("ALTER TABLE memory_l0_records ADD COLUMN visibility TEXT NOT NULL DEFAULT 'visible'")
    if "memory_eligible" not in columns:
        con.execute(
            "ALTER TABLE memory_l0_records ADD COLUMN memory_eligible "
            "INTEGER NOT NULL DEFAULT 1 CHECK(memory_eligible IN (0,1))"
        )
    con.execute(
        """UPDATE memory_l0_records SET visibility='non_dialogue',memory_eligible=0
           WHERE record_kind='conversation_message' AND COALESCE(role,'') NOT IN ('user','assistant')"""
    )
    con.execute(
        """UPDATE memory_l0_records SET visibility='visible',memory_eligible=1
           WHERE record_kind<>'conversation_message'"""
    )


__all__ = ["L0_SCHEMA_SQL", "L0_SCHEMA_VERSION", "ensure_l0_schema_extensions"]
