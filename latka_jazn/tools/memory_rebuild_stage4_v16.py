from __future__ import annotations

"""Stage4/runtime synchronization for memory_rebuild.py v16.0.

This module owns mutating rebuild/sync operations. Read-only Test 01-03 validation
lives in ``memory_rebuild_app.test_profiles`` and full Test 04 acceptance delegates
to ``latka_jazn.tools.memory_sqlite_test04``.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import argparse
import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import uuid

from latka_jazn.tools.memory_rebuild_app.report_sanitizer import write_report_pair
from latka_jazn.tools.memory_rebuild_app.read_only_validation import promotion_ledger_validation
from latka_jazn.tools.memory_rebuild_app.source_detection import probe_source
from latka_jazn.tools.memory_rebuild_app.runtime_sync import sync_runtime

TOOL_VERSION = "memory-rebuild/v16.0"
STAGE4_SCHEMA_VERSION = "jazn_memory_rebuild_stage4/v16"
_STAGE4_COMMAND = "stage4"

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _split_labels(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = [str(item).strip() for item in value]
    else:
        text = str(value).replace(";", ",")
        raw = [part.strip() for part in text.split(",")]
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _read_json_small(path: Path, max_bytes: int = 32 * 1024 * 1024) -> Any | None:
    if not path.is_file() or path.stat().st_size > max_bytes:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError, OSError):
        return None


def _probe_source_kind(path: Path) -> str:
    return probe_source(path).kind


@dataclass(slots=True)
class SourceInfo:
    path: str
    kind: str
    size_bytes: int
    sha256: str
    ordinal: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _discover_sources(
    source_dirs: Iterable[Path],
    *,
    chats: Iterable[Path],
    journals: Iterable[Path],
    music: Iterable[Path],
    legacy_dbs: Iterable[Path],
    recursive: bool,
) -> list[tuple[Path, str]]:
    ordered: list[tuple[Path, str]] = []
    for path in chats:
        ordered.append((Path(path).expanduser().resolve(), "chat"))
    for path in journals:
        ordered.append((Path(path).expanduser().resolve(), "journal"))
    for path in music:
        ordered.append((Path(path).expanduser().resolve(), "music"))
    for path in legacy_dbs:
        ordered.append((Path(path).expanduser().resolve(), "legacy_sqlite"))

    patterns = ("*.html", "*.htm", "*.zip", "*.json", "*.jsonl", "*.ndjson")
    for raw_root in source_dirs:
        root = Path(raw_root).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        candidates: list[Path] = []
        for pattern in patterns:
            candidates.extend(root.rglob(pattern) if recursive else root.glob(pattern))
        for path in sorted(set(candidates), key=lambda item: str(item).casefold()):
            kind = _probe_source_kind(path)
            if kind in {"chat", "journal", "music"}:
                ordered.append((path.resolve(), kind))

    seen: set[str] = set()
    result: list[tuple[Path, str]] = []
    for path, kind in ordered:
        if not path.is_file():
            raise FileNotFoundError(path)
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        result.append((path, kind))
    return result


def _source_manifest(sources: list[tuple[Path, str]]) -> list[SourceInfo]:
    manifest: list[SourceInfo] = []
    for ordinal, (path, kind) in enumerate(sources, 1):
        manifest.append(SourceInfo(str(path), kind, path.stat().st_size, _sha256_file(path), ordinal))
    return manifest


_STAGE4_SQL = r"""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS stage4_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stage4_sources(
  source_id TEXT PRIMARY KEY,
  source_sha256 TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_path TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  imported_at_utc TEXT NOT NULL,
  record_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  UNIQUE(source_sha256,source_kind)
);
CREATE TABLE IF NOT EXISTS music_analyses(
  analysis_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_record_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  title TEXT NOT NULL,
  emotions_json TEXT NOT NULL,
  genre TEXT NOT NULL,
  topics TEXT NOT NULL,
  book_relation TEXT NOT NULL,
  analysis_text TEXT NOT NULL,
  emotion_mirror TEXT NOT NULL,
  reflection TEXT NOT NULL,
  self_affect TEXT NOT NULL,
  introspection TEXT NOT NULL,
  summary TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  truth_status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  UNIQUE(source_id,source_record_id),
  FOREIGN KEY(source_id) REFERENCES stage4_sources(source_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_music_title ON music_analyses(title);
CREATE INDEX IF NOT EXISTS idx_music_truth ON music_analyses(truth_status);
CREATE TABLE IF NOT EXISTS affective_observations(
  affect_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_sha256 TEXT,
  event_time TEXT,
  emotions_json TEXT NOT NULL,
  feelings_json TEXT NOT NULL,
  impressions_json TEXT NOT NULL,
  reflection TEXT NOT NULL,
  context TEXT NOT NULL,
  truth_status TEXT NOT NULL,
  confidence REAL NOT NULL CHECK(confidence BETWEEN 0.0 AND 1.0),
  importance REAL NOT NULL CHECK(importance BETWEEN 0.0 AND 1.0),
  truth_boundary TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_affect_event_time ON affective_observations(event_time);
CREATE INDEX IF NOT EXISTS idx_affect_source ON affective_observations(source_type,source_id);
CREATE INDEX IF NOT EXISTS idx_affect_truth ON affective_observations(truth_status,status);
CREATE TABLE IF NOT EXISTS stage4_runs(
  run_id TEXT PRIMARY KEY,
  operation TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  completed_at_utc TEXT,
  target_database TEXT NOT NULL,
  source_manifest_sha256 TEXT NOT NULL,
  status TEXT NOT NULL,
  report_json TEXT NOT NULL
);
"""


TRUTH_BOUNDARY_AFFECT = (
    "Affective observation is a source-grounded operational/modelled state record. "
    "It preserves reported emotions, feelings, impressions and reflections but does not prove "
    "biological sensation, phenomenal consciousness or continuous background experience."
)


class Stage4Extension:
    def __init__(self, database: Path) -> None:
        self.database = Path(database).resolve()

    @contextlib.contextmanager
    def connect(self):
        con = sqlite3.connect(self.database, timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.executescript(_STAGE4_SQL)
            con.execute("INSERT OR REPLACE INTO stage4_meta(key,value) VALUES('schema_version',?)", (STAGE4_SCHEMA_VERSION,))
            con.execute("INSERT OR REPLACE INTO stage4_meta(key,value) VALUES('truth_boundary',?)", (TRUTH_BOUNDARY_AFFECT,))
            con.execute("INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('stage4_extension_schema_version',?)", (STAGE4_SCHEMA_VERSION,))

    def register_source(self, info: SourceInfo, record_count: int, status: str = "imported") -> str:
        source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"stage4-source:{info.kind}:{info.sha256}"))
        with self.connect() as con:
            con.execute(
                """INSERT INTO stage4_sources(source_id,source_sha256,source_kind,source_path,size_bytes,imported_at_utc,record_count,status)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(source_sha256,source_kind) DO UPDATE SET
                     source_path=excluded.source_path,size_bytes=excluded.size_bytes,
                     record_count=MAX(stage4_sources.record_count,excluded.record_count),status=excluded.status""",
                (source_id, info.sha256, info.kind, info.path, info.size_bytes, _utc_now(), int(record_count), status),
            )
        return source_id

    def import_music(self, path: Path, info: SourceInfo) -> dict[str, Any]:
        from latka_jazn.tools.memory_rebuild_journal import JournalReader, JournalStore

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        analyses = payload.get("analizy") if isinstance(payload, dict) else None
        if not isinstance(analyses, list):
            raise ValueError(f"{path} nie ma tablicy 'analizy'.")
        source_id = self.register_source(info, len(analyses))
        inserted = updated = linked = affect_inserted = 0
        journal_rows: list[dict[str, Any]] = []
        now = _utc_now()
        with self.connect() as con:
            for ordinal, raw in enumerate(analyses, 1):
                if not isinstance(raw, dict):
                    continue
                number = raw.get("numer", ordinal)
                title = str(raw.get("tytul") or raw.get("tytuł") or f"Analiza utworu {number}").strip()
                source_record_id = str(number)
                emotions = _split_labels(raw.get("emocje"))
                structured = {
                    "genre": str(raw.get("styl_gatunek") or "").strip(),
                    "topics": str(raw.get("tematyka") or "").strip(),
                    "book_relation": str(raw.get("zwiazek_z_ksiazka") or "").strip(),
                    "analysis": str(raw.get("analiza") or "").strip(),
                    "emotion_mirror": str(raw.get("lustro_emocji_latki") or "").strip(),
                    "reflection": str(raw.get("refleksja_latki") or "").strip(),
                    "self_affect": str(raw.get("moje_odczucia_latki") or "").strip(),
                    "introspection": str(raw.get("notatka_introspekcyjna") or "").strip(),
                    "summary": str(raw.get("podsumowanie") or "").strip(),
                }
                content_sha = _sha_text(_canonical_json(raw))
                analysis_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"music-analysis:{info.sha256}:{source_record_id}:{content_sha}"))
                existing = con.execute("SELECT content_sha256 FROM music_analyses WHERE source_id=? AND source_record_id=?", (source_id, source_record_id)).fetchone()
                con.execute(
                    """INSERT INTO music_analyses(
                         analysis_id,source_id,source_record_id,ordinal,title,emotions_json,genre,topics,book_relation,
                         analysis_text,emotion_mirror,reflection,self_affect,introspection,summary,raw_json,content_sha256,
                         truth_status,created_at_utc,updated_at_utc)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'source_recorded',?,?)
                       ON CONFLICT(source_id,source_record_id) DO UPDATE SET
                         ordinal=excluded.ordinal,title=excluded.title,emotions_json=excluded.emotions_json,
                         genre=excluded.genre,topics=excluded.topics,book_relation=excluded.book_relation,
                         analysis_text=excluded.analysis_text,emotion_mirror=excluded.emotion_mirror,
                         reflection=excluded.reflection,self_affect=excluded.self_affect,introspection=excluded.introspection,
                         summary=excluded.summary,raw_json=excluded.raw_json,content_sha256=excluded.content_sha256,
                         truth_status=excluded.truth_status,updated_at_utc=excluded.updated_at_utc""",
                    (
                        analysis_id, source_id, source_record_id, ordinal, title, _canonical_json(emotions),
                        structured["genre"], structured["topics"], structured["book_relation"], structured["analysis"],
                        structured["emotion_mirror"], structured["reflection"], structured["self_affect"],
                        structured["introspection"], structured["summary"], _canonical_json(raw), content_sha, now, now,
                    ),
                )
                if existing is None:
                    inserted += 1
                elif str(existing[0]) == content_sha:
                    linked += 1
                else:
                    updated += 1

                affect_payload = {
                    "emotions": emotions,
                    "feelings": [structured["self_affect"]] if structured["self_affect"] else [],
                    "impressions": [structured["emotion_mirror"]] if structured["emotion_mirror"] else [],
                    "reflection": structured["reflection"],
                    "context": f"Analiza utworu: {title}",
                }
                if any((affect_payload["emotions"], affect_payload["feelings"], affect_payload["impressions"], affect_payload["reflection"])):
                    if self._insert_affect(
                        source_type="music_analysis", source_id=analysis_id, source_sha256=content_sha,
                        event_time=None, emotions=affect_payload["emotions"], feelings=affect_payload["feelings"],
                        impressions=affect_payload["impressions"], reflection=affect_payload["reflection"],
                        context=affect_payload["context"], truth_status="source_recorded", confidence=1.0,
                        importance=0.65, raw=raw, con=con,
                    ):
                        affect_inserted += 1

                journal_rows.append({
                    "id": f"music-analysis:{info.sha256}:{source_record_id}",
                    "type": "analiza_utworu",
                    "category": "muzyka",
                    "title": title,
                    "content": structured["analysis"] or structured["summary"],
                    "emocje": emotions,
                    "styl_gatunek": structured["genre"],
                    "tematyka": structured["topics"],
                    "zwiazek_z_ksiazka": structured["book_relation"],
                    "doświadczenie_latki": structured["emotion_mirror"],
                    "refleksja": structured["reflection"],
                    "emocje_latki": structured["self_affect"],
                    "notatka_introspekcyjna": structured["introspection"],
                    "podsumowanie": structured["summary"],
                    "truth_status": "source_recorded",
                    "granica_prawdy": TRUTH_BOUNDARY_AFFECT,
                    "source": "source_recorded",
                    "source_sha256": info.sha256,
                })

        with tempfile.TemporaryDirectory(prefix="jazn-music-journal-") as tmp:
            normalized = Path(tmp) / "music_analyses_as_journal.json"
            normalized.write_text(json.dumps({"meta": {"source": str(path), "sha256": info.sha256}, "entries": journal_rows}, ensure_ascii=False), encoding="utf-8")
            reader = JournalReader(normalized)
            with JournalStore(self.database) as journal:
                journal_result = journal.import_reader(reader, dry_run=False)
        return {
            "ok": True, "status": "imported", "source": str(path), "source_sha256": info.sha256,
            "analyses_seen": len(analyses), "inserted": inserted, "updated": updated, "linked_existing": linked,
            "affective_inserted": affect_inserted, "journal_projection": journal_result,
        }

    def _insert_affect(
        self, *, source_type: str, source_id: str, source_sha256: str | None, event_time: str | None,
        emotions: Iterable[str], feelings: Iterable[str], impressions: Iterable[str], reflection: str,
        context: str, truth_status: str, confidence: float, importance: float, raw: dict[str, Any],
        con: sqlite3.Connection | None = None,
    ) -> bool:
        payload = {
            "source_type": source_type, "source_id": source_id, "source_sha256": source_sha256,
            "event_time": event_time, "emotions": list(emotions), "feelings": list(feelings),
            "impressions": list(impressions), "reflection": reflection, "context": context,
            "truth_status": truth_status,
        }
        content_sha = _sha_text(_canonical_json(payload))
        affect_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"affect:{source_type}:{source_id}:{content_sha}"))
        owns = con is None
        if con is None:
            con = sqlite3.connect(self.database, timeout=30)
            con.execute("PRAGMA foreign_keys=ON")
        try:
            existing = con.execute(
                "SELECT content_sha256 FROM affective_observations WHERE affect_id=?", (affect_id,)
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != content_sha:
                    raise ValueError("affective observation key collision with different content")
                if owns:
                    con.commit()
                return False
            con.execute(
                """INSERT INTO affective_observations(
                     affect_id,source_type,source_id,source_sha256,event_time,emotions_json,feelings_json,
                     impressions_json,reflection,context,truth_status,confidence,importance,truth_boundary,
                     raw_json,content_sha256,created_at_utc,status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active')""",
                (
                    affect_id, source_type, source_id, source_sha256, event_time,
                    _canonical_json(list(emotions)), _canonical_json(list(feelings)), _canonical_json(list(impressions)),
                    reflection, context, truth_status, max(0.0, min(1.0, float(confidence))),
                    max(0.0, min(1.0, float(importance))), TRUTH_BOUNDARY_AFFECT, _canonical_json(raw), content_sha, _utc_now(),
                ),
            )
            if owns:
                con.commit()
            return True
        finally:
            if owns:
                con.close()

    def derive_affect_from_journal(self) -> dict[str, int]:
        inserted = seen = 0
        with self.connect() as con:
            rows = con.execute(
                "SELECT entry_id,source_record_id,raw_json,truth_status,event_time_start,content_sha256,title,summary FROM journal_entries WHERE status='active' ORDER BY entry_id"
            ).fetchall()
            for row in rows:
                seen += 1
                try:
                    raw = json.loads(str(row["raw_json"]))
                except (TypeError, json.JSONDecodeError):
                    raw = {}
                if not isinstance(raw, dict):
                    raw = {}
                emotions = _split_labels(raw.get("emocje") or raw.get("emotions") or raw.get("emocje_latki"))
                feelings = _split_labels(raw.get("uczucia") or raw.get("feelings") or raw.get("moje_odczucia_latki"))
                impressions = _split_labels(raw.get("wrażenia") or raw.get("wrazenia") or raw.get("impressions") or raw.get("doświadczenie_latki") or raw.get("doswiadczenie_latki"))
                reflection = str(raw.get("refleksja") or raw.get("reflection") or raw.get("notatka_introspekcyjna") or "").strip()
                type_label = str(raw.get("typ") or raw.get("type") or raw.get("category") or raw.get("kategoria") or "").casefold()
                affective_type = any(marker in type_label for marker in ("emoc", "uczuc", "refleks", "introspek", "wspomn", "przeży", "przezy", "wraż", "wraz"))
                if not any((emotions, feelings, impressions, reflection)) and not affective_type:
                    continue
                context = str(row["title"] or row["summary"] or "Dziennik Jaźni")
                if self._insert_affect(
                    source_type="journal_entry", source_id=str(row["entry_id"]), source_sha256=str(row["content_sha256"]),
                    event_time=str(row["event_time_start"] or "") or None, emotions=emotions, feelings=feelings,
                    impressions=impressions, reflection=reflection, context=context,
                    truth_status=str(row["truth_status"] or "inferred"), confidence=1.0 if row["truth_status"] in {"source_recorded", "user_confirmed"} else 0.7,
                    importance=float(raw.get("importance", raw.get("ważność", raw.get("waznosc", 0.6))) or 0.6), raw=raw, con=con,
                ):
                    inserted += 1
        return {"journal_entries_seen": seen, "affective_inserted": inserted}

    def append_affect(self, payload: dict[str, Any]) -> dict[str, Any]:
        from latka_jazn.tools.memory_rebuild_journal import JournalReader, JournalStore

        source_type = str(payload.get("source_type") or "runtime_affect").strip()
        source_id = str(payload.get("source_id") or uuid.uuid4()).strip()
        source_sha = str(payload.get("source_sha256") or "").strip() or None
        event_time = str(payload.get("event_time") or _utc_now()).strip()
        emotions = _split_labels(payload.get("emotions"))
        feelings = _split_labels(payload.get("feelings"))
        impressions = _split_labels(payload.get("impressions"))
        reflection = str(payload.get("reflection") or "").strip()
        context = str(payload.get("context") or "Bieżący stan afektywny").strip()
        truth_status = str(payload.get("truth_status") or "source_recorded").strip()
        confidence = float(payload.get("confidence", 1.0))
        importance = float(payload.get("importance", 0.6))
        inserted = self._insert_affect(
            source_type=source_type, source_id=source_id, source_sha256=source_sha, event_time=event_time,
            emotions=emotions, feelings=feelings, impressions=impressions, reflection=reflection, context=context,
            truth_status=truth_status, confidence=confidence, importance=importance, raw=payload,
        )
        journal_entry = {
            "id": f"affect:{source_type}:{source_id}", "timestamp": event_time,
            "type": "emocje", "category": "dziennik Jaźni", "title": context,
            "content": reflection or "; ".join(emotions + feelings + impressions),
            "emocje": emotions, "uczucia": feelings, "wrażenia": impressions,
            "refleksja": reflection, "truth_status": truth_status,
            "granica_prawdy": TRUTH_BOUNDARY_AFFECT, "source": "source_recorded",
        }
        with tempfile.TemporaryDirectory(prefix="jazn-affect-journal-") as tmp:
            temp = Path(tmp) / "affect.json"
            temp.write_text(json.dumps({"entries": [journal_entry]}, ensure_ascii=False), encoding="utf-8")
            with JournalStore(self.database) as journal:
                journal_result = journal.import_reader(JournalReader(temp), dry_run=False)
        return {"ok": True, "inserted": inserted, "journal_projection": journal_result}

    def stats(self) -> dict[str, int]:
        if not self.database.is_file():
            return {"stage4_sources": 0, "music_analyses": 0, "affective_observations": 0, "stage4_runs": 0}
        with sqlite3.connect(f"file:{self.database.as_posix()}?mode=ro", uri=True, timeout=30) as con:
            con.row_factory = sqlite3.Row
            names = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "stage4_sources" not in names:
                return {"stage4_sources": 0, "music_analyses": 0, "affective_observations": 0, "stage4_runs": 0}
            return {
                "stage4_sources": int(con.execute("SELECT COUNT(*) FROM stage4_sources").fetchone()[0]),
                "music_analyses": int(con.execute("SELECT COUNT(*) FROM music_analyses").fetchone()[0]),
                "affective_observations": int(con.execute("SELECT COUNT(*) FROM affective_observations WHERE status='active'").fetchone()[0]),
                "stage4_runs": int(con.execute("SELECT COUNT(*) FROM stage4_runs").fetchone()[0]),
            }

    def validate(self) -> dict[str, Any]:
        if not self.database.is_file():
            return {"ok": False, "reason": "database_missing", "schema_version": STAGE4_SCHEMA_VERSION}
        with sqlite3.connect(f"file:{self.database.as_posix()}?mode=ro", uri=True, timeout=30) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            names = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            required = {"music_analyses", "affective_observations", "stage4_sources", "stage4_runs"}
            if not required.issubset(names):
                return {"ok": False, "reason": "stage4_schema_missing", "missing_tables": sorted(required - names), "schema_version": STAGE4_SCHEMA_VERSION}
            bad_music_hashes = 0
            for row in con.execute("SELECT raw_json,content_sha256 FROM music_analyses"):
                try:
                    raw = json.loads(str(row[0]))
                except json.JSONDecodeError:
                    bad_music_hashes += 1
                    continue
                if _sha_text(_canonical_json(raw)) != str(row[1]):
                    bad_music_hashes += 1
            bad_affect_hashes = 0
            for row in con.execute("SELECT source_type,source_id,source_sha256,event_time,emotions_json,feelings_json,impressions_json,reflection,context,truth_status,content_sha256 FROM affective_observations WHERE status='active'"):
                payload = {
                    "source_type": row[0], "source_id": row[1], "source_sha256": row[2], "event_time": row[3],
                    "emotions": json.loads(row[4]), "feelings": json.loads(row[5]), "impressions": json.loads(row[6]),
                    "reflection": row[7], "context": row[8], "truth_status": row[9],
                }
                if _sha_text(_canonical_json(payload)) != str(row[10]):
                    bad_affect_hashes += 1
            foreign_keys = [tuple(row) for row in con.execute("PRAGMA foreign_key_check")]
        stats = self.stats()
        return {
            "ok": bad_music_hashes == 0 and bad_affect_hashes == 0 and not foreign_keys,
            "schema_version": STAGE4_SCHEMA_VERSION,
            "stats": stats,
            "bad_music_hashes": bad_music_hashes,
            "bad_affect_hashes": bad_affect_hashes,
            "foreign_key_violations": foreign_keys,
            "truth_boundary": TRUTH_BOUNDARY_AFFECT,
        }


@dataclass(slots=True)
class Stage4Options:
    database: Path
    sources: list[tuple[Path, str]]
    manifest: list[SourceInfo]
    baselines: list[Path]
    report_dir: Path
    full_validation: bool
    generate_candidates: bool
    candidate_limit: int | None


def _manifest_hash(manifest: list[SourceInfo]) -> str:
    return _sha_text(_canonical_json([item.to_dict() for item in manifest]))


def _prepare_options(args: argparse.Namespace) -> Stage4Options:
    sources = _discover_sources(
        args.source_dir or [], chats=args.chat or [], journals=args.journal or [], music=args.music or [],
        legacy_dbs=args.legacy_db or [], recursive=bool(args.recursive),
    )
    if not sources:
        raise ValueError("Nie znaleziono żadnych źródeł ChatGPT/dziennika/analiz utworów.")
    manifest = _source_manifest(sources)
    database = Path(args.database).expanduser().resolve()
    report_dir = Path(args.report_dir or (database.parent / "memory_rebuild_reports")).expanduser().resolve()
    baselines = [Path(item).expanduser().resolve() for item in (args.baseline or [])]
    return Stage4Options(
        database=database, sources=sources, manifest=manifest, baselines=baselines, report_dir=report_dir,
        full_validation=not bool(args.quick_validation), generate_candidates=bool(args.generate_candidates),
        candidate_limit=(None if int(args.candidate_limit or 0) <= 0 else int(args.candidate_limit)),
    )


def _copy_sqlite_snapshot(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    src_uri = f"file:{source.as_posix()}?mode=ro"
    with sqlite3.connect(src_uri, uri=True, timeout=30) as src, sqlite3.connect(target, timeout=30) as dst:
        src.backup(dst, pages=256, sleep=0.05)


def _run_import_pipeline(database: Path, options: Stage4Options) -> dict[str, Any]:
    from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase

    store = UnifiedMemoryDatabase(database)
    store.initialize()
    extension = Stage4Extension(database)
    extension.initialize()
    manifest_by_path = {item.path: item for item in options.manifest}
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    # L0 conversations first, journal second, structured media last.
    ordered = sorted(options.sources, key=lambda item: {"legacy_sqlite": 0, "chat": 1, "journal": 2, "music": 3}.get(item[1], 9))
    for path, kind in ordered:
        info = manifest_by_path[str(path)]
        try:
            if kind in {"legacy_sqlite", "chat", "journal"}:
                result = store.import_source(path, dry_run=False, full_validation=False).to_dict()
                extension.register_source(info, int(result.get("details", {}).get("conversations_seen", 0) or result.get("details", {}).get("entries_seen", 0) or 0), str(result.get("status", "imported")))
            elif kind == "music":
                result = extension.import_music(path, info)
            else:
                continue
            results.append({"source": str(path), "kind": kind, "result": result})
        except Exception as exc:
            errors.append({"source": str(path), "kind": kind, "error_type": type(exc).__name__, "error": str(exc)})
            break

    affect_result = extension.derive_affect_from_journal() if not errors else {"journal_entries_seen": 0, "affective_inserted": 0}
    candidate_result: dict[str, Any] | None = None
    if not errors and options.generate_candidates:
        candidate_result = store.generate_candidates(chats=True, journal=True, limit=options.candidate_limit)

    validation = store.validate(full=options.full_validation) if not errors else {"ok": False, "reason": "import_error"}
    extension_validation = extension.validate() if not errors else {"ok": False, "reason": "import_error"}
    from latka_jazn.tools.memory_rebuild_app.test_profiles import run_test_profile
    test03 = run_test_profile(database, "test03", baselines=options.baselines, full_validation=options.full_validation) if not errors else {"ok": False, "reason": "import_error"}
    promotion_validation = promotion_ledger_validation(database) if not errors else {"ok": False, "reason": "import_error"}
    return {
        "ok": not errors and bool(validation.get("ok")) and bool(extension_validation.get("ok")) and bool(test03.get("ok")),
        "database": str(database), "results": results, "errors": errors,
        "affective_projection": affect_result, "candidate_generation": candidate_result,
        "validation": validation, "stage4_validation": extension_validation, "test03_preflight": test03,
        "promotion_ledger_validation": promotion_validation,
        "automatic_l2": promotion_validation.get("automatic_l2"),
        "automatic_l3": promotion_validation.get("automatic_l3"),
    }


def _stage4_plan(options: Stage4Options) -> dict[str, Any]:
    options.report_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jazn-stage4-plan-", dir=options.database.parent if options.database.parent.exists() else None) as tmp:
        preview = Path(tmp) / options.database.name
        if options.database.exists():
            _copy_sqlite_snapshot(options.database, preview)
        result = _run_import_pipeline(preview, options)
    payload = {
        "ok": bool(result.get("ok")), "status": "plan_only", "target_database": str(options.database),
        "source_manifest_sha256": _manifest_hash(options.manifest),
        "sources": [item.to_dict() for item in options.manifest], "preview_result": result,
        "target_modified": False,
        "automatic_l2": (result.get("promotion_ledger_validation") or {}).get("automatic_l2"),
        "automatic_l3": (result.get("promotion_ledger_validation") or {}).get("automatic_l3"),
    }
    payload["reports"] = write_report_pair(options.report_dir, "stage4-plan", payload)
    write_report_pair(options.report_dir, "stage4-source-manifest", {"schema_version": STAGE4_SCHEMA_VERSION, "sources": [item.to_dict() for item in options.manifest]})
    return payload


def _stage4_build(options: Stage4Options, *, resume: bool, overwrite: bool) -> dict[str, Any]:
    from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase

    target = options.database
    target.parent.mkdir(parents=True, exist_ok=True)
    options.report_dir.mkdir(parents=True, exist_ok=True)
    if target.exists() and not (resume or overwrite):
        raise FileExistsError(f"{target} już istnieje. Użyj --resume albo --overwrite.")
    if resume and overwrite:
        raise ValueError("--resume i --overwrite są wzajemnie wykluczające.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path: Path | None = None
    if target.exists():
        backup_dir = options.report_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{target.stem}.pre-stage4-{timestamp}{target.suffix}"
        UnifiedMemoryDatabase(target).backup(backup_path)

    staging = target.with_name(target.name + f".stage4-staging-{uuid.uuid4().hex}.sqlite3")
    if staging.exists():
        staging.unlink()
    if resume and target.exists():
        _copy_sqlite_snapshot(target, staging)

    run_id = str(uuid.uuid4())
    started = _utc_now()
    manifest_sha = _manifest_hash(options.manifest)
    try:
        result = _run_import_pipeline(staging, options)
        if not result.get("ok"):
            raise RuntimeError("Stage4 validation failed; target database was not replaced.")
        # final snapshot is itself validated before publication
        final_store = UnifiedMemoryDatabase(staging)
        final_validation = final_store.validate(full=True)
        if not final_validation.get("ok"):
            raise RuntimeError("Final full SQLite validation failed.")
        extension = Stage4Extension(staging)
        report = {
            "schema_version": STAGE4_SCHEMA_VERSION, "ok": True, "status": "ready_to_publish",
            "run_id": run_id, "started_at_utc": started, "completed_at_utc": _utc_now(),
            "target_database": str(target), "staging_database": str(staging),
            "backup": str(backup_path) if backup_path else None,
            "source_manifest_sha256": manifest_sha, "sources": [item.to_dict() for item in options.manifest],
            "pipeline": result, "final_validation": final_validation, "stage4_stats": extension.stats(),
            "promotion_ledger_validation": result.get("promotion_ledger_validation"),
            "automatic_l2": (result.get("promotion_ledger_validation") or {}).get("automatic_l2"),
            "automatic_l3": (result.get("promotion_ledger_validation") or {}).get("automatic_l3"),
        }
        with extension.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO stage4_runs(run_id,operation,started_at_utc,completed_at_utc,target_database,source_manifest_sha256,status,report_json) VALUES(?,?,?,?,?,?,?,?)",
                (run_id, "build", started, report["completed_at_utc"], str(target), manifest_sha, "published", _canonical_json(report)),
            )
        # Validate once more after run ledger write.
        if not UnifiedMemoryDatabase(staging).validate(full=True).get("ok"):
            raise RuntimeError("Post-ledger validation failed.")
        os.replace(staging, target)
        report["status"] = "published"
        report["database_sha256"] = _sha256_file(target)
        report["database_size_bytes"] = target.stat().st_size
        report["reports"] = write_report_pair(options.report_dir, f"stage4-build-{run_id}", report)
        write_report_pair(options.report_dir, "stage4-last-build", report)
        write_report_pair(options.report_dir, "stage4-source-manifest", {"schema_version": STAGE4_SCHEMA_VERSION, "source_manifest_sha256": manifest_sha, "sources": [item.to_dict() for item in options.manifest]})
        return report
    except BaseException:
        with contextlib.suppress(OSError):
            staging.unlink()
        raise


def _stage4_validate(database: Path, baselines: list[Path], full: bool = True) -> dict[str, Any]:
    from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase
    from latka_jazn.tools.memory_rebuild_app.test_profiles import run_test_profile

    store = UnifiedMemoryDatabase(database)
    validation = store.validate(full=full)
    extension = Stage4Extension(database)
    ext_validation = extension.validate()
    test03 = run_test_profile(database, "test03", baselines=baselines, full_validation=full)
    return {
        "ok": bool(validation.get("ok")) and bool(ext_validation.get("ok")) and bool(test03.get("ok")),
        "database": str(database), "validation": validation, "stage4_validation": ext_validation,
        "test03_preflight": test03,
        "full_test04": "run `memory_rebuild.py test04 ...` for the canonical acceptance protocol",
    }


def _add_common_sources(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--database", required=True, type=Path, help="Docelowy memory_jazn.sqlite3.")
    parser.add_argument("--source-dir", action="append", type=Path, default=[], help="Katalog do automatycznego wykrycia HTML/JSON/ZIP/dziennika/analiz.")
    parser.add_argument("--chat", action="append", type=Path, default=[], help="Jawne źródło rozmów ChatGPT; można podać wielokrotnie.")
    parser.add_argument("--journal", action="append", type=Path, default=[], help="Jawny dziennik JSON/JSONL; można podać wielokrotnie.")
    parser.add_argument("--music", action="append", type=Path, default=[], help="analizy_utworow.json; można podać wielokrotnie.")
    parser.add_argument("--legacy-db", action="append", type=Path, default=[], help="Jawna stara baza Test01–04/legacy do migracji; nie jest wykrywana automatycznie.")
    parser.add_argument("--baseline", action="append", type=Path, default=[], help="Baseline Test01–04 do testu braku regresji.")
    parser.add_argument("--report-dir", type=Path, help="Katalog raportów i backupów.")
    parser.add_argument("--recursive", action="store_true", help="Skanuj --source-dir rekursywnie.")
    parser.add_argument("--quick-validation", action="store_true", help="W planie użyj quick_check zamiast pełnego integrity_check.")
    parser.add_argument("--generate-candidates", action="store_true", help="Po pełnym L0 utwórz pending_review; bez automatycznej promocji.")
    parser.add_argument("--candidate-limit", type=int, default=0)


def _stage4_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory_rebuild.py stage4", description="Test04/Stage4: staging-first rebuild jednej bazy pamięci Jaźni.", allow_abbrev=False)
    parser.add_argument("--version", action="version", version=TOOL_VERSION)
    sub = parser.add_subparsers(dest="stage4_command", required=True)

    plan = sub.add_parser("plan", help="Pełna symulacja na tymczasowej bazie; docelowa baza nie jest modyfikowana.")
    _add_common_sources(plan)

    build = sub.add_parser("build", help="Zbuduj staging, zweryfikuj i atomowo opublikuj memory_jazn.sqlite3.")
    _add_common_sources(build)
    group = build.add_mutually_exclusive_group()
    group.add_argument("--resume", action="store_true", help="Zacznij od spójnego snapshotu istniejącej bazy.")
    group.add_argument("--overwrite", action="store_true", help="Zbuduj od zera; istniejąca baza zostanie najpierw zbackupowana.")

    validate = sub.add_parser("validate", help="Read-only walidacja unified DB + Stage4 + profil Test03; pełny Test04 uruchamiaj osobno.")
    validate.add_argument("--database", required=True, type=Path)
    validate.add_argument("--baseline", action="append", type=Path, default=[])
    validate.add_argument("--quick", action="store_true")

    sync = sub.add_parser("sync-runtime", help="Przyrostowo wciągnij runtime memory/raw/dziennik.json i memory/layered/*.jsonl do istniejącej unified DB.")
    sync.add_argument("--database", required=True, type=Path)
    sync.add_argument("--runtime-root", required=True, type=Path)
    sync.add_argument("--baseline", action="append", type=Path, default=[])
    sync.add_argument("--report-dir", type=Path)
    sync.add_argument("--quick-validation", action="store_true")
    sync.add_argument("--generate-candidates", action="store_true")
    sync.add_argument("--candidate-limit", type=int, default=0)

    affect = sub.add_parser("append-affect", help="Dopisz źródłowo ugruntowany stan afektywny do tej samej bazy i dziennika L0.")
    affect.add_argument("--database", required=True, type=Path)
    affect.add_argument("--stdin-json", action="store_true", help="Czytaj cały rekord JSON ze stdin.")
    affect.add_argument("--source-type", default="runtime_affect")
    affect.add_argument("--source-id")
    affect.add_argument("--source-sha256")
    affect.add_argument("--event-time")
    affect.add_argument("--emotions", action="append", default=[])
    affect.add_argument("--feelings", action="append", default=[])
    affect.add_argument("--impressions", action="append", default=[])
    affect.add_argument("--reflection", default="")
    affect.add_argument("--context", default="Bieżący stan afektywny")
    affect.add_argument("--truth-status", default="source_recorded")
    affect.add_argument("--confidence", type=float, default=1.0)
    affect.add_argument("--importance", type=float, default=0.6)

    return parser


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _run_stage4(args: list[str]) -> int:
    parser = _stage4_parser()
    ns = parser.parse_args(args[1:] if args and args[0] == _STAGE4_COMMAND else args)
    try:
        if ns.stage4_command == "plan":
            payload = _stage4_plan(_prepare_options(ns))
        elif ns.stage4_command == "build":
            payload = _stage4_build(_prepare_options(ns), resume=ns.resume, overwrite=ns.overwrite)
        elif ns.stage4_command == "validate":
            payload = _stage4_validate(Path(ns.database).expanduser().resolve(), [Path(item).expanduser().resolve() for item in ns.baseline], full=not ns.quick)
        elif ns.stage4_command == "sync-runtime":
            runtime_root = Path(ns.runtime_root).expanduser().resolve()
            database = Path(ns.database).expanduser().resolve()
            payload = sync_runtime(database, runtime_root, full_validation=not ns.quick_validation)
            report_dir = Path(ns.report_dir or (database.parent / "memory_rebuild_reports")).expanduser().resolve()
            payload["reports"] = write_report_pair(report_dir, "runtime-sync", payload)
        elif ns.stage4_command == "append-affect":
            database = Path(ns.database).expanduser().resolve()
            from latka_jazn.tools.memory_rebuild_app.unified_memory import UnifiedMemoryDatabase
            UnifiedMemoryDatabase(database).initialize()
            extension = Stage4Extension(database)
            extension.initialize()
            if ns.stdin_json:
                payload_in = json.load(sys.stdin)
                if not isinstance(payload_in, dict):
                    raise ValueError("stdin JSON musi być obiektem.")
            else:
                payload_in = {
                    "source_type": ns.source_type, "source_id": ns.source_id or str(uuid.uuid4()),
                    "source_sha256": ns.source_sha256, "event_time": ns.event_time or _utc_now(),
                    "emotions": ns.emotions, "feelings": ns.feelings, "impressions": ns.impressions,
                    "reflection": ns.reflection, "context": ns.context, "truth_status": ns.truth_status,
                    "confidence": ns.confidence, "importance": ns.importance,
                }
            payload = extension.append_affect(payload_in)
            payload["validation"] = _stage4_validate(database, [], full=False)
        else:
            raise AssertionError(ns.stage4_command)
        _emit(payload)
        return 0 if payload.get("ok", True) else 2
    except KeyboardInterrupt:
        _emit({"ok": False, "status": "cancelled"})
        return 130
    except Exception as exc:
        _emit({"ok": False, "error_type": type(exc).__name__, "error": str(exc)})
        return 1



def main(argv: Sequence[str] | None = None) -> int:
    return _run_stage4(list(sys.argv[1:] if argv is None else argv))


__all__ = ["TOOL_VERSION", "STAGE4_SCHEMA_VERSION", "Stage4Extension", "main"]
