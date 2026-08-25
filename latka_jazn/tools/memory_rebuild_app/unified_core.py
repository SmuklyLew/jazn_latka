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
from .read_only_validation import read_only_stats, validate_existing_database
from .source_detection import probe_source
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

    def schema_ready(self) -> bool:
        if not self.path.is_file():
            return False
        try:
            with sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, timeout=5) as con:
                row = con.execute(
                    "SELECT value FROM unified_memory_meta WHERE key='schema_version'"
                ).fetchone()
                return bool(row and str(row[0]) in {"jazn_unified_memory/v2.4", UNIFIED_SCHEMA_VERSION})
        except sqlite3.DatabaseError:
            return False

    def ensure_initialized(self) -> dict[str, Any]:
        if self.schema_ready():
            return {"ok": True, "database": str(self.path), "schema_version": UNIFIED_SCHEMA_VERSION, "already_initialized": True}
        return self.initialize()

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
        self.ensure_initialized()
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
        self.ensure_initialized()
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_dir():
            payload = ChatExportImporter().import_one(path, self.path, dry_run=dry_run, full_validation=full_validation).to_dict()
            return UnifiedImportResult(str(path), "chatgpt_export_directory", str(payload.get("status")), payload)

        probe = probe_source(path)
        kind = probe.kind
        suffix = path.suffix.lower()
        if kind == "chat":
            if suffix in {".html", ".htm"}:
                payload = import_chat_html(path, self.path, dry_run=dry_run).to_dict()
                return UnifiedImportResult(str(path), "chatgpt_html", str(payload.get("mode")), {**payload, "source_probe": probe.to_dict()})
            if suffix == ".zip":
                try:
                    payload = ChatExportImporter().import_one(path, self.path, dry_run=dry_run, full_validation=full_validation).to_dict()
                    return UnifiedImportResult(str(path), "chatgpt_export_zip", str(payload.get("status")), {**payload, "source_probe": probe.to_dict()})
                except ValueError as exc:
                    if "conversation JSON" not in str(exc) and "canonical conversations" not in str(exc):
                        raise
                    payload = import_chat_html(path, self.path, dry_run=dry_run).to_dict()
                    return UnifiedImportResult(str(path), "chatgpt_html_zip", str(payload.get("mode")), {**payload, "source_probe": probe.to_dict()})
            payload = ChatExportImporter().import_one(path, self.path, dry_run=dry_run, full_validation=full_validation).to_dict()
            return UnifiedImportResult(str(path), "chatgpt_conversation_json", str(payload.get("status")), {**payload, "source_probe": probe.to_dict()})
        if kind == "journal":
            reader = JournalReader(path)
            with JournalStore(self.path) as store:
                payload = store.import_reader(reader, dry_run=dry_run)
            return UnifiedImportResult(str(path), "journal", str(payload.get("status")), {**payload, "source_probe": probe.to_dict()})
        if kind == "legacy_sqlite":
            payload = self.migrate_databases([path], dry_run=dry_run)
            return UnifiedImportResult(str(path), "legacy_sqlite", str(payload.get("status")), {**payload, "source_probe": probe.to_dict()})
        return UnifiedImportResult(str(path), kind, "not_imported", {
            "ok": True,
            "status": "reference_only",
            "detected_kind": kind,
            "source_probe": probe.to_dict(),
            "reason": (
                "Źródło zostało sklasyfikowane schematowo, ale wymaga dedykowanego importera Stage4/sync-runtime; "
                "nie jest automatycznie traktowane jako dziennik ani eksport ChatGPT."
            ),
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
        """Return counts without creating, migrating, checkpointing or rebuilding the database."""
        return read_only_stats(self.path)

    def validate(self, *, full: bool = True) -> dict[str, Any]:
        """Strict read-only validation of an existing unified database.

        Repair/init is intentionally separate.  FTS5 integrity-check runs on a
        temporary SQLite backup snapshot, never on the database being assessed.
        """
        return validate_existing_database(self.path, full=full, include_fts=True)

    def repair_and_validate(self, *, full: bool = True) -> dict[str, Any]:
        """Explicit mutating maintenance path; never used by Test 01-04 profiles."""
        self.initialize()
        self.checkpoint()
        return validate_existing_database(self.path, full=full, include_fts=True)
