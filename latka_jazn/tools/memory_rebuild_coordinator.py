from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from latka_jazn.memory.memory_tier_store import MemoryTierStore
from latka_jazn.tools.chat_export_importer import ChatExportImporter
from latka_jazn.tools.chat_export_reader import ChatExportReader, probe_json_source_kind
from latka_jazn.tools.chat_export_store import ChatExportArchiveStore
from latka_jazn.tools.memory_rebuild_catalog import CatalogStore
from latka_jazn.tools.memory_rebuild_experience import ExperienceStore
from latka_jazn.tools.memory_rebuild_journal import JournalReader, JournalStore
from latka_jazn.tools.memory_rebuild_common import (
    DATABASE_FILENAMES, MemoryRebuildPaths, SCHEMA_VERSION, TRUTH_BOUNDARY, fts_queries,
)


def _chat_source_details(reader: ChatExportReader) -> dict[str, Any]:
    info = reader.info
    return {
        "kind": "chat_export",
        "path": str(reader.path),
        "sha256": info.sha256,
        "size_bytes": info.size_bytes,
        "source_kind": info.source_kind,
        "canonical_conversations_available": info.has_canonical_conversations,
        "canonical_conversation_members": list(info.conversation_members),
        "shared_link_metadata_available": info.has_shared_link_metadata,
        "shared_conversation_members": list(info.shared_conversations_members),
        "shared_metadata_only": info.shared_metadata_only,
        "chat_html_available": bool(info.html_member),
        "rejection_reason": (
            "shared_conversations_metadata_only"
            if info.shared_metadata_only
            else "chat_export_without_canonical_conversation_json"
            if not info.has_canonical_conversations
            else None
        ),
    }


def detect_source(path: str | Path) -> dict[str, Any]:
    """Detect a rebuild source without loading a large JSON file into memory."""

    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if source.is_dir() or suffix in {".zip", ".html", ".htm"}:
        with ChatExportReader(source, verify_crc=True) as reader:
            return _chat_source_details(reader)
    if suffix in {".jsonl", ".ndjson"}:
        reader = JournalReader(source)
        return {
            "kind": "journal", "path": str(source), "sha256": reader.sha256,
            "size_bytes": source.stat().st_size, "source_kind": reader.format,
        }
    if suffix == ".json":
        source_kind = probe_json_source_kind(source)
        if source_kind in {"conversation", "shared_metadata", "empty_array"}:
            with ChatExportReader(source, verify_crc=False) as reader:
                details = _chat_source_details(reader)
                details["json_probe_kind"] = source_kind
                return details
        reader = JournalReader(source)
        return {
            "kind": "journal", "path": str(source), "sha256": reader.sha256,
            "size_bytes": source.stat().st_size, "source_kind": reader.format,
            "json_probe_kind": source_kind,
        }
    raise ValueError(f"unsupported source: {source}")


def _unique_sources_in_user_order(sources: Sequence[str | Path]) -> list[Path]:
    ordered: list[Path] = []
    seen: set[str] = set()
    for raw in sources:
        path = Path(raw).expanduser().resolve()
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


