from __future__ import annotations

L0_SCHEMA_VERSION = "memory_rebuild_l0/v16.1"

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

__all__ = ["L0_SCHEMA_SQL", "L0_SCHEMA_VERSION"]
