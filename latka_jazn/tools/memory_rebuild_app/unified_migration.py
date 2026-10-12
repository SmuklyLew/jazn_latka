from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid

from latka_jazn.tools.chat_export_reader import build_conversation_graph
from latka_jazn.tools.chat_export_store import ChatExportArchiveStore
from latka_jazn.tools.memory_rebuild_experience import ExperienceStore
from latka_jazn.tools.memory_rebuild_journal import JournalStore
from latka_jazn.tools.sqlite_archive_snapshot import create_sqlite_snapshot
from latka_jazn.tools.chat_export_reader import sha256_file

from .unified_contracts import UnifiedMixinHost
from .unified_schema import CANONICAL_DATABASE_NAME, COPY_ORDER, LEGACY_DATABASE_NAMES, quote


class UnifiedMigrationMixin(UnifiedMixinHost):
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".jazn-unified-migration-",
            dir=self.path.parent,
        ) as temporary_root:
            temporary = Path(temporary_root)
            staged_path = temporary / CANONICAL_DATABASE_NAME
            target_snapshot: dict[str, Any] | None = None
            if self.path.exists():
                target_snapshot = create_sqlite_snapshot(
                    self.path,
                    staged_path,
                    full_integrity_check=True,
                ).to_dict()
            else:
                type(self)(staged_path).initialize()

            source_snapshots: list[dict[str, Any]] = []
            snapshot_paths: list[Path] = []
            for index, source in enumerate(paths):
                snapshot = temporary / "legacy-snapshots" / f"{index:04d}-{source.name}"
                report = create_sqlite_snapshot(
                    source,
                    snapshot,
                    full_integrity_check=True,
                )
                source_snapshots.append({
                    "source": str(source),
                    "source_sha256": sha256_file(source),
                    "snapshot_sha256": report.snapshot_sha256,
                    "snapshot_size_bytes": report.snapshot_size_bytes,
                    "integrity_check": report.integrity_check,
                    "foreign_key_error_count": report.foreign_key_error_count,
                })
                snapshot_paths.append(snapshot)

            staged = type(self)(staged_path)
            payload = staged._migrate_databases_impl(snapshot_paths)
            if not payload.get("ok"):
                raise sqlite3.IntegrityError(
                    f"staged unified memory migration has {payload.get('unresolved_migration_conflicts', 0)} unresolved conflicts"
                )
            validation = staged.validate(full=True)
            if not validation.get("ok"):
                raise sqlite3.DatabaseError("staged unified memory validation failed")
            staged.checkpoint()
            os.replace(staged_path, self.path)
            payload.update({
                "database": str(self.path),
                "legacy_databases": [str(item) for item in paths],
                "source_snapshots": source_snapshots,
                "target_snapshot": target_snapshot,
                "atomic_replace": True,
                "source_databases_modified": False,
                "validation": validation,
            })
            for item in payload.get("plan", []):
                if isinstance(item, dict) and "database" in item:
                    item["database"] = "validated_sqlite_backup_snapshot"
            return payload

    @staticmethod
    def _row_sha(columns: list[str], row: sqlite3.Row | tuple[Any, ...]) -> str:
        values = list(row)
        payload = json.dumps(dict(zip(columns, values)), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _primary_key_columns(con: sqlite3.Connection, schema: str, table: str) -> list[str]:
        rows = list(con.execute(f"PRAGMA {quote(schema)}.table_info({quote(table)})"))
        return [str(row[1]) for row in sorted((row for row in rows if int(row[5]) > 0), key=lambda row: int(row[5]))]

    @staticmethod
    def _revision_relation(columns: list[str], target: sqlite3.Row | tuple[Any, ...], incoming: sqlite3.Row | tuple[Any, ...]) -> str:
        if "revision" not in columns:
            return "same_key_different_content"
        idx = columns.index("revision")
        try:
            left, right = int(target[idx]), int(incoming[idx])
        except (TypeError, ValueError):
            return "revision_unparseable"
        if right > left:
            return "incoming_newer_revision"
        if right < left:
            return "incoming_older_revision"
        return "same_revision_different_content"

    def _record_migration_conflict(
        self,
        con: sqlite3.Connection,
        *,
        source_name: str,
        table: str,
        key: dict[str, Any],
        target_sha: str | None,
        incoming_sha: str,
        relation: str,
        status: str = "unresolved",
        details: dict[str, Any] | None = None,
    ) -> None:
        con.execute(
            """INSERT INTO unified_migration_conflicts(
               conflict_id,source_database_name,table_name,key_json,target_sha256,incoming_sha256,
               revision_relation,status,details_json,created_at_utc)
               VALUES(?,?,?,?,?,?,?,?,?,datetime('now'))""",
            (
                str(uuid.uuid4()), source_name, table,
                json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
                target_sha, incoming_sha, relation, status,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
            ),
        )

    def _copy_table_reconciled(
        self,
        con: sqlite3.Connection,
        *,
        alias: str,
        source_name: str,
        table: str,
        columns: list[str],
    ) -> dict[str, int]:
        selected = ",".join(quote(item) for item in columns)
        pk = self._primary_key_columns(con, alias, table)
        result = {"seen": 0, "inserted": 0, "identical_duplicates": 0, "resolved_metadata": 0, "conflicts": 0}
        source_cursor = con.execute(f"SELECT {selected} FROM {quote(alias)}.{quote(table)}")
        for incoming in source_cursor:
            result["seen"] += 1
            incoming_tuple = tuple(incoming)
            incoming_sha = self._row_sha(columns, incoming_tuple)
            existing = None
            key: dict[str, Any] = {}
            if pk and all(item in columns for item in pk):
                key = {name: incoming_tuple[columns.index(name)] for name in pk}
                where = " AND ".join(f"{quote(name)} IS ?" for name in pk)
                existing = con.execute(
                    f"SELECT {selected} FROM {quote(table)} WHERE {where}", tuple(key[name] for name in pk),
                ).fetchone()
            else:
                where = " AND ".join(f"{quote(name)} IS ?" for name in columns)
                existing = con.execute(f"SELECT {selected} FROM {quote(table)} WHERE {where} LIMIT 1", incoming_tuple).fetchone()
                key = {"row_sha256": incoming_sha}
            if existing is not None:
                target_tuple = tuple(existing)
                target_sha = self._row_sha(columns, target_tuple)
                if target_sha == incoming_sha:
                    result["identical_duplicates"] += 1
                    continue
                # Canonical target metadata wins explicitly; this is recorded, never silently ignored.
                if table in {"unified_memory_meta", "archive_meta", "journal_meta", "experience_meta", "memory_store_meta", "catalog_meta"}:
                    self._record_migration_conflict(
                        con, source_name=source_name, table=table, key=key, target_sha=target_sha,
                        incoming_sha=incoming_sha, relation="target_metadata_canonical",
                        status="resolved_target_canonical",
                    )
                    result["resolved_metadata"] += 1
                    continue
                relation = self._revision_relation(columns, target_tuple, incoming_tuple)
                self._record_migration_conflict(
                    con, source_name=source_name, table=table, key=key, target_sha=target_sha,
                    incoming_sha=incoming_sha, relation=relation,
                )
                result["conflicts"] += 1
                continue
            placeholders = ",".join("?" for _ in columns)
            try:
                con.execute(
                    f"INSERT INTO {quote(table)}({selected}) VALUES({placeholders})",
                    incoming_tuple,
                )
                result["inserted"] += 1
            except sqlite3.IntegrityError as exc:
                self._record_migration_conflict(
                    con, source_name=source_name, table=table, key=key, target_sha=None,
                    incoming_sha=incoming_sha, relation="unique_or_constraint_conflict",
                    details={"sqlite_error": str(exc)},
                )
                result["conflicts"] += 1
        return result

    def _migrate_databases_impl(self, paths: list[Path]) -> dict[str, Any]:
        self.ensure_initialized()
        plan: list[dict[str, Any]] = []
        copied: dict[str, int] = {}
        reconciliation: dict[str, dict[str, int]] = {}
        with self.connect() as con:
            con.row_factory = sqlite3.Row
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
                        if "VIRTUAL TABLE" in source_tables[table].upper() or table.startswith("sqlite_") or table == "unified_migration_conflicts":
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
                        stats = self._copy_table_reconciled(
                            con, alias=alias, source_name=legacy.name, table=table, columns=columns,
                        )
                        reconciliation[f"{legacy.name}:{table}"] = stats
                        copied[table] = copied.get(table, 0) + stats["inserted"]
                    con.commit()
                except BaseException:
                    con.rollback()
                    raise
                finally:
                    con.execute(f"DETACH DATABASE {quote(alias)}")
            unresolved = int(con.execute(
                "SELECT COUNT(*) FROM unified_migration_conflicts WHERE status='unresolved'"
            ).fetchone()[0])
        if unresolved:
            return {
                "ok": False,
                "status": "migration_conflicts_detected",
                "database": str(self.path),
                "legacy_databases": [str(item) for item in paths],
                "plan": plan,
                "rows_copied": copied,
                "reconciliation": reconciliation,
                "unresolved_migration_conflicts": unresolved,
                "search_indexes": {},
                "validation": self.validate(full=True),
                "automatic_l2": False,
                "automatic_l3": False,
            }
        search_indexes = self.rebuild_search_indexes()
        return {
            "ok": True, "status": "migrated", "database": str(self.path),
            "legacy_databases": [str(item) for item in paths], "plan": plan, "rows_copied": copied,
            "reconciliation": reconciliation,
            "unresolved_migration_conflicts": 0,
            "search_indexes": search_indexes, "validation": self.validate(full=True),
            "automatic_l2": False, "automatic_l3": False,
        }

    def rebuild_search_indexes(self) -> dict[str, int]:
        self.ensure_initialized()
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
        self.ensure_initialized()
        result: dict[str, Any] = {"ok": True, "automatic_experience": False, "automatic_l2": False, "automatic_l3": False}
        with ExperienceStore(self.path) as experience:
            if chats:
                result["chats"] = experience.from_chats(self.path, limit=limit)
            if journal:
                with JournalStore(self.path) as journal_store:
                    result["journal"] = experience.from_journal(journal_store, limit=limit)
            result["counts"] = experience.counts()
        return result