class MemoryRebuildCoordinator:
    def __init__(self, root: str | Path) -> None:
        self.paths = MemoryRebuildPaths.from_root(root)

    def init(self) -> dict[str, Any]:
        self.paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
        with ChatExportArchiveStore(self.paths.archive_chats) as store:
            archive = store.validate(full=False)
        with JournalStore(self.paths.journal) as store:
            journal = store.validate(full=False)
        with MemoryTierStore(self.paths.memory_jazn) as store:
            memory = store.validate(full=False)
        with ExperienceStore(self.paths.experience) as store:
            experience = store.validate(full=False)
        with CatalogStore(self.paths.import_catalog) as store:
            catalog = store.validate(full=False)
        checks = {
            "archive_chats": archive, "journal": journal, "memory_jazn": memory,
            "experience": experience, "import_catalog": catalog,
        }
        return {
            "ok": all(item["ok"] for item in checks.values()), "schema_version": SCHEMA_VERSION,
            "root": str(self.paths.root), "databases": self.paths.as_dict(), "validation": checks,
            "truth_boundary": TRUTH_BOUNDARY,
        }

    def inspect(self, sources: Sequence[str | Path]) -> dict[str, Any]:
        self.init()
        reports = []
        with CatalogStore(self.paths.import_catalog) as catalog:
            for path in _unique_sources_in_user_order(sources):
                detected = detect_source(path)
                if detected["kind"] == "chat_export":
                    with ChatExportReader(path, verify_crc=True) as reader:
                        inspection = reader.inspect().to_dict()
                        report = {**detected, **inspection}
                        if not report.get("ok"):
                            report["metadata_only"] = bool(reader.info.shared_metadata_only)
                            report["assets_only"] = bool(
                                reader.info.html_member
                                and not reader.info.has_canonical_conversations
                                and not reader.info.has_shared_link_metadata
                            )
                else:
                    report = {**detected, **JournalReader(path).inspect()}
                report["catalog_source_id"] = catalog.source(
                    path, detected["sha256"], detected["kind"], detected["size_bytes"], report,
                )
                reports.append(report)
        return {"ok": bool(reports) and all(report.get("ok") for report in reports), "reports": reports}

    def plan_chats(self, sources: Sequence[str | Path], details: bool = False) -> dict[str, Any]:
        self.init()
        plans = []
        importer = ChatExportImporter()
        for source in _unique_sources_in_user_order(sources):
            plan = importer.plan(source, self.paths.archive_chats).to_dict()
            if not details:
                plan.pop("conversations", None)
            plans.append(plan)
        return {"ok": bool(plans) and all(plan.get("ok", True) for plan in plans), "plans": plans}

    def import_chats(
        self,
        sources: Sequence[str | Path],
        dry_run: bool = False,
        full_validation: bool = True,
        continue_on_error: bool = False,
    ) -> dict[str, Any]:
        self.init()
        results = []
        importer = ChatExportImporter()
        ordered = _unique_sources_in_user_order(sources)
        with CatalogStore(self.paths.import_catalog) as catalog:
            for source in ordered:
                operation: str | None = None
                try:
                    with ChatExportReader(source, verify_crc=True) as reader:
                        if not reader.info.has_canonical_conversations:
                            if reader.info.shared_metadata_only:
                                raise ValueError(
                                    "shared_conversations contains link metadata only and cannot be imported as chat history"
                                )
                            raise ValueError(
                                "chat.html alone cannot be imported; conversations.json or numbered conversation JSON is required"
                            )
                        source_id = catalog.source(
                            source, reader.info.sha256, "chat_export", reader.info.size_bytes,
                            reader.info.to_dict(),
                        )
                    operation = catalog.begin(
                        "import_chats_dry_run" if dry_run else "import_chats",
                        source_id,
                        DATABASE_FILENAMES["archive_chats"],
                    )
                    result = importer.import_one(
                        source,
                        self.paths.archive_chats,
                        dry_run=dry_run,
                        full_validation=full_validation,
                    ).to_dict()
                    result["ok"] = result.get("validation", {}).get("ok", True) and not result.get("errors")
                    result["operation_id"] = operation
                    catalog.finish(operation, result, "verified" if result["ok"] else "needs_review")
                    results.append(result)
                except BaseException as exc:
                    if operation is not None:
                        catalog.fail(operation, exc)
                    results.append({
                        "ok": False, "source": str(source), "operation_id": operation,
                        "error_type": type(exc).__name__, "error": str(exc),
                    })
                    if not continue_on_error:
                        break
        return {
            "ok": bool(results) and all(row["ok"] for row in results),
            "database": str(self.paths.archive_chats),
            "dry_run": dry_run,
            "source_order": [str(path) for path in ordered],
            "source_order_policy": "explicit_user_order_deduplicated",
            "results": results,
            "automatic_l2": False,
            "automatic_l3": False,
        }

    def import_journal(self, source: str | Path, dry_run: bool = False) -> dict[str, Any]:
        self.init()
        reader = JournalReader(source)
        with CatalogStore(self.paths.import_catalog) as catalog:
            source_id = catalog.source(
                reader.path, reader.sha256, "journal", reader.path.stat().st_size, reader.inspect(),
            )
            operation = catalog.begin(
                "import_journal_dry_run" if dry_run else "import_journal",
                source_id,
                DATABASE_FILENAMES["journal"],
            )
            try:
                with JournalStore(self.paths.journal) as journal:
                    result = journal.import_reader(reader, dry_run=dry_run)
                    result["validation"] = journal.validate(full=False)
                result["operation_id"] = operation
                catalog.finish(operation, result)
                return result
            except BaseException as exc:
                catalog.fail(operation, exc)
                raise

    def reclassify_journal(self, dry_run: bool = False, limit: int = 100) -> dict[str, Any]:
        """Refresh derived journal truth labels while preserving raw source and revisions."""
        self.init()
        with CatalogStore(self.paths.import_catalog) as catalog:
            operation = catalog.begin(
                "reclassify_journal_dry_run" if dry_run else "reclassify_journal",
                None,
                DATABASE_FILENAMES["journal"],
            )
            try:
                with JournalStore(self.paths.journal) as journal:
                    result = journal.reclassify(dry_run=dry_run, sample_limit=limit)
                    result["validation"] = journal.validate(full=False)
                with ExperienceStore(self.paths.experience) as experience:
                    candidate_count = experience.counts()["candidates"]
                result["existing_candidate_count"] = candidate_count
                result["candidate_rebuild_recommended"] = bool(candidate_count and result["changed"])
                result["operation_id"] = operation
                catalog.finish(operation, result)
                return result
            except BaseException as exc:
                catalog.fail(operation, exc)
                raise

    def build_experience_candidates(self, source: str, limit: int | None = None) -> dict[str, Any]:
        self.init()
        if source not in {"journal", "chats", "all"}:
            raise ValueError("source must be journal, chats, or all")
        reports = []
        with ExperienceStore(self.paths.experience) as experience, CatalogStore(self.paths.import_catalog) as catalog:
            operation = catalog.begin("build_experience_candidates", None, DATABASE_FILENAMES["experience"])
            try:
                if source in {"journal", "all"}:
                    with JournalStore(self.paths.journal) as journal:
                        reports.append(experience.from_journal(journal, limit))
                if source in {"chats", "all"}:
                    reports.append(experience.from_chats(self.paths.archive_chats, limit))
                for report in reports:
                    source_db = report["source"]
                    for candidate_id in report["candidate_ids"]:
                        row = experience.con.execute(
                            "SELECT * FROM candidates WHERE candidate_id=?", (candidate_id,),
                        ).fetchone()
                        catalog.link(
                            source_db, row["source_type"], row["source_record_id"],
                            DATABASE_FILENAMES["experience"], "experience_candidate",
                            candidate_id, "candidate_from_source", row["source_sha256"],
                        )
                payload = {
                    "ok": True, "reports": reports, "counts": experience.counts(),
                    "automatic_experience": False, "automatic_l2": False, "automatic_l3": False,
                }
                catalog.finish(operation, payload)
                return payload
            except BaseException as exc:
                catalog.fail(operation, exc)
                raise

    def approve_experience(
        self,
        candidate_id: str,
        confirm_candidate_id: str,
        approved_by: str,
        reason: str,
    ) -> dict[str, Any]:
        self.init()
        with ExperienceStore(self.paths.experience) as experience, CatalogStore(self.paths.import_catalog) as catalog:
            operation = catalog.begin("approve_experience", None, DATABASE_FILENAMES["experience"])
            try:
                result = experience.approve(candidate_id, confirm_candidate_id, approved_by, reason)
                catalog.finish(operation, result)
                return result
            except BaseException as exc:
                catalog.fail(operation, exc)
                raise

    def audit_classifiers(self, limit: int = 50) -> dict[str, Any]:
        """Audit derived classifications without altering source or memory tiers."""
        self.init()
        with JournalStore(self.paths.journal) as journal:
            journal_report = journal.classification_audit(limit)

        with ChatExportArchiveStore(self.paths.archive_chats) as archive:
            has_segments = archive.con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_segments'"
            ).fetchone() is not None
            if has_segments:
                segment_count = archive.con.execute("SELECT COUNT(*) FROM conversation_segments").fetchone()[0]
                profile_count = archive.con.execute("SELECT COUNT(*) FROM conversation_topic_profiles").fetchone()[0]
                domain_counts = {
                    str(row[0]): int(row[1])
                    for row in archive.con.execute(
                        "SELECT primary_domain,COUNT(*) FROM conversation_segments GROUP BY primary_domain ORDER BY primary_domain"
                    )
                }
                mode_counts = {
                    str(row[0]): int(row[1])
                    for row in archive.con.execute(
                        "SELECT mode,COUNT(*) FROM conversation_segments GROUP BY mode ORDER BY mode"
                    )
                }
                truth_counts = {
                    str(row[0]): int(row[1])
                    for row in archive.con.execute(
                        "SELECT truth_status,COUNT(*) FROM conversation_segments GROUP BY truth_status ORDER BY truth_status"
                    )
                }
                low_confidence = archive.con.execute(
                    "SELECT COUNT(*) FROM conversation_segments WHERE confidence < 0.45"
                ).fetchone()[0]
            else:
                segment_count = profile_count = low_confidence = 0
                domain_counts = mode_counts = truth_counts = {}
            chat_report = {
                "topic_tables_present": has_segments,
                "analysis_required": not has_segments or segment_count == 0,
                "conversation_topic_profiles": profile_count,
                "conversation_segments": segment_count,
                "domain_counts": domain_counts,
                "mode_counts": mode_counts,
                "truth_status_counts": truth_counts,
                "low_confidence_segments": low_confidence,
            }

        return {
            "ok": True,
            "journal": journal_report,
            "chats": chat_report,
            "truth_boundary": TRUTH_BOUNDARY,
            "source_data_modified": False,
            "automatic_experience": False,
            "automatic_l2": False,
            "automatic_l3": False,
        }

    def verify(self, full: bool = True) -> dict[str, Any]:
        self.init()
        with ChatExportArchiveStore(self.paths.archive_chats) as store:
            archive = store.validate(full=full)
        with JournalStore(self.paths.journal) as store:
            journal = {**store.validate(full), "counts": store.counts()}
        with MemoryTierStore(self.paths.memory_jazn) as store:
            memory = {**store.validate(full=full), "stats": store.stats()}
        with ExperienceStore(self.paths.experience) as store:
            experience = {**store.validate(full), "counts": store.counts()}
        with CatalogStore(self.paths.import_catalog) as store:
            catalog = {**store.validate(full), "counts": store.status()}
        results = {
            "archive_chats": archive, "journal": journal, "memory_jazn": memory,
            "experience": experience, "import_catalog": catalog,
        }
        return {
            "ok": all(item["ok"] for item in results.values()),
            "mode": "full" if full else "quick",
            "databases": self.paths.as_dict(),
            "results": results,
            "truth_boundary": TRUTH_BOUNDARY,
        }

    def status(self) -> dict[str, Any]:
        self.init()
        with ChatExportArchiveStore(self.paths.archive_chats) as archive:
            archive_counts = archive.counts()
        with JournalStore(self.paths.journal) as journal:
            journal_counts = journal.counts()
        with MemoryTierStore(self.paths.memory_jazn) as memory:
            memory_counts = memory.stats()
        with ExperienceStore(self.paths.experience) as experience:
            experience_counts = experience.counts()
        with CatalogStore(self.paths.import_catalog) as catalog:
            catalog_counts = catalog.status()
        return {
            "ok": True,
            "root": str(self.paths.root),
            "databases": self.paths.as_dict(),
            "counts": {
                "archive_chats": archive_counts,
                "journal": journal_counts,
                "memory_jazn": memory_counts,
                "experience": experience_counts,
                "import_catalog": catalog_counts,
            },
            "automatic_l2": False,
            "automatic_l3": False,
        }

    def search(self, query: str, limit: int = 20) -> dict[str, Any]:
        self.init()
        with ChatExportArchiveStore(self.paths.archive_chats) as archive:
            chats = []
            for fts_query in fts_queries(query):
                chats = archive.search(fts_query, limit=limit)
                if chats:
                    break
        with JournalStore(self.paths.journal) as journal:
            journals = journal.search(query, limit)
        with ExperienceStore(self.paths.experience) as experience:
            experiences = experience.search(query, limit)
        with MemoryTierStore(self.paths.memory_jazn) as memory:
            rows = memory.con.execute(
                "SELECT memory_id,tier,kind,content,domain,truth_status,confidence,importance "
                "FROM memory_records WHERE active=1 AND content LIKE ? ORDER BY importance DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return {
            "ok": True,
            "query": query,
            "results": {
                "memory_jazn": [dict(row) for row in rows],
                "experience": experiences,
                "journal": journals,
                "archive_chats": chats,
            },
            "search_order": [
                DATABASE_FILENAMES[key]
                for key in ("memory_jazn", "experience", "journal", "archive_chats")
            ],
            "import_catalog_used_for_recall": False,
        }
