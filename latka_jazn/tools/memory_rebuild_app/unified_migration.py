from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import os
import sqlite3
import tempfile

from latka_jazn.tools.chat_export_reader import build_conversation_graph
from latka_jazn.tools.chat_export_store import ChatExportArchiveStore
from latka_jazn.tools.memory_rebuild_experience import ExperienceStore
from latka_jazn.tools.memory_rebuild_journal import JournalStore

from .unified_schema import CANONICAL_DATABASE_NAME, COPY_ORDER, LEGACY_DATABASE_NAMES, quote


class UnifiedMigrationMixin:
    path: Path

    def discover_legacy_databases(self, root: str | Path) -> list[Path]:
        base = Path(root).expanduser().resolve()
        if base.is_file():
            return [base] if base.name in LEGACY_DATABASE_NAMES else []
        found: list[Path] = []
        for name in LEGACY_DATABASE_NAMES:
            found.extend(path.resolve() for path in base.rglob(name) if path.is_file() and path.resolve() != self.path)
        seen: set[str] = set()
        result: list[Path] = []
        for path in found:
            key = os.path.normcase(str(path))
            if key not in seen:
                seen.add(key)
                result.append(path)
        return result

    def migrate_legacy_root(self, root: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
        return self.migrate_databases(self.discover_legacy_databases(root), dry_run=dry_run)

    def migrate_databases(self, databases: Iterable[str | Path], *, dry_run: bool = False) -> dict[str, Any]:
        paths = [Path(item).expanduser().resolve() for item in databases]
        paths = [item for item in paths if item.is_file() and item.resolve() != self.path]
        if dry_run:
            with tempfile.TemporaryDirectory(prefix="jazn-memory-migration-plan-") as temporary_root:
                preview_path = Path(temporary_root) / CANONICAL_DATABASE_NAME
                preview = type(self)(preview_path)
                if self.path.exists():
                    self.backup(preview_path)
                else:
                    preview.initialize()
                payload = preview._migrate_databases_impl(paths)
                payload["dry_run"] = True
                payload["status"] = "plan_only"
                payload["database"] = str(self.path)
                payload["preview_database"] = "temporary_deleted_after_plan"
                return payload
        return self._migrate_databases_impl(paths)

    def _migrate_databases_impl(self, paths: list[Path]) -> dict[str, Any]:
        self.initialize()
        plan: list[dict[str, Any]] = []
        copied: dict[str, int] = {}
        with self.connect() as con:
            target_tables = {str(row[0]): str(row[1] or "") for row in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
            for index, legacy in enumerate(paths):
                alias = f"legacy_{index}"
                con.execute(f"ATTACH DATABASE ? AS {quote(alias)}", (str(legacy),))
                try:
                    source_tables = {str(row[0]): str(row[1] or "") for row in con.execute(f"SELECT name,sql FROM {quote(alias)}.sqlite_master WHERE type='table'")}
                    con.execute("BEGIN IMMEDIATE")
                    for table in COPY_ORDER:
                        if table not in source_tables or table not in target_tables:
                            continue
                        if "VIRTUAL TABLE" in source_tables[table].upper() or table.startswith("sqlite_"):
                            continue
                        source_columns = [str(row[1]) for row in con.execute(f"PRAGMA {quote(alias)}.table_info({quote(table)})")]
                        target_columns = [str(row[1]) for row in con.execute(f"PRAGMA table_info({quote(table)})")]
                        columns = [item for item in target_columns if item in source_columns]
                        if not columns:
                            continue
                        count = int(con.execute(f"SELECT COUNT(*) FROM {quote(alias)}.{quote(table)}").fetchone()[0])
                        plan.append({"database": str(legacy), "table": table, "rows_seen": count, "columns": columns})
                        if count == 0:
                            continue
                        selected = ",".join(quote(item) for item in columns)
                        before = con.total_changes
                        con.execute(f"INSERT OR IGNORE INTO {quote(table)}({selected}) SELECT {selected} FROM {quote(alias)}.{quote(table)}")
                        copied[table] = copied.get(table, 0) + max(0, con.total_changes - before)
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
                finally:
                    con.execute(f"DETACH DATABASE {quote(alias)}")
        search_indexes = self.rebuild_search_indexes()
        return {
            "ok": True, "status": "migrated", "database": str(self.path),
            "legacy_databases": [str(item) for item in paths], "plan": plan, "rows_copied": copied,
            "search_indexes": search_indexes, "validation": self.validate(full=True),
            "automatic_l2": False, "automatic_l3": False,
        }

    def rebuild_search_indexes(self) -> dict[str, int]:
        self.initialize()
        counts = {"message_fts": 0, "journal_fts": 0, "experience_fts": 0}
        with ChatExportArchiveStore(self.path) as archive:
            try:
                archive.con.execute("INSERT INTO message_fts(message_fts) VALUES('delete-all')")
            except sqlite3.DatabaseError:
                archive.con.execute("DELETE FROM message_fts")
            for row in archive.con.execute("SELECT conversation_id FROM conversations ORDER BY conversation_id").fetchall():
                payload = archive.conversation_payload(str(row["conversation_id"]))
                if payload is None:
                    continue
                graph = build_conversation_graph(payload)
                rowids = {str(item["node_id"]): int(item["rowid"]) for item in archive.con.execute("SELECT rowid,node_id FROM fts_docs WHERE conversation_id=?", (graph.conversation_id,))}
                values = [(rowids[node.node_id], node.text) for node in graph.nodes if node.text and node.node_id in rowids]
                archive.con.executemany("INSERT INTO message_fts(rowid,text) VALUES(?,?)", values)
                counts["message_fts"] += len(values)
        with JournalStore(self.path) as journal:
            try:
                journal.con.execute("INSERT INTO journal_fts(journal_fts) VALUES('delete-all')")
            except sqlite3.DatabaseError:
                journal.con.execute("DELETE FROM journal_fts")
            rows = journal.con.execute("SELECT d.rowid,e.title,e.summary,e.content FROM journal_fts_docs d JOIN journal_entries e ON e.entry_id=d.entry_id ORDER BY d.rowid").fetchall()
            journal.con.executemany("INSERT INTO journal_fts(rowid,text) VALUES(?,?)", [(int(row["rowid"]), f"{row['title']}\n{row['summary']}\n{row['content']}") for row in rows])
            counts["journal_fts"] = len(rows)
        with ExperienceStore(self.path) as experience:
            try:
                experience.con.execute("INSERT INTO experience_fts(experience_fts) VALUES('delete-all')")
            except sqlite3.DatabaseError:
                experience.con.execute("DELETE FROM experience_fts")
            values: list[tuple[int, str]] = []
            for doc in experience.con.execute("SELECT rowid,record_type,record_id FROM experience_fts_docs ORDER BY rowid").fetchall():
                if doc["record_type"] == "candidate":
                    row = experience.con.execute("SELECT title,summary,domains_json FROM candidates WHERE candidate_id=?", (doc["record_id"],)).fetchone()
                else:
                    row = experience.con.execute("SELECT title,summary,'[]' domains_json FROM experiences WHERE experience_id=?", (doc["record_id"],)).fetchone()
                if row is not None:
                    values.append((int(doc["rowid"]), f"{row['title']}\n{row['summary']}\n{row['domains_json']}"))
            experience.con.executemany("INSERT INTO experience_fts(rowid,text) VALUES(?,?)", values)
            counts["experience_fts"] = len(values)
        return counts

    def generate_candidates(self, *, chats: bool = True, journal: bool = True, limit: int | None = None) -> dict[str, Any]:
        self.initialize()
        result: dict[str, Any] = {"ok": True, "automatic_experience": False, "automatic_l2": False, "automatic_l3": False}
        with ExperienceStore(self.path) as experience:
            if chats:
                result["chats"] = experience.from_chats(self.path, limit=limit)
            if journal:
                with JournalStore(self.path) as journal_store:
                    result["journal"] = experience.from_journal(journal_store, limit=limit)
            result["counts"] = experience.counts()
        return result
