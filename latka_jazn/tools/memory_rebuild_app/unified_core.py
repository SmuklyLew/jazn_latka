from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Literal
import os
import sqlite3
import tempfile

from latka_jazn.memory.memory_tier_core_store import MemoryTierCoreStore
from latka_jazn.tools.chat_export_importer import ChatExportImporter
from latka_jazn.tools.chat_export_reader import probe_json_source_kind, sha256_file
from latka_jazn.tools.chat_export_store import ChatExportArchiveStore
from latka_jazn.tools.memory_rebuild_catalog import CatalogStore
from latka_jazn.tools.memory_rebuild_experience import ExperienceStore
from latka_jazn.tools.memory_rebuild_journal import JournalReader, JournalStore

from .attachment_support import install_attachment_metadata_support
from .html_import import import_chat_html
from .unified_contracts import UnifiedMixinHost
from .unified_schema import (
    CANONICAL_DATABASE_NAME, EXTRA_SCHEMA, UNIFIED_SCHEMA_VERSION, UnifiedImportResult, quote, utc_now,
)

install_attachment_metadata_support()


class _ClosingSQLiteConnection(sqlite3.Connection):
    """Commit or roll back like sqlite3.Connection, then always release the file handle."""

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


class UnifiedCoreMixin(UnifiedMixinHost):
    path: Path

    def initialize(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for store_type in (ChatExportArchiveStore, JournalStore, ExperienceStore, MemoryTierCoreStore, CatalogStore):
            store = store_type(self.path)
            store.close()
        with self.connect() as con:
            previous = con.execute(
                "SELECT value FROM unified_memory_meta WHERE key='schema_version'"
            ).fetchone() if "unified_memory_meta" in {
                str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            } else None
            con.executescript(EXTRA_SCHEMA)
            indexed = int(con.execute("SELECT COUNT(*) FROM memory_records_fts").fetchone()[0])
            records = int(con.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0])
            if previous is None or str(previous[0]) != UNIFIED_SCHEMA_VERSION or indexed != records:
                con.execute("INSERT INTO memory_records_fts(memory_records_fts) VALUES('rebuild')")
            con.execute("INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('schema_version',?)", (UNIFIED_SCHEMA_VERSION,))
            con.execute("INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('layout','single_physical_database')")
            con.execute(
                "INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('truth_boundary',?)",
                ("Rozmowy i dziennik są L0. Kandydaci wymagają przeglądu; L2/L3 wymagają osobnych decyzji i ledgerów.",),
            )
            con.execute("INSERT OR REPLACE INTO unified_memory_meta(key,value) VALUES('initialized_at_utc',?)", (utc_now(),))
            con.commit()
        return {"ok": True, "database": str(self.path), "schema_version": UNIFIED_SCHEMA_VERSION}

    def connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            con = sqlite3.connect(
                f"file:{self.path.as_posix()}?mode=ro",
                uri=True,
                timeout=30,
                factory=_ClosingSQLiteConnection,
            )
        else:
            con = sqlite3.connect(self.path, timeout=30, factory=_ClosingSQLiteConnection)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def checkpoint(self) -> None:
        if not self.path.exists():
            return
        with self.connect() as con:
            con.execute("PRAGMA wal_checkpoint(FULL)")

    def backup(self, output: str | Path) -> Path:
        self.initialize()
        self.checkpoint()
        target = Path(output).expanduser().resolve()
        if target.is_dir() or not target.suffix:
            target = target / CANONICAL_DATABASE_NAME
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        if temporary.exists():
            temporary.unlink()
        with self.connect(read_only=True) as source, sqlite3.connect(
            temporary,
            factory=_ClosingSQLiteConnection,
        ) as destination:
            source.backup(destination)
        os.replace(temporary, target)
        return target

    def import_source(self, source: str | Path, *, dry_run: bool = False, full_validation: bool = True) -> UnifiedImportResult:
        self.initialize()
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        suffix = path.suffix.lower()
        if path.is_dir():
            payload = ChatExportImporter().import_one(path, self.path, dry_run=dry_run, full_validation=full_validation).to_dict()
            return UnifiedImportResult(str(path), "chatgpt_export_directory", str(payload.get("status")), payload)
        if suffix in {".html", ".htm"}:
            payload = import_chat_html(path, self.path, dry_run=dry_run).to_dict()
            return UnifiedImportResult(str(path), "chatgpt_html", str(payload.get("mode")), payload)
        if suffix == ".zip":
            try:
                payload = ChatExportImporter().import_one(path, self.path, dry_run=dry_run, full_validation=full_validation).to_dict()
                return UnifiedImportResult(str(path), "chatgpt_export_zip", str(payload.get("status")), payload)
            except ValueError as exc:
                if "conversation JSON" not in str(exc) and "canonical conversations" not in str(exc):
                    raise
                payload = import_chat_html(path, self.path, dry_run=dry_run).to_dict()
                return UnifiedImportResult(str(path), "chatgpt_html_zip", str(payload.get("mode")), payload)
        if suffix == ".json" and probe_json_source_kind(path) == "conversation":
            payload = ChatExportImporter().import_one(path, self.path, dry_run=dry_run, full_validation=full_validation).to_dict()
            return UnifiedImportResult(str(path), "chatgpt_conversation_json", str(payload.get("status")), payload)
        if suffix in {".json", ".jsonl", ".ndjson"}:
            reader = JournalReader(path)
            with JournalStore(self.path) as store:
                payload = store.import_reader(reader, dry_run=dry_run)
            return UnifiedImportResult(str(path), "journal", str(payload.get("status")), payload)
        if suffix in {".sqlite", ".sqlite3", ".db"}:
            payload = self.migrate_databases([path], dry_run=dry_run)
            return UnifiedImportResult(str(path), "legacy_sqlite", str(payload.get("status")), payload)
        return UnifiedImportResult(str(path), "reference_only", "not_imported", {
            "ok": True, "status": "reference_only",
            "reason": "Typ pliku pozostaje źródłem referencyjnym; nie ma bezpiecznego importera do bazy pamięci.",
        })

    def _preview_import_sources(self, sources: list[str | Path], *, full_validation: bool) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="jazn-memory-plan-") as temporary_root:
            preview_path = Path(temporary_root) / CANONICAL_DATABASE_NAME
            preview = type(self)(preview_path)
            if self.path.exists():
                self.backup(preview_path)
            else:
                preview.initialize()
            payload = preview.import_sources(sources, dry_run=False, full_validation=full_validation)
            payload["dry_run"] = True
            payload["status"] = "plan_only"
            payload["database"] = str(self.path)
            payload["preview_database"] = "temporary_deleted_after_plan"
            for result in payload.get("results", []):
                result["planned_status"] = result.get("status")
                result["status"] = "planned"
            return payload

    def import_sources(self, sources: Iterable[str | Path], *, dry_run: bool = False, full_validation: bool = True) -> dict[str, Any]:
        source_list = list(sources)
        if dry_run:
            return self._preview_import_sources(source_list, full_validation=full_validation)
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for source in source_list:
            try:
                results.append(self.import_source(source, dry_run=False, full_validation=full_validation).to_dict())
            except Exception as exc:
                errors.append({"source": str(source), "error_type": type(exc).__name__, "error": str(exc)})
                break
        validation = self.validate(full=full_validation) if self.path.exists() else {"ok": not errors}
        return {
            "ok": not errors and bool(validation.get("ok")), "database": str(self.path), "dry_run": False,
            "results": results, "errors": errors, "validation": validation,
            "automatic_l2": False, "automatic_l3": False,
        }

    def stats(self) -> dict[str, int]:
        self.initialize()
        tables = (
            "import_sources", "conversations", "nodes", "fts_docs", "assets", "import_conflicts",
            "journal_sources", "journal_entries", "journal_revisions", "candidates", "experiences",
            "candidate_revisions", "candidate_evidence", "memory_records", "memory_evidence",
            "promotion_requests", "promotion_decisions", "promotion_ledger", "sources", "operations",
        )
        with self.connect(read_only=True) as con:
            result: dict[str, int] = {}
            for table in tables:
                exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                result[table] = int(con.execute(f"SELECT COUNT(*) FROM {quote(table)}").fetchone()[0]) if exists else 0
            return result

    def validate(self, *, full: bool = True) -> dict[str, Any]:
        self.initialize()
        self.checkpoint()
        with self.connect(read_only=True) as con:
            pragma = "integrity_check" if full else "quick_check"
            integrity_rows = [str(row[0]) for row in con.execute(f"PRAGMA {pragma}")]
            foreign_keys = [tuple(row) for row in con.execute("PRAGMA foreign_key_check")]
            meta = {str(row["key"]): str(row["value"]) for row in con.execute("SELECT key,value FROM unified_memory_meta")}
        ok = integrity_rows == ["ok"] and not foreign_keys and meta.get("schema_version") == UNIFIED_SCHEMA_VERSION
        return {
            "ok": ok, "database": str(self.path), "single_physical_database": True,
            "schema_version": meta.get("schema_version"), "validation_mode": pragma,
            "integrity": integrity_rows, "foreign_key_error_count": len(foreign_keys),
            "foreign_key_errors": foreign_keys[:100], "size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "sha256": sha256_file(self.path) if self.path.exists() else None, "stats": self.stats(),
        }
